"""Zona común (sesión 29b): una sola forma de decir "dónde" en todas las vistas.

Una zona viaja como texto corto, la clave de zona, en la URL, en la cuenta ("zona en
la que opero") y de Mapo a mapo_core:

    ent:14                     un estado
    mun:14039,14120            uno o varios municipios, de uno o varios estados
    zm:14.1.01                 una metrópoli de Metrópolis de México 2020
    cp:45615                   un código postal, con el polígono de SEPOMEX
    col:14098_0135             una colonia de CONAPO 2020
    pol:-103.35,20.67;...      un polígono dibujado (lon,lat; de 3 a 200 vértices)
    cir:-103.35,20.67,2500     un círculo, punto y radio en metros

`validar` la lee sin tocar la base, `geom_sql` da el SQL de su geometría con
parámetros (nada del navegador se interpola), `resolver` la lleva a nombre, polígono,
área y municipios que toca, y `buscar` sugiere zonas para el autocompletado. Ver
docs/producto/zona.md y docs/fuentes/zonas.md.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import unicodedata
import zipfile
from pathlib import Path

import shapefile
from psycopg.rows import dict_row
from shapely.geometry import Polygon

MAX_MUNICIPIOS = 100
MAX_VERTICES = 200
MAX_KM2_DIBUJO = 10_000
# Lo más que calculan /riesgos y /accesibilidad: cabe el municipio más grande cargado
# (Mezquitic, 3,364 km²) y la ZMG (2,487), no un estado, que tardaría minutos.
MAX_KM2_CONSULTA = 5_000
RADIO_MIN_M, RADIO_MAX_M = 100, 25_000
# México en grados, con margen: lo de afuera no es una zona de Mapo.
LON_MIN, LON_MAX, LAT_MIN, LAT_MAX = -119.0, -85.0, 14.0, 33.5
TOLERANCIA = 0.005  # la mayor, la de un estado
# Un municipio cuenta como "tocado" si tiene al menos esta parte del área de la zona:
# los polígonos de CONAPO e INEGI no coinciden al metro. En Jalisco, 81 colonias
# tienen de 1 a 5 % en un municipio que no es el suyo (López Cotilla, 1.6 % en
# Tlajomulco): con 1 % el vecino se colaba en la sequía y las defunciones.
PARTE_MINIMA = 0.05

TIPOS_METROPOLI = {"1": "Zona metropolitana", "2": "Metrópoli municipal", "3": "Zona conurbada"}
METROPOLIS_CSV = Path(__file__).with_name("metropolis_2020.csv")
COLONIAS_URL = "https://conapo.segob.gob.mx/work/models/CONAPO/Datos_Abiertos/Colonia/imc2020_shp.zip"

FUENTE_MARCO = "INEGI, Marco Geoestadístico"
FUENTE_METROPOLIS = "SEDATU, CONAPO e INEGI, Metrópolis de México 2020 (edición 2024)"
FUENTE_COLONIAS = "CONAPO, Índice de marginación urbana 2020, cartografía de colonias"
FUENTE_CP = "Correos de México (SEPOMEX), códigos postales por entidad federativa"
SIN_CP = ("Los códigos postales llegan cuando se carguen los polígonos oficiales de SEPOMEX; "
          "mientras, busca la colonia o el municipio.")


class ZonaInvalida(ValueError):
    pass


def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos, igual que `_NORM_SQL` del lado de la base."""
    sin = unicodedata.normalize("NFD", texto)
    return "".join(c for c in sin if unicodedata.category(c) != "Mn").lower().strip()


def _norm_sql(columna: str) -> str:
    return f"translate(lower({columna}), 'áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunaeiouun')"


def _numero(texto: str) -> float:
    try:
        x = float(texto)
    except ValueError:
        raise ZonaInvalida(f"{texto!r} no es un número") from None
    if not math.isfinite(x):
        raise ZonaInvalida("número no finito")
    return x


def _punto(lon: float, lat: float) -> tuple[float, float]:
    if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
        raise ZonaInvalida("el punto no está en México")
    return round(lon, 5), round(lat, 5)


