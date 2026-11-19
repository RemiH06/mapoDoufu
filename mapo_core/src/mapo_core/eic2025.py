"""Encuesta Intercensal 2025 (INEGI): bloque de vivienda por municipio.

Datos abiertos de "Principales resultados por localidad de 50 000 y más
habitantes": total nacional, 32 estados, 2,478 municipios y 265 localidades
grandes. Es muestra (levantada del 6 de octubre al 14 de noviembre de 2025), así
que cada indicador viene con cinco renglones: valor, error estándar, límites del
intervalo y coeficiente de variación. Se guardan juntos, para que nadie lea el
valor sin su precisión. Ver docs/fuentes/eic2025.md.

Solo se carga el bloque de vivienda (de `VIVPARHAB` al final: tenencia,
escrituras, materiales, servicios, bienes). `MI` (muestra insuficiente) y `NA`
(no aplica) quedan como valor nulo con su nota, nunca como cero.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile

import httpx

from mapo_core.db import get_pool

URL = "https://www.inegi.org.mx/contenidos/programas/eic/2025/datosabiertos/conjunto_de_datos_eic2025_105_csv.zip"
CSV = "conjunto_de_datos/conjunto_datos_eic2025_105.csv"
PRIMER_INDICADOR = "VIVPARHAB"
FECHA_REFERENCIA = "2025-10-15"
_ESTIMADORES = {
    "Valor": "valor",
    "Error estándar": "error_estandar",
    "Límite inferior de confianza": "lim_inf",
    "Límite superior de confianza": "lim_sup",
    "Coeficiente de variación": "cv",
}
_NOTAS = {"MI", "NA"}


class ArchivoInvalido(Exception):
    pass


def _nivel(cve_ent: str, cve_mun: str, cve_loc: str) -> str:
    if cve_ent == "00":
        return "nacional"
    if cve_mun == "000":
        return "estado"
    return "municipio" if cve_loc == "0000" else "localidad"


def _nombre(r: list[str], ix: dict[str, int]) -> str:
    if r[ix["CVE_LOC"]] != "0000":
        nombre = r[ix["NOM_LOC"]]
    elif r[ix["CVE_MUN"]] != "000":
        nombre = r[ix["NOM_MUN"]]
    else:
        nombre = r[ix["NOM_ENT"]]
    # El asterisco marca municipio censado (*) o con muestra insuficiente (**).
    return re.sub(r"\s*\*+$", "", nombre)


def _numero(texto: str) -> float | None:
    texto = texto.strip()
    if texto == "" or texto in _NOTAS:
        return None
    return float(texto)


def leer(zip_bytes: bytes) -> list[dict]:
    """Una fila por zona e indicador, con los cinco estimadores juntos."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        texto = z.read(CSV).decode("latin-1")
    lector = csv.reader(io.StringIO(texto))
    encabezado = next(lector)
    if PRIMER_INDICADOR not in encabezado or "ESTIMADOR" not in encabezado:
        raise ArchivoInvalido("El CSV no trae las columnas esperadas (VIVPARHAB, ESTIMADOR).")
    ix = {c: i for i, c in enumerate(encabezado)}
    indicadores = encabezado[ix[PRIMER_INDICADOR]:]

    zonas: dict[str, dict] = {}
    for r in lector:
        if not r:
            continue
        estimador = _ESTIMADORES.get(r[ix["ESTIMADOR"]])
        if estimador is None:
            raise ArchivoInvalido(f"Estimador desconocido: {r[ix['ESTIMADOR']]!r}.")
        cvegeo = r[ix["CVEGEO"]]
        zona = zonas.setdefault(cvegeo, {
            "cvegeo": cvegeo,
            "cve_ent": r[ix["CVE_ENT"]],
            "cve_mun": r[ix["CVE_MUN"]],
            "cve_loc": r[ix["CVE_LOC"]],
            "nombre": _nombre(r, ix),
            "indicadores": {},
        })
        for ind in indicadores:
            celda = r[ix[ind]].strip()
            datos = zona["indicadores"].setdefault(ind, {"nota": None})
            datos[estimador] = _numero(celda)
            if estimador == "valor" and celda in _NOTAS:
                datos["nota"] = celda

    filas = []
    for zona in zonas.values():
        nivel = _nivel(zona["cve_ent"], zona["cve_mun"], zona["cve_loc"])
        for ind, datos in zona["indicadores"].items():
            filas.append({
                **{k: zona[k] for k in ("cvegeo", "cve_ent", "cve_mun", "cve_loc", "nombre")},
                "nivel": nivel,
                "indicador": ind,
                **{c: datos.get(c) for c in _ESTIMADORES.values()},
                "nota": datos["nota"],
            })
    estados = {f["cve_ent"] for f in filas if f["nivel"] == "estado"}
    if len(estados) != 32 or not any(f["nivel"] == "nacional" for f in filas):
        raise ArchivoInvalido(f"Se esperaban el total nacional y 32 estados; llegaron {len(estados)} estados.")
    return filas


async def descargar(archivo: bytes | None = None) -> dict[str, int]:
    """Baja el ZIP (o usa el dado) y reemplaza la tabla en una transacción.
    Regresa cuántas zonas quedaron por nivel."""
    if archivo is None:
        async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as cliente:
            r = await cliente.get(URL)
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith("application/"):
                raise ArchivoInvalido(f"{URL} no regresó un ZIP (INEGI responde 200 con HTML si no existe).")
            archivo = r.content
    filas = leer(archivo)

    columnas = ["cvegeo", "nivel", "cve_ent", "cve_mun", "cve_loc", "nombre", "indicador",
                "valor", "error_estandar", "lim_inf", "lim_sup", "cv", "nota"]
    pool = await get_pool()
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("DELETE FROM fuente_eic2025_vivienda")
        async with conn.cursor().copy(
            f"COPY fuente_eic2025_vivienda ({', '.join(columnas)}) FROM STDIN"
        ) as copia:
            for f in filas:
                await copia.write_row([f[c] for c in columnas])

    zonas: dict[str, set] = {}
    for f in filas:
        zonas.setdefault(f["nivel"], set()).add(f["cvegeo"])
    return {nivel: len(c) for nivel, c in zonas.items()}
