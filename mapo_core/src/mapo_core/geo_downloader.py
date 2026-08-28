"""Descargador del Marco Geoestadistico de INEGI (estados, municipios,
AGEBs urbanas), vendorizado de `gaiarda/src/gaiarda/{api,downloader}.py`.

A diferencia de Gaiarda (que guarda cada poligono como .kml de
precision completa + .geojson simplificado en disco, y solo une la
ruta en la tabla), aca el poligono va directo a una columna
`geometry` en Postgres/PostGIS (`ST_GeomFromGeoJSON`); no hay archivos
que administrar. La simplificacion para que Leaflet no se ponga lento
se aplica al leer (`ST_Simplify`), no al guardar.

Checkpoint por entidad (no uno solo para toda la corrida): si se
interrumpe a medio camino, `gaiarda estados` original (y esto tambien)
retoma desde la entidad que falte, no desde cero. Una entidad que
responde con error se marca como intentada de todas formas (mismo
patron que Gaiarda: "se documenta como intentado; no se reintenta
indefinidamente"), para no quedarse atorada reintentando una clave que
de verdad no existe.
"""

from __future__ import annotations

import asyncio
import json

import httpx

from mapo_core.db import esta_hecho, get_pool, marcar_hecho

BASE_URL = "https://gaia.inegi.org.mx/wscatgeo/v2"
ENTIDADES_MX = [f"{i:02d}" for i in range(1, 33)]
_TIMEOUT = 60.0
_INTENTOS = 3


def _cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"User-Agent": "mapo_core/0.1.0 (uso personal, no comercial)"},
        timeout=_TIMEOUT,
    )


async def _get(client: httpx.AsyncClient, path: str) -> dict:
    """GET con reintentos ante fallas de transporte (conexion caida,
    timeout). Un error de status (ej. 404 de una clave puntual) no se
    reintenta: es una respuesta real del API, no una falla de red."""
    ultima_excepcion: Exception | None = None
    for intento in range(1, _INTENTOS + 1):
        try:
            respuesta = await client.get(path)
            respuesta.raise_for_status()
            return respuesta.json()
        except httpx.HTTPStatusError:
            raise
        except httpx.TransportError as exc:
            ultima_excepcion = exc
            await asyncio.sleep(intento)
    raise ultima_excepcion


def _int_seguro(valor) -> int | None:
    """El API de INEGI usa '-' (y a veces vacio) como marcador de dato
    no disponible en campos numericos. int('-') truena; esto lo
    regresa como None en vez de tronar toda la descarga."""
    if valor in (None, "", "-"):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _cvegeo_geom(feature: dict) -> str:
    return json.dumps(feature["geometry"])


async def descargar_estados() -> int:
    """Descarga los 32 estados con su poligono real."""
    pool = await get_pool()
    total = 0
    async with _cliente() as client, pool.connection() as conn:
        for cve_ent in ENTIDADES_MX:
            clave = f"estado:{cve_ent}"
            if await esta_hecho(conn, clave):
                continue
            try:
                fc = await _get(client, f"/geo/mgee/{cve_ent}")
            except httpx.HTTPStatusError as exc:
                print(f"[WARN] estado {cve_ent}: {exc}")
                await marcar_hecho(conn, clave)
                continue

            for feature in fc.get("features", []):
                props = feature.get("properties", {})
                cvegeo = props.get("cvegeo", cve_ent)
                nombre = props.get("nomgeo", cvegeo)
                await conn.execute(
                    """INSERT INTO entidades (cve_ent, nombre, geom)
                       VALUES (%(cve_ent)s, %(nombre)s,
                               ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))
                       ON CONFLICT (cve_ent) DO UPDATE
                         SET nombre = EXCLUDED.nombre, geom = EXCLUDED.geom, actualizado = now()""",
                    {"cve_ent": cvegeo, "nombre": nombre, "geojson": _cvegeo_geom(feature)},
                )
                total += 1
            await marcar_hecho(conn, clave)
    return total


