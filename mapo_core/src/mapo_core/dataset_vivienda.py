"""Dataset tipo Boston Housing por AGEB urbana para una zona metropolitana.

Una fila por AGEB con censo, con las variables del Boston Housing de Harrison y
Rubinfeld (1978) traducidas a fuentes abiertas de México. Mapo arma la tabla; el
modelo vive fuera (un precio predicho sería un puntaje único, RNF5). Cada
columna, su fuente y su equivalente de Boston están en DICCIONARIO y en
`docs/producto/dataset-vivienda.md`.

    python -m mapo_core.cli dataset_vivienda --estado 14 \
        --municipios 002,039,044,051,070,097,098,101,120,124 --salida /app/data/vivienda_gdl

Las columnas que salen de otras fuentes (catastro, satélite, OSM) se agregan
después con su propio paso; aquí quedan en blanco y el diccionario lo dice.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from psycopg_pool import AsyncConnectionPool
from shapely import wkb
from shapely.geometry import mapping

from mapo_core import rubros

# Personal ocupado estimado por estrato de DENUE: punto medio del rango. El
# último estrato no tiene tope; 300 es una convención, se dice en el diccionario.
PERSONAL_POR_ESTRATO = {
    "0 a 5 personas": 3,
    "6 a 10 personas": 8,
    "11 a 30 personas": 20.5,
    "31 a 50 personas": 40.5,
    "51 a 100 personas": 75.5,
    "101 a 250 personas": 175.5,
    "251 y más personas": 300,
}

# INDUS de Boston: superficie de negocios no minoristas. Aquí, la parte del
# personal ocupado en estos sectores de `rubros/sectores.csv`.
SECTORES_NO_MINORISTAS = ("industria", "mayoreo", "transporte_y_logistica", "agro_mineria_y_energia")

# DIS de Boston: distancia ponderada a cinco centros de empleo.
CENTROS_DE_EMPLEO = 5
CELDA_EMPLEO_M = 1000  # rejilla para encontrar los focos de empleo
SEPARACION_CENTROS_M = 4000  # dos centros no pueden estar más cerca que esto


# Etiquetas de tramo mínimas para dar medv_calle: con una o dos, un solo corredor
# decidiría el valor de la AGEB.
MIN_VALORES_CALLE = 3


@dataclass(frozen=True)
class Columna:
    nombre: str
    descripcion: str
    boston: str  # variable equivalente en Boston, o "" si es extra
    fuente: str
    nivel: str
    metodo: str


DICCIONARIO = [
    Columna("cvegeo", "Clave geoestadística de la AGEB (13 caracteres)", "", "INEGI, marco geoestadístico 2020", "AGEB", "llave"),
    Columna("cve_mun", "Clave del municipio", "", "INEGI", "municipio", "llave"),
    Columna("municipio", "Nombre del municipio", "", "INEGI", "municipio", "llave"),
    Columna("lon", "Longitud de un punto dentro de la AGEB", "", "PostGIS ST_PointOnSurface", "AGEB", "calculado"),
    Columna("lat", "Latitud de un punto dentro de la AGEB", "", "PostGIS ST_PointOnSurface", "AGEB", "calculado"),
    Columna("area_ha", "Superficie de la AGEB en hectáreas", "", "PostGIS, sobre el elipsoide", "AGEB", "calculado"),
    Columna("pobtot", "Población total", "", "Censo 2020, POBTOT", "AGEB", "directo"),
    Columna("viv_hab", "Viviendas particulares habitadas", "", "Censo 2020, VIVPAR_HAB", "AGEB", "directo"),
    Columna("medv", "Mediana del valor catastral de suelo de zona, $/m², pesos del año de la tabla", "MEDV", "Tablas de valores municipales (scripts/catastro/fuentes.csv)", "AGEB", "mediana de las etiquetas de valor de zona que caen en la AGEB; ver medv_metodo"),
    Columna("medv_n", "Etiquetas de valor de zona dentro de la AGEB", "", "Tablas de valores municipales", "AGEB", "conteo; una zona rotulada en dos hojas cuenta dos veces"),
    Columna("medv_calle", "Mediana del valor catastral por tramo de calle, $/m²", "MEDV (alternativa)", "Tablas de valores municipales", "AGEB", f"mediana de las etiquetas de tramo; vacía con menos de {MIN_VALORES_CALLE}. Los corredores comerciales la suben"),
    Columna("medv_calle_n", "Etiquetas de valor por tramo dentro de la AGEB", "", "Tablas de valores municipales", "AGEB", "conteo"),
    Columna("medv_anio", "Año fiscal de la tabla de valores", "", "scripts/catastro/fuentes.csv", "municipio", "directo; tablas de años distintos no son comparables sin deflactar"),
    Columna("medv_metodo", "De dónde sale medv o por qué está vacío", "", "", "AGEB", "texto"),
    Columna("crim", "Delitos registrados en el año base por 100 mil habitantes del municipio", "CRIM", "SESNSP, incidencia municipal; población del censo 2020", "municipio", "suma de cantidad del año base / POBTOT municipal × 100 000"),
    Columna("viv_ha", "Viviendas particulares habitadas por hectárea", "ZN (sustituto)", "Censo 2020 + área de la AGEB", "AGEB", "VIVPAR_HAB / area_ha. ZN de Boston es zonificación de lote grande: aquí la densidad, que va en sentido contrario"),
    Columna("indus", "Parte del personal ocupado en industria, mayoreo, transporte y agro", "INDUS", "DENUE (personal estimado por estrato)", "AGEB", "personal en sectores no minoristas / personal total de la AGEB; vacío si no hay negocios"),
    Columna("chas", "Hay un río o canal a 100 m o menos de la AGEB (1 o 0)", "CHAS", "OSM, waterway=river|canal", "AGEB", "intersección de la AGEB con un búfer de 100 m de los cauces; los arroyos (stream) no cuentan"),
    Columna("nox", "NO₂ troposférico medio", "NOX", "Sentinel-5P TROPOMI", "~5 km", "pendiente"),
    Columna("rm", "Cuartos promedio por vivienda (cota inferior)", "RM", "Censo 2020, VPH_1CUART, VPH_2CUART, VPH_3YMASC", "AGEB", "(1·VPH_1CUART + 2·VPH_2CUART + 3·VPH_3YMASC) / suma; '3 y más' cuenta como 3"),
    Columna("pro_ocup_c", "Ocupantes por cuarto", "", "Censo 2020, PRO_OCUP_C", "AGEB", "directo"),
    Columna("pct_viv_3ymas_cuartos", "% de viviendas con 3 cuartos o más", "RM (complemento)", "Censo 2020, VPH_3YMASC", "AGEB", "VPH_3YMASC / VIVPARH_CV × 100. El censo no abre más allá de 3 cuartos, por eso rm casi no varía"),
    Columna("pct_viv_2ymas_dorm", "% de viviendas con 2 dormitorios o más", "RM (complemento)", "Censo 2020, VPH_2YMASD", "AGEB", "VPH_2YMASD / VIVPARH_CV × 100"),
    Columna("age", "Parte de la superficie construida en 2020 que ya existía en 1990", "AGE", "JRC GHSL GHS-BUILT-S R2023A, 100 m, CC BY 4.0", "AGEB (píxeles de 100 m)", "superficie construida 1990 / 2020 en los píxeles cuyo centro cae en la AGEB; vacío si no hay nada construido en 2020"),
    Columna("age_1975", "Parte de la superficie construida en 2020 que ya existía en 1975", "AGE (variante)", "JRC GHSL GHS-BUILT-S R2023A", "AGEB (píxeles de 100 m)", "igual que age, con la época 1975"),
    Columna("dis_km", "Distancia promedio en línea recta a los 5 centros de empleo, ponderada por su empleo", "DIS", "DENUE (personal estimado por estrato)", "AGEB", "focos de empleo en rejilla de 1 km separados al menos 4 km; ver centros_empleo.csv"),
    Columna("rad_km", "Distancia en línea recta a la vía rápida más cercana, km", "RAD", "OSM, highway=motorway|trunk", "AGEB", "desde el punto dentro de la AGEB (lon, lat); RAD de Boston es un índice de acceso, aquí la distancia"),
    Columna("tax", "Tasa de predial del municipio", "TAX", "Ley de ingresos municipal", "municipio", "pendiente"),
    Columna("ptratio", "Alumnos por docente", "PTRATIO", "SEP 911 o sustituto", "por definir", "pendiente"),
    Columna("pct_sin_secundaria", "% de 15 años o más sin secundaria completa", "LSTAT (componente)", "Censo 2020, P15YM_SE, P15PRI_IN, P15PRI_CO, P15SEC_IN, P_15YMAS", "AGEB", "(P15YM_SE + P15PRI_IN + P15PRI_CO + P15SEC_IN) / P_15YMAS × 100"),
    Columna("pct_sin_servicios_salud", "% de población sin afiliación a servicios de salud", "LSTAT (componente)", "Censo 2020, PSINDER", "AGEB", "PSINDER / POBTOT × 100"),
    Columna("pct_piso_tierra", "% de viviendas con piso de tierra", "LSTAT (componente)", "Censo 2020, VPH_PISOTI", "AGEB", "VPH_PISOTI / VIVPARH_CV × 100"),
    Columna("graproes", "Grado promedio de escolaridad", "LSTAT (componente)", "Censo 2020, GRAPROES", "AGEB", "directo"),
    Columna("pct_viv_deshabitadas", "% de viviendas particulares deshabitadas", "", "Censo 2020, VIVPAR_DES, TVIVPAR", "AGEB", "VIVPAR_DES / TVIVPAR × 100; extra, Boston no lo tiene"),
    Columna("pct_viv_auto", "% de viviendas con automóvil", "", "Censo 2020, VPH_AUTOM", "AGEB", "VPH_AUTOM / VIVPARH_CV × 100; extra"),
    Columna("pct_viv_internet", "% de viviendas con internet", "", "Censo 2020, VPH_INTER", "AGEB", "VPH_INTER / VIVPARH_CV × 100; extra"),
]
COLUMNAS = [c.nombre for c in DICCIONARIO]


def _num(datos: dict, clave: str) -> float | None:
    """El censo usa '*' (reservado por confidencialidad) y 'N/D': esos son None."""
    try:
        return float(datos.get(clave))
    except (TypeError, ValueError):
        return None


def _porcentaje(numerador: float | None, denominador: float | None) -> float | None:
    if numerador is None or not denominador:
        return None
    return round(100 * numerador / denominador, 2)


def cuartos_promedio(datos: dict) -> float | None:
    uno, dos, tres = (_num(datos, k) for k in ("VPH_1CUART", "VPH_2CUART", "VPH_3YMASC"))
    if None in (uno, dos, tres) or uno + dos + tres == 0:
        return None
    return round((uno + 2 * dos + 3 * tres) / (uno + dos + tres), 3)


def sin_secundaria(datos: dict) -> float | None:
    partes = [_num(datos, k) for k in ("P15YM_SE", "P15PRI_IN", "P15PRI_CO", "P15SEC_IN")]
    if None in partes:
        return None
    return _porcentaje(sum(partes), _num(datos, "P_15YMAS"))


def centros_de_empleo(negocios: list[tuple[float, float, float]], n: int = CENTROS_DE_EMPLEO) -> list[dict]:
    """Los n focos de empleo más grandes: celdas de 1 km con más personal,
    sin dos a menos de SEPARACION_CENTROS_M. Determinista y sin parámetros que
    dependan de la ciudad, para poder correrlo en cualquier zona."""
    if not negocios:
        return []
    lat0 = sum(n_[1] for n_ in negocios) / len(negocios)
    m_lon = 111_320 * math.cos(math.radians(lat0))
    celdas: dict[tuple[int, int], list[float]] = {}
    for lon, lat, personal in negocios:
        clave = (int(lon * m_lon // CELDA_EMPLEO_M), int(lat * 110_540 // CELDA_EMPLEO_M))
        c = celdas.setdefault(clave, [0.0, 0.0, 0.0])
        c[0] += personal
        c[1] += lon * personal
        c[2] += lat * personal
    ordenadas = sorted(celdas.values(), key=lambda c: -c[0])
    elegidos: list[dict] = []
    for personal, slon, slat in ordenadas:
        lon, lat = slon / personal, slat / personal
        if all(_metros(lon, lat, e["lon"], e["lat"]) >= SEPARACION_CENTROS_M for e in elegidos):
            elegidos.append({"lon": round(lon, 5), "lat": round(lat, 5), "personal": round(personal)})
        if len(elegidos) == n:
            break
    return elegidos


def _metros(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Haversine en metros."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def distancia_ponderada_km(lon: float, lat: float, centros: list[dict]) -> float | None:
    if not centros:
        return None
    total = sum(c["personal"] for c in centros)
    return round(sum(_metros(lon, lat, c["lon"], c["lat"]) * c["personal"] for c in centros) / total / 1000, 3)


async def _agebs(pool: AsyncConnectionPool, cve_ent: str, municipios: list[str]) -> list[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT a.cvegeo, a.cve_mun, m.nombre, c.datos_json,
                      ST_X(p.geom), ST_Y(p.geom), ST_Area(a.geom::geography) / 10000, ST_AsBinary(a.geom)
               FROM agebs a
               JOIN fuente_censo_poblacion c ON c.cvegeo = a.cvegeo AND c.nivel = 'ageb'
               JOIN municipios m ON m.cve_ent = a.cve_ent AND m.cve_mun = a.cve_mun
               CROSS JOIN LATERAL (SELECT ST_PointOnSurface(a.geom) AS geom) p
               WHERE a.cve_ent = %(ent)s AND a.cve_mun = ANY(%(muns)s)
               ORDER BY a.cvegeo""",
            {"ent": cve_ent, "muns": municipios},
        )
        filas = await cur.fetchall()
    return [
        {"cvegeo": cvegeo, "cve_mun": mun, "municipio": nombre, "datos": datos, "lon": lon, "lat": lat,
         "area_ha": area, "geom": bytes(geom)}
        for cvegeo, mun, nombre, datos, lon, lat, area, geom in filas
    ]