def _km2_aprox(pol: Polygon) -> float:
    # Grados cuadrados a km² con el coseno de la latitud media: basta para un tope.
    lat = pol.centroid.y
    return pol.area * 111.32 ** 2 * math.cos(math.radians(lat))


def validar(clave) -> dict:
    """Clave de zona -> dict con `tipo` y sus datos. ZonaInvalida si no es una."""
    if not isinstance(clave, str) or ":" not in clave or len(clave) > 6_000:
        raise ZonaInvalida("la zona es un texto como mun:14039 o zm:14.1.01")
    tipo, _, resto = clave.strip().partition(":")
    if tipo == "ent":
        if not re.fullmatch(r"\d{2}", resto) or not 1 <= int(resto) <= 32:
            raise ZonaInvalida("ent: lleva la clave de 2 dígitos del estado")
        return {"tipo": "estado", "cve_ent": resto}
    if tipo == "mun":
        claves = list(dict.fromkeys(resto.split(",")))
        if not claves or not all(re.fullmatch(r"\d{5}", c) for c in claves):
            raise ZonaInvalida("mun: lleva claves de municipio de 5 dígitos separadas por coma")
        if len(claves) > MAX_MUNICIPIOS:
            raise ZonaInvalida(f"a lo más {MAX_MUNICIPIOS} municipios")
        return {"tipo": "municipios", "cvegeos": claves}
    if tipo == "zm":
        if not re.fullmatch(r"\d{2}\.[123]\.\d{2}", resto):
            raise ZonaInvalida("zm: lleva la clave de Metrópolis de México 2020, como 14.1.01")
        return {"tipo": "metropoli", "clave": resto}
    if tipo == "cp":
        if not re.fullmatch(r"\d{5}", resto):
            raise ZonaInvalida("cp: lleva un código postal de 5 dígitos")
        return {"tipo": "cp", "cp": resto}
    if tipo == "col":
        if not re.fullmatch(r"\d{5}_\d{1,6}", resto):
            raise ZonaInvalida("col: lleva la clave de colonia de CONAPO, como 14098_0135")
        return {"tipo": "colonia", "cve_col": resto}
    if tipo == "pol":
        pares = [p for p in resto.split(";") if p]
        if not 3 <= len(pares) <= MAX_VERTICES:
            raise ZonaInvalida(f"el polígono lleva de 3 a {MAX_VERTICES} vértices")
        vertices = []
        for p in pares:
            partes = p.split(",")
            if len(partes) != 2:
                raise ZonaInvalida("cada vértice es lon,lat")
            vertices.append(_punto(_numero(partes[0]), _numero(partes[1])))
        if vertices[0] == vertices[-1]:
            vertices.pop()
        pol = Polygon(vertices) if len(set(vertices)) >= 3 else None
        if pol is None or not pol.is_valid or pol.area == 0:
            raise ZonaInvalida("el polígono se cruza consigo mismo o no encierra área")
        if _km2_aprox(pol) > MAX_KM2_DIBUJO:
            raise ZonaInvalida(f"un polígono dibujado mide a lo más {MAX_KM2_DIBUJO:,} km²")
        return {"tipo": "poligono", "vertices": vertices}
    if tipo == "cir":
        partes = resto.split(",")
        if len(partes) != 3:
            raise ZonaInvalida("cir: lleva lon,lat,radio")
        lon, lat = _punto(_numero(partes[0]), _numero(partes[1]))
        radio = _numero(partes[2])
        if not RADIO_MIN_M <= radio <= RADIO_MAX_M:
            raise ZonaInvalida(f"el radio va de {RADIO_MIN_M} a {RADIO_MAX_M:,} m")
        return {"tipo": "circulo", "lon": lon, "lat": lat, "radio_m": round(radio)}
    raise ZonaInvalida(f"tipo de zona desconocido: {tipo!r}")


def clave(zona: dict) -> str:
    """La clave canónica de una zona validada (la inversa de `validar`)."""
    t = zona["tipo"]
    if t == "estado":
        return f"ent:{zona['cve_ent']}"
    if t == "municipios":
        return "mun:" + ",".join(zona["cvegeos"])
    if t == "metropoli":
        return f"zm:{zona['clave']}"
    if t == "cp":
        return f"cp:{zona['cp']}"
    if t == "colonia":
        return f"col:{zona['cve_col']}"
    if t == "poligono":
        return "pol:" + ";".join(f"{lon},{lat}" for lon, lat in zona["vertices"])
    return f"cir:{zona['lon']},{zona['lat']},{zona['radio_m']}"


