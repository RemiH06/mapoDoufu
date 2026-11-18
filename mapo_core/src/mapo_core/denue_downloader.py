"""Cargador de DENUE (negocios) desde la descarga masiva de INEGI: un ZIP
por estado con un CSV de todos sus negocios.

Hasta la sesión 18 se paginaba `BuscarEntidad` de la API (vendorizado de
Gaiarda). Se dejó porque la paginación no es estable: la misma página pedida
dos veces trae otro orden y otros negocios, y en la recarga de Jalisco del
2026-11-17 llegaron 6,109 repetidos y faltaron otros tantos
(docs/fuentes/denue.md). El CSV trae los mismos negocios de la misma edición,
completo, sin token y en minutos en vez de media hora.

`cve_mun` y `cve_ageb` se siguen asignando con `ST_Contains` contra los
polígonos cargados, aunque el CSV traiga las claves: así `cve_ageb` solo
existe donde hay AGEB urbana en la base, como antes.
"""

from __future__ import annotations

import csv
import io
import tempfile
import zipfile
from pathlib import Path

import httpx

from mapo_core.db import get_pool, marcar_hecho

URL_TEMPLATE = "https://www.inegi.org.mx/contenidos/masiva/denue/denue_{cve_ent}_csv.zip"
_TIMEOUT = 600.0
# El CSV de INEGI viene en Latin-1 ("Zúñiga" se lee bien así).
CODIFICACION = "latin-1"
LOTE = 5000

# Si la carga nueva trae mucho menos que lo que ya hay, lo más probable es un
# archivo cortado: se deja todo y se avisa en vez de borrar medio estado.
MAX_PARTE_SIN_VENIR = 0.10


class ArchivoInvalido(Exception):
    pass


def _texto(fila: dict, campo: str) -> str | None:
    valor = (fila.get(campo) or "").strip()
    return valor or None


def _float_seguro(valor) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _normalizar(fila: dict, cve_ent: str) -> dict | None:
    """Un renglón del CSV masivo a las columnas de `fuente_denue_negocios`
    (los mismos nombres que usaba la carga por API)."""
    id_ = _texto(fila, "id")
    if not id_:
        return None
    lugar = [_texto(fila, c) for c in ("localidad", "municipio", "entidad")]
    return {
        "id": id_,
        "clee": _texto(fila, "clee"),
        # Plaza, mercado, edificio o parque industrial donde está el local. Sin
        # marca no quiere decir que esté en la calle: INEGI no siempre la pone.
        "tipo_plaza": _texto(fila, "tipoCenCom"),
        "plaza": _texto(fila, "nom_CenCom"),
        "numero_local": _texto(fila, "num_local"),
        "nombre": _texto(fila, "nom_estab"),
        "razon_social": _texto(fila, "raz_social"),
        "clase_actividad": _texto(fila, "nombre_act"),
        "estrato": _texto(fila, "per_ocu"),
        "calle": _texto(fila, "nom_vial"),
        "colonia": _texto(fila, "nomb_asent"),
        "codigo_postal": _texto(fila, "cod_postal"),
        "ubicacion": ", ".join(p for p in lugar if p) or None,
        "telefono": _texto(fila, "telefono"),
        "correo": _texto(fila, "correoelec"),
        "sitio_web": _texto(fila, "www"),
        "tipo": _texto(fila, "tipoUniEco"),
        "lat": _float_seguro(fila.get("latitud")),
        "lon": _float_seguro(fila.get("longitud")),
        "cve_ent": cve_ent,
    }


_COLUMNAS = [
    "id", "clee", "tipo_plaza", "plaza", "numero_local", "nombre", "razon_social", "clase_actividad",
    "estrato", "calle", "colonia", "codigo_postal", "ubicacion", "telefono", "correo", "sitio_web",
    "tipo", "lat", "lon", "cve_ent",
]

# Si el negocio se movió, su municipio y AGEB se vuelven a calcular.
_SE_MOVIO = "(n.lat, n.lon) IS DISTINCT FROM (EXCLUDED.lat, EXCLUDED.lon)"
_INSERTAR = f"""INSERT INTO fuente_denue_negocios AS n ({", ".join(_COLUMNAS)})
    VALUES ({", ".join(f"%({c})s" for c in _COLUMNAS)})
    ON CONFLICT (id) DO UPDATE SET {", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNAS if c != "id")},
        cve_mun = CASE WHEN {_SE_MOVIO} THEN NULL ELSE n.cve_mun END,
        cve_ageb = CASE WHEN {_SE_MOVIO} THEN NULL ELSE n.cve_ageb END,
        actualizado = now()"""


