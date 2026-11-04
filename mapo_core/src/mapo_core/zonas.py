"""Zonas candidatas: qué AGEB cumplen criterios que se ven y se mueven.

No es un puntaje (RNF5, docs/arquitectura/decisiones.md). Hay dos criterios, se
aplican los dos y nada se suma ni se pondera: un indicador del censo con un
mínimo, y minutos en auto hasta el negocio más cercano del rubro. Se ordena por
uno de los dos, y se dice cuántas AGEB dejó fuera cada uno.

Los minutos salen de la misma matriz de OSRM que usa /logistica, desde un punto
dentro de cada AGEB. Con Zapopan tarda segundos, así que se calculan una vez y
se guardan: mover un criterio solo vuelve a filtrar.
"""

from __future__ import annotations

import asyncio
import math
from collections import OrderedDict

import numpy as np
from psycopg_pool import AsyncConnectionPool
from scipy.spatial import cKDTree

from mapo_core import consultas
from mapo_core.isocronas import VELOCIDAD_FALLBACK_KMH
from mapo_core.osrm_client import OSRMClient

INDICADORES = {
    "pobtot": "Población total",
    "tothog": "Hogares",
    "p_0a2": "Población de 0 a 2 años",
    "p_6a11": "Población de 6 a 11 años",
    "p_18a24": "Población de 18 a 24 años",
    "p_60ymas": "Población de 60 años o más",
    "pocupada": "Población ocupada",
    "vph_autom": "Viviendas con automóvil",
}

# Destinos por AGEB, los más cercanos en línea recta: el más cercano en línea
# recta no suele ser el más cercano por calle (docs/producto/buscador.md).
VECINOS = 10

# 25 AGEB con 10 destinos cada una son 6,250 celdas como mucho; `osrm-routed` rechaza
# más de 10,000 por llamada y la URL no puede pasar de unos 25 KB.
AGEBS_POR_LOTE = 25
LLAMADAS_A_LA_VEZ = 4

# Unos 25 s en Aerilate. Cabe la zona metropolitana (1,840 AGEB), no el estado.
MAX_AGEBS = 2000

MAX_FILAS = 20

# (puntos de las AGEB, minutos por AGEB). Solo lo calculado por calle, y hasta
# reiniciar: DENUE cambia con una carga a mano. Con esto, mover un criterio es
# una consulta al censo y un filtro.
_MINUTOS_GUARDADOS = 32
_guardados: OrderedDict[tuple, tuple[list[tuple], dict[str, float | None]]] = OrderedDict()


class DemasiadasZonas(Exception):
    pass


def _plano(lat: np.ndarray, lon: np.ndarray, lat_media: float) -> np.ndarray:
    """Coordenadas en km, equirectangular: basta para hallar vecinos."""
    return np.column_stack([lat * 111.32, lon * 111.32 * math.cos(math.radians(lat_media))])


async def _minutos_por_calle(
    osrm: OSRMClient, origenes: list[tuple[float, float]], negocios: np.ndarray, vecinos: np.ndarray
) -> list[float | None] | None:
    """Minutos de cada origen a su negocio más cercano por calle, entre sus
    `vecinos`. None si falla cualquier lote: no se mezclan métodos."""
    limite = asyncio.Semaphore(LLAMADAS_A_LA_VEZ)

    async def lote(inicio: int) -> list[float | None] | None:
        filas = vecinos[inicio : inicio + AGEBS_POR_LOTE]
        destinos = sorted({int(i) for fila in filas for i in fila})
        posicion = {i: j for j, i in enumerate(destinos)}
        async with limite:
            matriz = await osrm.duraciones_matriz(
                origenes[inicio : inicio + AGEBS_POR_LOTE],
                [(float(negocios[i, 0]), float(negocios[i, 1])) for i in destinos],
            )
        if matriz is None:
            return None
        tiempos = []
        for fila_matriz, fila_vecinos in zip(matriz, filas):
            alcanzables = [t for t in (fila_matriz[posicion[int(i)]] for i in fila_vecinos) if t is not None]
            tiempos.append(min(alcanzables, default=None))
        return tiempos

    lotes = await asyncio.gather(*(lote(i) for i in range(0, len(origenes), AGEBS_POR_LOTE)))
    if any(t is None for t in lotes):
        return None
    return [t for tiempos in lotes for t in tiempos]


async def _minutos(
    osrm: OSRMClient, agebs: list[tuple], negocios: list[tuple[float, float]]
) -> tuple[dict[str, float | None], str]:
    """{cvegeo: minutos} y el método. Sin OSRM, línea recta a velocidad asumida
    y se dice, igual que el círculo de las isócronas."""
    puntos = np.array(negocios, dtype=float)
    a_lat = np.array([a[3] for a in agebs], dtype=float)
    a_lon = np.array([a[4] for a in agebs], dtype=float)
    lat_media = float(a_lat.mean())
    arbol = cKDTree(_plano(puntos[:, 0], puntos[:, 1], lat_media))
    k = min(VECINOS, len(puntos))
    distancias, vecinos = arbol.query(_plano(a_lat, a_lon, lat_media), k=k)
    distancias, vecinos = distancias.reshape(len(agebs), k), vecinos.reshape(len(agebs), k)

    origenes = list(zip(a_lat.tolist(), a_lon.tolist()))
    tiempos = await _minutos_por_calle(osrm, origenes, puntos, vecinos)
    cvegeos = [a[0] for a in agebs]

    if tiempos is None:
        en_linea = distancias[:, 0] / VELOCIDAD_FALLBACK_KMH * 60
        return dict(zip(cvegeos, en_linea.round(2).tolist())), "linea_recta_aproximada"
    return dict(zip(cvegeos, tiempos)), "carretera_real"


