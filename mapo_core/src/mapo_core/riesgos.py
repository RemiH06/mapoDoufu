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
import math
import re
from decimal import Decimal

import numpy as np
from psycopg.rows import dict_row
from scipy.spatial import cKDTree

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


def _partida(zona: dict) -> str:
    """Los CTE `zona`, `zs` (la zona en pedazos chicos, el nombre que usa zona.dentro) y
    `cs` (la zona ampliada, igual): punto en polígono contra pedazos, no contra el
    contorno entero."""
    return (f"zona AS MATERIALIZED ({_zona_sql(zona)}),"
            " zs AS MATERIALIZED (SELECT ST_Subdivide(geom, 128) AS g FROM zona),"
            " cs AS MATERIALIZED (SELECT ST_Subdivide(cerca, 128) AS g FROM zona)")


_EN_CERCA = "EXISTS (SELECT 1 FROM cs WHERE cs.g && {g} AND ST_Intersects(cs.g, {g}))"
_PUNTO = "ST_X({g}) AS lon, ST_Y({g}) AS lat"


async def _ex(conn, sql: str, params: dict):
    # Cursor propio con dict_row: la conexión vuelve al pool y los demás esperan tuplas.
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(sql, params)
    return cur


_CLAVES = tuple(k for k, _ in GRUPOS + VIVIENDAS)

# Dónde vive la gente de la zona: el AGEB urbano (con su censo) si está cargado, y si
# no, el punto de la localidad del ITER. Una localidad dentro de un AGEB cargado ya
# está contada en el AGEB. Se lee una vez por consulta: antes cada peligro la volvía a
# sumar en SQL contra el contorno entero, y la ZMG tardaba 76 s.
_UNIDADES_SQL = """
SELECT a.cve_ent || a.cve_mun AS mun, 'ageb' AS tipo, c.datos_json AS d,
       ST_X(pt.p) AS lon, ST_Y(pt.p) AS lat
FROM agebs a JOIN fuente_censo_poblacion c ON c.cvegeo = a.cvegeo
     -- OFFSET 0: sin él, el punto se calculaba otra vez contra cada pedazo de la zona.
     CROSS JOIN LATERAL (SELECT ST_PointOnSurface(a.geom) AS p OFFSET 0) pt
WHERE a.geom && (SELECT geom FROM zona) AND {ageb}
UNION ALL
SELECT l.cve_ent || l.cve_mun, 'localidad', l.datos, ST_X(l.geom), ST_Y(l.geom)
FROM localidades l
WHERE l.geom && (SELECT geom FROM zona) AND {loc}
  AND NOT EXISTS (SELECT 1 FROM agebs a WHERE a.geom && l.geom AND ST_Covers(a.geom, l.geom))
"""


async def _unidades(conn, zona: dict) -> list[dict]:
    sql = f"WITH {_partida(zona)} " + _UNIDADES_SQL.format(
        ageb=zona_comun.dentro("pt.p"), loc=zona_comun.dentro("l.geom"))
    cur = await _ex(conn, sql, zona)
    return await cur.fetchall()


def _ecef(puntos: list[dict]) -> np.ndarray:
    """Metros en el elipsoide WGS84: la cuerda entre dos puntos a 5 km o menos difiere de
    la distancia sobre el terreno en menos de un milímetro."""
    lon = np.radians(np.array([p["lon"] for p in puntos], dtype=float))
    lat = np.radians(np.array([p["lat"] for p in puntos], dtype=float))
    a, e2 = 6378137.0, 6.69437999014e-3
    n = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    return np.column_stack([n * np.cos(lat) * np.cos(lon), n * np.cos(lat) * np.sin(lon), n * (1 - e2) * np.sin(lat)])


def cerca_de(unidades: list[dict], puntos: list[dict], cerca_m: int) -> list[dict]:
    """Las unidades a `cerca_m` metros o menos de algún punto."""
    if not unidades or not puntos:
        return []
    d, _ = cKDTree(_ecef(puntos)).query(_ecef(unidades), distance_upper_bound=cerca_m + 0.001)
    return [u for u, x in zip(unidades, d) if math.isfinite(x)]


def _valor(d: dict | None, clave: str) -> int | None:
    v = (d or {}).get(clave)
    if isinstance(v, int):
        return v
    return int(v) if isinstance(v, str) and re.fullmatch(r"[0-9]+", v) else None


def _poblacion(unidades: list[dict]) -> dict:
    """Suma de cada grupo. INEGI reserva con '*' los valores de lugares con pocas
    viviendas: se cuentan aparte, no como cero."""
    agebs = sum(u["tipo"] == "ageb" for u in unidades)
    fila = {"agebs": agebs, "localidades": len(unidades) - agebs}
    for k in _CLAVES:
        valores = [v for u in unidades if (v := _valor(u["d"], k)) is not None]
        fila[k] = sum(valores) if valores else None
        fila[f"{k}_reservado"] = sum((u["d"] or {}).get(k) == "*" for u in unidades)
    # Una localidad urbana sin AGEB cargados cuenta entera por su punto: avisarlo.
    urbanas = [v for u in unidades if u["tipo"] == "localidad" and (v := _valor(u["d"], "POBTOT") or 0) >= 2500]
    return {"agebs": agebs, "localidades": fila["localidades"], "grupos": _grupos(fila),
            "urbanas_por_punto": len(urbanas), "pob_urbanas_por_punto": sum(urbanas)}


