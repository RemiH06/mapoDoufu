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
mano (el usuario lo deja en `mapo_core/data/sesnsp/`, gitignored, ver
`.gitignore`), y se parsea desde ahi.

El archivo real (`Municipal-Delitos-2015-2025_ago2026.csv`, el
"formato CSV consolidado" que documenta el propio SESNSP en su PDF
"1. PARA_EVITAR_ERRORES_ANTES_DE_SU_USO") pesa ~380 MB y viene en
formato "ancho" (un mes = una columna); se transforma a "largo" (una
fila por año-mes) al cargarlo, igual que en Gaiarda. Con 10 años
consolidados esto expande a decenas de millones de filas, muy distinto
al tamaño de un solo corte mensual que manejaba Gaiarda originalmente.

**Bug real de memoria encontrado y corregido**: la primera version de
este modulo leia el archivo completo a memoria (`Path.read_bytes()`),
lo decodificaba entero, y materializaba TODAS las filas expandidas
(formato largo) en una sola lista de Python antes de tocar la base.
Contra el archivo real de 380 MB, esto tumbo el contenedor entero por
falta de memoria (`OOMKilled`, confirmado con `docker inspect`).
Corregido a un pipeline en streaming: el archivo se lee linea por
linea (nunca completo en memoria), y las filas se mandan a Postgres
via `COPY` (streaming nativo, no un INSERT por fila) hacia una tabla
temporal; el upsert final contra la tabla real es una sola sentencia
`INSERT ... ON CONFLICT`, no un loop en Python.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

from mapo_core.db import get_pool

MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

_COLUMNAS = [
    "anio", "mes", "cve_ent", "entidad", "cve_mun", "municipio",
    "bien_juridico", "tipo_delito", "subtipo_delito", "modalidad", "cantidad",
]


def _abrir_texto(ruta: Path):
    """Abre el archivo en modo texto, detectando la codificacion real
    sin leerlo completo a memoria: se prueba decodificar un pedazo
    chico primero, y se abre el archivo entero ya con esa codificacion
    confirmada. utf-8-sig primero, latin-1 de respaldo (mismo criterio
    que el resto de las fuentes de INEGI/SESNSP en este proyecto)."""
    muestra = ruta.read_bytes()[:65536]
    for codificacion in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            muestra.decode(codificacion)
            return open(ruta, encoding=codificacion, newline="")
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


def parsear_archivo(ruta: str | Path) -> Iterator[dict]:
    """Generador: una fila del CSV a la vez, ya en formato largo. Nunca
    materializa el archivo completo ni la expansion completa en
    memoria (el archivo real pesa ~380 MB y expande a decenas de
    millones de filas)."""
    with _abrir_texto(Path(ruta)) as f:
        for fila_csv in csv.DictReader(f):
            yield from _normalizar_fila(fila_csv)


_TABLA_STAGING = "staging_sesnsp_carga"
_TAMANO_LOTE = 50_000


async def cargar_archivo(ruta: str | Path) -> int:
    """Carga el archivo a `fuente_sesnsp_delitos_municipal` via COPY a
    una tabla temporal + un solo merge (INSERT ... ON CONFLICT), en vez
    de un INSERT por fila. Regresa cuantas filas (formato largo, una
    por año-mes) se cargaron."""
    columnas_sql = ", ".join(_COLUMNAS)

    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""CREATE TEMP TABLE {_TABLA_STAGING} (
                        anio INTEGER, mes INTEGER, cve_ent TEXT, entidad TEXT,
                        cve_mun TEXT, municipio TEXT, bien_juridico TEXT,
                        tipo_delito TEXT, subtipo_delito TEXT, modalidad TEXT, cantidad INTEGER
                    ) ON COMMIT DROP"""
            )

            total = 0
            async with cur.copy(f"COPY {_TABLA_STAGING} ({columnas_sql}) FROM STDIN") as copy:
                for fila in parsear_archivo(ruta):
                    await copy.write_row(tuple(fila[c] for c in _COLUMNAS))
                    total += 1

            await cur.execute(
                f"""INSERT INTO fuente_sesnsp_delitos_municipal ({columnas_sql})
                    SELECT {columnas_sql} FROM {_TABLA_STAGING}
                    ON CONFLICT (anio, mes, cve_ent, cve_mun, bien_juridico, tipo_delito, subtipo_delito, modalidad)
                    DO UPDATE SET entidad=excluded.entidad, municipio=excluded.municipio,
                                  cantidad=excluded.cantidad, actualizado=now()"""
            )
    return total
