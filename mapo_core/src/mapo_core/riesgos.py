"""Vista de riesgos (sesión 23): una zona y cada peligro por separado, con cuánta
gente vive dentro de la zona y cerca de cada uno. Ver docs/producto/vista-riesgos.md.

Reglas: nunca un índice ni la palabra "expuesta". Cada bloque dice su fuente, la
fecha del dato, su nivel geográfico y su método, y las frases son de lugar:
"dentro de la zona", "a menos de 1,000 m de un sitio en rojo". Si una fuente no
tiene nada en la zona, el bloque lo dice; si no está cargada, también.

La zona es cualquiera de la zona común (zona.py: estado, municipios, metrópoli,
CP, colonia, polígono dibujado o círculo). Todo lo que manda el navegador pasa por
`zona_valida` y `cerca_valido`: nada se interpola en el SQL.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

from psycopg.rows import dict_row

from mapo_core import zona as zona_comun
from mapo_core.db import get_pool

RADIO_MAX_M = zona_comun.RADIO_MAX_M
CERCAS_M = (250, 500, 1_000, 2_000, 5_000)
MAX_PUNTOS_CAPA = 2_000

# Calificaciones que Conagua cuenta como incumplimiento (calidad_generalidades_2025.pdf).
INCUMPLE_SUPERFICIAL = ("Contaminada", "Fuertemente contaminada", "Toxicidad alta")
INCUMPLE_SUBTERRANEA = ("No apta como FAAP", "Indeseable como FAAP", "Puede afectar la salud", "Contaminada",
                        "Fuertemente contaminada", "Indeseable")

# Grupos de población: variables de INEGI que vienen igual en el censo por AGEB y en el ITER.
GRUPOS = (
    ("POBTOT", "personas"),
    ("P_0A2", "de 0 a 2 años"),
    ("P_3A5", "de 3 a 5 años"),
    ("P_60YMAS", "de 60 años o más"),
    ("PCON_DISC", "con discapacidad"),
    ("PSINDER", "sin afiliación a servicios de salud"),
    ("P3YM_HLI", "de 3 años o más que hablan una lengua indígena"),
)
VIVIENDAS = (
    ("TVIVPARHAB", "viviendas particulares habitadas"),
    ("VPH_AGUAFV", "sin agua entubada en la vivienda o el terreno"),
    ("VPH_NODREN", "sin drenaje"),
)


class ZonaInvalida(ValueError):
    pass


def zona_valida(cve_ent=None, cve_mun=None, lon=None, lat=None, radio_m=None, clave=None) -> dict:
    """La zona como la entiende zona.py. Acepta la clave de zona común (`clave`) o,
    como antes de la 29b, un municipio (`cve_ent` y `cve_mun`) o un círculo."""
    if clave is None:
        if cve_ent is not None or cve_mun is not None:
            if not (isinstance(cve_ent, str) and re.fullmatch(r"\d{2}", cve_ent)
                    and isinstance(cve_mun, str) and re.fullmatch(r"\d{3}", cve_mun)):
                raise ZonaInvalida("cve_ent de 2 dígitos y cve_mun de 3")
            clave = f"mun:{cve_ent}{cve_mun}"
        elif None in (lon, lat, radio_m):
            raise ZonaInvalida("hace falta una zona, un municipio o lon, lat y radio_m")
        else:
            clave = f"cir:{lon},{lat},{radio_m}"
    try:
        return zona_comun.validar(clave)
    except zona_comun.ZonaInvalida as exc:
        raise ZonaInvalida(str(exc)) from None


def cerca_valido(cerca_m) -> int:
    try:
        cerca = int(cerca_m)
    except (TypeError, ValueError):
        raise ZonaInvalida(f"cerca_m es uno de {CERCAS_M}") from None
    if cerca not in CERCAS_M:
        raise ZonaInvalida(f"cerca_m es uno de {CERCAS_M}")
    return cerca


async def preparar(conn, zona: dict, cerca_m: int) -> dict | None:
    """La zona y la zona ampliada `cerca_m` metros se calculan una vez (el buffer en
    geography de un municipio tarda) y viajan como parámetros a todas las consultas:
    "dentro o cerca" queda como punto en polígono, que el índice resuelve rápido."""
    sql, params = zona_comun.geom_sql(zona)
    cur = await _ex(conn,
        "SELECT encode(ST_AsEWKB(geom), 'hex') AS z,"
        " encode(ST_AsEWKB(ST_Buffer(geom::geography, %(cerca_m)s)::geometry), 'hex') AS zc"
        f" FROM ({sql}) q", {**params, "cerca_m": cerca_m})
    fila = await cur.fetchone()
    if fila is None or fila["z"] is None:
        return None
    return {**zona, "cerca_m": cerca_m, "z_wkb": fila["z"], "zc_wkb": fila["zc"]}


def _zona_sql(zona: dict) -> str:
    return ("SELECT ST_GeomFromEWKB(decode(%(z_wkb)s, 'hex')) AS geom,"
            " ST_GeomFromEWKB(decode(%(zc_wkb)s, 'hex')) AS cerca")


def _suma(clave: str) -> str:
    # INEGI reserva con '*' los valores de lugares con pocas viviendas: no es cero.
    return (f"sum(CASE WHEN u.d->>'{clave}' ~ '^[0-9]+$' THEN (u.d->>'{clave}')::bigint END) AS \"{clave}\","
            f" count(*) FILTER (WHERE u.d->>'{clave}' = '*') AS \"{clave}_reservado\"")


_SUMAS = ", ".join(_suma(k) for k, _ in GRUPOS + VIVIENDAS)

# Dónde vive la gente de la zona: el AGEB urbano (con su censo) si está cargado, y si
# no, el punto de la localidad del ITER. Una localidad dentro de un AGEB cargado ya
# está contada en el AGEB.
_UNIDADES = """
unidades AS (
    SELECT ST_PointOnSurface(a.geom) AS punto, c.datos_json AS d, 'ageb' AS tipo
    FROM agebs a JOIN fuente_censo_poblacion c ON c.cvegeo = a.cvegeo, zona z
    WHERE a.geom && z.geom AND ST_Intersects(z.geom, ST_PointOnSurface(a.geom))
    UNION ALL
    SELECT l.geom, l.datos, 'localidad'
    FROM localidades l, zona z
    WHERE l.geom && z.geom AND ST_Intersects(z.geom, l.geom)
      AND NOT EXISTS (SELECT 1 FROM agebs a WHERE a.geom && l.geom AND ST_Covers(a.geom, l.geom))
)"""


async def _ex(conn, sql: str, params: dict):
    # Cursor propio con dict_row: la conexión vuelve al pool y los demás esperan tuplas.
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(sql, params)
    return cur


def _grupos(fila: dict) -> dict:
    # Sin ningún lugar que sumar, la suma de SQL es NULL pero lo cierto es cero:
    # "sin dato" queda para cuando hay lugares y todos traen el dato reservado.
    hay_lugares = (fila.get("agebs") or 0) + (fila.get("localidades") or 0) > 0
    salida = {}
    for clave, etiqueta in GRUPOS + VIVIENDAS:
        valor = fila.get(clave) if hay_lugares else 0
        salida[clave] = {"etiqueta": etiqueta, "valor": valor, "reservados": fila.get(f"{clave}_reservado", 0)}
    return salida


async def _poblacion(conn, zona: dict, cerca_de: str | None = None, cerca_m: int = 0,
                     extra: dict | None = None) -> dict:
    """Población de la zona; con `cerca_de` (SQL que da una columna `geom` de puntos o
    polígonos), solo la que vive a `cerca_m` metros o menos de alguno."""
    filtro = ""
    previa = ""
    if cerca_de:
        # Un solo polígono con el área a `cerca_m` de cualquier peligro (buffer en metros,
        # sobre geography) y luego punto en polígono: con cientos de establecimientos y
        # miles de AGEB, medir cada par tardaba segundos.
        previa = (f", peligro AS MATERIALIZED ({cerca_de}),"
                  " area AS (SELECT ST_Union(ST_Buffer(geom::geography, %(cerca_m)s, 'quad_segs=4')::geometry) AS g FROM peligro)")
        filtro = "WHERE ST_Intersects(u.punto, (SELECT g FROM area))"
    zona_sql = _zona_sql(zona) if cerca_de else _zona_sql(zona)
    sql = (f"WITH zona AS ({zona_sql}), {_UNIDADES}{previa} "
           f"SELECT count(*) FILTER (WHERE tipo = 'ageb') AS agebs, count(*) FILTER (WHERE tipo = 'localidad') AS localidades,"
           # Una localidad urbana sin AGEB cargados cuenta entera por su punto: avisarlo.
           f" count(*) FILTER (WHERE tipo = 'localidad' AND u.d->>'POBTOT' ~ '^[0-9]+$'"
           f" AND (u.d->>'POBTOT')::int >= 2500) AS urbanas_por_punto,"
           f" coalesce(sum((u.d->>'POBTOT')::int) FILTER (WHERE tipo = 'localidad' AND u.d->>'POBTOT' ~ '^[0-9]+$'"
           f" AND (u.d->>'POBTOT')::int >= 2500), 0) AS pob_urbanas_por_punto,"
           f" {_SUMAS} FROM unidades u {filtro}")
    cur = await _ex(conn, sql, {**zona, "cerca_m": cerca_m, **(extra or {})})
    fila = await cur.fetchone()
    return {"agebs": fila["agebs"], "localidades": fila["localidades"], "grupos": _grupos(fila),
            "urbanas_por_punto": fila["urbanas_por_punto"], "pob_urbanas_por_punto": fila["pob_urbanas_por_punto"]}


def _bloque(clave, titulo, fuente, fecha, nivel, metodo, hechos, poblacion=None, capa=None, ficha=None):
    return {"clave": clave, "titulo": titulo, "fuente": fuente, "fecha_dato": fecha, "nivel": nivel,
            "metodo": metodo, "hechos": hechos, "poblacion_cerca": poblacion, "capa": capa, "ficha": ficha}


def _capa(filas: list[dict], props: list[str]) -> dict:
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": json.loads(f["gj"]), "properties": {k: f.get(k) for k in props}}
        for f in filas[:MAX_PUNTOS_CAPA]]}


def _n(x) -> str:
    """Número con separador de miles, como se escribe en México."""
    if x is None:
        return "sin dato"
    if isinstance(x, Decimal):
        x = float(x)
    if isinstance(x, float) and not x.is_integer():
        return f"{x:,.1f}"
    return f"{int(x):,}"


def _cuenta(n: int, singular: str, plural: str) -> str:
    return f"{_n(n)} {singular if n == 1 else plural}"


def _masa(kg: float) -> str:
    """Kilos hasta una tonelada; arriba, toneladas (el CO₂ de un ingenio son millones de kg)."""
    return f"{_n(kg)} kg" if kg < 1000 else f"{_n(round(kg / 1000))} t"


# Nombres de los parámetros de la RENAMECA, por el principio de la columna.
_PARAMETROS = (
    ("DBO", "DBO"), ("DQO", "DQO"), ("SST", "sólidos suspendidos"), ("COLI_FEC", "coliformes fecales"),
    ("E_COLI", "E. coli"), ("ENTEROC", "enterococos"), ("OD_", "oxígeno disuelto"), ("TOX_", "toxicidad"),
    ("ALC", "alcalinidad"), ("CONDUCT", "conductividad"), ("SDT", "sólidos disueltos"), ("FLUORUROS", "fluoruros"),
    ("DUR", "dureza"), ("N_NO3", "nitratos"), ("AS_", "arsénico"), ("CD_", "cadmio"), ("CR_", "cromo"),
    ("HG_", "mercurio"), ("PB_", "plomo"), ("MN_", "manganeso"), ("FE_", "hierro"),
)


def nombre_parametro(columna: str) -> str:
    for prefijo, nombre in _PARAMETROS:
        if columna.upper().startswith(prefijo):
            return nombre
    return columna


# --- Peligros con puntos ----------------------------------------------------
async def _agua(conn, zona, cerca_m, tipo):
    incumple = INCUMPLE_SUPERFICIAL if tipo == "superficial" else INCUMPLE_SUBTERRANEA
    dentro_o_cerca = ("SELECT s.* FROM fuente_renameca_sitios s, zona z WHERE s.tipo = %(tipo)s"
                      " AND s.geom && z.cerca AND ST_Intersects(s.geom, z.cerca)")
    cur = await _ex(conn, 
        f"WITH zona AS ({_zona_sql(zona)}) SELECT s.clave, s.nombre, s.cuerpo, s.semaforo, s.parametros,"
        f" ST_Intersects(s.geom, z.geom) AS dentro, ST_AsGeoJSON(s.geom, 5) AS gj FROM ({dentro_o_cerca}) s, zona z"
        f" ORDER BY s.semaforo = 'ROJO' DESC, s.clave",
        {**zona, "tipo": tipo, "cerca_m": cerca_m})
    sitios = await cur.fetchall()
    for s in sitios:
        s["incumple"] = sorted({nombre_parametro(k) for k, v in s["parametros"].items()
                                if v.get("calidad") in incumple or v.get("calidad_2") in incumple})
    dentro = [s for s in sitios if s["dentro"]]
    rojos = [s for s in sitios if s["semaforo"] == "ROJO"]
    hechos = []
    if not sitios:
        hechos.append(f"Ningún sitio de la red dentro de la zona ni a menos de {_n(cerca_m)} m.")
    else:
        por_color = {}
        for s in dentro:
            por_color[s["semaforo"] or "sin semáforo"] = por_color.get(s["semaforo"] or "sin semáforo", 0) + 1
        hechos.append(f"{_cuenta(len(dentro), 'sitio', 'sitios')} dentro de la zona" + (
            ": " + ", ".join(f"{k} en {c.lower()}" for c, k in sorted(por_color.items())) + "." if por_color else "."))
        fuera = len(sitios) - len(dentro)
        if fuera:
            hechos.append(f"{_n(fuera)} más fuera de la zona, a menos de {_n(cerca_m)} m de su borde.")
        conteo = {}
        for s in sitios:
            for p in s["incumple"]:
                conteo[p] = conteo.get(p, 0) + 1
        if conteo:
            hechos.append("Parámetros que incumplen en algún sitio: " + ", ".join(
                f"{p} ({k})" for p, k in sorted(conteo.items(), key=lambda x: -x[1])) + ".")
    poblacion = None
    if rojos:
        poblacion = await _poblacion(
            conn, zona, "SELECT geom FROM fuente_renameca_sitios WHERE tipo = %(tipo)s AND clave = ANY(%(claves)s)",
            cerca_m, {"tipo": tipo, "claves": [s["clave"] for s in rojos]})
        poblacion["frase"] = f"viven a menos de {_n(cerca_m)} m de un sitio en rojo"
    titulo = "Calidad del agua superficial" if tipo == "superficial" else "Calidad del agua subterránea"
    metodo = ("Semáforo de Conagua tal cual. Cada sitio resume sus mediciones de 2012 a 2025 (mediana o media "
              f"geométrica según el parámetro). Incumplir es calificar como {', '.join(incumple)}. "
              "La red no mide plaguicidas.")
    return _bloque(f"agua_{tipo}", titulo, "Conagua, RENAMECA", "2012 a 2025", "punto (sitio de monitoreo)",
                   metodo, hechos, poblacion,
                   _capa(sitios, ["clave", "nombre", "cuerpo", "semaforo", "incumple"]))


async def _descargas(conn, zona, cerca_m):
    cur = await _ex(conn, 
        f"WITH zona AS ({_zona_sql(zona)}) SELECT d.titulo, d.uso, d.volumen_anual, d.procedencia,"
        f" d.cuerpo_receptor, ST_Intersects(d.geom, z.geom) AS dentro, ST_AsGeoJSON(d.geom, 5) AS gj"
        f" FROM fuente_repda_descargas d, zona z"
        f" WHERE d.geom IS NOT NULL AND d.geom && z.cerca AND ST_Intersects(d.geom, z.cerca)",
        {**zona, "cerca_m": cerca_m})
    filas = await cur.fetchall()
    dentro = [f for f in filas if f["dentro"]]
    hechos = []
    if not filas:
        hechos.append(f"Ninguna descarga con permiso dentro de la zona ni a menos de {_n(cerca_m)} m.")
    else:
        hechos.append(f"{_cuenta(len(dentro), 'punto', 'puntos')} de descarga con permiso dentro de la zona; "
                      f"{_n(len(filas) - len(dentro))} más a menos de {_n(cerca_m)} m de su borde.")
        por_uso = {}
        for f in dentro:
            u = por_uso.setdefault(f["uso"] or "sin uso", [0, 0.0])
            u[0] += 1
            u[1] += f["volumen_anual"] or 0
        if por_uso:
            hechos.append("Dentro, por uso del título: " + "; ".join(
                f"{u.lower()}: {_n(k)} ({_n(v / 1000)} mil m³ al año)"
                for u, (k, v) in sorted(por_uso.items(), key=lambda x: -x[1][1])) + ".")
    poblacion = None
    if filas:
        poblacion = await _poblacion(conn, zona, (
            f"SELECT d.geom FROM fuente_repda_descargas d, zona z WHERE d.geom IS NOT NULL"
            " AND d.geom && z.cerca AND ST_Intersects(d.geom, z.cerca)"), cerca_m)
        poblacion["frase"] = f"viven a menos de {_n(cerca_m)} m de un punto de descarga con permiso"
    return _bloque("descargas", "Descargas de aguas residuales con permiso", "Conagua, REPDA",
                   "títulos vigentes al 2026-11-13", "punto (descarga declarada)",
                   "Lo permitido en el título, no lo medido ni su calidad. Las descargas sin título no están. "
                   "El volumen incluye agua de enfriamiento.", hechos, poblacion,
                   _capa(filas, ["titulo", "uso", "volumen_anual", "procedencia", "cuerpo_receptor"]))


async def _retc(conn, zona, cerca_m):
    cur = await _ex(conn, 
        f"WITH zona AS ({_zona_sql(zona)}), ultimo AS ("
        f" SELECT DISTINCT ON (e.nra) e.* FROM fuente_retc_establecimientos e, zona z"
        f" WHERE e.geom IS NOT NULL AND e.geom && z.cerca AND ST_Intersects(e.geom, z.cerca)"
        f" ORDER BY e.nra, e.anio DESC)"
        f" SELECT u.nra, u.anio, u.actividad, u.sector, ST_Intersects(u.geom, z.geom) AS dentro,"
        f" ST_AsGeoJSON(u.geom, 5) AS gj FROM ultimo u, zona z ORDER BY u.anio DESC",
        {**zona, "cerca_m": cerca_m})
    filas = await cur.fetchall()
    hechos = []
    if not filas:
        hechos.append(f"Ningún establecimiento reportó al RETC dentro de la zona ni a menos de {_n(cerca_m)} m.")
        return _bloque("retc", "Establecimientos que reportan emisiones", "SEMARNAT, RETC", "2004 a 2022",
                       "punto (establecimiento)", _METODO_RETC, hechos)
    dentro = [f for f in filas if f["dentro"]]
    hechos.append(f"{_cuenta(len(dentro), 'establecimiento', 'establecimientos')} dentro de la zona y {_n(len(filas) - len(dentro))} a menos "
                  f"de {_n(cerca_m)} m de su borde reportaron alguna vez de 2004 a 2022.")
    actividades = {}
    for f in filas:
        actividades[f["actividad"] or f["sector"] or "sin actividad"] = actividades.get(
            f["actividad"] or f["sector"] or "sin actividad", 0) + 1
    hechos.append("Actividades: " + "; ".join(f"{a} ({k})" for a, k in sorted(actividades.items(),
                                                                         key=lambda x: -x[1])[:6]) + ".")
    cur = await _ex(conn, 
        "SELECT sustancia, sum(coalesce(aire_kg,0)) aire, sum(coalesce(agua_kg,0)) agua, sum(coalesce(suelo_kg,0)) suelo"
        " FROM fuente_retc_emisiones e JOIN unnest(%(nras)s::text[], %(anios)s::int[]) AS u(nra, anio)"
        " ON e.nra = u.nra AND e.anio = u.anio GROUP BY 1"
        " ORDER BY sum(coalesce(aire_kg,0) + coalesce(agua_kg,0) + coalesce(suelo_kg,0)) DESC LIMIT 6",
        {"nras": [f["nra"] for f in filas], "anios": [f["anio"] for f in filas]})
    sustancias = await cur.fetchall()
    if sustancias:
        hechos.append("En su último reporte, lo más grande: " + "; ".join(
            f"{s['sustancia']}: " + ", ".join(f"{m} {_masa(s[m])}" for m in ("aire", "agua", "suelo") if s[m])
            for s in sustancias) + ".")
    poblacion = await _poblacion(conn, zona, (
        f"SELECT e.geom FROM fuente_retc_establecimientos e, zona z WHERE e.geom IS NOT NULL"
        " AND e.geom && z.cerca AND ST_Intersects(e.geom, z.cerca)"), cerca_m)
    poblacion["frase"] = f"viven a menos de {_n(cerca_m)} m de un establecimiento que reportó al RETC"
    return _bloque("retc", "Establecimientos que reportan emisiones", "SEMARNAT, RETC", "2004 a 2022",
                   "punto (establecimiento)", _METODO_RETC, hechos, poblacion,
                   _capa(filas, ["nra", "anio", "actividad"]))


_METODO_RETC = ("Lo que reporta cada establecimiento obligado, sin verificación pública; los que no están obligados "
                "no aparecen. Se toma el último año que reportó cada uno. Sin nombres: algunos son personas.")


async def _fuego(conn, zona, cerca_m):
    cur = await _ex(conn, 
        f"WITH zona AS ({_zona_sql(zona)}) SELECT extract(year FROM f.fecha)::int AS anio,"
        f" count(*) FILTER (WHERE f.tipo IS DISTINCT FROM 2) AS vegetacion, count(*) FILTER (WHERE f.tipo = 2) AS fija"
        f" FROM fuente_firms_focos f, zona z WHERE f.sensor = 'VIIRS_SNPP' AND f.geom && z.geom"
        f" AND ST_Intersects(f.geom, z.geom) GROUP BY 1 ORDER BY 1", zona)
    por_anio = await cur.fetchall()
    hechos = []
    if not por_anio:
        hechos.append("Ningún foco de calor VIIRS dentro de la zona de 2012 a 2025.")
        return _bloque("fuego", "Focos de calor", "NASA FIRMS, VIIRS S-NPP", "2012 a 2025", "punto (píxel de 375 m)",
                       _METODO_FUEGO, hechos)
    ultimo = por_anio[-1]["anio"]
    ultimos = [f for f in por_anio if f["anio"] > ultimo - 5]
    hechos.append("Focos dentro de la zona por año: " + ", ".join(f"{f['anio']}: {_n(f['vegetacion'])}" for f in ultimos) + ".")
    fija = sum(f["fija"] for f in por_anio)
    if fija:
        hechos.append(f"Además, {_n(fija)} focos de 2012 a {ultimo} marcados por FIRMS como fuente fija (industria, quema recurrente en el mismo punto).")
    cur = await _ex(conn, 
        f"WITH zona AS ({_zona_sql(zona)}) SELECT f.fecha::text AS fecha, f.confianza, f.frp, ST_AsGeoJSON(f.geom, 5) AS gj"
        f" FROM fuente_firms_focos f, zona z WHERE f.sensor = 'VIIRS_SNPP' AND f.geom && z.geom"
        f" AND ST_Intersects(f.geom, z.geom) AND extract(year FROM f.fecha) = %(ultimo)s ORDER BY f.fecha",
        {**zona, "ultimo": ultimo})
    puntos = await cur.fetchall()
    poblacion = await _poblacion(conn, zona, (
        f"SELECT f.geom FROM fuente_firms_focos f, zona z WHERE f.sensor = 'VIIRS_SNPP'"
        f" AND f.geom && z.geom AND ST_Intersects(f.geom, z.geom) AND extract(year FROM f.fecha) = {int(ultimo)}"
        " AND f.tipo IS DISTINCT FROM 2"), cerca_m)
    poblacion["frase"] = f"viven a menos de {_n(cerca_m)} m de un foco de {ultimo}"
    return _bloque("fuego", "Focos de calor", "NASA FIRMS, VIIRS S-NPP", f"2012 a {ultimo}", "punto (píxel de 375 m)",
                   _METODO_FUEGO, hechos, poblacion, _capa(puntos, ["fecha", "confianza", "frp"]))


_METODO_FUEGO = ("Un foco es un píxel más caliente que su entorno al paso del satélite: puede ser quema agrícola, "
                 "incendio o industria. No es un incendio confirmado. Confianza baja incluida.")


# --- Peligros por polígono o municipio --------------------------------------
async def _municipios_de_la_zona(conn, zona) -> list[tuple[str, str]]:
    if zona["tipo"] == "municipios":
        return [(c[:2], c[2:]) for c in zona["cvegeos"]]
    # Por polígono de municipio, como zona.py: una colonia urbana no tiene ningún
    # punto del ITER adentro (sesión 29b). Sin municipios cargados, por localidades.
    cur = await _ex(conn,
        f"WITH zona AS ({_zona_sql(zona)}) SELECT m.cve_ent, m.cve_mun FROM municipios m, zona z"
        " WHERE m.geom && z.geom AND ST_Intersects(m.geom, z.geom)"
        " AND ST_Area(ST_Intersection(m.geom, z.geom)) >= %(parte)s * ST_Area(z.geom) ORDER BY 1, 2",
        {**zona, "parte": zona_comun.PARTE_MINIMA})
    por_poligono = [(f["cve_ent"], f["cve_mun"]) for f in await cur.fetchall()]
    if por_poligono:
        return por_poligono
    cur = await _ex(conn, 
        f"WITH zona AS ({_zona_sql(zona)}) SELECT DISTINCT l.cve_ent, l.cve_mun FROM localidades l, zona z"
        f" WHERE l.geom && z.geom AND ST_Intersects(l.geom, z.geom) ORDER BY 1, 2", zona)
    return [(f["cve_ent"], f["cve_mun"]) for f in await cur.fetchall()]


async def _nombres(conn, municipios) -> dict:
    cur = await _ex(conn, 
        "SELECT DISTINCT ON (cve_ent, cve_mun) cve_ent, cve_mun, nom_mun FROM localidades"
        " WHERE (cve_ent, cve_mun) IN (SELECT * FROM unnest(%(e)s::text[], %(m)s::text[]))",
        {"e": [e for e, _ in municipios], "m": [m for _, m in municipios]})
    return {(f["cve_ent"], f["cve_mun"]): f["nom_mun"] for f in await cur.fetchall()}


async def _acuifero(conn, zona):
    cur = await _ex(conn, 
        f"WITH zona AS ({_zona_sql(zona)}) SELECT a.clave, a.nombre, a.disponibilidad, a.recarga, a.descarga_natural, a.veas,"
        f" round((100 * ST_Area(ST_Intersection(a.geom, z.geom)::geography) / ST_Area(z.geom::geography))::numeric, 1) AS pct"
        f" FROM fuente_acuiferos a, zona z WHERE a.geom && z.geom AND ST_Intersects(a.geom, z.geom) ORDER BY pct DESC", zona)
    acuiferos = await cur.fetchall()
    cur = await _ex(conn, 
        f"WITH zona AS ({_zona_sql(zona)}) SELECT DISTINCT o.tipo, o.nombre, o.fecha_dof::text AS fecha FROM"
        f" fuente_acuiferos_ordenamientos o, zona z WHERE o.geom && z.geom AND ST_Intersects(o.geom, z.geom)"
        f" ORDER BY fecha", zona)
    ordenes = await cur.fetchall()
    cur = await _ex(conn, 
        f"WITH zona AS ({_zona_sql(zona)}) SELECT p.pne FROM fuente_piezometria p, zona z"
        f" WHERE p.geom && z.geom AND ST_Intersects(p.geom, z.geom)", zona)
    pozos = [f["pne"] for f in await cur.fetchall()]
    hechos = []
    for a in acuiferos:
        estado = "sin disponibilidad" if a["disponibilidad"] <= 0 else "con disponibilidad"
        hechos.append(f"{a['pct']} % de la zona sobre el acuífero {a['nombre'].title()} ({a['clave']}), {estado}: "
                      f"{_n(a['disponibilidad'])} hm³ al año (recarga {_n(a['recarga'])}, menos descarga natural "
                      f"comprometida {_n(a['descarga_natural'])}, menos extracción {_n(a['veas'])}).")
    nombres = {"veda": "Veda", "suspension": "Suspensión de libre alumbramiento", "reglamento": "Reglamento"}
    for o in ordenes:
        hechos.append(f"{nombres[o['tipo']]}: {o['nombre']} (DOF {o['fecha'] or 'sin fecha'}).")
    if pozos:
        ultimos = [max(p.items(), key=lambda kv: kv[0]) for p in pozos if p]
        hechos.append(f"{_cuenta(len(pozos), 'pozo', 'pozos')} de la red piezométrica dentro de la zona; última medición de cada uno "
                      f"entre {min(a for a, _ in ultimos)} y {max(a for a, _ in ultimos)}, con el agua de "
                      f"{_n(min(v for _, v in ultimos))} a {_n(max(v for _, v in ultimos))} m de profundidad.")
    else:
        hechos.append("Ningún pozo de la red piezométrica dentro de la zona: no hay medición de la profundidad del agua.")
    return _bloque("acuifero", "Agua subterránea disponible", "Conagua", "DOF 2023-11-09 (corte 2022); piezometría 1996 a 2023",
                   "acuífero", "Balance de Conagua: disponibilidad = recarga − descarga natural comprometida − "
                   "extracción. Es administrativo, no una medición del nivel.", hechos)


async def _sequia(conn, municipios, nombres):
    if not municipios:
        return _bloque("sequia", "Sequía", "SMN, Monitor de Sequía", "", "municipio", _METODO_SEQUIA,
                       ["La zona no tiene localidades: no se sabe a qué municipio pertenece."])
    cur = await _ex(conn, 
        "WITH u AS (SELECT max(fecha) AS f FROM fuente_sequia_municipal)"
        " SELECT s.cve_ent, s.cve_mun, max(s.fecha)::text AS ultima,"
        " (array_agg(s.categoria ORDER BY s.fecha DESC))[1] AS actual,"
        " count(*) FILTER (WHERE s.fecha > u.f - interval '5 years') AS cortes,"
        " count(*) FILTER (WHERE s.fecha > u.f - interval '5 years' AND s.categoria IN ('D2','D3','D4')) AS severa"
        " FROM fuente_sequia_municipal s, u"
        " WHERE (s.cve_ent, s.cve_mun) IN (SELECT * FROM unnest(%(e)s::text[], %(m)s::text[])) GROUP BY 1, 2",
        {"e": [e for e, _ in municipios], "m": [m for _, m in municipios]})
    filas = await cur.fetchall()
    etiquetas = {"sin": "sin anomalía", "D0": "anormalmente seco", "D1": "sequía moderada", "D2": "sequía severa",
                 "D3": "sequía extrema", "D4": "sequía excepcional"}
    hechos = [f"{nombres.get((f['cve_ent'], f['cve_mun']), f['cve_ent'] + f['cve_mun'])}: {etiquetas[f['actual']]} "
              f"al {f['ultima']}; {f['severa']} de {f['cortes']} cortes de los últimos 5 años en sequía severa o peor."
              for f in filas]
    fecha = filas[0]["ultima"] if filas else ""
    return _bloque("sequia", "Sequía", "SMN, Monitor de Sequía", f"2003 a {fecha}", "municipio", _METODO_SEQUIA,
                   hechos or ["El Monitor no trae estos municipios."])


_METODO_SEQUIA = ("Categoría del Monitor asignada al municipio entero en cada corte (quincenal). Severa o peor es D2 a D4. "
                  "Si la zona toca varios municipios, uno por renglón.")


async def _anp(conn, zona):
    cur = await _ex(conn, 
        f"WITH zona AS ({_zona_sql(zona)}) SELECT a.nombre, a.categoria,"
        f" ST_Intersects(a.geom, z.geom) AS dentro,"
        # La distancia, redondeada a 100 m, se mide sobre los contornos simplificados a ~50 m.
        f" round(ST_Distance(ST_Simplify(a.geom, 0.0005, true)::geography, ST_Simplify(z.geom, 0.0005, true)::geography)::numeric, -2) AS distancia_m,"
        f" round((100 * ST_Area(ST_Intersection(a.geom, z.geom)::geography) / ST_Area(z.geom::geography))::numeric, 1) AS pct"
        f" FROM fuente_anp a, zona z WHERE a.geom && ST_Expand(z.geom, 0.6) AND ST_DWithin(ST_Simplify(a.geom, 0.0005, true)::geography,"
        f" ST_Simplify(z.geom, 0.0005, true)::geography, 50000)"
        f" ORDER BY distancia_m LIMIT 5", zona)
    filas = await cur.fetchall()
    hechos = []
    for f in filas:
        if f["dentro"]:
            hechos.append(f"{f['pct']} % de la zona dentro de {f['nombre']} ({f['categoria']}).")
        else:
            hechos.append(f"{f['nombre']} ({f['categoria']}) a {_n(f['distancia_m'])} m del borde de la zona.")
    if not filas:
        hechos.append("Ningún área natural protegida federal a menos de 50 km.")
    return _bloque("anp", "Áreas naturales protegidas federales", "CONANP vía CONABIO (CC BY-NC 2.5 MX)", "2020-08",
                   "polígono", "Solo federales; las estatales y municipales no están cargadas.", hechos)


async def _uso_suelo(conn, zona):
    cur = await _ex(conn, 
        f"WITH zona AS ({_zona_sql(zona)}), t AS (SELECT ST_Area(geom::geography) AS a FROM zona)"
        f" SELECT u.serie, u.descripcion, round((100 * sum(ST_Area(ST_Intersection(u.geom, z.geom)::geography)) / t.a)::numeric, 1) AS pct"
        f" FROM fuente_uso_suelo u, zona z, t WHERE u.geom && z.geom AND ST_Intersects(u.geom, z.geom)"
        f" GROUP BY 1, 2, t.a ORDER BY 1 DESC, 3 DESC", zona)
    filas = await cur.fetchall()
    if not filas:
        return _bloque("uso_suelo", "Uso de suelo y vegetación", "INEGI vía CONABIO", "", "polígono 1:250 000", _METODO_USO,
                       ["Sin uso de suelo cargado para la zona."])
    s7 = [f for f in filas if f["serie"] == 7]
    s6 = {f["descripcion"]: f["pct"] for f in filas if f["serie"] == 6}
    hechos = ["Serie VII (2018): " + "; ".join(f"{f['descripcion'].lower()} {f['pct']} %" for f in s7[:6]) + "."]
    agricola = lambda fs: sum(float(f["pct"]) for f in fs if "AGR" in f["descripcion"].upper())
    a7, a6 = agricola(s7), agricola([f for f in filas if f["serie"] == 6])
    if s6:
        hechos.append(f"Agricultura (riego, temporal y humedad): {a6:.1f} % en la serie VI (2014) y {a7:.1f} % en la VII (2018).")
    return _bloque("uso_suelo", "Uso de suelo y vegetación", "INEGI vía CONABIO (CC BY-NC 2.5 MX)", "2014 y 2018",
                   "polígono 1:250 000", _METODO_USO, hechos)


_METODO_USO = ("Porcentaje del área de la zona por clase. A 1:250 000 la orilla de los pueblos se generaliza: para "
               "distancias de cientos de metros sirve más la frontera agrícola 1:10 000 del paquete ambiental.")


async def _agricultura(conn, municipios, nombres):
    if not municipios:
        return None
    cur = await _ex(conn, 
        "WITH u AS (SELECT max(anio) AS a FROM fuente_siap_agricola)"
        " SELECT s.anio, s.cultivo, s.modalidad, sum(s.sembrada) AS ha FROM fuente_siap_agricola s, u"
        " WHERE s.anio = u.a AND (s.cve_ent, s.cve_mun) IN (SELECT * FROM unnest(%(e)s::text[], %(m)s::text[]))"
        " GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT 8",
        {"e": [e for e, _ in municipios], "m": [m for _, m in municipios]})
    filas = await cur.fetchall()
    lugar = ", ".join(sorted(nombres.get(m, "".join(m)) for m in municipios))
    if not filas:
        return _bloque("agricultura", "Qué se siembra", "SIAP", "", "municipio", _METODO_AGRI,
                       [f"El SIAP no reporta siembra en {lugar}."])
    anio = filas[0]["anio"]
    hechos = [f"{lugar}, {anio}: " + "; ".join(
        f"{f['cultivo'].lower()} de {f['modalidad'].lower()} {_n(f['ha'])} ha" for f in filas) + "."]
    return _bloque("agricultura", "Qué se siembra", "SIAP", str(anio), "municipio", _METODO_AGRI, hechos)


_METODO_AGRI = ("Hectáreas sembradas del cierre agrícola en los municipios de la zona, no solo dentro de ella. "
                "No dice qué agroquímicos se usan.")


async def _defunciones(conn, municipios, nombres):
    if not municipios:
        return None
    params = {"e": [e for e, _ in municipios], "m": [m for _, m in municipios]}
    cur = await _ex(conn, 
        "SELECT anio_registro AS anio, sum(defunciones) AS total,"
        " sum(defunciones) FILTER (WHERE causa BETWEEN 'C00' AND 'D48') AS tumores,"
        " sum(defunciones) FILTER (WHERE causa BETWEEN 'N00' AND 'N29') AS renales,"
        " sum(defunciones) FILTER (WHERE causa LIKE 'J%%') AS respiratorias"
        " FROM fuente_defunciones_municipal"
        " WHERE (cve_ent, cve_mun) IN (SELECT * FROM unnest(%(e)s::text[], %(m)s::text[])) GROUP BY 1 ORDER BY 1",
        params)
    filas = await cur.fetchall()
    cur = await _ex(conn, 
        "SELECT sum(pobtot) AS p FROM localidades WHERE (cve_ent, cve_mun) IN"
        " (SELECT * FROM unnest(%(e)s::text[], %(m)s::text[]))", params)
    pob = (await cur.fetchone())["p"]
    lugar = ", ".join(sorted(nombres.get(m, "".join(m)) for m in municipios))
    if not filas:
        return _bloque("defunciones", "Defunciones registradas", "INEGI", "", "municipio", _METODO_DEFUN,
                       [f"Sin defunciones registradas de residentes de {lugar}."])

    def tasa(k):
        return f" ({k * 100_000 / pob:,.0f} por 100 mil)" if pob else ""

    hechos = [f"Residentes de {lugar} (población 2020: {_n(pob)})."]
    hechos += [f"{f['anio']}: {_n(f['total'])} en total{tasa(f['total'] or 0)}; tumores {_n(f['tumores'] or 0)}, "
               f"renales {_n(f['renales'] or 0)}, respiratorias {_n(f['respiratorias'] or 0)}." for f in filas]
    return _bloque("defunciones", "Defunciones registradas", "INEGI, estadísticas de defunciones registradas",
                   f"{filas[0]['anio']} a {filas[-1]['anio']}", "municipio de residencia", _METODO_DEFUN, hechos)


_METODO_DEFUN = ("Por municipio de residencia y año de registro, sin ajustar por edad. Tumores es C00 a D48, renales "
                 "N00 a N29 y respiratorias el capítulo J de la CIE-10. Es contexto: no dice que la causa sea ambiental.")


# --- Todo junto ------------------------------------------------------------
async def resumen(zona: dict, cerca_m: int) -> dict | None:
    pool = await get_pool()
    async with pool.connection() as conn:
        km2 = await zona_comun.area_km2(conn, zona)
        if km2 is None:
            return None
        if motivo := zona_comun.demasiado_grande(km2):
            raise ZonaInvalida(motivo)
        zona = await preparar(conn, zona, cerca_m)
        if zona is None:
            return None
        cur = await _ex(conn, 
            f"WITH zona AS ({_zona_sql(zona)}) SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0005), 5) AS gj,"
            f" round((ST_Area(geom::geography) / 1e6)::numeric, 1) AS km2 FROM zona", zona)
        z = await cur.fetchone()
        if z is None or z["gj"] is None:
            return None
        municipios = await _municipios_de_la_zona(conn, zona)
        nombres = await _nombres(conn, municipios)
        poblacion = await _poblacion(conn, zona)
        bloques = [
            await _agua(conn, zona, cerca_m, "superficial"),
            await _agua(conn, zona, cerca_m, "subterranea"),
            await _descargas(conn, zona, cerca_m),
            await _retc(conn, zona, cerca_m),
            await _fuego(conn, zona, cerca_m),
            await _acuifero(conn, zona),
            await _sequia(conn, municipios, nombres),
            await _anp(conn, zona),
            await _uso_suelo(conn, zona),
            await _agricultura(conn, municipios, nombres),
            await _defunciones(conn, municipios, nombres),
        ]
    visible = {k: v for k, v in zona.items() if k in ("tipo", "lon", "lat", "radio_m")}
    return {"zona": {**visible, "clave": zona_comun.clave(zona), "geojson": json.loads(z["gj"]), "km2": float(z["km2"]),
                     "municipios": [{"cve_ent": e, "cve_mun": m, "nombre": nombres.get((e, m))} for e, m in municipios]},
            "cerca_m": cerca_m, "poblacion": poblacion,
            "metodo_poblacion": ("AGEB urbanos con su censo 2020 donde están cargados (su punto interior dentro de la "
                                 "zona); en el resto, el punto de cada localidad del ITER 2020. '*' de INEGI son "
                                 "valores reservados: se cuentan aparte, no como cero."),
            "bloques": [b for b in bloques if b is not None]}
