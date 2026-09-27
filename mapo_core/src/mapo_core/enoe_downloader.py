"""Descargador de ENOE (laboral), vendorizado de
`gaiarda/src/gaiarda/fuentes/enoe/{api,downloader,tablas}.py`.

Gaiarda porta las 5 tablas trimestrales completas (viv, hog, sdem,
coe1, coe2) con un esquema generado dinamicamente, pero nunca expuso
un endpoint de *consulta* sobre ellas (solo descarga). Mapo si necesita
consultar, y lo unico que hace falta para eso es un indicador: la tasa
de desocupacion por entidad, que se calcula completa a partir de UNA
sola tabla (`sdem`, Sociodemografico). Por eso aca no se guardan las
~400 mil filas de microdatos crudos por trimestre (que nadie en Mapo
consultaria directo): se calcula el agregado ponderado por entidad al
momento de descargar, y solo eso se guarda (una fila por entidad por
trimestre).

**Bug real de URL encontrado y corregido (septiembre 2026)**: la URL
que usaba Gaiarda (`enoe_n_{anio}_{trimestre}_dbf.zip`, con el
segmento `_n_`) devuelve una pagina "no encontrada" (200 pero HTML,
no el zip real) para cualquier trimestre de 2023 en adelante. Se
confirmo contra descargas reales que el patron cambio a
`enoe_{anio}_{trimestre}_dbf.zip` (sin el `_n_`) a partir del primer
trimestre de 2023 (coincide con el corte documentado por el propio
INEGI: la ENOE retoma su nombre despues del periodo ENOEN de 2020-2022).
Los trimestres de 2022 y anteriores siguen en el patron viejo, pero
quedan fuera de alcance: Mapo solo necesita el trimestre mas reciente
para un indicador de "ahorita", no una serie historica.

La ENOE NO tiene representatividad a nivel municipio (diseno muestral
por "ciudades autorepresentadas" y resto del estado): el indicador se
calcula y se sirve solo por entidad, nunca por municipio, y hay que
decirlo honesto donde se muestre.

Formula (confirmada contra datos reales, congruente con la cifra
nacional oficial ~2.9% en 2025-T3): de las filas con entrevista
completa (`R_DEF == '00'`), la Poblacion Economicamente Activa es
`CLASE1 == 1`; de esas, las desocupadas son `CLASE2 == 2`. Cada fila
pesa `FAC_TRI` personas reales (factor de expansion trimestral).
Tasa de desocupacion = desocupada_ponderada / pea_ponderada * 100.
"""
from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import httpx
from dbfread import DBF

from mapo_core.db import esta_hecho, get_pool, marcar_hecho

BASE_URL = "https://www.inegi.org.mx/contenidos/programas/enoe/15ymas/microdatos"
TRIMESTRES_VALIDOS = {"trim1", "trim2", "trim3", "trim4"}
_TIMEOUT = 180.0


def url_trimestre(anio: int, trimestre: str) -> str:
    if trimestre not in TRIMESTRES_VALIDOS:
        raise ValueError(f"trimestre invalido: '{trimestre}'. Usa uno de: {sorted(TRIMESTRES_VALIDOS)}")
    return f"{BASE_URL}/enoe_{anio}_{trimestre}_dbf.zip"


async def _descargar_zip(anio: int, trimestre: str) -> bytes:
    url = url_trimestre(anio, trimestre)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
    if resp.headers.get("content-type", "").startswith("text/html"):
        raise ValueError(
            f"'{url}' no regreso un zip (regreso HTML, probablemente 'pagina no encontrada'). "
            f"Ese trimestre puede no estar publicado todavia, o INEGI volvio a cambiar el patron de URL."
        )
    return resp.content