def _personas(unidades: list[dict]) -> int | None:
    """Personas, con la regla de `_grupos`: sin lugares es 0; con puros reservados, None."""
    valores = [v for u in unidades if (v := _valor(u["d"], "POBTOT")) is not None]
    return sum(valores) if valores or not unidades else None


def _grupos(fila: dict) -> dict:
    # Sin ningún lugar que sumar lo cierto es cero: "sin dato" queda para cuando hay
    # lugares y todos traen el dato reservado.
    hay_lugares = (fila.get("agebs") or 0) + (fila.get("localidades") or 0) > 0
    salida = {}
    for clave, etiqueta in GRUPOS + VIVIENDAS:
        valor = fila.get(clave) if hay_lugares else 0
        salida[clave] = {"etiqueta": etiqueta, "valor": valor, "reservados": fila.get(f"{clave}_reservado", 0)}
    return salida


# --- Medidas: la cifra de cada celda de la matriz -------------------------------
# La clase (cuánta tinta) la pone la pantalla con cortes fijos, los mismos para todos
# los peligros; aquí va la cifra, de la zona entera y de cada municipio. `lugares` es
# {"todas": unidades de la zona, "municipios": [cvegeo]}.

def medida_gente(lugares: dict, puntos: list[dict], cerca_m: int) -> dict:
    """Gente que vive a `cerca_m` de alguno de `puntos`. `cercanas` son sus unidades."""
    def celda(unidades, cercanas):
        total, cerca = _personas(unidades), _personas(cercanas)
        pct = None if not total or cerca is None else round(100 * cerca / total, 4)
        return {"personas": cerca, "total": total, "pct": pct}

    cercanas = cerca_de(lugares["todas"], puntos, cerca_m)
    por_mun = {m: celda([u for u in lugares["todas"] if u["mun"] == m], [u for u in cercanas if u["mun"] == m])
               for m in lugares["municipios"]}
    return {"tipo": "gente", "zona": celda(lugares["todas"], cercanas), "municipios": por_mun, "cercanas": cercanas}


async def _municipios_de(conn, puntos: list[dict], municipios: list[str], cerca_m: int = 0) -> list[set[str]]:
    """Por punto, los municipios en los que cae; con `cerca_m`, también los que quedan a
    esos metros."""
    salida: list[set[str]] = [set() for _ in puntos]
    if not puntos or not municipios:
        return salida
    condicion = ("ST_Intersects(m.g, p.geom)" if not cerca_m
                 else "ST_DWithin(m.g::geography, p.geom::geography, %(cerca)s)")
    cur = await _ex(conn,
        "WITH ms AS MATERIALIZED (SELECT cvegeo, ST_Subdivide(geom, 128) AS g FROM municipios"
        "  WHERE cvegeo = ANY(%(muns)s)),"
        " p AS MATERIALIZED (SELECT i, ST_SetSRID(ST_MakePoint(lon, lat), 4326) AS geom FROM"
        "  unnest(%(lon)s::float8[], %(lat)s::float8[]) WITH ORDINALITY AS x(lon, lat, i))"
        f" SELECT DISTINCT p.i, m.cvegeo FROM p JOIN ms m ON m.g && ST_Expand(p.geom, %(grados)s) AND {condicion}",
        {"muns": municipios, "cerca": cerca_m, "grados": cerca_m / 100_000,
         "lon": [p["lon"] for p in puntos], "lat": [p["lat"] for p in puntos]})
    for f in await cur.fetchall():
        salida[f["i"] - 1].add(f["cvegeo"])
    return salida


async def _contar(conn, medida: dict, puntos: list[dict], lugares: dict, detalle, cerca_m: int = 0,
                  corto=lambda ps: _n(len(ps))) -> None:
    """Agrega a cada celda cuántos puntos hay (`cuenta`), cómo se dice (`detalle`) y cómo cabe
    en la matriz, cuya columna ya dice la unidad (`corto`): los de dentro de la zona o de la parte del municipio que está en ella; con `cerca_m`, también
    los que quedan a esos metros de su borde."""
    contados = puntos if cerca_m else [p for p in puntos if p["dentro"]]
    medida["zona"] |= {"cuenta": len(contados), "detalle": detalle(contados), "corto": corto(contados)}
    de = await _municipios_de(conn, contados, lugares["municipios"], cerca_m)
    for m, celda in medida["municipios"].items():
        suyos = [p for p, ms in zip(contados, de) if m in ms]
        celda |= {"cuenta": len(suyos), "detalle": detalle(suyos), "corto": corto(suyos)}


def _cerca(medida: dict, frase: str) -> dict:
    """La gente cerca, con sus grupos, para la hoja. Saca `cercanas` de la medida."""
    return {**_poblacion(medida.pop("cercanas")), "frase": frase}


