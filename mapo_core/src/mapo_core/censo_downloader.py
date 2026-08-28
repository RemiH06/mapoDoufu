"""Descargador del Censo de Poblacion y Vivienda 2020 (AGEB-manzana),
vendorizado de `gaiarda/src/gaiarda/fuentes/censo_poblacion/{api,downloader}.py`.

No es un API REST: es un .zip completo por estado, sin paginacion. El
mismo CSV trae CUATRO niveles de agregacion mezclados en las mismas
filas (se distinguen por las claves, no por columnas separadas):
entidad (MUN='000', LOC='0000', AGEB='0000'), municipio (MUN!='000',
LOC='0000', AGEB='0000'), localidad (LOC!='0000', AGEB='0000'), AGEB
(AGEB!='0000'). Un quinto nivel, manzana (MZA!='000'), se descarta a
proposito (serian cientos de miles de filas extra por estado grande,
y ni Voronoi ni coropletas lo necesitan).

De los 222 indicadores oficiales, 27 de los mas usados tienen columna
propia; el resto vive en `datos_json` (jsonb, mejor que el TEXT que
usa Gaiarda: ya queda consultable nativo con `datos_json->>'CAMPO'`
sin json_extract).
"""

from __future__ import annotations

import csv
import io
import json
import zipfile

import httpx

from mapo_core.db import esta_hecho, get_pool, marcar_hecho

URL_TEMPLATE = (
    "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/"
    "ageb_manzana/ageb_mza_urbana_{cve_ent}_cpv2020_csv.zip"
)

# CSV -> columna propia en fuente_censo_poblacion. Nombres de INEGI en
# mayusculas, confirmados contra una descarga real.
_COLUMNAS_PROPIAS = {
    "POBTOT": "pobtot", "POBFEM": "pobfem", "POBMAS": "pobmas",
    "P_0A2": "p_0a2", "P_3A5": "p_3a5", "P_6A11": "p_6a11", "P_12A14": "p_12a14",
    "P_15A17": "p_15a17", "P_18A24": "p_18a24", "P_60YMAS": "p_60ymas",
    "GRAPROES": "graproes",
    "PEA": "pea", "PEA_F": "pea_f", "PEA_M": "pea_m", "PE_INAC": "pe_inac",
    "POCUPADA": "pocupada", "PDESOCUP": "pdesocup",
    "PDER_SS": "pder_ss",
    "TOTHOG": "tothog", "VIVTOT": "vivtot", "TVIVHAB": "tvivhab", "PROM_OCUP": "prom_ocup",
    "VPH_INTER": "vph_inter", "VPH_PC": "vph_pc", "VPH_AUTOM": "vph_autom",
    "VPH_CEL": "vph_cel", "VPH_SNBIEN": "vph_snbien",
}
_COLUMNAS_REALES = {"graproes", "prom_ocup"}  # el resto son enteros


async def descargar_zip_estado(cve_ent: str) -> bytes:
    async with httpx.AsyncClient(timeout=300.0) as client:
        respuesta = await client.get(URL_TEMPLATE.format(cve_ent=cve_ent))
        respuesta.raise_for_status()
        return respuesta.content


def _decodificar(datos: bytes) -> str:
    """No se pudo confirmar la codificacion exacta del CSV en el
    entorno donde se escribio Gaiarda originalmente; se intenta
    UTF-8 primero y se cae a Latin-1 si falla, en vez de asumir
    ciegamente."""
    for codificacion in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return datos.decode("latin-1", errors="replace")


def extraer_csv(zip_bytes: bytes, cve_ent: str) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        nombre_esperado = f"conjunto_de_datos_ageb_urbana_{cve_ent}_cpv2020.csv"
        candidatos = [n for n in zf.namelist() if n.endswith(nombre_esperado)]
        if not candidatos:
            candidatos = [n for n in zf.namelist() if n.endswith(".csv")]
        if not candidatos:
            raise ValueError(f"El zip de censo_poblacion para {cve_ent} no trae ningun .csv")

        texto = _decodificar(zf.read(candidatos[0]))

    lector = csv.DictReader(io.StringIO(texto))
    if lector.fieldnames is None or len(lector.fieldnames) <= 1:
        raise ValueError(
            f"El CSV de censo_poblacion para {cve_ent} no parseo columnas reales "
            "(posible delimitador equivocado, no guardar en silencio)"
        )
    return list(lector)