def demasiado_grande(km2: float) -> str | None:
    """Por qué una zona es muy grande para calcular, o None."""
    if km2 <= MAX_KM2_CONSULTA:
        return None
    return (f"la zona mide {km2:,.0f} km² y aquí se calcula hasta {MAX_KM2_CONSULTA:,} km²: elige menos "
            "municipios, una metrópoli o dibuja la parte que te interesa")


async def area_km2(conn, zona: dict) -> float | None:
    sql, params = geom_sql(zona)
    cur = await conn.execute(f"SELECT (ST_Area(geom::geography) / 1e6)::float FROM ({sql}) q", params)
    fila = await cur.fetchone()
    return fila[0] if fila else None


def _wkt(vertices: list[tuple[float, float]]) -> str:
    anillo = vertices + [vertices[0]]
    return "POLYGON((" + ",".join(f"{lon} {lat}" for lon, lat in anillo) + "))"


def geom_sql(zona: dict) -> tuple[str, dict]:
    """SQL de un renglón con la columna `geom` (MultiPolygon 4326) y sus parámetros."""
    t = zona["tipo"]
    if t == "estado":
        return "SELECT geom FROM entidades WHERE cve_ent = %(zona_ent)s", {"zona_ent": zona["cve_ent"]}
    if t == "municipios":
        return ("SELECT ST_Multi(ST_Union(geom)) AS geom FROM municipios WHERE cvegeo = ANY(%(zona_muns)s)",
                {"zona_muns": zona["cvegeos"]})
    if t == "metropoli":
        return ("SELECT ST_Multi(ST_Union(m.geom)) AS geom FROM municipios m"
                " JOIN metropolis z ON m.cvegeo = ANY(z.cvegeos) WHERE z.clave = %(zona_zm)s",
                {"zona_zm": zona["clave"]})
    if t == "cp":
        return "SELECT geom FROM codigos_postales WHERE cp = %(zona_cp)s", {"zona_cp": zona["cp"]}
    if t == "colonia":
        return "SELECT geom FROM colonias WHERE cve_col = %(zona_col)s", {"zona_col": zona["cve_col"]}
    if t == "poligono":
        return ("SELECT ST_Multi(ST_GeomFromText(%(zona_wkt)s, 4326)) AS geom",
                {"zona_wkt": _wkt(zona["vertices"])})
    return ("SELECT ST_Multi(ST_Buffer(ST_SetSRID(ST_MakePoint(%(zona_lon)s, %(zona_lat)s), 4326)::geography,"
            " %(zona_radio)s)::geometry) AS geom",
            {"zona_lon": zona["lon"], "zona_lat": zona["lat"], "zona_radio": zona["radio_m"]})


def partida_sql(zona: dict) -> tuple[str, dict]:
    """Dos CTE para un WITH: `z` con la geometría de la zona y `zs` con ella partida en
    pedazos chicos. Punto en polígono contra un municipio entero tardaba más de un
    segundo con decenas de miles de lugares; contra los pedazos, milisegundos."""
    sql, params = geom_sql(zona)
    return (f"z AS MATERIALIZED ({sql}),"
            " zs AS MATERIALIZED (SELECT ST_Subdivide(geom, 128) AS g FROM z)"), params


def dentro(geom: str) -> str:
    """Condición SQL: `geom` toca la zona de `partida_sql`."""
    return f"EXISTS (SELECT 1 FROM zs WHERE zs.g && {geom} AND ST_Intersects(zs.g, {geom}))"