def _bloque(clave, hechos, *, fecha=None, poblacion=None, capa=None, medida=None, fuente=None):
    ficha = FICHAS[clave]
    return {"clave": clave, "titulo": ficha["titulo"], "fuente": fuente or ficha["fuente"],
            "fecha_dato": ficha["fecha"] if fecha is None else fecha, "nivel": ficha["nivel"], "metodo": ficha["metodo"],
            "hechos": hechos, "poblacion_cerca": poblacion, "capa": capa, "medida": medida}


# Lo que lleva la capa de cada peligro de puntos (las propiedades de su ficha).
_PROPS = {
    "agua_superficial": ("clave", "nombre", "cuerpo", "semaforo", "incumple", "dentro"),
    "agua_subterranea": ("clave", "nombre", "cuerpo", "semaforo", "incumple", "dentro"),
    "descargas": ("titulo", "uso", "volumen_anual", "procedencia", "cuerpo_receptor", "dentro"),
    "retc": ("nra", "anio", "actividad", "dentro"),
    "fuego": ("fecha", "confianza", "frp", "fija", "dentro"),
}


def _capa(filas: list[dict], props) -> dict:
    """Puntos para el plano, hasta MAX_PUNTOS_CAPA; `total` dice cuántos hay de verdad."""
    return {"type": "FeatureCollection", "total": len(filas), "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(f["lon"], 5), round(f["lat"], 5)]},
         "properties": {k: f.get(k) for k in props}}
        for f in filas[:MAX_PUNTOS_CAPA]]}


def _poligonos(filas: list[dict], props) -> dict:
    return {"type": "FeatureCollection", "total": len(filas), "features": [
        {"type": "Feature", "geometry": json.loads(f["gj"]), "properties": {k: f.get(k) for k in props}}
        for f in filas if f["gj"]]}


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
# Cada uno con sus filas aparte: /riesgos las cuenta y las dibuja, y el acetato de
# /mapa (`capas`) solo las dibuja.

async def _filas_agua(conn, zona, tipo):
    incumple = INCUMPLE_SUPERFICIAL if tipo == "superficial" else INCUMPLE_SUBTERRANEA
    cur = await _ex(conn,
        f"WITH {_partida(zona)} SELECT s.clave, s.nombre, s.cuerpo, s.semaforo, s.parametros,"
        f" {zona_comun.dentro('s.geom')} AS dentro, {_PUNTO.format(g='s.geom')}"
        f" FROM fuente_renameca_sitios s WHERE s.tipo = %(tipo)s AND s.geom && (SELECT cerca FROM zona)"
        f" AND {_EN_CERCA.format(g='s.geom')} ORDER BY s.semaforo = 'ROJO' DESC, s.clave",
        {**zona, "tipo": tipo})
    sitios = await cur.fetchall()
    for s in sitios:
        s["incumple"] = sorted({nombre_parametro(k) for k, v in s["parametros"].items()
                                if v.get("calidad") in incumple or v.get("calidad_2") in incumple})
    return sitios


def _rojos(sitios):
    return f"{_n(sum(s['semaforo'] == 'ROJO' for s in sitios))} de {_n(len(sitios))}"


async def _agua(conn, zona, cerca_m, tipo, lugares):
    sitios = await _filas_agua(conn, zona, tipo)
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
    medida = medida_gente(lugares, rojos, cerca_m)
    poblacion = _cerca(medida, f"viven a menos de {_n(cerca_m)} m de un sitio en rojo")
    await _contar(conn, medida, sitios, lugares, lambda ss: f"{_rojos(ss)} en rojo", cerca_m, corto=_rojos)
    # Sin sitios de la red no hay medición: 0 % diría que el agua está limpia.
    for celda in (medida["zona"], *medida["municipios"].values()):
        celda["sin_medicion"] = celda["cuenta"] == 0
    return _bloque(f"agua_{tipo}", hechos, poblacion=poblacion if rojos else None,
                   capa=_capa(sitios, _PROPS[f"agua_{tipo}"]), medida=medida)


async def _filas_descargas(conn, zona):
    cur = await _ex(conn,
        f"WITH {_partida(zona)} SELECT d.titulo, d.uso, d.volumen_anual, d.procedencia, d.cuerpo_receptor,"
        f" {zona_comun.dentro('d.geom')} AS dentro, {_PUNTO.format(g='d.geom')}"
        f" FROM fuente_repda_descargas d WHERE d.geom && (SELECT cerca FROM zona) AND {_EN_CERCA.format(g='d.geom')}",
        zona)
    return await cur.fetchall()


async def _descargas(conn, zona, cerca_m, lugares):
    filas = await _filas_descargas(conn, zona)
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
    medida = medida_gente(lugares, filas, cerca_m)
    poblacion = _cerca(medida, f"viven a menos de {_n(cerca_m)} m de un punto de descarga con permiso")
    await _contar(conn, medida, filas, lugares, lambda fs: _cuenta(len(fs), "descarga", "descargas"))
    return _bloque("descargas", hechos, poblacion=poblacion if filas else None,
                   capa=_capa(filas, _PROPS["descargas"]), medida=medida)


