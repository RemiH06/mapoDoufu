"""Censos Económicos 2024 de INEGI por municipio y sector (sesión 28): unidades
económicas, personal ocupado, remuneraciones, ingresos, producción y valor agregado
del año 2023. Ver docs/fuentes/censos-economicos.md.

Los datos abiertos llegan a municipio, no a AGEB (el producto por AGEB urbana de
2019 no se repitió en 2024). Un valor vacío es un dato reservado por
confidencialidad: se guarda `null` y se dice, nunca cero.
"""

from __future__ import annotations

import csv
import io
import urllib.request
import zipfile
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

URL = "https://www.inegi.org.mx/contenidos/programas/ce/2024/datosabiertos/conjunto_de_datos_ce_{abr}_2024_csv.zip"
ABREVIATURAS = {
    "01": "ags", "02": "bc", "03": "bcs", "04": "camp", "05": "coah", "06": "col", "07": "chis", "08": "chih",
    "09": "cdmx", "10": "dgo", "11": "gto", "12": "gro", "13": "hgo", "14": "jal", "15": "mex", "16": "mich",
    "17": "mor", "18": "nay", "19": "nl", "20": "oax", "21": "pue", "22": "qro", "23": "qroo", "24": "slp",
    "25": "sin", "26": "son", "27": "tab", "28": "tamps", "29": "tlax", "30": "ver", "31": "yuc", "32": "zac",
}
# Columna de la base -> variable de INEGI (diccionario_de_datos_ce2024.csv).
VARIABLES = {
    "ue": "UE",  # unidades económicas
    "personal": "H001A",  # personal ocupado total
    "remuneraciones": "J000A",  # millones de pesos
    "ingresos": "M000A",  # ingresos por suministro de bienes y servicios, millones de pesos
    "produccion": "A111A",  # producción bruta total, millones de pesos
    "vacb": "A131A",  # valor agregado censal bruto, millones de pesos
}
TOTAL = "total"


class ArchivoInvalido(Exception):
    pass


def _numero(texto: str) -> float | None:
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _csv(z: zipfile.ZipFile, sufijo: str) -> list[dict]:
    nombre = next((n for n in z.namelist() if n.endswith(sufijo)), None)
    if nombre is None:
        raise ArchivoInvalido(f"falta {sufijo}")
    crudo = z.open(nombre).read()
    try:
        texto = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = crudo.decode("latin-1")
    return list(csv.DictReader(io.StringIO(texto)))


def leer(ruta: Path, cve_ent: str) -> tuple[list[dict], dict]:
    """(filas por municipio y sector, total del estado). Solo el nivel de sector, sin
    estrato. Comprueba que los municipios sumen el total del estado."""
    with zipfile.ZipFile(ruta) as z:
        datos = _csv(z, f"tr_ce_{ABREVIATURAS[cve_ent]}_2024.csv")
        nombres = {c["CODIGO"].strip(): c["DESC_CODIGO"].strip() for c in _csv(z, "tc_codigo_actividad.csv")
                   if (c.get("CLASIFICADOR_CODIGO") or "").strip() == "Sector"}
    faltan = [v for v in VARIABLES.values() if v not in (datos[0] if datos else {})]
    if faltan:
        raise ArchivoInvalido(f"faltan columnas: {', '.join(faltan)}")
    filas, estado = [], None
    for f in datos:
        if f["E03"].strip() != cve_ent or (f.get("SUBSECTOR") or "").strip() or (f.get("ID_ESTRATO") or "").strip():
            continue
        codigo = f["CODIGO"].strip()
        sector = TOTAL if codigo == "TOTAL DE SECTOR" else codigo
        valores = {col: _numero(f[var]) for col, var in VARIABLES.items()}
        if not f["E04"].strip():
            if sector == TOTAL:
                estado = valores
            continue
        filas.append({"cve_ent": cve_ent, "cve_mun": f["E04"].strip().zfill(3), "sector": sector,
                      "nombre": "Todos los sectores" if sector == TOTAL else nombres.get(sector, sector), **valores})
    if estado is None or not filas:
        raise ArchivoInvalido("sin total del estado o sin municipios")
    suma = sum(f["ue"] or 0 for f in filas if f["sector"] == TOTAL)
    if round(suma) != round(estado["ue"] or 0):
        raise ArchivoInvalido(f"los municipios suman {suma:,.0f} unidades y el estado dice {estado['ue']:,.0f}")
    return filas, estado


def descargar(cve_ent: str, carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"ce2024_{ABREVIATURAS[cve_ent]}.zip"
    if destino.exists() and zipfile.is_zipfile(destino):
        return destino
    req = urllib.request.Request(URL.format(abr=ABREVIATURAS[cve_ent]), headers={"User-Agent": "mapo-datos/0.1"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        if not resp.headers.get("content-type", "").startswith("application/"):
            raise ArchivoInvalido(f"INEGI no mandó un zip para {cve_ent} (¿cambió la URL?)")
        destino.with_suffix(".tmp").write_bytes(resp.read())
    destino.with_suffix(".tmp").replace(destino)
    return destino


async def cargar(pool: AsyncConnectionPool, cve_ent: str, archivo: Path) -> dict:
    filas, estado = leer(archivo, cve_ent)
    columnas = ["cve_ent", "cve_mun", "sector", "nombre", *VARIABLES]
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM fuente_ce2024_municipal WHERE cve_ent = %s", (cve_ent,))
            async with conn.cursor() as cur:
                async with cur.copy(f"COPY fuente_ce2024_municipal ({', '.join(columnas)}) FROM STDIN") as copia:
                    for f in filas:
                        await copia.write_row([f[c] for c in columnas])
    return {"cve_ent": cve_ent, "municipios": len({f["cve_mun"] for f in filas}), "filas": len(filas),
            "ue_estado": estado["ue"], "personal_estado": estado["personal"],
            "reservados": sum(1 for f in filas if f["personal"] is None)}


async def municipio(pool: AsyncConnectionPool, cve_ent: str, cve_mun: str) -> dict | None:
    """Total del municipio y sus sectores, de más a menos personal ocupado. None si
    el estado no está cargado; `sin_dato` si el municipio no aparece."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""SELECT sector, nombre, {', '.join(VARIABLES)}, actualizado::date::text
                FROM fuente_ce2024_municipal WHERE cve_ent = %s AND cve_mun = %s""", (cve_ent, cve_mun))
        filas = await cur.fetchall()
        if not filas:
            cur = await conn.execute("SELECT 1 FROM fuente_ce2024_municipal WHERE cve_ent = %s LIMIT 1", (cve_ent,))
            return {"sin_dato": True} if await cur.fetchone() else None
    claves = ["sector", "nombre", *VARIABLES, "cargado"]
    registros = [dict(zip(claves, f)) for f in filas]
    total = next((r for r in registros if r["sector"] == TOTAL), None)
    sectores = sorted((r for r in registros if r["sector"] != TOTAL),
                      key=lambda r: (r["personal"] is None, -(r["personal"] or 0)))
    return {"anio_datos": 2023, "total": total, "sectores": sectores,
            "reservados": sum(1 for r in sectores if r["personal"] is None),
            "cargado": registros[0]["cargado"]}
