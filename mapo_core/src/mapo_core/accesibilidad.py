"""Accesibilidad a servicios (sesión 26): cuánta gente vive a más de N minutos, a pie
o en auto, de cada servicio. Ver docs/producto/accesibilidad.md.

Reglas: cada servicio por separado y con su grupo de población (primaria: de 6 a
11 años), nunca un índice. El umbral lo mueve quien consulta: se guardan los
minutos de cada lugar y la consulta regresa, por servicio, cuánta gente queda a
m minutos o menos para cada m de 0 a `MAX_MINUTOS`; la pantalla resta.

Los minutos se calculan una vez por estado (`cli accesibilidad`), no al consultar:
son cientos de miles de rutas. Los lugares son los mismos que en /riesgos: el AGEB
urbano con censo (desde un punto dentro) y, donde no hay AGEB, el punto de la
localidad del ITER. Los destinos de cada servicio se guardan con la carga, para
poder decir cuál fue el más cercano.
"""

from __future__ import annotations

import csv
import datetime
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from scipy.spatial import cKDTree

from mapo_core import rubros, transporte
from mapo_core.osrm_client import OSRMClient
from mapo_core.zonas import minutos_por_calle, plano

MAX_MINUTOS = 120
# Destinos por lugar, los más cercanos en línea recta (como el buscador).
VECINOS = 10
# El tramo del punto al camino más cercano se suma a paso de peatón (foot.lua: 5 km/h).
ACERCAMIENTO_KMH = 5.0
MODOS = {"pie": "a pie", "auto": "en auto"}
# Datos de OSM con que se preparó cada OSRM (docs/fuentes/osrm.md).
RED = {
    "pie": "OSM de Geofabrik del 2026-11-20, perfil foot.lua de OSRM 26.7.3 (5 km/h)",
    "auto": "OSM de Geofabrik del 2026-08-01, perfil car.lua de OSRM 26.7.3 (sin tráfico)",
}


@dataclass(frozen=True)
class Servicio:
    clave: str
    titulo: str
    grupo: str  # variable del censo y del ITER
    grupo_etiqueta: str
    fuente: str  # clues | denue | estaciones | gtfs
    filtro: dict = field(default_factory=dict)
    modos: tuple[str, ...] = ("pie", "auto")
    # Solo desde AGEB urbanos: la fuente no registra el servicio fuera de ellos.
    solo_agebs: bool = False
    # Solo en los municipios donde la fuente tiene destinos: un GTFS cubre unas
    # ciudades, y fuera de ellas sí hay camiones que no están en ningún feed.
    solo_cobertura: bool = False


def _clases(rubros_publicos: tuple[str, ...]) -> list[str]:
    return sorted(c for c, x in rubros.clases().items() if x.rubro in rubros_publicos and x.sector_publico)