async def _filas_retc(conn, zona):
    cur = await _ex(conn,
        # El último reporte de cada uno, y luego si cae aquí: al revés, uno que cambió su
        # punto contaba donde estuvo antes.
        f"WITH {_partida(zona)}, ultimo AS (SELECT DISTINCT ON (e.nra) e.* FROM fuente_retc_establecimientos e"
        f" WHERE e.nra IN (SELECT x.nra FROM fuente_retc_establecimientos x WHERE x.geom && (SELECT cerca FROM zona))"
        f" AND e.geom IS NOT NULL ORDER BY e.nra, e.anio DESC)"
        f" SELECT u.nra, u.anio, u.actividad, u.sector, {zona_comun.dentro('u.geom')} AS dentro,"
        f" {_PUNTO.format(g='u.geom')} FROM ultimo u WHERE {_EN_CERCA.format(g='u.geom')} ORDER BY u.anio DESC", zona)
    return await cur.fetchall()


async def _retc(conn, zona, cerca_m, lugares):
    filas = await _filas_retc(conn, zona)
    medida = medida_gente(lugares, filas, cerca_m)
    poblacion = _cerca(medida, f"viven a menos de {_n(cerca_m)} m de un establecimiento que reportó al RETC")
    await _contar(conn, medida, filas, lugares, lambda fs: _cuenta(len(fs), "reportó", "reportaron"))
    if not filas:
        return _bloque("retc", [f"Ningún establecimiento reportó al RETC dentro de la zona ni a menos de {_n(cerca_m)} m."],
                       medida=medida)
    dentro = [f for f in filas if f["dentro"]]
    hechos = [f"{_cuenta(len(dentro), 'establecimiento', 'establecimientos')} dentro de la zona y "
              f"{_n(len(filas) - len(dentro))} a menos de {_n(cerca_m)} m de su borde reportaron alguna vez de 2004 a 2022."]
    actividades = {}
    for f in filas:
        a = f["actividad"] or f["sector"] or "sin actividad"
        actividades[a] = actividades.get(a, 0) + 1
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
    return _bloque("retc", hechos, poblacion=poblacion, capa=_capa(filas, _PROPS["retc"]), medida=medida)


async def _anio_fuego(conn) -> int | None:
    """El último año con focos VIIRS en todo el país: una zona sin focos este año tiene
    cero, no "los de 2016"."""
    cur = await _ex(conn, "SELECT extract(year FROM max(fecha))::int AS anio FROM fuente_firms_focos"
                          " WHERE sensor = 'VIIRS_SNPP'", {})
    return (await cur.fetchone())["anio"]


async def _filas_fuego(conn, zona, anio):
    cur = await _ex(conn,
        f"WITH {_partida(zona)} SELECT f.fecha::text AS fecha, f.confianza, f.frp, f.tipo = 2 AS fija,"
        f" {zona_comun.dentro('f.geom')} AS dentro, {_PUNTO.format(g='f.geom')}"
        f" FROM fuente_firms_focos f WHERE f.sensor = 'VIIRS_SNPP'"
        f" AND f.fecha >= make_date(%(anio)s, 1, 1) AND f.fecha < make_date(%(anio)s + 1, 1, 1)"
        f" AND f.geom && (SELECT cerca FROM zona) AND {_EN_CERCA.format(g='f.geom')} ORDER BY f.fecha",
        {**zona, "anio": anio})
    return await cur.fetchall()


async def _fuego(conn, zona, cerca_m, lugares):
    anio = await _anio_fuego(conn)
    if anio is None:
        return _bloque("fuego", ["Sin focos de calor cargados."])
    cur = await _ex(conn,
        f"WITH {_partida(zona)} SELECT extract(year FROM f.fecha)::int AS anio,"
        f" count(*) FILTER (WHERE f.tipo IS DISTINCT FROM 2) AS vegetacion, count(*) FILTER (WHERE f.tipo = 2) AS fija"
        f" FROM zs JOIN fuente_firms_focos f ON f.geom && zs.g AND ST_Intersects(zs.g, f.geom)"
        f" WHERE f.sensor = 'VIIRS_SNPP' GROUP BY 1", zona)
    por_anio = {f["anio"]: f for f in await cur.fetchall()}
    filas = await _filas_fuego(conn, zona, anio)
    focos = [f for f in filas if not f["fija"]]
    hechos = ["Focos dentro de la zona por año: " + ", ".join(
        f"{a}: {_n(por_anio[a]['vegetacion'] if a in por_anio else 0)}" for a in range(anio - 4, anio + 1)) + "."
        if por_anio else f"Ningún foco de calor VIIRS dentro de la zona de 2012 a {anio}."]
    fija = sum(f["fija"] for f in por_anio.values())
    if fija:
        hechos.append(f"Además, {_n(fija)} focos de 2012 a {anio} marcados por FIRMS como fuente fija "
                      "(industria, quema recurrente en el mismo punto).")
    medida = medida_gente(lugares, focos, cerca_m)
    poblacion = _cerca(medida, f"viven a menos de {_n(cerca_m)} m de un foco de {anio}")
    await _contar(conn, medida, focos, lugares, lambda fs: f"{_cuenta(len(fs), 'foco', 'focos')} en {anio}")
    return _bloque("fuego", hechos, fecha=f"2012 a {anio}", poblacion=poblacion if focos else None,
                   capa=_capa(filas, _PROPS["fuego"]), medida=medida)


