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

from mapo_core import iieg_oferta, rubros, vivienda_entorno

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
    Columna("medv", "Mediana del precio de oferta por vivienda (casas y departamentos en venta), pesos de medv_periodo", "MEDV", "IIEG, anuncios de portales inmobiliarios (BD_SECTOR_INMOBILIARIO) y polígonos de colonia (mapa_venta)", "AGEB", f"mediana ponderada de los anuncios de las colonias que tocan la AGEB; peso = parte del área de la colonia dentro de la AGEB; vacía con menos de {iieg_oferta.MIN_ANUNCIOS} anuncios efectivos; ver medv_metodo"),
    Columna("medv_n", "Anuncios efectivos de la AGEB", "", "IIEG", "AGEB", "suma de los pesos; un anuncio de una colonia partida en dos AGEB cuenta en las dos en proporción"),
    Columna("medv_m2", "Mediana del precio de oferta por m² construido, pesos de medv_periodo", "MEDV (por m²)", "IIEG", "AGEB", f"igual que medv con precio / m² de construcción ({iieg_oferta.M2_MIN} a {iieg_oferta.M2_MAX} m²)"),
    Columna("pct_departamentos", "% de departamentos entre los anuncios efectivos", "", "IIEG", "AGEB", "ponderado igual que medv; el resto son casas"),
    Columna("medv_periodo", "Mes de los anuncios", "", "IIEG", "municipio", "directo; vacío si el IIEG no cubre el municipio"),
    Columna("medv_metodo", "De dónde sale medv o por qué está vacío", "", "", "AGEB", "texto"),
    Columna("suelo_m2", "Mediana del valor catastral de suelo de zona, $/m², pesos del año de la tabla", "", "Tablas de valores municipales (scripts/catastro/fuentes.csv)", "AGEB", "mediana de las etiquetas de valor de zona que caen en la AGEB; ver suelo_metodo. Hasta la v7 se llamaba medv"),
    Columna("suelo_n", "Etiquetas de valor de zona dentro de la AGEB", "", "Tablas de valores municipales", "AGEB", "conteo; una zona rotulada en dos hojas cuenta dos veces"),
    Columna("suelo_calle_m2", "Mediana del valor catastral por tramo de calle, $/m²", "", "Tablas de valores municipales", "AGEB", f"mediana de las etiquetas de tramo; vacía con menos de {MIN_VALORES_CALLE}. Los corredores comerciales la suben"),
    Columna("suelo_calle_n", "Etiquetas de valor por tramo dentro de la AGEB", "", "Tablas de valores municipales", "AGEB", "conteo"),
    Columna("suelo_anio", "Año fiscal de la tabla de valores", "", "scripts/catastro/fuentes.csv", "municipio", "directo; tablas de años distintos no son comparables sin deflactar"),
    Columna("suelo_metodo", "De dónde sale suelo_m2 o por qué está vacío", "", "", "AGEB", "texto"),
    Columna("suelo_2026_m2", "Mediana del valor catastral de suelo con las tablas de 2026, $/m² (zona y tramo juntos)", "", "Tablas de valores 2026: Guadalajara, Zapopan y Tonalá (expedientes de INFOLEJ y Zapopan)", "AGEB", "mediana de las etiquetas dentro, con 3 como mínimo; todas del mismo año fiscal, para comparar municipios"),
    Columna("suelo_2026_n", "Etiquetas de valor de 2026 dentro de la AGEB", "", "Tablas de valores 2026", "AGEB", "conteo; vacío si el municipio no tiene tabla 2026 ubicada"),
    Columna("crim", "Delitos registrados en el año base por 100 mil habitantes del municipio", "CRIM", "SESNSP, incidencia municipal; población del censo 2020", "municipio", "suma de cantidad del año base / POBTOT municipal × 100 000"),
    Columna("viv_ha", "Viviendas particulares habitadas por hectárea", "ZN (sustituto)", "Censo 2020 + área de la AGEB", "AGEB", "VIVPAR_HAB / area_ha. ZN de Boston es zonificación de lote grande: aquí la densidad, que va en sentido contrario"),
    Columna("indus", "Parte del personal ocupado en industria, mayoreo, transporte y agro", "INDUS", "DENUE (personal estimado por estrato)", "AGEB", "personal en sectores no minoristas / personal total de la AGEB; vacío si no hay negocios"),
    Columna("chas", "Hay un río o canal a 100 m o menos de la AGEB (1 o 0)", "CHAS", "OSM, waterway=river|canal", "AGEB", "intersección de la AGEB con un búfer de 100 m de los cauces; los arroyos (stream) no cuentan"),
    Columna("nox", "NO₂ troposférico medio del año, µmol/m²", "NOX", "Copernicus Sentinel-5P TROPOMI L2 OFFL, vía scripts/ambiental/no2_s5p.py", "píxel de ~5.5 × 3.5 km, en rejilla de 0.01°", "valor de la celda donde cae el punto de la AGEB; columna total, no concentración a nivel de calle"),
    Columna("nox_obs", "Observaciones de TROPOMI que promedian la celda de nox", "", "Sentinel-5P", "celda de 0.01°", "píxeles con qa_value > 0.75 en el año"),
    Columna("rm", "Cuartos promedio por vivienda (cota inferior)", "RM", "Censo 2020, VPH_1CUART, VPH_2CUART, VPH_3YMASC", "AGEB", "(1·VPH_1CUART + 2·VPH_2CUART + 3·VPH_3YMASC) / suma; '3 y más' cuenta como 3"),
    Columna("pro_ocup_c", "Ocupantes por cuarto", "", "Censo 2020, PRO_OCUP_C", "AGEB", "directo"),
    Columna("pct_viv_3ymas_cuartos", "% de viviendas con 3 cuartos o más", "RM (complemento)", "Censo 2020, VPH_3YMASC", "AGEB", "VPH_3YMASC / VIVPARH_CV × 100. El censo no abre más allá de 3 cuartos, por eso rm casi no varía"),
    Columna("pct_viv_2ymas_dorm", "% de viviendas con 2 dormitorios o más", "RM (complemento)", "Censo 2020, VPH_2YMASD", "AGEB", "VPH_2YMASD / VIVPARH_CV × 100"),
    Columna("age", "Parte de la superficie construida en 2020 que ya existía en 1990", "AGE", "JRC GHSL GHS-BUILT-S R2023A, 100 m, CC BY 4.0", "AGEB (píxeles de 100 m)", "superficie construida 1990 / 2020 en los píxeles cuyo centro cae en la AGEB; vacío si no hay nada construido en 2020"),
    Columna("age_1975", "Parte de la superficie construida en 2020 que ya existía en 1975", "AGE (variante)", "JRC GHSL GHS-BUILT-S R2023A", "AGEB (píxeles de 100 m)", "igual que age, con la época 1975"),
    Columna("dis_km", "Distancia promedio en línea recta a los 5 centros de empleo, ponderada por su empleo", "DIS", "DENUE (personal estimado por estrato)", "AGEB", "focos de empleo en rejilla de 1 km separados al menos 4 km; ver centros_empleo.csv"),
    Columna("rad_km", "Distancia en línea recta a la vía rápida más cercana, km", "RAD", "OSM, highway=motorway|trunk", "AGEB", "desde el punto dentro de la AGEB (lon, lat); RAD de Boston es un índice de acceso, aquí la distancia"),
    Columna("tax", "Predial anual por cada $10,000 de valor fiscal, para una propiedad de $1,000,000", "TAX", "Leyes de ingresos municipales (predial_tablas.csv)", "municipio", "6 × ((VF − LI) × T + CF) / VF × 10 000 con VF = 1 000 000 y el tramo de la tabla del municipio; ver tax_anio"),
    Columna("tax_anio", "Año fiscal de la tabla de predial", "", "predial_tablas.csv", "municipio", "directo"),
    Columna("ptratio", "Alumnos por docente en educación básica pública del municipio", "PTRATIO", "SEP, DGPPyEE, Principales cifras (formato 911), vía scripts/vivienda/sep_cifras.py", "municipio", "alumnos / docentes, escolarizada, preescolar a secundaria, control público; ver ptratio_ciclo"),
    Columna("ptratio_todas", "Alumnos por docente en educación básica, públicas y privadas", "PTRATIO (variante)", "SEP, DGPPyEE, Principales cifras", "municipio", "alumnos / docentes, control todos"),
    Columna("ptratio_ciclo", "Ciclo escolar de ptratio", "", "SEP", "municipio", "el sitio solo abre por municipio el ciclo vigente"),
    Columna("pct_sin_secundaria", "% de 15 años o más sin secundaria completa", "LSTAT (componente)", "Censo 2020, P15YM_SE, P15PRI_IN, P15PRI_CO, P15SEC_IN, P_15YMAS", "AGEB", "(P15YM_SE + P15PRI_IN + P15PRI_CO + P15SEC_IN) / P_15YMAS × 100"),
    Columna("pct_sin_servicios_salud", "% de población sin afiliación a servicios de salud", "LSTAT (componente)", "Censo 2020, PSINDER", "AGEB", "PSINDER / POBTOT × 100"),
    Columna("pct_piso_tierra", "% de viviendas con piso de tierra", "LSTAT (componente)", "Censo 2020, VPH_PISOTI", "AGEB", "VPH_PISOTI / VIVPARH_CV × 100"),
    Columna("graproes", "Grado promedio de escolaridad", "LSTAT (componente)", "Censo 2020, GRAPROES", "AGEB", "directo"),
    Columna("pct_viv_deshabitadas", "% de viviendas particulares deshabitadas", "", "Censo 2020, VIVPAR_DES, TVIVPAR", "AGEB", "VIVPAR_DES / TVIVPAR × 100; extra, Boston no lo tiene"),
    Columna("pct_viv_auto", "% de viviendas con automóvil", "", "Censo 2020, VPH_AUTOM", "AGEB", "VPH_AUTOM / VIVPARH_CV × 100; extra"),
    Columna("pct_viv_internet", "% de viviendas con internet", "", "Censo 2020, VPH_INTER", "AGEB", "VPH_INTER / VIVPARH_CV × 100; extra"),
    # Entorno: Boston no las tiene (vivienda_entorno.py).
    Columna("pct_60ymas", "% de población de 60 años o más", "", "Censo 2020, P_60YMAS", "AGEB", "P_60YMAS / POBTOT × 100"),
    Columna("razon_dependencia", "Dependientes (0 a 14 y 65 o más) por cada 100 de 15 a 64", "", "Censo 2020, POB0_14, POB65_MAS, POB15_64", "AGEB", "(POB0_14 + POB65_MAS) / POB15_64 × 100"),
    Columna("pct_jefatura_femenina", "% de hogares con jefatura femenina", "", "Censo 2020, HOGJEF_F, TOTHOG", "AGEB", "HOGJEF_F / TOTHOG × 100"),
    Columna("pct_nacidos_otra_entidad", "% de población nacida en otro estado", "", "Censo 2020, PNACOE", "AGEB", "PNACOE / POBTOT × 100"),
    Columna("pct_con_discapacidad", "% de población con discapacidad", "", "Censo 2020, PCON_DISC", "AGEB", "PCON_DISC / POBTOT × 100"),
    Columna("pct_viv_uso_temporal", "% de viviendas de uso temporal", "", "Censo 2020, VIVPAR_UT, TVIVPAR", "AGEB", "VIVPAR_UT / TVIVPAR × 100"),
    Columna("pct_viv_agua_fuera", "% de viviendas con agua entubada solo fuera de la vivienda", "", "Censo 2020, VPH_AGUAFV", "AGEB", "VPH_AGUAFV / VIVPARH_CV × 100"),
    Columna("pct_viv_sin_drenaje", "% de viviendas sin drenaje", "", "Censo 2020, VPH_NODREN", "AGEB", "VPH_NODREN / VIVPARH_CV × 100"),
    Columna("negocios_1km", "Negocios de DENUE a 1 km o menos del punto de la AGEB", "", "DENUE", "radio de 1 km", "conteo en línea recta"),
    Columna("escuelas_1km", "Escuelas a 1 km o menos", "", "DENUE, sector educación de rubros/sectores.csv", "radio de 1 km", "conteo; públicas y privadas, todos los niveles"),
    Columna("salud_1km", "Unidades de salud a 1 km o menos", "", "DENUE, sector salud", "radio de 1 km", "conteo; incluye consultorios y farmacias"),
    Columna("supermercados_1km", "Supermercados a 1 km o menos", "", "DENUE, rubro supermercado", "radio de 1 km", "conteo"),
    Columna("restaurantes_cafes_1km", "Restaurantes y cafeterías a 1 km o menos", "", "DENUE, rubros restaurante y cafetería", "radio de 1 km", "conteo"),
    Columna("diversidad_giros_1km", "Diversidad de sectores de los negocios a 1 km", "", "DENUE", "radio de 1 km", "entropía de Shannon de los sectores, en nats; 0 si todos son de un sector"),
    Columna("transporte_km", "Distancia en línea recta a la estación de transporte masivo más cercana, km", "", "OSM, scripts/vivienda/transporte_masivo.py", "AGEB", "Mi Tren (líneas 1 a 4), Mi Macro Calzada, Periférico y Aeropuerto; ver transporte_red"),
    Columna("transporte_red", "Red de la estación más cercana", "", "OSM", "AGEB", "directo"),
    Columna("parques_ha_1km", "Hectáreas de parque urbano a 1 km o menos", "", "OSM, leisure=park|garden", "radio de 1 km", "área de la unión de polígonos dentro del círculo; depende de qué tan completo esté OSM"),
    Columna("reserva_km", "Distancia a la reserva natural más cercana, km (0 si está dentro)", "", "OSM, leisure=nature_reserve (La Primavera, Cerro Viejo, barrancas del Santiago…)", "AGEB", "desde el punto dentro de la AGEB al borde del polígono"),
    Columna("altitud_m", "Altitud media de la AGEB, m", "", "Copernicus DEM GLO-30", "AGEB (píxeles de 30 m)", "media de los píxeles dentro"),
    Columna("pendiente_grados", "Pendiente media del terreno, grados", "", "Copernicus DEM GLO-30", "AGEB (píxeles de 30 m)", "gradiente del DEM con el tamaño del píxel en metros a esa latitud"),
    Columna("altura_edificios_m", "Altura media de los edificios, m", "", "JRC GHSL GHS-BUILT-H ANBH 2018, 100 m, CC BY 4.0", "AGEB (píxeles de 100 m)", "media de las celdas con edificios (las de 0 no cuentan)"),
    Columna("ndvi", "NDVI medio de la AGEB (verde urbano)", "", "Sentinel-2 L2A, mediana de abril de 2020, scripts/ambiental/imagenes.py", "AGEB (píxeles de 10 m)", "media de los píxeles dentro; de -1 a 1, más verde más alto"),
    Columna("lst_c", "Temperatura de superficie media de secas, °C", "", "Landsat 8 y 9 C2 L2, mediana de marzo a mayo de 2020, scripts/ambiental/imagenes.py", "AGEB (píxeles de 30 m)", "media de los píxeles dentro; temperatura del suelo y techos, no del aire"),
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