SERVICIOS = {s.clave: s for s in (
    # Atiende a quien llegue, con o sin seguridad social: Secretaría de Salud,
    # IMSS-Bienestar, servicios estatales y municipales.
    Servicio("centro_salud", "Centro de salud", "POBTOT", "personas", "clues",
             {"tipo": "DE CONSULTA EXTERNA", "instituciones": ("SSA", "IMB", "IMO", "SME", "SMM")}),
    # La clínica del IMSS solo atiende a sus afiliados: se cuenta a esa gente.
    Servicio("umf_imss", "Clínica del IMSS", "PDER_IMSS", "personas afiliadas al IMSS", "clues",
             {"tipo": "DE CONSULTA EXTERNA", "instituciones": ("IMS",)}),
    Servicio("hospital_publico", "Hospital público", "POBTOT", "personas", "clues",
             {"tipo": "DE HOSPITALIZACIÓN", "instituciones": ("SSA", "IMB", "IMO", "SME", "SMM", "IMS", "IST")}),
    # DENUE trae casi todas las escuelas públicas de las ciudades y casi ninguna
    # del campo (Mezquitic: 5 de las 218 de básica que cuenta la SEP en 2025-2026;
    # Guadalajara: 801 de 873). Fuera de los AGEB no se calcula: se diría que una
    # ranchería está a horas de la escuela que tiene. Ver docs/producto/accesibilidad.md.
    Servicio("preescolar_publico", "Preescolar pública", "P_3A5", "personas de 3 a 5 años", "denue",
             {"rubros": ("preescolar",)}, solo_agebs=True),
    Servicio("primaria_publica", "Primaria pública", "P_6A11", "personas de 6 a 11 años", "denue",
             {"rubros": ("primaria",)}, solo_agebs=True),
    Servicio("secundaria_publica", "Secundaria pública", "P_12A14", "personas de 12 a 14 años", "denue",
             {"rubros": ("secundaria",)}, solo_agebs=True),
    Servicio("media_superior_publica", "Bachillerato público", "P_15A17", "personas de 15 a 17 años", "denue",
             {"rubros": ("preparatoria",)}, solo_agebs=True),
    Servicio("supermercado", "Supermercado", "POBTOT", "personas", "denue",
             {"clases": ("Comercio al por menor en supermercados",)}),
    # A una estación se llega a pie: en auto no dice nada que sirva.
    Servicio("transporte_masivo", "Estación de transporte masivo", "POBTOT", "personas", "estaciones",
             modos=("pie",)),
    # Sesión 27: paradas de los GTFS (docs/fuentes/gtfs.md). La frecuente es donde
    # alguna ruta pasa cada 15 minutos o menos de 7 a 9 de un día hábil.
    Servicio("parada_transporte", "Parada de transporte público", "POBTOT", "personas", "gtfs",
             {"frecuente": False}, modos=("pie",), solo_cobertura=True),
    Servicio("parada_frecuente", "Parada con paso cada 15 minutos o menos", "POBTOT", "personas", "gtfs",
             {"frecuente": True}, modos=("pie",), solo_cobertura=True),
)}


# Unidades que no son un lugar fijo de consulta general.
TIPOLOGIAS_FUERA = ("UNIDAD MÓVIL", "UNIDAD DE ESPECIALIDADES MÉDICAS (UNEMES)")


class ErrorDeRed(Exception):
    """OSRM no respondió a un lote ni tras reintentar: no se guarda nada a medias."""


class ConsultaInvalida(ValueError):
    pass


# ---------------------------------------------------------------- carga por estado

_LUGARES_SQL = """
SELECT a.cvegeo AS clave, 'ageb' AS tipo, a.cve_mun, ST_Y(p.punto) AS lat, ST_X(p.punto) AS lon
FROM agebs a JOIN fuente_censo_poblacion c ON c.cvegeo = a.cvegeo
CROSS JOIN LATERAL (SELECT ST_PointOnSurface(a.geom) AS punto) p
WHERE a.cve_ent = %(e)s AND a.geom IS NOT NULL
UNION ALL
SELECT l.cvegeo, 'localidad', l.cve_mun, ST_Y(l.geom), ST_X(l.geom)
FROM localidades l
WHERE l.cve_ent = %(e)s AND coalesce(l.pobtot, 1) > 0
  AND NOT EXISTS (SELECT 1 FROM agebs a WHERE a.geom && l.geom AND ST_Covers(a.geom, l.geom))
"""


async def lugares(pool: AsyncConnectionPool, cve_ent: str) -> list[dict]:
    """Origenes del estado, ordenados por celda de ~5 km para que cada lote de
    OSRM comparta vecinos (matrices chicas)."""
    async with pool.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        await cur.execute(_LUGARES_SQL, {"e": cve_ent})
        filas = await cur.fetchall()
    return sorted(filas, key=lambda f: (int(f["lat"] * 20), int(f["lon"] * 20), f["clave"]))