def filtro_agebs(zona: dict, alias: str = "a") -> tuple[str, str, dict]:
    """(CTE para un WITH o "", condición, parámetros) para las AGEB de la zona: las que
    tienen su punto de dentro en ella. Un estado, municipios o una metrópoli son
    municipios enteros, así que van por clave: por geometría, un estado tardaba 44 s."""
    t = zona["tipo"]
    if t == "estado":
        return "", f"{alias}.cve_ent = %(zona_ent)s", {"zona_ent": zona["cve_ent"]}
    if t == "municipios":
        # El estado primero, para que entre el índice (cve_ent, cve_mun).
        return ("", f"{alias}.cve_ent = ANY(%(zona_ents)s) AND {alias}.cve_ent || {alias}.cve_mun = ANY(%(zona_muns)s)",
                {"zona_ents": sorted({c[:2] for c in zona["cvegeos"]}), "zona_muns": zona["cvegeos"]})
    if t == "metropoli":
        return ("", f"{alias}.cve_ent || {alias}.cve_mun = ANY((SELECT cvegeos FROM metropolis WHERE clave = %(zona_zm)s)::text[])",
                {"zona_zm": zona["clave"]})
    cte, params = partida_sql(zona)
    return cte, f"{alias}.geom && (SELECT geom FROM z) AND {dentro(f'ST_PointOnSurface({alias}.geom)')}", params


def _lista(nombres: list[str], total: int, sustantivo: str) -> str:
    if total == 0:
        return ""
    if total <= 3:
        return nombres[0] if total == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]
    return f"{', '.join(nombres[:2])} y {total - 2} {sustantivo} más"


async def _municipios_tocados(cur, sql: str, params: dict) -> list[dict]:
    await cur.execute(
        f"""WITH z AS ({sql}), a AS (SELECT geom, ST_Area(geom) AS area FROM z)
            SELECT m.cvegeo, m.cve_ent, m.cve_mun, m.nombre, e.nombre AS estado
            FROM municipios m LEFT JOIN entidades e USING (cve_ent), a
            WHERE m.geom && a.geom AND ST_Intersects(m.geom, a.geom)
              AND ST_Area(ST_Intersection(m.geom, a.geom)) >= %(parte)s * a.area
            ORDER BY m.cvegeo""", {**params, "parte": PARTE_MINIMA})
    return await cur.fetchall()


async def limites(conn, cvegeos: list[str]) -> list[dict]:
    """Contornos simplificados de municipios (cvegeo, nombre y geometría), para dibujar
    sus límites dentro de una zona."""
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        "SELECT cvegeo, nombre, ST_AsGeoJSON(ST_SimplifyPreserveTopology(coalesce(geom_mapa, geom), 0.0005), 5) AS gj"
        " FROM municipios WHERE cvegeo = ANY(%(m)s) AND geom IS NOT NULL ORDER BY cvegeo", {"m": cvegeos})
    return [{"cvegeo": f["cvegeo"], "nombre": f["nombre"], "geometry": json.loads(f["gj"])} for f in await cur.fetchall()]


def limites_geojson(filas: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": f["geometry"], "properties": {"cvegeo": f["cvegeo"], "nombre": f["nombre"]}}
        for f in filas]}


