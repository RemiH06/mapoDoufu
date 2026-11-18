"""Patrones de un rubro: si sus negocios se agrupan, dónde y junto a qué.

`donde_poner` asume que la competencia estorba, y hay rubros que se juntan a
propósito (florerías en Mezquitán, dulcerías en Santa Tere). Esto dice qué hace
el rubro, sin decir si conviene (RNF5, docs/arquitectura/decisiones.md).

Todo se compara contra los demás negocios del mismo recorte, reetiquetados al
azar: el comercio ya está agrupado de por sí (sigue a las calles y a la gente),
así que comparar contra puntos uniformes diría "se agrupa" de casi cualquier
rubro. Reetiquetar deja las ubicaciones donde están y sortea cuáles son del
rubro. La semilla es fija: la misma pregunta da siempre la misma respuesta.

- **¿Se agrupa?** Distancia media de cada negocio del rubro al otro más
  cercano del rubro, contra la misma medida en 199 sorteos.
- **¿En plazas?** Parte del rubro con marca de plaza, mercado o edificio
  comercial en DENUE, contra la de todos.
- **¿Junto a qué?** Cociente de colocación (Leslie y Kronenfeld, 2011): de los
  vecinos más cercanos de A, cuántas veces más de lo esperado son B. Es
  asimétrico: que A busque a B no implica lo contrario.
- **¿Dónde?** `ST_ClusterDBSCAN` de PostGIS, solo si el rubro se agrupa:
  encuentra los focos, deja fuera lo suelto y no pide cuántos hay.
"""

from __future__ import annotations

from collections import Counter, OrderedDict

import numpy as np
from psycopg_pool import AsyncConnectionPool
from scipy.spatial import cKDTree

from mapo_core import rubros
from mapo_core.zonas import plano

SORTEOS = 199
ALFA = 0.05
SEMILLA = 18

# Con menos, la distancia media depende de uno o dos negocios.
MIN_NEGOCIOS = 5

# Vecinos más cercanos por negocio para la colocación. En una plaza o mercado
# muchos comparten coordenada y empatan en distancia 0: el empate se reparte
# entre ellos (Leslie y Kronenfeld), pero solo entre los primeros que regresa
# el árbol. Con más empates que esto, se toma una parte, sin sesgo por rubro.
VECINOS = 10
EMPATE_KM = 0.001

# Colocación: cuántos rubros se listan y qué tan claro tiene que ser. Con 183
# rubros, a 0.05 saldrían nueve por puro azar; a 0.01 y con un mínimo de casos,
# casi ninguno.
MAX_JUNTO_A = 5
ALFA_JUNTO_A = 0.01
MIN_CASOS_JUNTO_A = 10

# Los que van al plano, de mayor a menor. La pantalla lista los primeros.
MAX_FOCOS = 50
MIN_POR_FOCO = 5
# El radio de los focos sale del azar: la mitad de la distancia media al
# vecino que tendría el rubro si sus negocios fueran cualesquiera.
MIN_RADIO_M = 10

# Toda la zona metropolitana de Guadalajara son unos 250 mil.
MAX_NEGOCIOS = 300_000

# Metros en todo México (ITRF2008, cónica conforme de Lambert).
SRID_METROS = 6372

_GUARDADOS = 32
_guardados: OrderedDict[tuple, dict] = OrderedDict()


class DemasiadosNegocios(Exception):
    pass


async def _negocios(pool: AsyncConnectionPool, cve_ent: str, cve_muns: list[str]) -> list[tuple]:
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """SELECT lat, lon, clase_actividad, tipo_plaza FROM fuente_denue_negocios
               WHERE cve_ent = %(cve_ent)s AND cve_mun = ANY(%(cve_muns)s)
                 AND lat IS NOT NULL AND lon IS NOT NULL""",
            {"cve_ent": cve_ent, "cve_muns": cve_muns},
        )
        return await cursor.fetchall()