async def descargar_municipios(cve_ent: str | None = None) -> int:
    """Descarga municipios con su poligono real. `cve_ent=None`
    descarga los 32 estados; si se da uno, solo ese."""
    entidades = [cve_ent] if cve_ent else ENTIDADES_MX
    pool = await get_pool()
    total = 0
    async with _cliente() as client, pool.connection() as conn:
        for ent in entidades:
            clave = f"municipios:{ent}"
            if await esta_hecho(conn, clave):
                continue
            try:
                fc = await _get(client, f"/geo/mgem/{ent}")
            except httpx.HTTPStatusError as exc:
                print(f"[WARN] municipios {ent}: {exc}")
                await marcar_hecho(conn, clave)
                continue

            for feature in fc.get("features", []):
                props = feature.get("properties", {})
                cvegeo = props.get("cvegeo")
                if not cvegeo:
                    continue
                await conn.execute(
                    """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, pob_total, geom)
                       VALUES (%(cvegeo)s, %(cve_ent)s, %(cve_mun)s, %(nombre)s, %(pob_total)s,
                               ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))
                       ON CONFLICT (cvegeo) DO UPDATE
                         SET nombre = EXCLUDED.nombre, pob_total = EXCLUDED.pob_total,
                             geom = EXCLUDED.geom, actualizado = now()""",
                    {
                        "cvegeo": cvegeo,
                        "cve_ent": props.get("cve_ent", ent),
                        "cve_mun": props.get("cve_mun", cvegeo[2:5] if len(cvegeo) >= 5 else ""),
                        "nombre": props.get("nomgeo", cvegeo),
                        "pob_total": _int_seguro(props.get("pob_total")),
                        "geojson": _cvegeo_geom(feature),
                    },
                )
                total += 1
            await marcar_hecho(conn, clave)
    return total


async def descargar_agebs(cve_ent: str | None = None) -> int:
    """Descarga AGEBs urbanas con su poligono real (~56 mil a nivel
    nacional, corre esto por estado salvo que de verdad hagan falta
    todas)."""
    entidades = [cve_ent] if cve_ent else ENTIDADES_MX
    pool = await get_pool()
    total = 0
    async with _cliente() as client, pool.connection() as conn:
        for ent in entidades:
            clave = f"agebs:{ent}"
            if await esta_hecho(conn, clave):
                continue
            try:
                fc = await _get(client, f"/geo/agebu/{ent}")
            except httpx.HTTPStatusError as exc:
                print(f"[WARN] agebs {ent}: {exc}")
                await marcar_hecho(conn, clave)
                continue

            for feature in fc.get("features", []):
                props = feature.get("properties", {})
                cvegeo = props.get("cvegeo", "")
                if not cvegeo:
                    continue
                cve_mun = props.get("cve_mun", cvegeo[2:5] if len(cvegeo) >= 5 else "")
                cve_loc = props.get("cve_loc", cvegeo[5:9] if len(cvegeo) >= 9 else None)
                cve_ageb = props.get("cve_ageb", cvegeo[9:] if len(cvegeo) >= 9 else cvegeo)
                await conn.execute(
                    """INSERT INTO agebs (cvegeo, cve_ent, cve_mun, cve_loc, cve_ageb, ambito, geom)
                       VALUES (%(cvegeo)s, %(cve_ent)s, %(cve_mun)s, %(cve_loc)s, %(cve_ageb)s, %(ambito)s,
                               ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))
                       ON CONFLICT (cvegeo) DO UPDATE
                         SET geom = EXCLUDED.geom, actualizado = now()""",
                    {
                        "cvegeo": cvegeo,
                        "cve_ent": ent,
                        "cve_mun": cve_mun,
                        "cve_loc": cve_loc,
                        "cve_ageb": cve_ageb,
                        "ambito": "URBANA",
                        "geojson": _cvegeo_geom(feature),
                    },
                )
                total += 1
            await marcar_hecho(conn, clave)
    return total