_METODO_RETC = ("Lo que reporta cada establecimiento obligado, sin verificación pública; los que no están obligados "
                "no aparecen. Se toma el último año que reportó cada uno. Sin nombres: algunos son personas.")
_METODO_FUEGO = ("Un foco es un píxel más caliente que su entorno al paso del satélite: puede ser quema agrícola, "
                 "incendio o industria. No es un incendio confirmado. Confianza baja incluida. La gente cerca no "
                 "cuenta los focos de fuente fija.")


# --- Peligros por polígono o municipio --------------------------------------
async def _municipios_de_la_zona(conn, zona) -> list[tuple[str, str]]:
    if zona["tipo"] == "municipios":
        return [(c[:2], c[2:]) for c in zona["cvegeos"]]
    if zona["tipo"] == "metropoli":
        # Todos los suyos: con la parte mínima de área, la ZMG perdía El Salto y Juanacatlán.
        cur = await _ex(conn, "SELECT unnest(cvegeos) AS c FROM metropolis WHERE clave = %(clave)s", zona)
        return [(f["c"][:2], f["c"][2:]) for f in await cur.fetchall()]
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


async def _capa_acuifero(conn, zona):
    """Los acuíferos que toca la zona, recortados a su alrededor."""
    cur = await _ex(conn,
        f"WITH zona AS ({_zona_sql(zona)}) SELECT a.clave, a.nombre, a.disponibilidad, ST_AsGeoJSON(ST_Simplify("
        " ST_Intersection(a.geom, ST_Expand(ST_Envelope(z.cerca), 0.05)), 0.0005, true), 5) AS gj"
        " FROM fuente_acuiferos a, zona z WHERE a.geom && z.geom AND ST_Intersects(a.geom, z.geom)", zona)
    return _poligonos(await cur.fetchall(), ("clave", "nombre", "disponibilidad"))


async def _medida_acuifero(conn, zona, acuiferos, lugares):
    """% del área de la zona, y de cada municipio, sobre un acuífero sin disponibilidad."""
    # Un borde que apenas roza (0.0 % del área) no cuenta como acuífero de la zona.
    acuiferos = [a for a in acuiferos if a["pct"] > 0]
    sin = [a for a in acuiferos if a["disponibilidad"] <= 0]
    def textos(n, total):
        return {"detalle": f"{_n(n)} de {_cuenta(total, 'acuífero', 'acuíferos')}", "corto": f"{_n(n)} de {_n(total)}"}

    medida = {"tipo": "area", "municipios": {}, "zona": {
        "pct": min(100.0, float(sum(a["pct"] for a in sin))) if acuiferos else None,
        "cuenta": len(sin), **textos(len(sin), len(acuiferos))}}
    cur = await _ex(conn,
        f"WITH zona AS ({_zona_sql(zona)}), m AS MATERIALIZED (SELECT m.cvegeo,"
        " ST_Intersection(coalesce(m.geom_mapa, m.geom), z.geom) AS g FROM municipios m, zona z"
        " WHERE m.cvegeo = ANY(%(muns)s))"
        " SELECT m.cvegeo, count(*) AS total, count(*) FILTER (WHERE a.disponibilidad <= 0) AS sin,"
        " (100 * sum(ST_Area(ST_Intersection(a.geom, m.g))) FILTER (WHERE a.disponibilidad <= 0)"
        "  / max(ST_Area(m.g)))::float AS pct"
        " FROM m JOIN fuente_acuiferos a ON a.geom && m.g AND ST_Intersects(a.geom, m.g)"
        " AND ST_Area(ST_Intersection(a.geom, m.g)) > 0.0005 * ST_Area(m.g) GROUP BY 1",
        {**zona, "muns": lugares["municipios"]})
    for f in await cur.fetchall():
        medida["municipios"][f["cvegeo"]] = {"pct": min(100.0, round(f["pct"] or 0, 2)), "cuenta": f["sin"],
                                             **textos(f["sin"], f["total"])}
    return medida


async def _acuifero(conn, zona, lugares):
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
    return _bloque("acuifero", hechos, capa=await _capa_acuifero(conn, zona),
                   medida=await _medida_acuifero(conn, zona, acuiferos, lugares))


CATEGORIAS_SEQUIA = {"sin": "sin anomalía", "D0": "anormalmente seco", "D1": "sequía moderada", "D2": "sequía severa",
                     "D3": "sequía extrema", "D4": "sequía excepcional"}


def medida_sequia(filas: list[dict]) -> dict:
    """Por municipio, la categoría del último corte y los cortes severos de 5 años. La
    zona entera solo tiene categoría si todos sus municipios tienen la misma."""
    por_mun = {f["cve_ent"] + f["cve_mun"]: {
        "categoria": f["actual"], "texto": CATEGORIAS_SEQUIA[f["actual"]], "severa": f["severa"], "cortes": f["cortes"],
        "detalle": f"{f['severa']} de {f['cortes']} en D2+", "corto": f"{f['severa']} de {f['cortes']}"} for f in filas}
    orden = list(CATEGORIAS_SEQUIA)
    cats = sorted({c["categoria"] for c in por_mun.values()}, key=orden.index)
    if len(por_mun) == 1:
        zona = dict(next(iter(por_mun.values())))
    else:
        zona = {"categoria": cats[0] if len(cats) == 1 else None, "rango": [cats[0], cats[-1]] if cats else None,
                "texto": CATEGORIAS_SEQUIA[cats[0]] if len(cats) == 1 else None, "detalle": None}
    return {"tipo": "categoria", "zona": zona, "municipios": por_mun}