def leer_zip(ruta: Path, cve_ent: str):
    """Renglones normalizados del CSV dentro del ZIP, sin cargarlo entero en
    memoria (Jalisco son 215 MB de texto). Truena si un id se repite: el
    archivo no está completo o no es el que se espera."""
    with zipfile.ZipFile(ruta) as zf:
        nombres = [n for n in zf.namelist() if n.startswith("conjunto_de_datos/") and n.endswith(".csv")]
        if len(nombres) != 1:
            raise ArchivoInvalido(f"Se esperaba un CSV en conjunto_de_datos/, hay {len(nombres)}.")
        with zf.open(nombres[0]) as crudo:
            vistos: set[str] = set()
            for fila in csv.DictReader(io.TextIOWrapper(crudo, encoding=CODIFICACION, newline="")):
                if fila.get("cve_ent") != cve_ent:
                    raise ArchivoInvalido(f"El archivo trae negocios del estado {fila.get('cve_ent')}, no del {cve_ent}.")
                normalizado = _normalizar(fila, cve_ent)
                if normalizado is None:
                    continue
                if normalizado["id"] in vistos:
                    raise ArchivoInvalido(f"El id {normalizado['id']} viene dos veces.")
                vistos.add(normalizado["id"])
                yield normalizado


async def descargar_zip(cve_ent: str, destino: Path) -> None:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        async with client.stream("GET", URL_TEMPLATE.format(cve_ent=cve_ent)) as respuesta:
            respuesta.raise_for_status()
            with open(destino, "wb") as f:
                async for parte in respuesta.aiter_bytes():
                    f.write(parte)


async def cargar_zip(ruta: Path, cve_ent: str) -> tuple[int, int | None]:
    """Reemplaza los negocios del estado con los del ZIP. Regresa (guardados,
    borrados); `borrados` es None si eran demasiados para borrarlos
    (MAX_PARTE_SIN_VENIR) y entonces no se borra ninguno."""
    pool = await get_pool()
    async with pool.connection() as conn:
        cursor = await conn.execute("SELECT now()")
        (inicio,) = await cursor.fetchone()

        total = 0
        lote: list[dict] = []
        async with conn.cursor() as cur:
            for fila in leer_zip(ruta, cve_ent):
                lote.append(fila)
                if len(lote) == LOTE:
                    await cur.executemany(_INSERTAR, lote)
                    total += len(lote)
                    lote = []
            if lote:
                await cur.executemany(_INSERTAR, lote)
                total += len(lote)

        borrados = await _borrar_los_que_no_vinieron(conn, cve_ent, inicio)
        await marcar_hecho(conn, f"denue:{cve_ent}")

    await enriquecer_con_ubicacion(cve_ent)
    return total, borrados


async def descargar_estado(cve_ent: str, archivo: Path | None = None) -> tuple[int, int | None]:
    """Baja el ZIP del estado (o usa `archivo`, ya bajado) y lo carga."""
    if archivo is not None:
        return await cargar_zip(archivo, cve_ent)
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / f"denue_{cve_ent}_csv.zip"
        await descargar_zip(cve_ent, ruta)
        return await cargar_zip(ruta, cve_ent)


async def _borrar_los_que_no_vinieron(conn, cve_ent: str, inicio) -> int | None:
    """La carga entera es una transacción, y `now()` da su hora de arranque:
    lo que vino en esta carga tiene `actualizado = inicio`; lo de antes, menos."""
    cursor = await conn.execute(
        """SELECT count(*) FILTER (WHERE actualizado < %(inicio)s), count(*)
           FROM fuente_denue_negocios WHERE cve_ent = %(cve_ent)s""",
        {"cve_ent": cve_ent, "inicio": inicio},
    )
    viejos, todos = await cursor.fetchone()
    if viejos > MAX_PARTE_SIN_VENIR * todos:
        return None
    await conn.execute(
        "DELETE FROM fuente_denue_negocios WHERE cve_ent = %(cve_ent)s AND actualizado < %(inicio)s",
        {"cve_ent": cve_ent, "inicio": inicio},
    )
    return viejos


async def enriquecer_con_ubicacion(cve_ent: str) -> int:
    """Rellena cve_mun/cve_ageb de los negocios que todavia no lo
    tienen, cruzando su punto (lat, lon) contra los poligonos reales
    ya descargados (`ST_Contains`)."""
    pool = await get_pool()
    async with pool.connection() as conn:
        cursor_mun = await conn.execute(
            """UPDATE fuente_denue_negocios n
               SET cve_mun = m.cve_mun
               FROM municipios m
               WHERE n.cve_ent = %(cve_ent)s AND n.cve_mun IS NULL
                 AND n.lat IS NOT NULL AND n.lon IS NOT NULL
                 AND ST_Contains(m.geom, ST_SetSRID(ST_MakePoint(n.lon, n.lat), 4326))""",
            {"cve_ent": cve_ent},
        )
        actualizados_mun = cursor_mun.rowcount

        cursor_ageb = await conn.execute(
            """UPDATE fuente_denue_negocios n
               SET cve_ageb = a.cve_ageb
               FROM agebs a
               WHERE n.cve_ent = %(cve_ent)s AND n.cve_ageb IS NULL
                 AND n.lat IS NOT NULL AND n.lon IS NOT NULL
                 AND ST_Contains(a.geom, ST_SetSRID(ST_MakePoint(n.lon, n.lat), 4326))""",
            {"cve_ent": cve_ent},
        )
        actualizados_ageb = cursor_ageb.rowcount

    return actualizados_mun + actualizados_ageb