TABLAS_PREDIAL = Path(__file__).parent / "predial_tablas.csv"
# Boston usa una tasa por municipio. Aquí el predial es progresivo, así que la
# tasa depende del valor: se fija una propiedad de referencia.
VALOR_FISCAL_REFERENCIA = 1_000_000


def tablas_predial(ruta: Path = TABLAS_PREDIAL) -> dict[str, dict]:
    """{clave de municipio: {"anio", "tramos": [(límite inferior, cuota fija, tasa)]}}.
    Una tabla `millar` es un solo tramo desde 0. Fuente y notas en el CSV."""
    tablas: dict[str, dict] = {}
    with open(ruta, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            t = tablas.setdefault(fila["municipio"], {"anio": int(fila["anio"]), "tramos": []})
            t["tramos"].append((float(fila["limite_inferior"]), float(fila["cuota_fija"]), float(fila["tasa"])))
    for t in tablas.values():
        t["tramos"].sort()
    return tablas


def predial_anual(tramos: list[tuple[float, float, float]], valor_fiscal: float) -> float:
    """((VF − LI) × T + CF) por bimestre, seis bimestres."""
    li, cf, tasa = max((t for t in tramos if t[0] <= valor_fiscal), key=lambda t: t[0])
    return 6 * ((valor_fiscal - li) * tasa + cf)


def tax_por_municipio(cve_ent: str, tablas: dict[str, dict]) -> dict[str, tuple[float, int]]:
    """{cve_mun: (predial anual por $10,000, año)} para los municipios del estado."""
    v = VALOR_FISCAL_REFERENCIA
    return {clave[2:]: (round(predial_anual(t["tramos"], v) / v * 10_000, 2), t["anio"])
            for clave, t in tablas.items() if clave.startswith(cve_ent)}


def asignar_no2(filas: list[dict], ruta: Path) -> None:
    """NOX: banda 1 (media) y 2 (observaciones) del GeoTIFF de no2_s5p.py en el punto de cada AGEB."""
    import rasterio

    with rasterio.open(ruta) as r:
        for f, (media, obs) in zip(filas, r.sample([(f["lon"], f["lat"]) for f in filas], indexes=[1, 2])):
            dentro = obs > 0 and not np.isnan(media)
            f["nox"] = round(float(media), 2) if dentro else None
            f["nox_obs"] = int(obs) if dentro else None


def leer_ptratio(ruta: Path, cve_ent: str) -> dict[str, dict]:
    """{cve_mun: {ptratio, ptratio_todas, ptratio_ciclo}} desde el CSV de sep_cifras.py."""
    por_mun: dict[str, dict] = {}
    with open(ruta, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            if not fila["municipio"].startswith(cve_ent):
                continue
            alumnos, docentes = float(fila["alumnos"]), float(fila["docentes"])
            razon = round(alumnos / docentes, 2) if docentes else None
            d = por_mun.setdefault(fila["municipio"][2:], {"ptratio": None, "ptratio_todas": None,
                                                           "ptratio_ciclo": fila["ciclo"]})
            d["ptratio" if fila["control"] == "publico" else "ptratio_todas"] = razon
    return por_mun


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


def asignar_suelo_mismo_anio(filas: list[dict], valores: list[dict], cve_ent: str, anio: int) -> None:
    """`suelo_<año>_m2`: mediana de todas las etiquetas (zona y tramo juntas) de las tablas
    de un mismo año fiscal, para comparar municipios sin mezclar años. Las tablas
    escaneadas no distinguen zona de tramo, así que aquí tampoco."""
    from shapely import STRtree
    from shapely.geometry import Point

    arbol = STRtree([wkb.loads(f["_geom"]) for f in filas])
    por_ageb: dict[int, list[float]] = {}
    municipios = {v["municipio"] for v in valores if v["anio"] == anio}
    for v in valores:
        if v["anio"] == anio:
            for i in arbol.query(Point(v["lon"], v["lat"]), predicate="intersects"):
                if v["municipio"] == cve_ent + filas[int(i)]["cve_mun"]:  # solo en su municipio
                    por_ageb.setdefault(int(i), []).append(v["valor"])
    for i, f in enumerate(filas):
        vals = por_ageb.get(i, [])
        con_tabla = cve_ent + f["cve_mun"] in municipios
        f[f"suelo_{anio}_m2"] = float(np.median(vals)) if len(vals) >= MIN_VALORES_CALLE else None
        f[f"suelo_{anio}_n"] = len(vals) if con_tabla else None


def asignar_suelo(filas: list[dict], valores: list[dict], cve_ent: str) -> None:
    """Valor catastral de suelo: mediana por AGEB, por clase. Nunca rellena con vecinas: lo que falta se dice."""
    from shapely import STRtree
    from shapely.geometry import Point

    geoms = [wkb.loads(f["_geom"]) for f in filas]
    arbol = STRtree(geoms)
    por_ageb: dict[int, dict[str, list[float]]] = {}
    for v in valores:
        for i in arbol.query(Point(v["lon"], v["lat"]), predicate="intersects"):
            # Una tabla solo vale en su municipio: la etiqueta de Guadalajara que cae del
            # otro lado del límite no es valor de Tlaquepaque.
            if v["municipio"] != cve_ent + filas[int(i)]["cve_mun"]:
                continue
            por_ageb.setdefault(int(i), {"zona": [], "calle": []}).setdefault(v["clase"] or "calle", []).append(v["valor"])
    anio_por_mun = {v["municipio"]: v["anio"] for v in valores}
    for i, fila in enumerate(filas):
        anio = anio_por_mun.get(cve_ent + fila["cve_mun"])
        grupos = por_ageb.get(i, {"zona": [], "calle": []})
        zona, calle = grupos.get("zona", []), grupos.get("calle", [])
        fila["suelo_anio"] = anio
        fila["suelo_n"], fila["suelo_calle_n"] = len(zona), len(calle)
        fila["suelo_m2"] = float(np.median(zona)) if zona else None
        fila["suelo_calle_m2"] = float(np.median(calle)) if len(calle) >= MIN_VALORES_CALLE else None
        if anio is None:
            fila["suelo_metodo"] = "sin tabla de valores ubicada para este municipio"
            fila["suelo_n"] = fila["suelo_calle_n"] = None
        elif zona:
            fila["suelo_metodo"] = f"mediana de {len(zona)} valores de zona, tabla {anio}"
        else:
            fila["suelo_metodo"] = f"sin valor de zona dentro de la AGEB (tabla {anio}; {len(calle)} de tramo)"


async def construir(pool: AsyncConnectionPool, cve_ent: str, municipios: list[str], anio_crimen: int = 2020,
                    valores: list[dict] | None = None, agua: Path | None = None, vias: Path | None = None,
                    valores_2026: list[dict] | None = None,
                    ghsl: dict[int, Path | None] | None = None,
                    sep: Path | None = None, no2: Path | None = None,
                    entorno: dict[str, Path | None] | None = None,
                    oferta: tuple[list, dict, str] | None = None) -> tuple[list[dict], list[dict]]:
    """Filas del dataset y los centros de empleo usados para DIS."""
    agebs = await _agebs(pool, cve_ent, municipios)
    negocios = await _negocios(pool, cve_ent, municipios)
    crimen = await _crimen(pool, cve_ent, municipios, anio_crimen)
    tax = tax_por_municipio(cve_ent, tablas_predial())
    ptratio = leer_ptratio(sep, cve_ent) if sep else {}

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
            "chas": None, "nox": None, "nox_obs": None, "age": None, "age_1975": None, "rad_km": None,
            "rm": cuartos_promedio(d),
            "pro_ocup_c": _num(d, "PRO_OCUP_C"),
            "pct_viv_3ymas_cuartos": _porcentaje(_num(d, "VPH_3YMASC"), con_carac),
            "pct_viv_2ymas_dorm": _porcentaje(_num(d, "VPH_2YMASD"), con_carac),
            "dis_km": distancia_ponderada_km(a["lon"], a["lat"], centros),
            "tax": tax.get(a["cve_mun"], (None, None))[0], "tax_anio": tax.get(a["cve_mun"], (None, None))[1],
            **ptratio.get(a["cve_mun"], {"ptratio": None, "ptratio_todas": None, "ptratio_ciclo": None}),
            "pct_sin_secundaria": sin_secundaria(d),
            "pct_sin_servicios_salud": _porcentaje(_num(d, "PSINDER"), _num(d, "POBTOT")),
            "pct_piso_tierra": _porcentaje(_num(d, "VPH_PISOTI"), con_carac),
            "graproes": _num(d, "GRAPROES"),
            "pct_viv_deshabitadas": _porcentaje(_num(d, "VIVPAR_DES"), _num(d, "TVIVPAR")),
            "pct_viv_auto": _porcentaje(_num(d, "VPH_AUTOM"), con_carac),
            "pct_viv_internet": _porcentaje(_num(d, "VPH_INTER"), con_carac),
            **vivienda_entorno.censo_extra(d),
            "_geom": a["geom"],
        })
    asignar_suelo(filas, valores or [], cve_ent)
    asignar_suelo_mismo_anio(filas, valores_2026 or [], cve_ent, 2026)
    if oferta and cve_ent == "14":
        iieg_oferta.asignar(filas, *oferta)
    asignar_osm(filas, agua, vias)
    if ghsl:
        asignar_ghsl(filas, ghsl)
    if no2:
        asignar_no2(filas, no2)
    vivienda_entorno.asignar_amenidades(filas, negocios)
    e = entorno or {}
    if e.get("transporte"):
        vivienda_entorno.asignar_transporte(filas, e["transporte"])
    if e.get("parques"):
        vivienda_entorno.asignar_parques(filas, e["parques"])
    if e.get("dem"):
        vivienda_entorno.asignar_relieve(filas, e["dem"])
    if e.get("altura"):
        vivienda_entorno.media_zonal(filas, e["altura"], "altura_edificios_m", solo_positivos=True, decimales=2)
    if e.get("ndvi"):
        vivienda_entorno.media_zonal(filas, e["ndvi"], "ndvi", escala=1 / 10_000, decimales=4)
    if e.get("lst"):
        vivienda_entorno.media_zonal(filas, e["lst"], "lst_c", escala=1 / 100, decimales=2)
    return filas, centros


def escribir(filas: list[dict], centros: list[dict], salida: Path, notas: dict,
             municipal: list[dict] | None = None) -> None:
    """CSV para el modelo, GeoJSON para el SIG, diccionario, centros de empleo y,
    si hay anuncios, el resumen municipal del IIEG."""
    salida.mkdir(parents=True, exist_ok=True)
    if municipal:
        with open(salida / "mercado_municipal.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(municipal[0]))
            w.writeheader()
            w.writerows(municipal)
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
        "precios de oferta, IIEG con información de sitios web de venta de propiedades (medv);\n"
        "valores catastrales, tablas de valores de cada municipio (ver suelo_anio); predial, leyes\n"
        "de ingresos municipales 2026; alumnos y docentes, SEP DGPPyEE (formato 911); NO2,\n"
        "Copernicus Sentinel-5P procesado por Mapo (contiene datos modificados de Copernicus).\n",
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
