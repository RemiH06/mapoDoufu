"""Consultas a la base que comparten el modo técnico (`server.py`) y el
buscador (`buscador.py`). Una sola versión de cada una: el buscador es una
capa sobre el modo técnico, no una copia (docs/producto/buscador.md).

Los municipios van siempre como lista (`cve_muns`): el modo técnico pasa
uno, el buscador uno o varios. `None` en `cve_muns` es el estado entero.
"""

from __future__ import annotations

import json

from psycopg_pool import AsyncConnectionPool

from mapo_core.voronoi import PuntoVoronoi

# Simplificacion aplicada al leer poligonos (no al guardar): mismo
# valor y misma razon que ya usaba Gaiarda, sin esto Leaflet se pone
# lento dibujando miles de vertices de mas. Con esa tolerancia (unos
# 50 m) sobran decimales: ST_AsGeoJSON(..., 5) deja 1 m de precision y
# casi parte a la mitad lo que viaja hasta el navegador.
TOLERANCIA_SIMPLIFICACION = 0.0005

# Arriba de esto el Voronoi tarda segundos en calcularse y el navegador
# no lo mueve con fluidez (Guadalajara sin filtro son 97 mil negocios).
MAX_NEGOCIOS_VORONOI = 5000

# Unicos indicadores permitidos como columna dinamica en el
# choropleth. Whitelist explicita, no se interpola el nombre de
# columna directo del query param (puerta a inyeccion SQL).
INDICADORES_CHOROPLETH = {
    "pobtot", "pobfem", "pobmas", "p_0a2", "p_3a5", "p_6a11", "p_12a14",
    "p_15a17", "p_18a24", "p_60ymas", "graproes", "pea", "pea_f", "pea_m",
    "pe_inac", "pocupada", "pdesocup", "pder_ss", "tothog", "vivtot",
    "tvivhab", "prom_ocup", "vph_inter", "vph_pc", "vph_autom", "vph_cel", "vph_snbien",
}


def feature(cvegeo: str, nombre: str, geojson_geom: str | None, props_extra: dict | None = None) -> dict:
    propiedades = {"cvegeo": cvegeo, "nomgeo": nombre, **(props_extra or {})}
    return {
        "type": "Feature",
        "properties": propiedades,
        "geometry": json.loads(geojson_geom) if geojson_geom else None,
    }


async def coropleta(
    pool: AsyncConnectionPool, indicador: str, cve_ent: str, cve_muns: list[str] | None
) -> list[dict]:
    """AGEBs con el valor de `indicador` del censo. Si falta el censo de un
    AGEB, trae `valor_choropleth: null`, nunca un cero inventado."""
    if indicador not in INDICADORES_CHOROPLETH:
        raise ValueError(f"indicador invalido: {indicador}")

    async with pool.connection() as conn:
        cursor = await conn.execute(
            f"""SELECT a.cvegeo, ST_AsGeoJSON(ST_Simplify(a.geom, %(tolerancia)s), 5), c.{indicador}
                FROM agebs a
                LEFT JOIN fuente_censo_poblacion c
                  ON c.cvegeo = a.cvegeo AND c.nivel = 'ageb'
                WHERE a.cve_ent = %(cve_ent)s
                  AND (%(cve_muns)s::text[] IS NULL OR a.cve_mun = ANY(%(cve_muns)s))
                ORDER BY a.cvegeo""",
            {"cve_ent": cve_ent, "cve_muns": cve_muns, "tolerancia": TOLERANCIA_SIMPLIFICACION},
        )
        filas = await cursor.fetchall()

    return [
        feature(cvegeo, cvegeo, geom, {"indicador": indicador, "valor_choropleth": valor})
        for cvegeo, geom, valor in filas
        if geom is not None
    ]


