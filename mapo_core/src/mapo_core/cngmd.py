"""Censo Nacional de Gobiernos Municipales y Demarcaciones Territoriales 2025 de
INEGI (sesión 28): por ahora, los instrumentos de planeación territorial de cada
municipio en 2024 (plan de desarrollo urbano, atlas de riesgos, programa de
movilidad...), si existían, si se publicaron y su vigencia. Ver docs/fuentes/cngmd.md.

Cada respuesta se guarda como la da el municipio, con sus códigos de "no se sabe" o
"información no disponible": nunca se vuelven "no".
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

URL = ("https://www.inegi.org.mx/contenidos/programas/cngmd/2025/datosabiertos/"
       "conjunto_de_datos_ins_plan_ord_jur_cngmd2025_csv.zip")
RESPUESTAS = {"0": "no aplica", "1": "sí", "2": "no", "9": "no se sabe",
              "97": "sin elementos para responder", "98": "información no disponible"}
# Los que se muestran siempre, aunque la respuesta sea "no".
PRINCIPALES = (1, 9, 10, 8, 15)


class ArchivoInvalido(Exception):
    pass


def _texto(z: zipfile.ZipFile, sufijo: str) -> str:
    nombre = next((n for n in z.namelist() if n.endswith(sufijo)), None)
    if nombre is None:
        raise ArchivoInvalido(f"falta {sufijo}")
    crudo = z.open(nombre).read()
    try:
        return crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return crudo.decode("latin-1")


def leer(ruta: Path) -> list[dict]:
    with zipfile.ZipFile(ruta) as z:
        nombres = {int(f["instmun_a"]): f["descrip"].strip()
                   for f in csv.DictReader(io.StringIO(_texto(z, "instmun_a_cngmd2025.csv")))}
        filas = list(csv.DictReader(io.StringIO(_texto(z, "m2s14p10_cngmd2025.csv"))))
    salida = []
    for f in filas:
        try:
            instrumento = int(f["instmun_a"])
        except (KeyError, ValueError):
            continue
        salida.append({
            "cve_ent": f["cve_ent"].zfill(2), "cve_mun": f["cve_mun"].zfill(3), "instrumento": instrumento,
            "nombre": nombres.get(instrumento, str(instrumento)),
            "existio": RESPUESTAS.get(f.get("rensnn1", "").strip(), f.get("rensnn1", "").strip() or None),
            "publicado": RESPUESTAS.get(f.get("rensnn3", "").strip(), f.get("rensnn3", "").strip() or None),
            "vigencia": (f.get("vigncia1") or "").strip() or None,
        })
    return salida


async def cargar(pool: AsyncConnectionPool, ruta: Path) -> dict:
    filas = leer(ruta)
    if len(filas) < 10_000:
        raise ArchivoInvalido(f"solo {len(filas)} renglones: son 17 instrumentos por municipio")
    columnas = ["cve_ent", "cve_mun", "instrumento", "nombre", "existio", "publicado", "vigencia"]
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM fuente_cngmd_planeacion")
            async with conn.cursor() as cur:
                async with cur.copy(f"COPY fuente_cngmd_planeacion ({', '.join(columnas)}) FROM STDIN") as copia:
                    for f in filas:
                        await copia.write_row([f[c] for c in columnas])
    pdu = [f for f in filas if f["instrumento"] == 1]
    return {"municipios": len({(f["cve_ent"], f["cve_mun"]) for f in filas}), "renglones": len(filas),
            "con_plan_desarrollo_urbano": sum(f["existio"] == "sí" for f in pdu),
            "con_atlas_riesgos": sum(f["existio"] == "sí" for f in filas if f["instrumento"] == 9)}


async def municipio(pool: AsyncConnectionPool, cve_ent: str, cve_mun: str) -> dict | None:
    """Los instrumentos principales con su respuesta y los demás que sí existían.
    None si no está cargado; `sin_dato` si el municipio no aparece."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT instrumento, nombre, existio, publicado, vigencia FROM fuente_cngmd_planeacion
               WHERE cve_ent = %s AND cve_mun = %s ORDER BY instrumento""", (cve_ent, cve_mun))
        filas = [dict(zip(("instrumento", "nombre", "existio", "publicado", "vigencia"), f))
                 for f in await cur.fetchall()]
        if not filas:
            cur = await conn.execute("SELECT 1 FROM fuente_cngmd_planeacion LIMIT 1")
            return {"sin_dato": True} if await cur.fetchone() else None
    principales = sorted((f for f in filas if f["instrumento"] in PRINCIPALES),
                         key=lambda f: PRINCIPALES.index(f["instrumento"]))
    otros = [f for f in filas if f["instrumento"] not in PRINCIPALES and f["existio"] == "sí"]
    return {"anio": 2024, "principales": principales, "otros": otros}