async def destinos(pool: AsyncConnectionPool, cve_ent: str, s: Servicio,
                   estaciones: Path | None = None) -> tuple[list[dict], str, list[str]]:
    """(destinos, fuente con fecha, avisos). Un destino fuera de su lugar (del estado;
    en el CLUES, de su municipio) se descarta y se dice: es una coordenada mal capturada."""
    avisos: list[str] = []
    async with pool.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        if s.fuente == "clues":
            await cur.execute(
                # La coordenada tiene que caer a 1 km o menos del municipio que declara, o en
                # uno cuyo nombre lleve la unidad: el CLUES a veces trae mal la clave
                # ("UMF 82 Unión de Tula" con la clave de otro municipio) y a veces la
                # coordenada ("UMF 55 Guadalajara" en Tuxcueca). Ver docs/fuentes/clues.md.
                """SELECT c.clues AS id, c.nombre || ' (' || c.cve_institucion || ')' AS nombre, c.lat, c.lon,
                          ST_DWithin(m.geom::geography, c.geom::geography, 1000) OR EXISTS (
                            SELECT 1 FROM municipios m2 WHERE m2.cve_ent = c.cve_ent AND ST_Covers(m2.geom, c.geom)
                              AND upper(unaccent(c.nombre)) LIKE '%%' || upper(unaccent(m2.nombre)) || '%%'
                          ) AS dentro, c.corte
                   FROM fuente_clues c JOIN municipios m ON m.cve_ent = c.cve_ent AND m.cve_mun = c.cve_mun
                   WHERE c.cve_ent = %(e)s AND c.tipo = %(tipo)s AND c.estatus = 'EN OPERACION'
                     AND c.cve_institucion = ANY(%(inst)s) AND c.geom IS NOT NULL
                     AND c.unidad_movil = '' AND c.tipologia <> ALL(%(fuera)s)""",
                {"e": cve_ent, "tipo": s.filtro["tipo"], "inst": list(s.filtro["instituciones"]),
                 "fuera": list(TIPOLOGIAS_FUERA)})
            filas = await cur.fetchall()
            corte = filas[0]["corte"] if filas else "sin cargar"
            fuente = (f"CLUES de la Secretaría de Salud (DGIS), corte {corte}; en operación y fijas de"
                      f" {', '.join(s.filtro['instituciones'])}")
        elif s.fuente == "denue":
            clases = list(s.filtro.get("clases") or _clases(s.filtro["rubros"]))
            await cur.execute(
                """SELECT d.id, coalesce(d.nombre, '') AS nombre, d.lat::float8 AS lat, d.lon::float8 AS lon,
                          ST_Covers(e.geom, ST_SetSRID(ST_MakePoint(d.lon, d.lat), 4326)) AS dentro,
                          d.actualizado::date::text AS cargado
                   FROM fuente_denue_negocios d JOIN entidades e ON e.cve_ent = d.cve_ent
                   WHERE d.cve_ent = %(e)s AND d.clase_actividad = ANY(%(clases)s)
                     AND d.lat IS NOT NULL AND d.lon IS NOT NULL""",
                {"e": cve_ent, "clases": clases})
            filas = await cur.fetchall()
            fuente = f"DENUE de INEGI, cargado el {filas[0]['cargado'] if filas else 'sin cargar'}"
        elif s.fuente == "gtfs":
            # Los feeds que dan una parada por ruta repiten el punto: se juntan a ~10 m.
            await cur.execute(
                """SELECT 'p' || round(p.lat::numeric, 4) || ',' || round(p.lon::numeric, 4) AS id,
                          min(p.nombre) AS nombre, avg(p.lat) AS lat, avg(p.lon) AS lon, true AS dentro,
                          string_agg(DISTINCT p.feed, ',') AS feeds
                   FROM transporte_paradas p JOIN transporte_feeds f USING (feed)
                   WHERE p.cve_ent = %(e)s AND p.feed <> 'osm'
                     AND (NOT %(frecuente)s OR (f.frecuencia_util AND p.pasadas_ruta_max >= %(minimo)s))
                   GROUP BY 1""",
                {"e": cve_ent, "frecuente": s.filtro["frecuente"], "minimo": transporte.pasadas_frecuente()})
            filas = await cur.fetchall()
            feeds = sorted({f for r in filas for f in r["feeds"].split(",")})
            await cur.execute(
                "SELECT feed, fecha_ref::text AS ref FROM transporte_feeds WHERE feed = ANY(%(f)s) ORDER BY feed",
                {"f": feeds})
            fuente = "GTFS " + "; ".join(f"{r['feed']} (frecuencias del {r['ref']})" for r in await cur.fetchall())
        else:
            if estaciones is None:
                return [], "", ["sin archivo de estaciones (--estaciones)"]
            with open(estaciones, encoding="utf-8", newline="") as fh:
                crudas = list(csv.DictReader(fh))
            await cur.execute(
                """SELECT ST_Covers(e.geom, ST_SetSRID(ST_MakePoint(x.lon, x.lat), 4326)) AS dentro
                   FROM unnest(%(lon)s::float8[], %(lat)s::float8[]) AS x(lon, lat), entidades e
                   WHERE e.cve_ent = %(e)s""",
                {"e": cve_ent, "lon": [float(r["lon"]) for r in crudas], "lat": [float(r["lat"]) for r in crudas]})
            dentro = [r["dentro"] for r in await cur.fetchall()]
            filas = [{"id": f"{r['red']}|{r['nombre']}", "nombre": f"{r['nombre']} ({r['red']})",
                      "lat": float(r["lat"]), "lon": float(r["lon"]), "dentro": d}
                     for r, d in zip(crudas, dentro)]
            fecha = datetime.date.fromtimestamp(estaciones.stat().st_mtime).isoformat()
            redes = sorted({r["red"] for r in crudas})
            fuente = f"OpenStreetMap ({estaciones.name}, {fecha}): {', '.join(redes)}"
    fuera = [f for f in filas if not f["dentro"]]
    if fuera:
        avisos.append(f"{len(fuera)} con la coordenada fuera de su lugar, descartados: "
                      + ", ".join(sorted(f["id"] for f in fuera)[:20]))
    # Un mismo id puede repetirse en las estaciones (dos líneas en la misma parada).
    unicos = {f["id"]: f for f in filas if f["dentro"]}
    return list(unicos.values()), fuente, avisos


