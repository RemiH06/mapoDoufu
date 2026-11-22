"""Grado de Rezago Social por AGEB urbana 2020 de CONEVAL (sesión 28): un grado (de
muy bajo a muy alto) y 17 indicadores en porcentaje por AGEB, calculados con el Censo
2020. Ver docs/fuentes/rezago-social.md.

Es un grado de CONEVAL con su método, no un puntaje de Mapo: se muestra tal cual y
junto a cuánta gente vive en cada grado. Las AGEB con menos de 3 viviendas traen solo
el grado (reserva de la LSNIEG): sus indicadores quedan `null`.
"""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl
from psycopg_pool import AsyncConnectionPool

URL = "https://www.coneval.org.mx/Medicion/Documents/GRS_AGEB_2020/GRS_AGEB_urbana_2020.zip"
GRADOS = ("Muy bajo", "Bajo", "Medio", "Alto", "Muy alto")
# Encabezados de la fila 5 del Excel (los indicadores), en orden.
INDICADORES = (
    "analfabeta_15", "no_asiste_6_14", "no_asiste_15_24", "basica_incompleta_15", "sin_salud", "hacinamiento",
    "sin_agua", "sin_excusado", "sin_drenaje", "sin_luz", "piso_tierra", "sin_lavadora", "sin_refrigerador",
    "sin_telefono", "sin_celular", "sin_computadora", "sin_internet",
)


class ArchivoInvalido(Exception):
    pass


def _numero(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def leer(ruta: Path) -> list[dict]:
    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        hoja = libro[libro.sheetnames[0]]
        filas = hoja.iter_rows(values_only=True)
        encabezado = None
        for i, f in enumerate(filas):
            if f and f[7] == "Clave de la AGEB":
                encabezado = f
                break
            if i > 20:
                break
        if encabezado is None or encabezado[-1] != "Grado de Rezago Social":
            raise ArchivoInvalido("no se encontró el encabezado 'Clave de la AGEB' ... 'Grado de Rezago Social'")
        salida = []
        for f in filas:
            if not f or not isinstance(f[7], str) or len(f[7]) != 13:
                continue
            grado = (f[-1] or "").strip()
            if grado not in GRADOS:
                raise ArchivoInvalido(f"grado desconocido en {f[7]}: {grado!r}")
            salida.append({
                "cvegeo": f[7], "cve_ent": f[0], "cve_mun": f[2][2:], "pobtot": _numero(f[8]),
                "grado": grado, "indicadores": {k: _numero(v) for k, v in zip(INDICADORES, f[10:27])},
            })
        return salida
    finally:
        libro.close()


async def cargar(pool: AsyncConnectionPool, ruta: Path) -> dict:
    filas = leer(ruta)
    if len(filas) < 50_000:
        raise ArchivoInvalido(f"solo {len(filas)} AGEB: CONEVAL publica 61,430")
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM fuente_rezago_social_ageb")
            async with conn.cursor() as cur:
                async with cur.copy("COPY fuente_rezago_social_ageb (cvegeo, cve_ent, cve_mun, pobtot, grado,"
                                    " indicadores) FROM STDIN") as copia:
                    for f in filas:
                        await copia.write_row([f["cvegeo"], f["cve_ent"], f["cve_mun"], f["pobtot"], f["grado"],
                                               json.dumps(f["indicadores"])])
    conteo = {g: sum(1 for f in filas if f["grado"] == g) for g in GRADOS}
    return {"agebs": len(filas), "por_grado": conteo,
            "solo_grado": sum(1 for f in filas if all(v is None for v in f["indicadores"].values()))}


async def municipio(pool: AsyncConnectionPool, cve_ent: str, cve_mun: str) -> dict | None:
    """AGEB urbanas y personas del municipio en cada grado. None si no está cargado."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT grado, count(*), sum(pobtot), bool_or(pobtot IS NULL), max(actualizado)::date::text
               FROM fuente_rezago_social_ageb WHERE cve_ent = %s AND cve_mun = %s GROUP BY grado""",
            (cve_ent, cve_mun))
        filas = {g: (n, p, nulos, f) for g, n, p, nulos, f in await cur.fetchall()}
        if not filas:
            cur = await conn.execute("SELECT 1 FROM fuente_rezago_social_ageb LIMIT 1")
            return {"sin_dato": True} if await cur.fetchone() else None
    return {
        "anio": 2020,
        "grados": [{"grado": g, "agebs": filas[g][0], "personas": filas[g][1]} for g in GRADOS if g in filas],
        "agebs": sum(v[0] for v in filas.values()),
        "personas": sum(v[1] or 0 for v in filas.values()),
        "cargado": max(v[3] for v in filas.values()),
    }