async def resolver(conn, zona: dict) -> dict | None:
    """Nombre, polígono simplificado, área y municipios de una zona validada. None si
    no hay nada cargado con esa clave (un CP sin colonias, municipios sin cargar)."""
    sql, params = geom_sql(zona)
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(
        # Simplificar según el tamaño: una colonia pide metros, un estado no.
        f"""SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, GREATEST(LEAST(
                     sqrt((ST_XMax(geom) - ST_XMin(geom)) ^ 2 + (ST_YMax(geom) - ST_YMin(geom)) ^ 2) / 1500,
                     %(tol)s), 0.00002)), 5) AS gj,
                   (ST_Area(geom::geography) / 1e6)::float AS km2,
                   ST_XMin(geom) AS x0, ST_YMin(geom) AS y0, ST_XMax(geom) AS x1, ST_YMax(geom) AS y1
            FROM ({sql}) q WHERE geom IS NOT NULL""", {**params, "tol": TOLERANCIA})
    g = await cur.fetchone()
    if g is None:
        return None

    t = zona["tipo"]
    faltan: list[str] = []
    fuente, metodo, aviso = FUENTE_MARCO, None, None
    if t == "estado":
        await cur.execute(
            """SELECT m.cvegeo, m.cve_ent, m.cve_mun, m.nombre, e.nombre AS estado
               FROM municipios m LEFT JOIN entidades e USING (cve_ent) WHERE m.cve_ent = %(e)s ORDER BY m.cvegeo""",
            {"e": zona["cve_ent"]})
        municipios = await cur.fetchall()
        await cur.execute("SELECT nombre FROM entidades WHERE cve_ent = %(e)s", {"e": zona["cve_ent"]})
        nombre = (await cur.fetchone())["nombre"]
        detalle = f"{len(municipios)} municipios cargados" if municipios else "sin municipios cargados en Mapo"
    elif t in ("municipios", "metropoli"):
        pedidos = zona.get("cvegeos")
        metro = None
        if t == "metropoli":
            await cur.execute("SELECT nombre, tipo, cvegeos FROM metropolis WHERE clave = %(c)s",
                              {"c": zona["clave"]})
            metro = await cur.fetchone()
            pedidos = metro["cvegeos"]
            fuente = FUENTE_METROPOLIS
        await cur.execute(
            """SELECT m.cvegeo, m.cve_ent, m.cve_mun, m.nombre, e.nombre AS estado
               FROM municipios m LEFT JOIN entidades e USING (cve_ent) WHERE m.cvegeo = ANY(%(c)s)""", {"c": pedidos})
        por_clave = {f["cvegeo"]: f for f in await cur.fetchall()}
        municipios = [por_clave[c] for c in pedidos if c in por_clave]
        faltan = [c for c in pedidos if c not in por_clave]
        if metro:
            nombre = metro["nombre"]
            detalle = f"{len(pedidos)} municipios" if len(pedidos) > 1 else "1 municipio"
        else:
            nombre = _lista([m["nombre"] for m in municipios], len(municipios), "municipios")
            estados = sorted({m["estado"] for m in municipios if m["estado"]})
            detalle = ", ".join(estados)
        if faltan:
            aviso = (f"{len(faltan)} de {len(pedidos)} municipios no están cargados en Mapo ({', '.join(faltan)}):"
                     " la zona queda sin ellos.")
    else:
        municipios = await _municipios_tocados(cur, sql, params)
        donde = _lista([m["nombre"] for m in municipios], len(municipios), "municipios") if municipios else None
        if municipios:
            donde += "".join(", " + e for e in sorted({m["estado"] for m in municipios if m["estado"]}))
        if t == "colonia":
            await cur.execute("SELECT nombre, clasif, nom_mun FROM colonias WHERE cve_col = %(c)s",
                              {"c": zona["cve_col"]})
            col = await cur.fetchone()
            nombre = col["nombre"]
            detalle = f"{_clasif(col['clasif'])} · {donde or col['nom_mun']}"
            fuente = FUENTE_COLONIAS
        elif t == "cp":
            nombre = f"CP {zona['cp']}"
            detalle = donde or "fuera de los municipios cargados"
            fuente = FUENTE_CP
        elif t == "poligono":
            nombre = "Polígono dibujado"
            detalle = donde or "fuera de los municipios cargados"
            fuente = "dibujado en Mapo"
        else:
            nombre = f"Círculo de {_km(zona['radio_m'])} de radio"
            detalle = donde or "fuera de los municipios cargados"
            fuente = "dibujado en Mapo"

    return {
        "clave": clave(zona),
        "tipo": t,
        "nombre": nombre,
        "detalle": detalle,
        "geojson": json.loads(g["gj"]),
        "km2": round(g["km2"], 2),
        "bbox": [g["x0"], g["y0"], g["x1"], g["y1"]],
        "municipios": [{"cvegeo": m["cvegeo"], "cve_ent": m["cve_ent"], "cve_mun": m["cve_mun"],
                        "nombre": m["nombre"], "estado": m["estado"]} for m in municipios],
        "estados": sorted({m["cve_ent"] for m in municipios}),
        "faltan": faltan,
        "fuente": fuente,
        "metodo": metodo,
        "aviso": aviso,
    }


def _clasif(clasif: str | None) -> str:
    # CONAPO pone "-" en las localidades que cuenta enteras.
    return clasif if clasif and clasif != "-" else "Asentamiento"


def _km(metros: float) -> str:
    return f"{metros:,.0f} m" if metros < 1000 else f"{metros / 1000:g} km"