async def limite_municipios(pool: AsyncConnectionPool, cve_ent: str, cve_muns: list[str]) -> dict | None:
    """Polígono de la unión de los municipios (uno solo si la lista es de
    uno). None si alguno no está en la base."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """SELECT count(*), ST_AsGeoJSON(ST_Simplify(ST_Union(geom), %(tolerancia)s), 5)
               FROM municipios WHERE cve_ent = %(cve_ent)s AND cve_mun = ANY(%(cve_muns)s)""",
            {"cve_ent": cve_ent, "cve_muns": cve_muns, "tolerancia": TOLERANCIA_SIMPLIFICACION},
        )
        encontrados, geom = await cursor.fetchone()
    if encontrados != len(set(cve_muns)) or geom is None:
        return None
    return json.loads(geom)


async def negocios(
    pool: AsyncConnectionPool,
    cve_ent: str,
    cve_muns: list[str],
    *,
    patron: str | None = None,
    clases: list[str] | None = None,
) -> list[PuntoVoronoi]:
    """Negocios de DENUE con coordenadas en los municipios. El modo técnico
    filtra por texto (`patron`, contiene); el buscador, por la lista exacta
    de clases de un rubro (`clases`). Sin ninguno de los dos, todos."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """SELECT id, nombre, lat, lon FROM fuente_denue_negocios
               WHERE cve_ent = %(cve_ent)s AND cve_mun = ANY(%(cve_muns)s)
                 AND lat IS NOT NULL AND lon IS NOT NULL
                 AND (%(patron)s::text IS NULL OR clase_actividad ILIKE %(patron)s)
                 AND (%(clases)s::text[] IS NULL OR clase_actividad = ANY(%(clases)s))""",
            {
                "cve_ent": cve_ent,
                "cve_muns": cve_muns,
                "patron": f"%{patron}%" if patron else None,
                "clases": clases,
            },
        )
        filas = await cursor.fetchall()

    return [PuntoVoronoi(id=id_, nombre=nombre, lat=lat, lon=lon) for id_, nombre, lat, lon in filas]


def aviso_voronoi(num_negocios: int) -> str | None:
    """Por qué no se puede dibujar el Voronoi con tantos negocios, o None si sí."""
    if num_negocios < 3:
        return (
            f"Solo hay {num_negocios} negocio(s) con esos filtros; se necesitan al menos 3 "
            "para un diagrama de Voronoi."
        )
    if num_negocios > MAX_NEGOCIOS_VORONOI:
        return (
            f"Hay {num_negocios} negocios con esos filtros; el máximo para dibujar el Voronoi es "
            f"{MAX_NEGOCIOS_VORONOI}. Filtra por giro."
        )
    return None


async def conteo_por_municipio(
    pool: AsyncConnectionPool, cve_ent: str, cve_muns: list[str], clases: list[str]
) -> dict[str, int]:
    """Negocios de esas clases por municipio, con o sin coordenadas (DENUE
    cuenta el negocio aunque no traiga ubicación)."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """SELECT cve_mun, count(*) FROM fuente_denue_negocios
               WHERE cve_ent = %(cve_ent)s AND cve_mun = ANY(%(cve_muns)s)
                 AND clase_actividad = ANY(%(clases)s)
               GROUP BY cve_mun""",
            {"cve_ent": cve_ent, "cve_muns": cve_muns, "clases": clases},
        )
        conteo = dict(await cursor.fetchall())
    return {cve_mun: conteo.get(cve_mun, 0) for cve_mun in cve_muns}


async def negocios_en_poligono(
    pool: AsyncConnectionPool, poligono: dict, clases: list[str]
) -> list[PuntoVoronoi]:
    """Negocios de esas clases dentro de un polígono GeoJSON (una isócrona).
    La caja del polígono filtra primero por lat/lon; ST_Contains decide."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """WITH area AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%(poligono)s), 4326) AS g)
               SELECT n.id, n.nombre, n.lat, n.lon FROM fuente_denue_negocios n, area
               WHERE n.clase_actividad = ANY(%(clases)s)
                 AND n.lat BETWEEN ST_YMin(area.g) AND ST_YMax(area.g)
                 AND n.lon BETWEEN ST_XMin(area.g) AND ST_XMax(area.g)
                 AND ST_Contains(area.g, ST_SetSRID(ST_MakePoint(n.lon, n.lat), 4326))""",
            {"poligono": json.dumps(poligono), "clases": clases},
        )
        filas = await cursor.fetchall()
    return [PuntoVoronoi(id=id_, nombre=nombre, lat=lat, lon=lon) for id_, nombre, lat, lon in filas]


async def censo_municipios(
    pool: AsyncConnectionPool, cve_ent: str, cve_muns: list[str], columna: str
) -> dict[str, tuple[str, int | float | None]]:
    """Nombre y valor de una columna del censo a nivel municipio (no la suma
    de sus AGEB: esa deja fuera la población rural). None si falta."""
    if columna not in INDICADORES_CHOROPLETH:
        raise ValueError(f"columna invalida: {columna}")

    async with pool.connection() as conn:
        cursor = await conn.execute(
            f"""SELECT m.cve_mun, m.nombre, c.{columna}
                FROM municipios m
                LEFT JOIN fuente_censo_poblacion c
                  ON c.cve_ent = m.cve_ent AND c.cve_mun = m.cve_mun AND c.nivel = 'municipio'
                WHERE m.cve_ent = %(cve_ent)s AND m.cve_mun = ANY(%(cve_muns)s)""",
            {"cve_ent": cve_ent, "cve_muns": cve_muns},
        )
        filas = await cursor.fetchall()
    return {cve_mun: (nombre, valor) for cve_mun, nombre, valor in filas}


async def puntos_de_agebs(
    pool: AsyncConnectionPool, cve_ent: str, cve_muns: list[str]
) -> list[tuple[str, str, str, float, float]]:
    """(cvegeo, cve_ageb, municipio, lat, lon) de cada AGEB. El punto es
    `ST_PointOnSurface`: cae siempre dentro, un centroide puede caer fuera de
    un AGEB con forma de herradura. Con 1,840 AGEB tarda más de un segundo."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """SELECT a.cvegeo, a.cve_ageb, m.nombre, ST_Y(p.punto), ST_X(p.punto)
               FROM agebs a
               JOIN municipios m ON m.cve_ent = a.cve_ent AND m.cve_mun = a.cve_mun
               CROSS JOIN LATERAL (SELECT ST_PointOnSurface(a.geom) AS punto) p
               WHERE a.cve_ent = %(cve_ent)s AND a.cve_mun = ANY(%(cve_muns)s)
                 AND a.geom IS NOT NULL
               ORDER BY a.cvegeo""",
            {"cve_ent": cve_ent, "cve_muns": cve_muns},
        )
        return await cursor.fetchall()


async def valores_por_ageb(
    pool: AsyncConnectionPool, cve_ent: str, cve_muns: list[str], indicador: str
) -> dict[str, int | float | None]:
    """{cvegeo: valor} del censo. Un AGEB sin censo no viene: es `None` al leer."""
    if indicador not in INDICADORES_CHOROPLETH:
        raise ValueError(f"indicador invalido: {indicador}")

    async with pool.connection() as conn:
        cursor = await conn.execute(
            f"""SELECT cvegeo, {indicador} FROM fuente_censo_poblacion
                WHERE nivel = 'ageb' AND cve_ent = %(cve_ent)s AND cve_mun = ANY(%(cve_muns)s)""",
            {"cve_ent": cve_ent, "cve_muns": cve_muns},
        )
        return dict(await cursor.fetchall())


async def ubicaciones_de_clases(
    pool: AsyncConnectionPool, cve_ent: str, clases: list[str]
) -> list[tuple[float, float]]:
    """(lat, lon) de los negocios de esas clases en todo el estado, no solo en
    los municipios de la pregunta: la competencia cruza la frontera municipal."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """SELECT lat, lon FROM fuente_denue_negocios
               WHERE cve_ent = %(cve_ent)s AND clase_actividad = ANY(%(clases)s)
                 AND lat IS NOT NULL AND lon IS NOT NULL""",
            {"cve_ent": cve_ent, "clases": clases},
        )
        return await cursor.fetchall()


async def municipios_de(pool: AsyncConnectionPool, cve_ent: str) -> list[tuple[str, str]]:
    """(cve_mun, nombre) de los municipios de un estado."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            "SELECT cve_mun, nombre FROM municipios WHERE cve_ent = %(cve_ent)s ORDER BY cve_mun",
            {"cve_ent": cve_ent},
        )
        return await cursor.fetchall()


async def laboral_de(pool: AsyncConnectionPool, cve_ent: str) -> dict | None:
    """Tasa de desocupacion del trimestre mas reciente disponible para
    esta entidad. La ENOE no tiene representatividad a nivel municipio
    (diseno muestral por entidad), asi que esto es del estado completo,
    nunca del municipio especifico. None si no hay ningun trimestre
    cargado todavia."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """SELECT anio, trimestre, tasa_desocupacion, pea_ponderada
               FROM fuente_enoe_tasa_desocupacion WHERE cve_ent = %(cve_ent)s
               ORDER BY anio DESC, trimestre DESC LIMIT 1""",
            {"cve_ent": cve_ent},
        )
        fila = await cursor.fetchone()

    if fila is None:
        return None
    anio, trimestre, tasa_desocupacion, pea_ponderada = fila
    return {
        "anio": anio,
        "trimestre": trimestre,
        "tasa_desocupacion": round(tasa_desocupacion, 2),
        "pea_ponderada": round(pea_ponderada),
    }
