"""Descargador de ENIGH (consumo), vendorizado de
`gaiarda/src/gaiarda/fuentes/enigh/{api,downloader,tablas}.py`.

Gaiarda porta las 17 tablas de microdatos con un esquema generado
dinamicamente (una columna TEXT por cada columna del CSV). Mapo solo
necesita `concentradohogar` (ingreso/gasto ya agregados por hogar, la
tabla que de verdad importa para "cuanto gasta la gente"), asi que
aca se usa un esquema fijo con las columnas reales que hacen falta
para el resumen ponderado por municipio (ver `enigh_resumen.py`), en
vez de portar la maquinaria generica de 17 tablas que Mapo no usa.

Confirmado contra el CSV real (septiembre 2026): 91,414 filas
nacionales, 126 columnas, separador coma (el bug de delimitador tab
que documenta Gaiarda ya esta corregido en la fuente real).
"""
from __future__ import annotations

import csv
import io
import zipfile

import httpx

from mapo_core.db import esta_hecho, get_pool, marcar_hecho

URL = "https://www.inegi.org.mx/contenidos/programas/enigh/nc/2024/microdatos/enigh2024_ns_concentradohogar_csv.zip"
_TIMEOUT = 120.0
_INTENTOS = 3

_COLUMNAS_RESUMEN = [
    "ing_cor", "ingtrab", "gasto_mon", "alimentos", "vivienda", "transporte",
    "educa_espa", "salud", "vesti_calz", "transf_gas", "percep_tot", "erogac_tot",
]
_COLUMNAS = ["folioviv", "foliohog", "ubica_geo", "cve_ent", "cve_mun", "factor", *_COLUMNAS_RESUMEN]


def _decodificar(contenido_bytes: bytes) -> str:
    for codificacion in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return contenido_bytes.decode(codificacion)
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo decodificar el CSV con utf-8 ni latin-1")


def _float_seguro(valor: str | None) -> float | None:
    if valor is None or str(valor).strip() == "":
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _normalizar(fila: dict) -> dict | None:
    folioviv = (fila.get("folioviv") or "").strip()
    foliohog = (fila.get("foliohog") or "").strip()
    if not folioviv or not foliohog:
        return None

    ubica_geo = (fila.get("ubica_geo") or "").strip().zfill(5)

    normalizado = {
        "folioviv": folioviv,
        "foliohog": foliohog,
        "ubica_geo": ubica_geo,
        "cve_ent": ubica_geo[:2],
        "cve_mun": ubica_geo[2:],
        "factor": _float_seguro(fila.get("factor")),
    }
    for columna in _COLUMNAS_RESUMEN:
        normalizado[columna] = _float_seguro(fila.get(columna))
    return normalizado


async def _descargar_zip(url: str = URL) -> bytes:
    ultimo_error: Exception | None = None
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for _ in range(_INTENTOS):
            try:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                return resp.content
            except httpx.TransportError as exc:
                ultimo_error = exc
                continue
    raise ultimo_error or RuntimeError("No se pudo descargar el zip de ENIGH")


def _extraer_filas(zip_bytes: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        nombres_csv = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not nombres_csv:
            raise ValueError("El zip de concentradohogar no contiene ningun .csv")
        contenido = _decodificar(zf.read(nombres_csv[0]))

    lector = csv.DictReader(io.StringIO(contenido))
    encabezado = list(lector.fieldnames or [])
    if len(encabezado) <= 1:
        raise ValueError(
            f"El CSV se leyo como una sola columna ({encabezado!r}): el delimitador "
            f"real probablemente cambio de nuevo. No se guarda asi."
        )
    return list(lector)


async def descargar() -> int:
    pool = await get_pool()
    clave = "enigh:concentradohogar"
    async with pool.connection() as conn:
        if await esta_hecho(conn, clave):
            return 0

        zip_bytes = await _descargar_zip()
        filas_csv = _extraer_filas(zip_bytes)

        columnas_sql = ", ".join(_COLUMNAS)
        marcadores = ", ".join(f"%({c})s" for c in _COLUMNAS)
        actualizaciones = ", ".join(
            f"{c}=excluded.{c}" for c in _COLUMNAS if c not in ("folioviv", "foliohog")
        )
        sql = f"""INSERT INTO fuente_enigh_concentradohogar ({columnas_sql})
                  VALUES ({marcadores})
                  ON CONFLICT (folioviv, foliohog) DO UPDATE SET {actualizaciones}"""

        total = 0
        for fila in filas_csv:
            normalizado = _normalizar(fila)
            if normalizado is None:
                continue
            await conn.execute(sql, normalizado)
            total += 1

        await marcar_hecho(conn, clave)
    return total