async def _filas_sequia(conn, municipios):
    cur = await _ex(conn,
        "WITH u AS (SELECT max(fecha) AS f FROM fuente_sequia_municipal)"
        " SELECT s.cve_ent, s.cve_mun, max(s.fecha)::text AS ultima,"
        " (array_agg(s.categoria ORDER BY s.fecha DESC))[1] AS actual,"
        " count(*) FILTER (WHERE s.fecha > u.f - interval '5 years') AS cortes,"
        " count(*) FILTER (WHERE s.fecha > u.f - interval '5 years' AND s.categoria IN ('D2','D3','D4')) AS severa"
        " FROM fuente_sequia_municipal s, u"
        " WHERE (s.cve_ent, s.cve_mun) IN (SELECT * FROM unnest(%(e)s::text[], %(m)s::text[])) GROUP BY 1, 2 ORDER BY 1, 2",
        {"e": [e for e, _ in municipios], "m": [m for _, m in municipios]})
    return await cur.fetchall()


async def _capa_sequia(conn, filas):
    cats = {f["cve_ent"] + f["cve_mun"]: f for f in filas}
    return {"type": "FeatureCollection", "total": len(filas), "features": [
        {"type": "Feature", "geometry": m["geometry"], "properties": {
            "nombre": m["nombre"], "categoria": cats[m["cvegeo"]]["actual"], "fecha": cats[m["cvegeo"]]["ultima"],
            "texto": CATEGORIAS_SEQUIA[cats[m["cvegeo"]]["actual"]]}}
        for m in await zona_comun.limites(conn, list(cats))]}


async def _sequia(conn, municipios, nombres):
    if not municipios:
        return _bloque("sequia", ["La zona no tiene localidades: no se sabe a qué municipio pertenece."], fecha="")
    filas = await _filas_sequia(conn, municipios)
    hechos = [f"{nombres.get((f['cve_ent'], f['cve_mun']), f['cve_ent'] + f['cve_mun'])}: {CATEGORIAS_SEQUIA[f['actual']]} "
              f"al {f['ultima']}; {f['severa']} de {f['cortes']} cortes de los últimos 5 años en sequía severa o peor."
              for f in filas]
    fecha = filas[0]["ultima"] if filas else ""
    return _bloque("sequia", hechos or ["El Monitor no trae estos municipios."], fecha=f"2003 a {fecha}" if filas else "",
                   capa=await _capa_sequia(conn, filas) if filas else None,
                   medida=medida_sequia(filas) if filas else None)


_METODO_SEQUIA = ("Categoría del Monitor asignada al municipio entero en cada corte (quincenal). Severa o peor es D2 a D4. "
                  "Si la zona toca varios municipios, uno por renglón.")


async def _capa_anp(conn, zona):
    """Las ANP que se ven alrededor de la zona, recortadas."""
    cur = await _ex(conn,
        f"WITH zona AS ({_zona_sql(zona)}) SELECT a.nombre, a.categoria, ST_AsGeoJSON(ST_Simplify(ST_Intersection("
        " a.geom, ST_Expand(ST_Envelope(z.cerca), 0.1)), 0.0005, true), 5) AS gj"
        " FROM fuente_anp a, zona z WHERE a.geom && ST_Expand(ST_Envelope(z.cerca), 0.1)"
        " AND ST_Intersects(a.geom, ST_Expand(ST_Envelope(z.cerca), 0.1))", zona)
    return _poligonos(await cur.fetchall(), ("nombre", "categoria"))


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
    return _bloque("anp", hechos, capa=await _capa_anp(conn, zona))