def _vecinos_con_empate(xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(índices, pesos) de los vecinos más cercanos de cada punto, sin él
    mismo. Los empatados se reparten el peso de 1."""
    k = min(VECINOS + 1, len(xy))
    distancias, indices = cKDTree(xy).query(xy, k=k)
    distancias = np.where(indices == np.arange(len(xy))[:, None], np.inf, distancias)
    empate = distancias <= distancias.min(axis=1, keepdims=True) + EMPATE_KM
    return indices, empate / empate.sum(axis=1, keepdims=True)


def _distancia_media_m(xy: np.ndarray) -> float:
    distancias, _ = cKDTree(xy).query(xy, k=2)
    return float(distancias[:, 1].mean() * 1000)


def _p(observado: float, sorteos: np.ndarray, mayor: bool) -> float:
    """Valor p de una cola contra los sorteos, contando lo observado."""
    extremos = (sorteos >= observado) if mayor else (sorteos <= observado)
    return float((1 + extremos.sum()) / (1 + len(sorteos)))


def _patron(observado: float, sorteos: np.ndarray, bajo: str, alto: str) -> str:
    if _p(observado, sorteos, mayor=False) < ALFA:
        return bajo
    if _p(observado, sorteos, mayor=True) < ALFA:
        return alto
    return "como_los_demas"


def analizar(negocios: list[tuple], clases_a: list[str]) -> dict:
    """Agrupación, plazas y colocación del rubro (las clases `clases_a`)
    contra todos los `negocios` (lat, lon, clase, tipo_plaza). Sin base: se
    prueba con datos hechos a mano."""
    lat = np.array([n[0] for n in negocios], dtype=float)
    lon = np.array([n[1] for n in negocios], dtype=float)
    nombres_clase = sorted({n[2] or "" for n in negocios})
    indice_clase = {c: i for i, c in enumerate(nombres_clase)}
    etiquetas = np.array([indice_clase[n[2] or ""] for n in negocios])
    en_plaza = np.array([n[3] is not None for n in negocios])

    a = set(clases_a)
    es_a = np.array([c in a for c in nombres_clase])
    filas_a = es_a[etiquetas]
    n_a = int(filas_a.sum())
    base = {"negocios": n_a, "todos": len(negocios), "sorteos": SORTEOS}
    if n_a < MIN_NEGOCIOS:
        return {**base, "agrupacion": None, "plazas": None, "junto_a": [],
                "nota": f"Con menos de {MIN_NEGOCIOS} negocios del rubro con ubicación no hay patrón que medir."}

    xy = plano(lat, lon, float(lat.mean()))
    rng = np.random.default_rng(SEMILLA)

    # Rubros vecinos: los que no comparten clases con el que se pregunta.
    catalogo = rubros.clases()
    claves = sorted({c.rubro for c in catalogo.values() if c.rubro} - {catalogo[c].rubro for c in a if c in catalogo})
    indice_rubro = {r: i for i, r in enumerate(claves)}
    rubro_de = np.array([
        indice_rubro.get(catalogo[c].rubro, -1) if c in catalogo and catalogo[c].rubro else -1
        for c in nombres_clase
    ])
    indices, pesos = _vecinos_con_empate(xy)

    def casos(filas: np.ndarray, etiq: np.ndarray) -> np.ndarray:
        vecino = rubro_de[etiq[indices[filas]]]
        valido = vecino >= 0
        return np.bincount(vecino[valido], weights=pesos[filas][valido], minlength=len(claves))

    distancia = _distancia_media_m(xy[filas_a])
    plaza = float(en_plaza[filas_a].mean())
    junto = casos(filas_a, etiquetas)
    s_distancia, s_plaza, s_junto = np.empty(SORTEOS), np.empty(SORTEOS), np.empty((SORTEOS, len(claves)))
    for s in range(SORTEOS):
        etiq = rng.permutation(etiquetas)
        filas = es_a[etiq]
        s_distancia[s] = _distancia_media_m(xy[filas])
        s_plaza[s] = en_plaza[filas].mean()
        s_junto[s] = casos(filas, etiq)

    agrupacion = {
        "patron": _patron(distancia, s_distancia, "se_agrupa", "se_dispersa"),
        "distancia_m": round(distancia),
        "al_azar_m": round(float(s_distancia.mean())),
        "al_azar_rango_m": [round(float(np.percentile(s_distancia, q))) for q in (2.5, 97.5)],
        "p_agrupa": _p(distancia, s_distancia, mayor=False),
    }

    plazas = None
    if en_plaza.any():
        plazas = {
            "patron": _patron(plaza, s_plaza, "menos_en_plazas", "mas_en_plazas"),
            "rubro": round(plaza, 3),
            "todos": round(float(en_plaza.mean()), 3),
            "tipos": [
                {"tipo": t, "negocios": k}
                for t, k in Counter(negocios[i][3] for i in np.flatnonzero(filas_a & en_plaza)).most_common(3)
            ],
        }

    # CLQ = (casos A->B / N_A) / (N_B / (N - 1)). N_B no cambia al reetiquetar,
    # así que la prueba compara los casos directo.
    n_b = np.bincount(rubro_de[etiquetas][rubro_de[etiquetas] >= 0], minlength=len(claves))
    junto_a = []
    for j in np.argsort(-junto):
        if junto[j] < MIN_CASOS_JUNTO_A or n_b[j] == 0:
            continue
        cociente = (junto[j] / n_a) / (n_b[j] / (len(negocios) - 1))
        if cociente > 1 and _p(junto[j], s_junto[:, j], mayor=True) < ALFA_JUNTO_A:
            junto_a.append({
                "rubro": claves[j],
                "nombre": rubros.rubros()[claves[j]].nombre,
                "cociente": round(float(cociente), 1),
                "casos": round(float(junto[j])),
            })
    junto_a.sort(key=lambda f: -f["cociente"])

    return {**base, "agrupacion": agrupacion, "plazas": plazas, "junto_a": junto_a[:MAX_JUNTO_A],
            "nota": None if plazas else "Esta carga de DENUE no trae la marca de plaza o mercado."}


async def _focos(pool: AsyncConnectionPool, cve_ent: str, cve_muns: list[str], clases: list[str], radio_m: float) -> list[dict]:
    """Grupos de al menos MIN_POR_FOCO negocios del rubro encadenados a menos
    de `radio_m`. La colonia es la que más se repite en DENUE."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """WITH a AS (
                 SELECT colonia, lat, lon,
                        ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), %(srid)s) AS g
                 FROM fuente_denue_negocios
                 WHERE cve_ent = %(cve_ent)s AND cve_mun = ANY(%(cve_muns)s)
                   AND clase_actividad = ANY(%(clases)s) AND lat IS NOT NULL AND lon IS NOT NULL),
               c AS (
                 SELECT *, ST_ClusterDBSCAN(g, eps := %(radio)s::float8, minpoints := %(minimo)s::int) OVER () AS foco
                 FROM a)
               SELECT count(*), avg(lat), avg(lon), mode() WITHIN GROUP (ORDER BY colonia),
                      ST_AsGeoJSON(ST_Transform(ST_Buffer(ST_ConvexHull(ST_Collect(g)), %(radio)s::float8 / 2), 4326), 5)
               FROM c WHERE foco IS NOT NULL
               GROUP BY foco ORDER BY count(*) DESC""",
            {"srid": SRID_METROS, "cve_ent": cve_ent, "cve_muns": cve_muns, "clases": clases,
             "radio": radio_m, "minimo": MIN_POR_FOCO},
        )
        filas = await cursor.fetchall()
    return [
        {"negocios": n, "lat": round(lat, 5), "lon": round(lon, 5), "colonia": colonia, "geojson": geojson}
        for n, lat, lon, colonia, geojson in filas
    ]


async def calcular(pool: AsyncConnectionPool, cve_ent: str, cve_muns: list[str], clases: list[str]) -> dict:
    llave = (cve_ent, tuple(sorted(cve_muns)), tuple(sorted(clases)))
    if llave in _guardados:
        _guardados.move_to_end(llave)
        return _guardados[llave]

    negocios = await _negocios(pool, cve_ent, cve_muns)
    if len(negocios) > MAX_NEGOCIOS:
        raise DemasiadosNegocios(
            f"Son {len(negocios):,} negocios: el patrón llega a {MAX_NEGOCIOS:,}. Elige menos municipios."
        )
    resultado = analizar(negocios, clases)

    focos: list[dict] = []
    radio = None
    agrupacion = resultado["agrupacion"]
    if agrupacion and agrupacion["patron"] == "se_agrupa":
        radio = max(MIN_RADIO_M, round(agrupacion["al_azar_m"] / 2))
        focos = await _focos(pool, cve_ent, cve_muns, clases, radio)
    resultado["focos"] = {
        "radio_m": radio,
        "minimo": MIN_POR_FOCO,
        "total": len(focos),
        "en_focos": sum(f["negocios"] for f in focos),
        "lista": focos[:MAX_FOCOS],
    }

    _guardados[llave] = resultado
    if len(_guardados) > _GUARDADOS:
        _guardados.popitem(last=False)
    return resultado