async def cobertura(pool: AsyncConnectionPool, cve_ent: str) -> set[str]:
    """Municipios del estado con paradas de algún GTFS."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT DISTINCT cve_mun FROM transporte_paradas WHERE cve_ent = %s AND feed <> 'osm' AND cve_mun IS NOT NULL",
            (cve_ent,))
        return {r[0] for r in await cur.fetchall()}


def vecinos_en_linea(origenes: list[dict], dest: list[dict], k: int = VECINOS) -> tuple[np.ndarray, np.ndarray]:
    """(metros al más cercano en línea recta, índices de los k más cercanos)."""
    lat = np.array([o["lat"] for o in origenes], dtype=float)
    lon = np.array([o["lon"] for o in origenes], dtype=float)
    d_lat = np.array([d["lat"] for d in dest], dtype=float)
    d_lon = np.array([d["lon"] for d in dest], dtype=float)
    lat_media = float(lat.mean())
    k = min(k, len(dest))
    distancias, indices = cKDTree(plano(d_lat, d_lon, lat_media)).query(plano(lat, lon, lat_media), k=k)
    distancias = distancias.reshape(len(origenes), k)
    return distancias[:, 0] * 1000, indices.reshape(len(origenes), k)


async def cargar_estado(
    pool: AsyncConnectionPool,
    cve_ent: str,
    clientes: dict[str, OSRMClient],
    *,
    servicios: list[str] | None = None,
    estaciones: Path | None = None,
    a_la_vez: int = 6,
    avisar=print,
) -> list[dict]:
    """Calcula y guarda los minutos de todo el estado, servicio por servicio y modo
    por modo. Cada (servicio, modo) se guarda en su propia transacción: si OSRM
    falla a medias, lo ya guardado se queda y lo demás conserva su carga anterior."""
    todos = await lugares(pool, cve_ent)
    if not todos:
        raise ConsultaInvalida(f"el estado {cve_ent} no tiene AGEB ni localidades cargados")
    resumen = []
    for clave in servicios or list(SERVICIOS):
        s = SERVICIOS[clave]
        origenes = [o for o in todos if o["tipo"] == "ageb"] if s.solo_agebs else todos
        if s.solo_cobertura:
            cubiertos = await cobertura(pool, cve_ent)
            origenes = [o for o in origenes if o["cve_mun"] in cubiertos]
            if not origenes:
                avisar(f"{clave}: ningún municipio del estado tiene paradas de un GTFS, no se calcula")
                continue
        coords = [(o["lat"], o["lon"]) for o in origenes]
        dest, fuente, avisos = await destinos(pool, cve_ent, s, estaciones)
        if not dest:
            avisar(f"{clave}: sin destinos ({'; '.join(avisos) or 'ninguno en el estado'}), no se calcula")
            continue
        linea_m, vecinos = vecinos_en_linea(origenes, dest)
        dest_latlon = np.array([(d["lat"], d["lon"]) for d in dest], dtype=float)
        async with pool.connection() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM accesibilidad_destinos WHERE cve_ent = %s AND servicio = %s",
                                   (cve_ent, clave))
                async with conn.cursor() as cur:
                    async with cur.copy("COPY accesibilidad_destinos (cve_ent, servicio, id, nombre, lat, lon)"
                                        " FROM STDIN") as copia:
                        for d in dest:
                            await copia.write_row([cve_ent, clave, d["id"], d["nombre"], d["lat"], d["lon"]])
        for modo in s.modos:
            if modo not in clientes:
                continue
            inicio = time.monotonic()
            tiempos = await minutos_por_calle(clientes[modo], coords, dest_latlon, vecinos, a_la_vez=a_la_vez,
                                              reintentos=3, acercamiento_kmh=ACERCAMIENTO_KMH)
            if tiempos is None:
                raise ErrorDeRed(f"{clave} {modo}: OSRM no respondió; lo calculado antes se conserva")
            sin_ruta = sum(t is None for t, _ in tiempos)
            async with pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "DELETE FROM accesibilidad_minutos WHERE cve_ent = %s AND servicio = %s AND modo = %s",
                        (cve_ent, clave, modo))
                    async with conn.cursor() as cur:
                        async with cur.copy("COPY accesibilidad_minutos (cve_ent, servicio, modo, clave, cve_mun,"
                                            " minutos, destino, linea_m) FROM STDIN") as copia:
                            for o, (t, i), lm in zip(origenes, tiempos, linea_m):
                                await copia.write_row([cve_ent, clave, modo, o["clave"], o["cve_mun"], t,
                                                       None if i is None else dest[i]["id"], round(float(lm), 1)])
                    segundos = round(time.monotonic() - inicio, 1)
                    await conn.execute(
                        """INSERT INTO accesibilidad_cargas (cve_ent, servicio, modo, origenes, destinos, sin_ruta,
                                                             fuente, red, segundos)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (cve_ent, servicio, modo) DO UPDATE SET origenes = EXCLUDED.origenes,
                             destinos = EXCLUDED.destinos, sin_ruta = EXCLUDED.sin_ruta, fuente = EXCLUDED.fuente,
                             red = EXCLUDED.red, segundos = EXCLUDED.segundos, actualizado = now()""",
                        (cve_ent, clave, modo, len(origenes), len(dest), sin_ruta, fuente, RED[modo], segundos))
            fila = {"servicio": clave, "modo": modo, "origenes": len(origenes), "destinos": len(dest),
                    "sin_ruta": sin_ruta, "segundos": segundos, "avisos": avisos}
            avisar(json.dumps(fila, ensure_ascii=False))
            resumen.append(fila)
    return resumen


# ---------------------------------------------------------------- consulta

def modo_valido(modo) -> str:
    if modo not in MODOS:
        raise ConsultaInvalida(f"modo es uno de {', '.join(MODOS)}")
    return modo


def _valor(d: dict, clave: str) -> int | None:
    v = (d or {}).get(clave)
    if isinstance(v, int):
        return v
    return int(v) if isinstance(v, str) and v.isdigit() else None


def curva(filas: list[tuple[int | None, float | None]]) -> dict:
    """filas = (personas, minutos). `dentro[m]` = personas a m minutos o menos.
    Personas `None` es un dato reservado por INEGI: se cuenta aparte, no como cero."""
    por_minuto = [0] * (MAX_MINUTOS + 1)
    total = reservados = sin_ruta = 0
    for personas, minutos in filas:
        if personas is None:
            reservados += 1
            continue
        total += personas
        if minutos is None:
            sin_ruta += personas
        elif minutos <= MAX_MINUTOS:
            por_minuto[max(0, math.ceil(minutos))] += personas
    return {"total": total, "reservados": reservados, "sin_ruta": sin_ruta,
            "dentro": np.cumsum(por_minuto).tolist()}


def metodo(s: Servicio, modo: str) -> str:
    extra = ""
    if s.fuente == "gtfs":
        extra = (" Las paradas del GTFS en el mismo punto (a unos 10 m) cuentan como una."
                 + (f" Frecuente: alguna ruta pasa {transporte.pasadas_frecuente()} veces o más de 7 a 9 de la mañana"
                    f" de un miércoles (cada {transporte.FRECUENTE_MIN} minutos o menos); los feeds con frecuencia de"
                    " relleno no cuentan." if s.filtro.get("frecuente") else "")
                 + " Solo en los municipios con paradas en algún GTFS.")
    origen = ("Toda la gente de un AGEB urbano cuenta en un punto dentro de él (censo 2020); las localidades sin"
              " AGEB no se calculan, porque DENUE casi no registra sus escuelas." if s.solo_agebs else
              "Toda la gente de un AGEB urbano cuenta en un punto dentro de él; donde no hay AGEB, en el punto"
              " de su localidad (censo 2020).")
    return (f"Minutos {MODOS[modo]} por calle con OSRM desde ese punto a los {VECINOS} destinos más cercanos en"
            f" línea recta; se toma el menor. El tramo del punto al camino se suma a {ACERCAMIENTO_KMH:.0f} km/h."
            f" {origen} Solo destinos del mismo estado.{extra}")


async def zona(pool: AsyncConnectionPool, cve_ent: str, cve_mun: str, modo: str) -> dict | None:
    """Un municipio: por servicio, la curva de su grupo de población, y el plano con
    los minutos de cada lugar. None si el municipio no está cargado."""
    async with pool.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        await cur.execute(
            """SELECT nombre, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0005), 5) AS gj
               FROM municipios WHERE cve_ent = %(e)s AND cve_mun = %(m)s""", {"e": cve_ent, "m": cve_mun})
        mun = await cur.fetchone()
        if mun is None:
            return None
        await cur.execute(
            """SELECT a.cvegeo AS clave, 'ageb' AS tipo, c.datos_json AS d,
                      ST_AsGeoJSON(ST_SimplifyPreserveTopology(a.geom, 0.0001), 5) AS gj
               FROM agebs a JOIN fuente_censo_poblacion c ON c.cvegeo = a.cvegeo
               WHERE a.cve_ent = %(e)s AND a.cve_mun = %(m)s AND a.geom IS NOT NULL
               UNION ALL
               SELECT l.cvegeo, 'localidad', l.datos, ST_AsGeoJSON(l.geom, 5)
               FROM localidades l
               WHERE l.cve_ent = %(e)s AND l.cve_mun = %(m)s AND coalesce(l.pobtot, 1) > 0
                 AND NOT EXISTS (SELECT 1 FROM agebs a WHERE a.geom && l.geom AND ST_Covers(a.geom, l.geom))""",
            {"e": cve_ent, "m": cve_mun})
        lugares_zona = await cur.fetchall()
        await cur.execute(
            """SELECT servicio, clave, minutos, destino FROM accesibilidad_minutos
               WHERE cve_ent = %(e)s AND cve_mun = %(m)s AND modo = %(modo)s""",
            {"e": cve_ent, "m": cve_mun, "modo": modo})
        minutos: dict[str, dict[str, tuple]] = {}
        for r in await cur.fetchall():
            minutos.setdefault(r["servicio"], {})[r["clave"]] = (r["minutos"], r["destino"])
        await cur.execute(
            """SELECT servicio, origenes, destinos, sin_ruta, fuente, red, actualizado::date::text AS calculado
               FROM accesibilidad_cargas WHERE cve_ent = %(e)s AND modo = %(modo)s""", {"e": cve_ent, "modo": modo})
        cargas = {r["servicio"]: r for r in await cur.fetchall()}
        await cur.execute(
            """SELECT EXISTS (SELECT 1 FROM transporte_paradas WHERE cve_ent = %(e)s AND cve_mun = %(m)s
                              AND feed <> 'osm') AS hay""", {"e": cve_ent, "m": cve_mun})
        con_gtfs = (await cur.fetchone())["hay"]
        # Para citar al productor de cada GTFS, no a Mapo.
        await cur.execute(
            """SELECT DISTINCT f.feed, f.titulo, f.productor, f.pagina, f.licencia, f.fecha_ref::text AS fecha_ref
               FROM transporte_feeds f JOIN transporte_paradas p USING (feed)
               WHERE p.cve_ent = %(e)s AND f.feed <> 'osm' ORDER BY f.feed""", {"e": cve_ent})
        feeds_gtfs = await cur.fetchall()
        usados = sorted({d for por_lugar in minutos.values() for _, d in por_lugar.values() if d})
        await cur.execute(
            """SELECT * FROM (
                 SELECT servicio, id, nombre, lat, lon, ST_Covers(
                   (SELECT geom FROM municipios WHERE cve_ent = %(e)s AND cve_mun = %(m)s),
                   ST_SetSRID(ST_MakePoint(lon, lat), 4326)) AS en_zona
                 FROM accesibilidad_destinos WHERE cve_ent = %(e)s) d
               WHERE en_zona OR id = ANY(%(ids)s)""",
            {"e": cve_ent, "m": cve_mun, "ids": usados})
        puntos = await cur.fetchall()

    servicios = []
    for s in SERVICIOS.values():
        if modo not in s.modos:
            continue
        carga = cargas.get(s.clave)
        sin_cobertura = s.solo_cobertura and not con_gtfs
        base = {"clave": s.clave, "titulo": s.titulo, "grupo": s.grupo, "grupo_etiqueta": s.grupo_etiqueta,
                "calculado": carga is not None and not sin_cobertura, "sin_cobertura": sin_cobertura}
        if carga is None or sin_cobertura:
            servicios.append(base)
            continue
        por_lugar = minutos.get(s.clave, {})
        cubiertos = [u for u in lugares_zona if u["tipo"] == "ageb" or not s.solo_agebs]
        c = curva([(_valor(u["d"], s.grupo), por_lugar.get(u["clave"], (None, None))[0]) for u in cubiertos])
        # La gente de las localidades que no se calculan se dice aparte, nunca como lejos.
        fuera = [_valor(u["d"], s.grupo) for u in lugares_zona if u["tipo"] != "ageb" and s.solo_agebs]
        servicios.append({**base, **c, "fuente": carga["fuente"], "red": carga["red"], "solo_agebs": s.solo_agebs,
                          "sin_calcular": sum(v for v in fuera if v is not None),
                          "sin_calcular_lugares": len(fuera),
                          "fecha": carga["calculado"], "destinos_estado": carga["destinos"],
                          "metodo": metodo(s, modo),
                          "destinos_zona": sum(1 for p in puntos if p["servicio"] == s.clave and p["en_zona"]),
                          **({"feeds": feeds_gtfs} if s.fuente == "gtfs" else {})})

    lugares_gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": json.loads(u["gj"]),
         "properties": {"c": u["clave"], "t": u["tipo"], "p": _valor(u["d"], "POBTOT"),
                        "m": {k: v[u["clave"]][0] for k, v in minutos.items() if u["clave"] in v}}}
        for u in lugares_zona]}
    destinos_gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(p["lon"], 6), round(p["lat"], 6)]},
         "properties": {"s": p["servicio"], "n": p["nombre"]}}
        for p in puntos]}
    return {
        "zona": {"cve_ent": cve_ent, "cve_mun": cve_mun, "nombre": mun["nombre"], "geojson": json.loads(mun["gj"])},
        "modo": modo,
        "max_minutos": MAX_MINUTOS,
        "lugares": len(lugares_zona),
        "agebs": sum(u["tipo"] == "ageb" for u in lugares_zona),
        "servicios": servicios,
        "plano": lugares_gj,
        "destinos": destinos_gj,
    }