def _num(valor, tipo=float):
    if valor is None:
        return None
    valor = valor.strip()
    if valor in ("", "*", "N/D", "-"):
        return None
    try:
        return tipo(valor) if tipo is float else int(float(valor))
    except (TypeError, ValueError):
        return None


def _nivel_y_cvegeo(fila: dict) -> tuple[str, str] | None:
    cve_ent = fila.get("ENTIDAD", "").strip()
    cve_mun = fila.get("MUN", "").strip()
    cve_loc = fila.get("LOC", "").strip()
    cve_ageb = fila.get("AGEB", "").strip()
    cve_mza = fila.get("MZA", "").strip()

    if cve_mza and cve_mza != "000":
        return None  # manzana, se descarta a proposito
    if cve_ageb and cve_ageb != "0000":
        return "ageb", f"{cve_ent}{cve_mun}{cve_loc}{cve_ageb}"
    if cve_loc and cve_loc != "0000":
        return "localidad", f"{cve_ent}{cve_mun}{cve_loc}"
    if cve_mun and cve_mun != "000":
        return "municipio", f"{cve_ent}{cve_mun}"
    return "entidad", cve_ent


def _normalizar(fila: dict) -> dict | None:
    resultado_nivel = _nivel_y_cvegeo(fila)
    if resultado_nivel is None:
        return None
    nivel, cvegeo = resultado_nivel

    cve_ent = fila.get("ENTIDAD", "").strip()
    cve_mun = fila.get("MUN", "").strip() or None
    cve_loc = fila.get("LOC", "").strip() or None
    cve_ageb = fila.get("AGEB", "").strip() or None

    if nivel == "entidad":
        nombre = fila.get("NOM_ENT")
    elif nivel == "municipio":
        nombre = fila.get("NOM_MUN")
    elif nivel == "localidad":
        nombre = fila.get("NOM_LOC")
    else:
        nombre = fila.get("NOM_LOC")

    normalizado = {
        "cvegeo": cvegeo,
        "nivel": nivel,
        "cve_ent": cve_ent,
        "cve_mun": cve_mun,
        "cve_loc": cve_loc,
        "cve_ageb": cve_ageb,
        "nombre": nombre,
        "datos_json": json.dumps(fila, ensure_ascii=False),
    }
    for columna_csv, columna_sql in _COLUMNAS_PROPIAS.items():
        tipo = float if columna_sql in _COLUMNAS_REALES else int
        normalizado[columna_sql] = _num(fila.get(columna_csv), tipo)

    return normalizado


_COLUMNAS_INSERT = ["cvegeo", "nivel", "cve_ent", "cve_mun", "cve_loc", "cve_ageb", "nombre"] + list(
    _COLUMNAS_PROPIAS.values()
) + ["datos_json"]


async def descargar_estado(cve_ent: str) -> int:
    pool = await get_pool()
    clave = f"censo_poblacion:{cve_ent}"

    async with pool.connection() as conn:
        if await esta_hecho(conn, clave):
            return 0

        zip_bytes = await descargar_zip_estado(cve_ent)
        filas_csv = extraer_csv(zip_bytes, cve_ent)

        columnas_sql = ", ".join(_COLUMNAS_INSERT)
        marcadores = ", ".join(f"%({c})s" for c in _COLUMNAS_INSERT)
        actualizables = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNAS_INSERT if c != "cvegeo")

        total = 0
        for fila in filas_csv:
            normalizada = _normalizar(fila)
            if normalizada is None:
                continue
            await conn.execute(
                f"""INSERT INTO fuente_censo_poblacion ({columnas_sql})
                    VALUES ({marcadores})
                    ON CONFLICT (cvegeo) DO UPDATE SET {actualizables}, actualizado = now()""",
                normalizada,
            )
            total += 1

        await marcar_hecho(conn, clave)
    return total