async def _negocios(pool: AsyncConnectionPool, cve_ent: str, municipios: list[str]) -> list[tuple]:
    """(cvegeo de la AGEB que lo contiene, lon, lat, clase, estrato). La AGEB se
    asigna por geometría: el campo cve_ageb de DENUE viene vacío a veces."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT a.cvegeo, n.lon, n.lat, n.clase_actividad, n.estrato
               FROM fuente_denue_negocios n
               LEFT JOIN agebs a ON a.cve_ent = n.cve_ent AND a.cve_mun = n.cve_mun
                    AND ST_Contains(a.geom, ST_SetSRID(ST_MakePoint(n.lon, n.lat), 4326))
               WHERE n.cve_ent = %(ent)s AND n.cve_mun = ANY(%(muns)s) AND n.lon IS NOT NULL""",
            {"ent": cve_ent, "muns": municipios},
        )
        return await cur.fetchall()


async def _crimen(pool: AsyncConnectionPool, cve_ent: str, municipios: list[str], anio: int) -> dict[str, float]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT d.cve_mun, sum(d.cantidad)::float * 100000 / max(c.pobtot)
               FROM fuente_sesnsp_delitos_municipal d
               JOIN fuente_censo_poblacion c ON c.nivel = 'municipio' AND c.cve_ent = d.cve_ent AND c.cve_mun = d.cve_mun
               WHERE d.cve_ent = %(ent)s AND d.cve_mun = ANY(%(muns)s) AND d.anio = %(anio)s
               GROUP BY d.cve_mun""",
            {"ent": cve_ent, "muns": municipios, "anio": anio},
        )
        return {mun: round(tasa, 1) for mun, tasa in await cur.fetchall()}


def _a_utm(geom, lon0: float):
    """Geometría de grados a la UTM de su zona, para medir en metros."""
    from rasterio.warp import transform_geom
    from shapely.geometry import shape

    zona = int((lon0 + 180) // 6) + 1
    return shape(transform_geom("EPSG:4326", f"EPSG:{32600 + zona}", mapping(geom)))


def _lineas_osm(ruta: Path, filtro) -> list:
    from shapely.geometry import LineString

    lineas = []
    for el in json.loads(Path(ruta).read_text(encoding="utf-8"))["elements"]:
        g = el.get("geometry")
        if el.get("type") == "way" and g and len(g) > 1 and filtro(el.get("tags", {})):
            lineas.append(LineString([(p["lon"], p["lat"]) for p in g]))
    return lineas


def asignar_osm(filas: list[dict], agua: Path | None, vias: Path | None) -> None:
    """CHAS y RAD desde extractos de Overpass (docs/producto/dataset-vivienda.md)."""
    from shapely import STRtree
    from shapely.geometry import Point
    from shapely.ops import unary_union

    if not filas:
        return
    lon0 = float(np.median([f["lon"] for f in filas]))
    if agua:
        cauces = _lineas_osm(agua, lambda t: t.get("waterway") in ("river", "canal"))
        bufer = _a_utm(unary_union(cauces), lon0).buffer(100) if cauces else None
        for f in filas:
            f["chas"] = int(bufer is not None and _a_utm(wkb.loads(f["_geom"]), lon0).intersects(bufer))
    if vias:
        rapidas = [_a_utm(g, lon0) for g in _lineas_osm(vias, lambda t: t.get("highway") in ("motorway", "trunk"))]
        if rapidas:
            arbol = STRtree(rapidas)
            for f in filas:
                p = _a_utm(Point(f["lon"], f["lat"]), lon0)
                f["rad_km"] = round(p.distance(rapidas[int(arbol.nearest(p))]) / 1000, 3)


def asignar_ghsl(filas: list[dict], rasters: dict[int, Path | None]) -> None:
    """AGE: superficie construida de 1990 (y 1975) entre la de 2020, por AGEB."""
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom
    from rasterio.windows import from_bounds
    from shapely.geometry import shape

    abiertos = {anio: rasterio.open(r) for anio, r in rasters.items() if r and Path(r).exists()}
    try:
        if 2020 not in abiertos:
            return
        ref = abiertos[2020]
        for f in filas:
            g = transform_geom("EPSG:4326", ref.crs, mapping(wkb.loads(f["_geom"])))
            ventana = from_bounds(*shape(g).bounds, transform=ref.transform).round_offsets().round_lengths()
            alto, ancho = max(int(ventana.height), 1), max(int(ventana.width), 1)
            ventana = ventana.__class__(ventana.col_off, ventana.row_off, ancho, alto)
            # Píxeles cuyo centro cae en la AGEB; si es tan chica que no tiene ninguno, los que toca.
            dentro = ~geometry_mask([g], out_shape=(alto, ancho), transform=ref.window_transform(ventana))
            if not dentro.any():
                dentro = ~geometry_mask([g], out_shape=(alto, ancho), transform=ref.window_transform(ventana), all_touched=True)
            suma = {a: float(r.read(1, window=ventana, boundless=True, fill_value=0)[dentro].sum()) for a, r in abiertos.items()}
            if suma[2020] > 0:
                f["age"] = round(min(suma[1990] / suma[2020], 1), 4) if 1990 in suma else None
                f["age_1975"] = round(min(suma[1975] / suma[2020], 1), 4) if 1975 in suma else None
    finally:
        for r in abiertos.values():
            r.close()


def leer_valores(rutas: list[Path]) -> list[dict]:
    """`valores.csv` de scripts/catastro/ubicar_pdf_mapa.py (o de cualquier adaptador
    con las mismas columnas: municipio, anio, valor_m2, clase, lon, lat)."""
    valores = []
    for ruta in rutas:
        with open(ruta, encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                valores.append({"municipio": fila["municipio"], "anio": int(fila["anio"]), "clase": fila["clase"],
                                "valor": float(fila["valor_m2"]), "lon": float(fila["lon"]), "lat": float(fila["lat"])})
    return valores


def asignar_medv(filas: list[dict], valores: list[dict], cve_ent: str) -> None:
    """Mediana por AGEB, por clase. Nunca rellena con vecinas: lo que falta se dice."""
    from shapely import STRtree
    from shapely.geometry import Point

    geoms = [wkb.loads(f["_geom"]) for f in filas]
    arbol = STRtree(geoms)
    por_ageb: dict[int, dict[str, list[float]]] = {}
    for v in valores:
        for i in arbol.query(Point(v["lon"], v["lat"]), predicate="intersects"):
            por_ageb.setdefault(int(i), {"zona": [], "calle": []}).setdefault(v["clase"] or "calle", []).append(v["valor"])
    anio_por_mun = {v["municipio"]: v["anio"] for v in valores}
    for i, fila in enumerate(filas):
        anio = anio_por_mun.get(cve_ent + fila["cve_mun"])
        grupos = por_ageb.get(i, {"zona": [], "calle": []})
        zona, calle = grupos.get("zona", []), grupos.get("calle", [])
        fila["medv_anio"] = anio
        fila["medv_n"], fila["medv_calle_n"] = len(zona), len(calle)
        fila["medv"] = float(np.median(zona)) if zona else None
        fila["medv_calle"] = float(np.median(calle)) if len(calle) >= MIN_VALORES_CALLE else None
        if anio is None:
            fila["medv_metodo"] = "sin tabla de valores ubicada para este municipio"
            fila["medv_n"] = fila["medv_calle_n"] = None
        elif zona:
            fila["medv_metodo"] = f"mediana de {len(zona)} valores de zona, tabla {anio}"
        else:
            fila["medv_metodo"] = f"sin valor de zona dentro de la AGEB (tabla {anio}; {len(calle)} de tramo)"


async def construir(pool: AsyncConnectionPool, cve_ent: str, municipios: list[str], anio_crimen: int = 2020,
                    valores: list[dict] | None = None, agua: Path | None = None, vias: Path | None = None,
                    ghsl: dict[int, Path | None] | None = None) -> tuple[list[dict], list[dict]]:
    """Filas del dataset y los centros de empleo usados para DIS."""
    agebs = await _agebs(pool, cve_ent, municipios)
    negocios = await _negocios(pool, cve_ent, municipios)
    crimen = await _crimen(pool, cve_ent, municipios, anio_crimen)

    no_minoristas = {c for s in SECTORES_NO_MINORISTAS for c in rubros.clases_de(sector=s)}
    personal: dict[str, list[float]] = {}
    puntos = []
    for cvegeo, lon, lat, clase, estrato in negocios:
        p = PERSONAL_POR_ESTRATO.get(estrato, 3)
        puntos.append((lon, lat, p))
        if cvegeo:
            acc = personal.setdefault(cvegeo, [0.0, 0.0])
            acc[0] += p
            acc[1] += p if clase in no_minoristas else 0
    centros = centros_de_empleo(puntos)

    filas = []
    for a in agebs:
        d = a["datos"]
        viv_hab = _num(d, "VIVPAR_HAB")
        # Las VPH_* cuentan sobre viviendas habitadas con características
        # (VIVPARH_CV), que es mayor que VIVPAR_HAB: con este último pasan de 100 %.
        con_carac = _num(d, "VIVPARH_CV")
        total, no_min = personal.get(a["cvegeo"], (0.0, 0.0))
        filas.append({
            "cvegeo": a["cvegeo"], "cve_mun": a["cve_mun"], "municipio": a["municipio"],
            "lon": round(a["lon"], 6), "lat": round(a["lat"], 6), "area_ha": round(a["area_ha"], 3),
            "pobtot": _num(d, "POBTOT"), "viv_hab": viv_hab,
            "crim": crimen.get(a["cve_mun"]),
            "viv_ha": round(viv_hab / a["area_ha"], 3) if viv_hab is not None and a["area_ha"] else None,
            "indus": round(no_min / total, 4) if total else None,
            "chas": None, "nox": None, "age": None, "age_1975": None, "rad_km": None,
            "rm": cuartos_promedio(d),
            "pro_ocup_c": _num(d, "PRO_OCUP_C"),
            "pct_viv_3ymas_cuartos": _porcentaje(_num(d, "VPH_3YMASC"), con_carac),
            "pct_viv_2ymas_dorm": _porcentaje(_num(d, "VPH_2YMASD"), con_carac),
            "dis_km": distancia_ponderada_km(a["lon"], a["lat"], centros),
            "tax": None, "ptratio": None,
            "pct_sin_secundaria": sin_secundaria(d),
            "pct_sin_servicios_salud": _porcentaje(_num(d, "PSINDER"), _num(d, "POBTOT")),
            "pct_piso_tierra": _porcentaje(_num(d, "VPH_PISOTI"), con_carac),
            "graproes": _num(d, "GRAPROES"),
            "pct_viv_deshabitadas": _porcentaje(_num(d, "VIVPAR_DES"), _num(d, "TVIVPAR")),
            "pct_viv_auto": _porcentaje(_num(d, "VPH_AUTOM"), con_carac),
            "pct_viv_internet": _porcentaje(_num(d, "VPH_INTER"), con_carac),
            "_geom": a["geom"],
        })
    asignar_medv(filas, valores or [], cve_ent)
    asignar_osm(filas, agua, vias)
    if ghsl:
        asignar_ghsl(filas, ghsl)
    return filas, centros


def escribir(filas: list[dict], centros: list[dict], salida: Path, notas: dict) -> None:
    """CSV para el modelo, GeoJSON para el SIG, diccionario y centros de empleo."""
    salida.mkdir(parents=True, exist_ok=True)
    with open(salida / "vivienda_ageb.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    rasgos = [
        {"type": "Feature", "properties": {k: v for k, v in fila.items() if k != "_geom"},
         "geometry": mapping(wkb.loads(fila["_geom"]))}
        for fila in filas
    ]
    with open(salida / "vivienda_ageb.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": rasgos}, f, ensure_ascii=False)
    with open(salida / "diccionario.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["columna", "descripcion", "equivalente_boston", "fuente", "nivel", "metodo", "vacios"])
        for c in DICCIONARIO:
            vacios = sum(1 for fila in filas if fila.get(c.nombre) is None)
            w.writerow([c.nombre, c.descripcion, c.boston, c.fuente, c.nivel, c.metodo, vacios])
    with open(salida / "centros_empleo.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["lon", "lat", "personal"])
        w.writeheader()
        w.writerows(centros)
    (salida / "LEEME.txt").write_text(
        "Dataset tipo Boston Housing por AGEB urbana, armado por Mapo.\n"
        + "".join(f"{k}: {v}\n" for k, v in notas.items())
        + "Columnas, fuentes y métodos: diccionario.csv. 'vacios' cuenta las AGEB sin dato;\n"
        "el censo reserva con '*' los valores de AGEB con muy pocas viviendas.\n"
        "Documentación completa: docs/producto/dataset-vivienda.md del repo de Mapo.\n"
        "Atribución: censo 2020 y DENUE, INEGI; incidencia delictiva, SESNSP; calles y cauces,\n"
        "© colaboradores de OpenStreetMap (ODbL); superficie construida, JRC GHSL (CC BY 4.0);\n"
        "valores catastrales, tablas de valores de cada municipio (ver medv_anio).\n",
        encoding="utf-8",
    )


def resumen(filas: list[dict]) -> dict[str, tuple[float, float, float]]:
    """p5, mediana y p95 por columna numérica, para revisar a ojo antes de entregar."""
    salida = {}
    for c in COLUMNAS[3:]:
        valores = np.array([f[c] for f in filas if isinstance(f.get(c), (int, float))], dtype=float)
        if len(valores):
            salida[c] = tuple(np.round(np.percentile(valores, [5, 50, 95]), 3))
    return salida
