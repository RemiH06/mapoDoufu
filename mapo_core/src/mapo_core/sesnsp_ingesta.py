"""Carga de incidencia delictiva municipal (SESNSP) desde un archivo
obtenido a mano, vendorizado de
`gaiarda/src/gaiarda/fuentes/sesnsp/{api,downloader}.py`.

Por que esto no es un downloader automatico como DENUE/censo/ENIGH: la
URL fija que usaba Gaiarda (`repodatos.atdt.gob.mx`) ya no responde
(el dominio completo da 403, confirmado septiembre 2026, no es un
problema de headers ni de User-Agent). SESNSP ahora distribuye este
dataset via un link de SharePoint que exige inicio de sesion
(`sspcgob-my.sharepoint.com`), no es un endpoint publico automatizable
con un cliente HTTP simple. Mismo patron que ya usa Gaiarda para
CAPUFE (`casetas/downloader.py`): se espera un archivo ya descargado a
mano (el CSV real, tal como lo entrega esa pagina), y se parsea desde
ahi. Si algun dia SESNSP vuelve a publicar en un endpoint estable,
esto se puede volver un downloader normal sin tocar el esquema.

El CSV viene en formato "ancho" (un mes = una columna); se transforma
a "largo" (una fila por año-mes) al cargarlo, igual que en Gaiarda.
"""
from __future__ import annotations

import csv
from pathlib import Path

from mapo_core.db import get_pool

MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

_COLUMNAS = [
    "anio", "mes", "cve_ent", "entidad", "cve_mun", "municipio",
    "bien_juridico", "tipo_delito", "subtipo_delito", "modalidad", "cantidad",
]


def _decodificar(contenido_bytes: bytes) -> str:
    for codificacion in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return contenido_bytes.decode(codificacion)
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo decodificar el CSV con utf-8 ni latin-1")


def _int_seguro(valor: str | None) -> int:
    if valor is None or str(valor).strip() == "":
        return 0
    try:
        return int(float(valor))
    except ValueError:
        return 0


def _normalizar_fila(fila: dict) -> list[dict]:
    """Una fila del CSV (un año + un municipio + un delito/subtipo/
    modalidad, con 12 columnas de meses) se convierte en 12 filas, una
    por mes, en formato largo."""
    cve_municipio_pad = (fila.get("Cve. Municipio") or "").strip().zfill(5)
    cve_ent = cve_municipio_pad[:2]
    cve_mun = cve_municipio_pad[2:]

    try:
        anio = int(fila.get("Año", 0))
    except ValueError:
        anio = 0

    base = dict(
        anio=anio,
        cve_ent=cve_ent,
        entidad=fila.get("Entidad"),
        cve_mun=cve_mun,
        municipio=fila.get("Municipio"),
        bien_juridico=fila.get("Bien jurídico afectado"),
        tipo_delito=fila.get("Tipo de delito"),
        subtipo_delito=fila.get("Subtipo de delito"),
        modalidad=fila.get("Modalidad"),
    )

    return [
        {**base, "mes": i, "cantidad": _int_seguro(fila.get(nombre_mes))}
        for i, nombre_mes in enumerate(MESES, start=1)
    ]


def parsear_archivo(ruta: str | Path) -> list[dict]:
    ruta = Path(ruta)
    texto = _decodificar(ruta.read_bytes())
    filas_csv = list(csv.DictReader(texto.splitlines()))

    filas_largas = []
    for fila in filas_csv:
        filas_largas.extend(_normalizar_fila(fila))
    return filas_largas


async def cargar_archivo(ruta: str | Path) -> int:
    filas = parsear_archivo(ruta)

    columnas_sql = ", ".join(_COLUMNAS)
    marcadores = ", ".join(f"%({c})s" for c in _COLUMNAS)
    sql = f"""INSERT INTO fuente_sesnsp_delitos_municipal ({columnas_sql})
              VALUES ({marcadores})
              ON CONFLICT (anio, mes, cve_ent, cve_mun, bien_juridico, tipo_delito, subtipo_delito, modalidad)
              DO UPDATE SET entidad=excluded.entidad, municipio=excluded.municipio,
                            cantidad=excluded.cantidad, actualizado=now()"""

    pool = await get_pool()
    async with pool.connection() as conn:
        for fila in filas:
            await conn.execute(sql, fila)
    return len(filas)