async def _uso_suelo(conn, zona):
    cur = await _ex(conn, 
        # Los polígonos son enormes: primero a la caja de la zona, luego contra sus pedazos.
        # `t` materializada: si no, el área de la zona se calculaba por renglón (25 s).
        f"WITH {_partida(zona)}, t AS MATERIALIZED (SELECT ST_Area(geom::geography) AS a FROM zona),"
        " u AS MATERIALIZED (SELECT s.serie, s.descripcion, ST_ClipByBox2D(s.geom, z.geom::box2d) AS geom"
        "  FROM fuente_uso_suelo s, zona z WHERE s.geom && z.geom),"
        " p AS MATERIALIZED (SELECT u.serie, u.descripcion, ST_Intersection(u.geom, zs.g) AS g"
        "  FROM zs JOIN u ON u.geom && zs.g AND ST_Intersects(u.geom, zs.g))"
        " SELECT serie, descripcion, round((100 * sum(ST_Area(g::geography)) / t.a)::numeric, 1) AS pct"
        " FROM p, t GROUP BY 1, 2, t.a ORDER BY 1 DESC, 3 DESC", zona)
    filas = await cur.fetchall()
    if not filas:
        return _bloque("uso_suelo", ["Sin uso de suelo cargado para la zona."], fecha="")
    s7 = [f for f in filas if f["serie"] == 7]
    s6 = {f["descripcion"]: f["pct"] for f in filas if f["serie"] == 6}
    hechos = ["Serie VII (2018): " + "; ".join(f"{f['descripcion'].lower()} {f['pct']} %" for f in s7[:6]) + "."]
    agricola = lambda fs: sum(float(f["pct"]) for f in fs if "AGR" in f["descripcion"].upper())
    a7, a6 = agricola(s7), agricola([f for f in filas if f["serie"] == 6])
    if s6:
        hechos.append(f"Agricultura (riego, temporal y humedad): {a6:.1f} % en la serie VI (2014) y {a7:.1f} % en la VII (2018).")
    return _bloque("uso_suelo", hechos)


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
        return _bloque("agricultura", [f"El SIAP no reporta siembra en {lugar}."], fecha="")
    anio = filas[0]["anio"]
    hechos = [f"{lugar}, {anio}: " + "; ".join(
        f"{f['cultivo'].lower()} de {f['modalidad'].lower()} {_n(f['ha'])} ha" for f in filas) + "."]
    return _bloque("agricultura", hechos, fecha=str(anio))


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
        return _bloque("defunciones", [f"Sin defunciones registradas de residentes de {lugar}."], fecha="")

    def tasa(k):
        return f" ({k * 100_000 / pob:,.0f} por 100 mil)" if pob else ""

    hechos = [f"Residentes de {lugar} (población 2020: {_n(pob)})."]
    hechos += [f"{f['anio']}: {_n(f['total'])} en total{tasa(f['total'] or 0)}; tumores {_n(f['tumores'] or 0)}, "
               f"renales {_n(f['renales'] or 0)}, respiratorias {_n(f['respiratorias'] or 0)}." for f in filas]
    return _bloque("defunciones", hechos, fecha=f"{filas[0]['anio']} a {filas[-1]['anio']}")


_METODO_DEFUN = ("Por municipio de residencia y año de registro, sin ajustar por edad. Tumores es C00 a D48, renales "
                 "N00 a N29 y respiratorias el capítulo J de la CIE-10. Es contexto: no dice que la causa sea ambiental.")


_METODO_AGUA = {tipo: (
    "Semáforo de Conagua tal cual. Cada sitio resume sus mediciones de 2012 a 2025 (mediana o media geométrica según el "
    f"parámetro). Incumplir es calificar como {', '.join(incumple)}. La red no mide plaguicidas.")
    for tipo, incumple in (("superficial", INCUMPLE_SUPERFICIAL), ("subterranea", INCUMPLE_SUBTERRANEA))}


def _ficha(titulo, fuente, fecha, nivel, metodo):
    return {"titulo": titulo, "fuente": fuente, "fecha": fecha, "nivel": nivel, "metodo": metodo}


FICHAS = {
    "agua_superficial": _ficha("Calidad del agua superficial", "Conagua, RENAMECA", "2012 a 2025",
                               "punto (sitio de monitoreo)", _METODO_AGUA["superficial"]),
    "agua_subterranea": _ficha("Calidad del agua subterránea", "Conagua, RENAMECA", "2012 a 2025",
                               "punto (sitio de monitoreo)", _METODO_AGUA["subterranea"]),
    "descargas": _ficha("Descargas de aguas residuales con permiso", "Conagua, REPDA", "títulos vigentes al 2026-11-13",
                        "punto (descarga declarada)", "Lo permitido en el título, no lo medido ni su calidad. Las "
                        "descargas sin título no están. El volumen incluye agua de enfriamiento."),
    "retc": _ficha("Establecimientos que reportan emisiones", "SEMARNAT, RETC", "2004 a 2022", "punto (establecimiento)",
                   _METODO_RETC),
    "fuego": _ficha("Focos de calor", "NASA FIRMS, VIIRS S-NPP", "", "punto (píxel de 375 m)", _METODO_FUEGO),
    "acuifero": _ficha("Agua subterránea disponible", "Conagua", "DOF 2023-11-09 (corte 2022); piezometría 1996 a 2023",
                       "acuífero", "Balance de Conagua: disponibilidad = recarga − descarga natural comprometida − "
                       "extracción. Es administrativo, no una medición del nivel."),
    "sequia": _ficha("Sequía", "SMN, Monitor de Sequía", "", "municipio", _METODO_SEQUIA),
    "anp": _ficha("Áreas naturales protegidas federales", "CONANP vía CONABIO (CC BY-NC 2.5 MX)", "2020-08", "polígono",
                  "Solo federales; las estatales y municipales no están cargadas."),
    "uso_suelo": _ficha("Uso de suelo y vegetación", "INEGI vía CONABIO (CC BY-NC 2.5 MX)", "2014 y 2018",
                        "polígono 1:250 000", _METODO_USO),
    "agricultura": _ficha("Qué se siembra", "SIAP", "", "municipio", _METODO_AGRI),
    "defunciones": _ficha("Defunciones registradas", "INEGI, estadísticas de defunciones registradas", "",
                          "municipio de residencia", _METODO_DEFUN),
}