async def buscar(conn, texto: str, limite: int = 10) -> dict:
    """Sugerencias para el autocompletado: estados, metrópolis y municipios cargados,
    luego colonias. Cinco dígitos es un código postal. `aviso` dice por qué no hay
    resultados cuando no es cosa de escribir otra cosa."""
    texto = (texto or "").strip()
    if len(texto) < 2:
        return {"resultados": [], "aviso": None}
    cur = conn.cursor(row_factory=dict_row)
    salida: list[dict] = []
    if re.fullmatch(r"\d{5}", texto):
        await cur.execute("SELECT EXISTS (SELECT 1 FROM codigos_postales) AS hay,"
                          " EXISTS (SELECT 1 FROM codigos_postales WHERE cp = %(c)s) AS este", {"c": texto})
        f = await cur.fetchone()
        if f["este"]:
            return {"resultados": [{"clave": f"cp:{texto}", "tipo": "cp", "nombre": f"CP {texto}",
                                    "detalle": "Código postal · SEPOMEX"}], "aviso": None}
        return {"resultados": [], "aviso": None if f["hay"] else SIN_CP}

    q = normalizar(texto)[:80]
    p = {"q": f"%{q}%", "pre": f"{q}%", "lim": limite}
    await cur.execute(
        f"""SELECT cve_ent, nombre FROM entidades WHERE {_norm_sql('nombre')} LIKE %(q)s
            ORDER BY {_norm_sql('nombre')} LIKE %(pre)s DESC, nombre LIMIT 2""", p)
    salida += [{"clave": f"ent:{f['cve_ent']}", "tipo": "estado", "nombre": f["nombre"], "detalle": "Estado"}
               for f in await cur.fetchall()]
    await cur.execute(
        f"""SELECT clave, nombre, tipo, cardinality(cvegeos) AS n FROM metropolis
            WHERE {_norm_sql('nombre')} LIKE %(q)s ORDER BY clave LIMIT 3""", p)
    salida += [{"clave": f"zm:{f['clave']}", "tipo": "metropoli", "nombre": f["nombre"],
                "detalle": f"{f['n']} municipio{'s' if f['n'] != 1 else ''} · Metrópolis de México 2020"}
               for f in await cur.fetchall()]
    await cur.execute(
        f"""SELECT m.cvegeo, m.nombre, e.nombre AS estado FROM municipios m LEFT JOIN entidades e USING (cve_ent)
            WHERE {_norm_sql('m.nombre')} LIKE %(q)s
            ORDER BY {_norm_sql('m.nombre')} LIKE %(pre)s DESC, m.pob_total DESC NULLS LAST LIMIT 4""", p)
    salida += [{"clave": f"mun:{f['cvegeo']}", "tipo": "municipio", "nombre": f["nombre"],
                "detalle": f"Municipio · {f['estado']}"} for f in await cur.fetchall()]
    if len(q) >= 3:
        await cur.execute(
            """SELECT c.cve_col, c.nombre, c.clasif, c.nom_mun, e.nombre AS estado
               FROM colonias c JOIN entidades e USING (cve_ent) WHERE c.nombre_norm LIKE %(q)s
               ORDER BY c.nombre_norm LIKE %(pre)s DESC, c.pobtot DESC NULLS LAST LIMIT %(lim)s""", p)
        salida += [{"clave": f"col:{f['cve_col']}", "tipo": "colonia", "nombre": f["nombre"],
                    "detalle": f"{_clasif(f['clasif'])} · {f['nom_mun']}, {f['estado']}"}
                   for f in await cur.fetchall()]
    return {"resultados": salida[:limite], "aviso": None}


# Carga -------------------------------------------------------------------------

def leer_metropolis(ruta: Path = METROPOLIS_CSV) -> list[dict]:
    por_clave: dict[str, dict] = {}
    with ruta.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if not re.fullmatch(r"\d{2}\.[123]\.\d{2}", r["clave_metropoli"]) or not re.fullmatch(r"\d{5}", r["cvegeo"]):
                raise ZonaInvalida(f"renglón raro en {ruta.name}: {r}")
            m = por_clave.setdefault(r["clave_metropoli"], {
                "clave": r["clave_metropoli"], "nombre": r["metropoli"],
                "tipo": TIPOS_METROPOLI[r["clave_metropoli"][3]], "cvegeos": []})
            m["cvegeos"].append(r["cvegeo"])
    return list(por_clave.values())