def _para_mostrar(valor: float | None) -> float | None:
    """4000.0 regresa como 4000: va directo al campo de la pantalla."""
    return int(valor) if valor is not None and float(valor).is_integer() else valor


def _mediana(valores: list[float]) -> float | None:
    """Dónde arranca un criterio: la mediana de lo que hay. Es solo el punto
    de partida, y la pantalla lo dice."""
    return float(np.median(valores)) if valores else None


async def calcular(
    pool: AsyncConnectionPool,
    osrm: OSRMClient,
    cve_ent: str,
    cve_muns: list[str],
    clases: list[str],
    *,
    indicador: str,
    minimo: float | None,
    minutos: float | None,
    orden: str,
    unidad: str,
) -> dict:
    llave = (cve_ent, tuple(sorted(cve_muns)), tuple(sorted(clases)))
    avisos: list[str] = []

    if llave in _guardados:
        _guardados.move_to_end(llave)
        agebs, por_ageb = _guardados[llave]
        metodo = "carretera_real"
    else:
        agebs = await consultas.puntos_de_agebs(pool, cve_ent, cve_muns)
        if len(agebs) > MAX_AGEBS:
            raise DemasiadasZonas(
                f"Son {len(agebs):,} AGEB: las zonas candidatas llegan a {MAX_AGEBS:,}. Elige menos municipios."
            )
        negocios = await consultas.ubicaciones_de_clases(pool, cve_ent, clases) if clases else []
        if not negocios:
            avisos.append(
                f"No hay {unidad} del rubro con ubicación en el estado: la distancia no descarta ninguna zona."
            )
        por_ageb, metodo = await _minutos(osrm, agebs, negocios) if negocios and agebs else ({}, "sin_negocios")
        if metodo == "carretera_real":
            _guardados[llave] = (agebs, por_ageb)
            if len(_guardados) > _MINUTOS_GUARDADOS:
                _guardados.popitem(last=False)

    if metodo == "linea_recta_aproximada":
        avisos.append(
            f"OSRM no respondió: los minutos son línea recta a {VELOCIDAD_FALLBACK_KMH:.0f} km/h, no tiempo real por calle."
        )
    usa_minutos = metodo != "sin_negocios"

    valores = await consultas.valores_por_ageb(pool, cve_ent, cve_muns, indicador)
    filas = [
        {
            "cvegeo": cvegeo,
            "ageb": cve_ageb,
            "municipio": municipio,
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "valor": valores.get(cvegeo),
            "minutos": por_ageb.get(cvegeo),
        }
        for cvegeo, cve_ageb, municipio, lat, lon in agebs
    ]
    con_dato = [f for f in filas if f["valor"] is not None and (f["minutos"] is not None or not usa_minutos)]

    if minimo is None:
        mediana = _mediana([f["valor"] for f in con_dato])
        minimo = round(mediana) if mediana is not None else 0
    if minutos is None and usa_minutos:
        # El campo es de minutos enteros, y "1.9 minutos" no dice más que 2.
        mediana = _mediana([f["minutos"] for f in con_dato])
        minutos = math.ceil(mediana) if mediana is not None else 0

    def cumple_indicador(f: dict) -> bool:
        return f["valor"] >= minimo

    def cumple_minutos(f: dict) -> bool:
        return not usa_minutos or f["minutos"] >= minutos

    candidatas = [f for f in con_dato if cumple_indicador(f) and cumple_minutos(f)]
    clave = "minutos" if orden == "minutos" and usa_minutos else "valor"
    candidatas.sort(key=lambda f: (-f[clave], f["cvegeo"]))

    return {
        "indicador": indicador,
        "etiqueta": INDICADORES[indicador],
        "metodo": metodo,
        "criterios": {
            "minimo": _para_mostrar(minimo),
            "minutos": _para_mostrar(minutos),
            "orden": "minutos" if clave == "minutos" else "indicador",
        },
        "total": len(filas),
        "total_candidatas": len(candidatas),
        # Cada criterio por separado: una AGEB puede fallar los dos.
        "descartes": {
            "sin_dato": len(filas) - len(con_dato),
            "por_indicador": sum(not cumple_indicador(f) for f in con_dato),
            "por_minutos": sum(not cumple_minutos(f) for f in con_dato),
        },
        "filas": candidatas[:MAX_FILAS],
        "cvegeos": [f["cvegeo"] for f in candidatas],
        "avisos": avisos,
    }