# Los peligros que se dibujan (el acetato "Riesgos" de /mapa).
PELIGROS = ("agua_superficial", "agua_subterranea", "descargas", "retc", "fuego", "acuifero", "sequia", "anp")


def peligros_validos(texto: str) -> list[str]:
    claves = list(dict.fromkeys(texto.split(",")))
    if not all(c in PELIGROS for c in claves):
        raise ZonaInvalida(f"peligros es una lista de {', '.join(PELIGROS)}")
    return claves


# --- Todo junto ------------------------------------------------------------
async def _preparada(conn, zona: dict, cerca_m: int) -> dict | None:
    # Son muchas consultas cortas con geometría: compilarlas (JIT) tardaba más que correrlas.
    await conn.execute("SET LOCAL jit = off")
    km2 = await zona_comun.area_km2(conn, zona)
    if km2 is None:
        return None
    if motivo := zona_comun.demasiado_grande(km2):
        raise ZonaInvalida(motivo)
    zona = await preparar(conn, zona, cerca_m)
    return zona and {**zona, "km2": km2}


async def capas(zona: dict, cerca_m: int, peligros: list[str]) -> dict | None:
    """Solo lo que se dibuja de cada peligro, sin contar gente."""
    pool = await get_pool()
    async with pool.connection() as conn:
        zona = await _preparada(conn, zona, cerca_m)
        if zona is None:
            return None
        salida = []
        for clave in peligros:
            fecha = None
            if clave.startswith("agua_"):
                datos = _capa(await _filas_agua(conn, zona, clave.removeprefix("agua_")), _PROPS[clave])
            elif clave == "descargas":
                datos = _capa(await _filas_descargas(conn, zona), _PROPS[clave])
            elif clave == "retc":
                datos = _capa(await _filas_retc(conn, zona), _PROPS[clave])
            elif clave == "fuego":
                anio = await _anio_fuego(conn)
                datos = _capa(await _filas_fuego(conn, zona, anio) if anio else [], _PROPS[clave])
                fecha = str(anio or "")
            elif clave == "acuifero":
                datos = await _capa_acuifero(conn, zona)
            elif clave == "sequia":
                filas = await _filas_sequia(conn, await _municipios_de_la_zona(conn, zona))
                datos = await _capa_sequia(conn, filas)
                fecha = filas[0]["ultima"] if filas else ""
            else:
                datos = await _capa_anp(conn, zona)
            ficha = FICHAS[clave]
            salida.append({"clave": clave, **ficha, "fecha_dato": ficha["fecha"] if fecha is None else fecha,
                           "datos": datos})
    return {"cerca_m": cerca_m, "capas": salida}


async def resumen(zona: dict, cerca_m: int) -> dict | None:
    pool = await get_pool()
    async with pool.connection() as conn:
        zona = await _preparada(conn, zona, cerca_m)
        if zona is None:
            return None
        cur = await _ex(conn,
            f"WITH zona AS ({_zona_sql(zona)})"
            " SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0005), 5) AS gj FROM zona", zona)
        z = await cur.fetchone()
        if z is None or z["gj"] is None:
            return None
        municipios = await _municipios_de_la_zona(conn, zona)
        nombres = await _nombres(conn, municipios)
        claves = [e + m for e, m in municipios]
        limites = zona_comun.limites_geojson(await zona_comun.limites(conn, claves))
        lugares = {"todas": await _unidades(conn, zona), "municipios": claves}
        bloques = [
            await _agua(conn, zona, cerca_m, "superficial", lugares),
            await _agua(conn, zona, cerca_m, "subterranea", lugares),
            await _descargas(conn, zona, cerca_m, lugares),
            await _retc(conn, zona, cerca_m, lugares),
            await _fuego(conn, zona, cerca_m, lugares),
            await _acuifero(conn, zona, lugares),
            await _sequia(conn, municipios, nombres),
            await _anp(conn, zona),
            await _uso_suelo(conn, zona),
            await _agricultura(conn, municipios, nombres),
            await _defunciones(conn, municipios, nombres),
        ]
    visible = {k: v for k, v in zona.items() if k in ("tipo", "lon", "lat", "radio_m")}
    return {"zona": {**visible, "clave": zona_comun.clave(zona), "geojson": json.loads(z["gj"]),
                     "km2": round(zona["km2"], 1), "limites": limites,
                     "municipios": [{"cvegeo": e + m, "cve_ent": e, "cve_mun": m, "nombre": nombres.get((e, m)),
                                     "poblacion": _personas([u for u in lugares["todas"] if u["mun"] == e + m])}
                                    for e, m in municipios]},
            "cerca_m": cerca_m, "poblacion": _poblacion(lugares["todas"]),
            "metodo_poblacion": ("AGEB urbanos con su censo 2020 donde están cargados (su punto interior dentro de la "
                                 "zona); en el resto, el punto de cada localidad del ITER 2020. '*' de INEGI son "
                                 "valores reservados: se cuentan aparte, no como cero."),
            "bloques": [b for b in bloques if b is not None]}
