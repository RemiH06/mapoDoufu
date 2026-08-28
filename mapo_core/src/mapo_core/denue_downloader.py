"""Descargador de DENUE (negocios), vendorizado de
`gaiarda/src/gaiarda/fuentes/denue/{api,downloader}.py`.

Requiere un token gratuito de INEGI (registro en
https://www.inegi.org.mx/app/api/denue/v1/tokenVerify.aspx), leido de
la variable de entorno `GAIARDA_DENUE_TOKEN` (o pasado explicito).

Solo usa `BuscarEntidad` (bulk por estado, paginado), no
`BuscarAreaAct`: Gaiarda nunca confirmo los nombres exactos de las
propiedades de AGEB/manzana que ese segundo metodo dice traer, y este
proyecto no reinventa esa incertidumbre. Por eso `BuscarEntidad` no
trae `cve_ageb`/`cve_mun`: se rellenan despues con un cruce espacial
contra los poligonos ya descargados (`municipios`/`agebs`), usando
`ST_Contains` directo en Postgres en vez de cargar geojson en memoria
como hace Gaiarda con su `IndiceEspacial` (mas simple, la base ya
tiene los poligonos).
"""

from __future__ import annotations

import asyncio
import os

import httpx

from mapo_core.db import esta_hecho, get_pool, marcar_hecho

BASE_URL = "https://www.inegi.org.mx/app/api/denue/v1/consulta"
TOKEN_ENV_VAR = "GAIARDA_DENUE_TOKEN"
TAMANO_PAGINA = 1000
_TIMEOUT = 60.0
_INTENTOS = 3


class TokenFaltante(Exception):
    pass


def _obtener_token(token: str | None) -> str:
    token = token or os.environ.get(TOKEN_ENV_VAR)
    if not token:
        raise TokenFaltante(
            f"Falta un token de DENUE. Pasa --token o define {TOKEN_ENV_VAR} "
            "(registro gratuito: https://www.inegi.org.mx/app/api/denue/v1/tokenVerify.aspx)"
        )
    return token


def _cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL, timeout=_TIMEOUT)


async def _get(client: httpx.AsyncClient, path: str) -> list[dict]:
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


async def buscar_entidad(
    client: httpx.AsyncClient, cve_ent: str, pos_ini: int, pos_fin: int, token: str, condicion: str = "todos"
) -> list[dict]:
    return await _get(client, f"/BuscarEntidad/{condicion}/{cve_ent}/{pos_ini}/{pos_fin}/{token}")


def _float_seguro(valor) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _normalizar(registro: dict, cve_ent: str) -> dict | None:
    id_ = registro.get("Id")
    if not id_:
        return None
    return {
        "id": str(id_),
        "nombre": registro.get("Nombre"),
        "razon_social": registro.get("Razon_social"),
        "clase_actividad": registro.get("Clase_actividad"),
        "estrato": registro.get("Estrato"),
        "calle": registro.get("Calle"),
        "colonia": registro.get("Colonia"),
        "codigo_postal": registro.get("CP"),
        "ubicacion": registro.get("Ubicacion"),
        "telefono": registro.get("Telefono"),
        "correo": registro.get("Correo_e"),
        "sitio_web": registro.get("Sitio_internet"),
        "tipo": registro.get("Tipo"),
        "lat": _float_seguro(registro.get("Latitud")),
        "lon": _float_seguro(registro.get("Longitud")),
        "cve_ent": cve_ent,
    }


_COLUMNAS = [
    "id", "nombre", "razon_social", "clase_actividad", "estrato", "calle", "colonia",
    "codigo_postal", "ubicacion", "telefono", "correo", "sitio_web", "tipo", "lat", "lon", "cve_ent",
]


async def descargar_estado(
    cve_ent: str, token: str | None = None, tamano_pagina: int = TAMANO_PAGINA
) -> int:
    """Descarga todos los negocios de un estado (paginado, checkpoint
    a nivel estado completo: si se interrumpe a medio camino, retoma
    ese estado desde cero al reintentar, no duplica nada gracias al
    upsert por id, solo repite llamadas ya hechas)."""
    token = _obtener_token(token)
    pool = await get_pool()
    clave = f"denue:{cve_ent}"

    async with pool.connection() as conn:
        if await esta_hecho(conn, clave):
            return 0

        total = 0
        async with _cliente() as client:
            pos_ini = 1
            while True:
                pos_fin = pos_ini + tamano_pagina - 1
                registros = await buscar_entidad(client, cve_ent, pos_ini, pos_fin, token)
                if not registros:
                    break

                for registro in registros:
                    normalizado = _normalizar(registro, cve_ent)
                    if normalizado is None:
                        continue
                    columnas_sql = ", ".join(_COLUMNAS)
                    marcadores = ", ".join(f"%({c})s" for c in _COLUMNAS)
                    actualizables = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNAS if c != "id")
                    await conn.execute(
                        f"""INSERT INTO fuente_denue_negocios ({columnas_sql})
                            VALUES ({marcadores})
                            ON CONFLICT (id) DO UPDATE SET {actualizables}, actualizado = now()""",
                        normalizado,
                    )
                    total += 1

                if len(registros) < tamano_pagina:
                    break
                pos_ini += tamano_pagina

        await marcar_hecho(conn, clave)

    await enriquecer_con_ubicacion(cve_ent)
    return total


async def enriquecer_con_ubicacion(cve_ent: str) -> int:
    """Rellena cve_mun/cve_ageb de los negocios que todavia no lo
    tienen, cruzando su punto (lat, lon) contra los poligonos reales
    ya descargados (`ST_Contains`). Sin esto, BuscarEntidad no trae
    esas claves directo."""
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