async def cargar_metropolis(pool) -> dict:
    metros = leer_metropolis()
    if len(metros) != 92:
        raise ZonaInvalida(f"{len(metros)} metrópolis: el documento trae 92")
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM metropolis")
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO metropolis (clave, nombre, tipo, cvegeos) VALUES (%(clave)s, %(nombre)s, %(tipo)s, %(cvegeos)s)",
                    metros)
    por_tipo = {t: sum(1 for m in metros if m["tipo"] == t) for t in TIPOS_METROPOLI.values()}
    return {"metropolis": len(metros), "municipios": sum(len(m["cvegeos"]) for m in metros), "por_tipo": por_tipo}


def leer_colonias(ruta: Path):
    """Renglones del shapefile de CONAPO (Lambert ITRF2008, EPSG 6372) como dicts con
    la geometría en GeoJSON, todavía sin reproyectar."""
    with zipfile.ZipFile(ruta) as z:
        base = next(n[:-4] for n in z.namelist() if n.lower().endswith(".shp"))
        codificacion = z.read(base + ".CPG").decode().strip() if base + ".CPG" in z.namelist() else "utf-8"
        r = shapefile.Reader(shp=io.BytesIO(z.read(base + ".shp")), dbf=io.BytesIO(z.read(base + ".dbf")),
                             shx=io.BytesIO(z.read(base + ".shx")), encoding=codificacion)
        prj = z.read(base + ".prj").decode(errors="replace")
    if "ITRF_2008" not in prj or "Lambert" not in prj:
        raise ZonaInvalida("la proyección no es la Lambert ITRF 2008 de INEGI: revisar antes de cargar")
    campos = [f[0] for f in r.fields[1:]]
    for i in range(len(r)):
        rec = dict(zip(campos, r.record(i)))
        forma = r.shape(i)
        if not forma.points:
            continue
        yield {
            "cve_col": rec["CVE_COL"].strip(), "nombre": rec["COLONIA"].strip(),
            "cve_ent": rec["CVE_ENT"], "cve_mun": rec["MUN"], "nom_mun": rec["NOM_MUN"],
            "clasif": (rec["CLASIF"] or "").strip() or None, "pobtot": rec["POBTOT"],
            "geojson": json.dumps(forma.__geo_interface__),
        }


async def cargar_colonias(pool, ruta: Path) -> dict:
    filas = list(leer_colonias(ruta))
    if len(filas) < 70_000:
        raise ZonaInvalida(f"solo {len(filas)} colonias: CONAPO publica 74,226")
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM colonias")
            async with conn.cursor() as cur:
                await cur.executemany(
                    """INSERT INTO colonias (cve_col, nombre, nombre_norm, cve_ent, cve_mun, nom_mun, clasif, pobtot, geom)
                       VALUES (%(cve_col)s, %(nombre)s, %(nombre_norm)s, %(cve_ent)s, %(cve_mun)s, %(nom_mun)s,
                               %(clasif)s, %(pobtot)s,
                               ST_Multi(ST_CollectionExtract(ST_MakeValid(
                                 ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 6372), 4326)), 3)))""",
                    [{**f, "nombre_norm": normalizar(f["nombre"])} for f in filas])
            cur = await conn.execute(
                "SELECT count(*), count(*) FILTER (WHERE NOT ST_IsValid(geom)) FROM colonias")
            total, invalidas = await cur.fetchone()
    return {"colonias": total, "invalidas": invalidas}



# Campos con el CP en los shapefiles de SEPOMEX: el conjunto de datos.gob.mx trae
# `d_cp`; los otros son por si cambia de nombre entre estados o versiones.
CAMPOS_CP = ("d_cp", "cp", "codigo_postal", "d_codigo")


def _srid(prj: str) -> int:
    if "PROJCS" not in prj and "GEOGCS" in prj:
        return 4326
    if "ITRF_2008" in prj and "Lambert" in prj:
        return 6372
    raise ZonaInvalida(f"proyección desconocida, revisar antes de cargar: {prj[:120]}")