def _extraer_sdem(zip_bytes: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        nombres = [n for n in zf.namelist() if "SDEM" in n.upper()]
        if not nombres:
            raise ValueError(f"No se encontro ningun .dbf de SDEM en el zip. Archivos: {zf.namelist()}")

        with tempfile.TemporaryDirectory() as tmpdir:
            ruta = Path(tmpdir) / "sdem.dbf"
            ruta.write_bytes(zf.read(nombres[0]))
            tabla = DBF(str(ruta), encoding="latin-1", ignore_missing_memofile=True)
            return [
                {
                    "cve_ent": str(fila["CVE_ENT"]).strip().zfill(2),
                    "clase1": fila["CLASE1"],
                    "clase2": fila["CLASE2"],
                    "fac_tri": fila["FAC_TRI"],
                }
                for fila in tabla
                if fila.get("R_DEF") == "00"
            ]


def _calcular_tasas(filas: list[dict]) -> dict[str, dict]:
    """Agrupa por entidad y calcula el indicador ponderado. Regresa
    {cve_ent: {pea_ponderada, ocupada_ponderada, desocupada_ponderada,
    tasa_desocupacion}}."""
    por_entidad: dict[str, dict] = {}
    for fila in filas:
        acumulado = por_entidad.setdefault(
            fila["cve_ent"], {"pea": 0.0, "ocupada": 0.0, "desocupada": 0.0}
        )
        if fila["clase1"] != 1:
            continue  # no es parte de la PEA (PNEA o no aplica)
        peso = float(fila["fac_tri"])
        acumulado["pea"] += peso
        if fila["clase2"] == 1:
            acumulado["ocupada"] += peso
        elif fila["clase2"] == 2:
            acumulado["desocupada"] += peso

    resultado = {}
    for cve_ent, acumulado in por_entidad.items():
        if acumulado["pea"] <= 0:
            continue
        resultado[cve_ent] = {
            "pea_ponderada": acumulado["pea"],
            "ocupada_ponderada": acumulado["ocupada"],
            "desocupada_ponderada": acumulado["desocupada"],
            "tasa_desocupacion": acumulado["desocupada"] / acumulado["pea"] * 100,
        }
    return resultado


async def descargar_trimestre(anio: int, trimestre: str) -> int:
    """Descarga un trimestre de ENOE, calcula la tasa de desocupacion
    ponderada por entidad, y guarda una fila por entidad (32 en total).
    Regresa cuantas entidades se guardaron (0 si el checkpoint ya
    marcaba este trimestre como hecho)."""
    if trimestre not in TRIMESTRES_VALIDOS:
        raise ValueError(f"trimestre invalido: '{trimestre}'. Usa uno de: {sorted(TRIMESTRES_VALIDOS)}")

    pool = await get_pool()
    clave = f"enoe:{anio}:{trimestre}"
    async with pool.connection() as conn:
        if await esta_hecho(conn, clave):
            return 0

        zip_bytes = await _descargar_zip(anio, trimestre)
        filas = _extraer_sdem(zip_bytes)
        tasas = _calcular_tasas(filas)

        for cve_ent, valores in tasas.items():
            await conn.execute(
                """INSERT INTO fuente_enoe_tasa_desocupacion
                     (cve_ent, anio, trimestre, pea_ponderada, ocupada_ponderada,
                      desocupada_ponderada, tasa_desocupacion)
                   VALUES (%(cve_ent)s, %(anio)s, %(trimestre)s, %(pea_ponderada)s,
                           %(ocupada_ponderada)s, %(desocupada_ponderada)s, %(tasa_desocupacion)s)
                   ON CONFLICT (cve_ent, anio, trimestre) DO UPDATE SET
                     pea_ponderada=excluded.pea_ponderada,
                     ocupada_ponderada=excluded.ocupada_ponderada,
                     desocupada_ponderada=excluded.desocupada_ponderada,
                     tasa_desocupacion=excluded.tasa_desocupacion,
                     actualizado=now()""",
                {"cve_ent": cve_ent, "anio": anio, "trimestre": trimestre, **valores},
            )

        await marcar_hecho(conn, clave)
    return len(tasas)