def leer_codigos_postales(ruta: Path):
    """(cp, geojson, srid) de un CP_XX.zip de SEPOMEX."""
    with zipfile.ZipFile(ruta) as z:
        nombres = z.namelist()
        shp = next((n for n in nombres if n.lower().endswith(".shp")), None)
        if shp is None:
            raise ZonaInvalida(f"{ruta.name} no trae un .shp")
        base = shp[:-4]
        buscar_ext = lambda ext: next((n for n in nombres if n.lower() == (base + ext).lower()), None)  # noqa: E731
        cpg = buscar_ext(".cpg")
        r = shapefile.Reader(shp=io.BytesIO(z.read(shp)), dbf=io.BytesIO(z.read(buscar_ext(".dbf"))),
                             shx=io.BytesIO(z.read(buscar_ext(".shx"))),
                             encoding=z.read(cpg).decode().strip() if cpg else "latin-1")
        prj = buscar_ext(".prj")
        srid = _srid(z.read(prj).decode(errors="replace")) if prj else 4326
    campos = [f[0] for f in r.fields[1:]]
    campo = next((c for c in campos if c.lower() in CAMPOS_CP), None)
    if campo is None:
        raise ZonaInvalida(f"{ruta.name}: ningún campo de CP entre {campos}")
    indice = campos.index(campo)
    for i in range(len(r)):
        cp = str(r.record(i)[indice] or "").strip()
        if re.fullmatch(r"\d{4}", cp):
            cp = "0" + cp  # la Ciudad de México empieza con 0 y a veces se pierde
        forma = r.shape(i)
        if re.fullmatch(r"\d{5}", cp) and forma.points:
            yield cp, json.dumps(forma.__geo_interface__), srid


async def cargar_codigos_postales(pool, ruta: Path) -> dict:
    """Carga (o reemplaza) los CP de un estado y dice cuántos negocios de DENUE del
    estado caen dentro del polígono del CP que declaran: la prueba con datos reales."""
    m = re.search(r"(\d{2})", ruta.stem)
    if not m or not 1 <= int(m.group(1)) <= 32:
        raise ZonaInvalida(f"{ruta.name}: el nombre debe llevar la clave del estado, como CP_14.zip")
    cve_ent = m.group(1)
    filas = list(leer_codigos_postales(ruta))
    if not filas:
        raise ZonaInvalida(f"{ruta.name} no trae ningún CP con polígono")
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM codigos_postales WHERE cve_ent = %(e)s", {"e": cve_ent})
            async with conn.cursor() as cur:
                await cur.executemany(
                    """INSERT INTO codigos_postales (cp, cve_ent, geom)
                       VALUES (%(cp)s, %(e)s, ST_Multi(ST_CollectionExtract(ST_MakeValid(
                               ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(gj)s), %(srid)s), 4326)), 3)))
                       ON CONFLICT (cp) DO UPDATE SET geom = ST_Multi(ST_Union(codigos_postales.geom, EXCLUDED.geom)),
                                                      actualizado = now()""",
                    [{"cp": cp, "e": cve_ent, "gj": gj, "srid": srid} for cp, gj, srid in filas])
            cur = await conn.execute(
                """WITH n AS (SELECT codigo_postal AS cp, ST_SetSRID(ST_MakePoint(lon, lat), 4326) AS p
                              FROM fuente_denue_negocios
                              WHERE cve_ent = %(e)s AND lat IS NOT NULL AND codigo_postal ~ '^[0-9]{5}$')
                   SELECT count(*) AS negocios,
                          count(*) FILTER (WHERE EXISTS (SELECT 1 FROM codigos_postales c
                                                         WHERE c.cp = n.cp AND ST_Covers(c.geom, n.p))) AS en_su_cp,
                          (SELECT count(*) FROM codigos_postales WHERE cve_ent = %(e)s) AS cps
                   FROM n""", {"e": cve_ent})
            negocios, en_su_cp, cps = await cur.fetchone()
    return {"cve_ent": cve_ent, "poligonos": len(filas), "cps": cps, "denue_negocios": negocios,
            "denue_en_su_cp": en_su_cp,
            "denue_parte": round(en_su_cp / negocios, 3) if negocios else None}
