"""Finanzas públicas municipales de INEGI, EFIPEM (sesión 28): ingresos por capítulo
(impuestos, derechos, participaciones, aportaciones...), el predial y egresos por
capítulo, de cada municipio y año. Ver docs/fuentes/efipem.md.

Del zip nacional (`efipem_municipal_csv.zip`, un CSV largo por año desde 1989) se
guardan los últimos años y solo los niveles de tema y capítulo, más la partida del
impuesto predial. Un municipio que no reportó un año no tiene renglones: se dice que
falta, nunca cero.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

URL = "https://www.inegi.org.mx/contenidos/programas/finanzas/datosabiertos/efipem_municipal_csv.zip"
ANIOS = 5
# Ingresos que recauda el propio municipio, contra los que le transfieren.
PROPIOS = ("Impuestos", "Contribuciones de Mejoras", "Derechos", "Productos", "Aprovechamientos")
TRANSFERENCIAS = ("Participaciones federales", "Aportaciones federales y estatales")
PREDIAL = "Impuesto predial"
_ANIO = re.compile(r"tr_cifra_(\d{4})\.csv$")


class ArchivoInvalido(Exception):
    pass


def _limpio(texto: str) -> str:
    # INEGI escribe a veces espacios duros ("Remuneraciones\xa0al\xa0personal").
    return " ".join((texto or "").replace("\xa0", " ").split())


def leer(ruta: Path, anios: int = ANIOS) -> list[dict]:
    with zipfile.ZipFile(ruta) as z:
        por_anio = sorted((int(m.group(1)), n) for n in z.namelist() if (m := _ANIO.search(n)))
        if not por_anio:
            raise ArchivoInvalido("no hay archivos efipem_municipal_anual_tr_cifra_AAAA.csv")
        filas = []
        for anio, nombre in por_anio[-anios:]:
            texto = io.TextIOWrapper(z.open(nombre), encoding="utf-8", errors="replace")
            for f in csv.DictReader(texto):
                categoria = _limpio(f["CATEGORIA"])
                concepto = _limpio(f["DESCRIPCION_CATEGORIA"])
                if categoria not in ("Tema", "Capítulo") and concepto != PREDIAL:
                    continue
                try:
                    valor = float(f["VALOR"])
                except ValueError:
                    continue
                filas.append({"anio": anio, "cve_ent": f["ID_ENTIDAD"].zfill(2), "cve_mun": f["ID_MUNICIPIO"].zfill(3),
                              "tema": _limpio(f["TEMA"]), "categoria": categoria, "concepto": concepto,
                              "valor": valor, "estatus": _limpio(f.get("ESTATUS", ""))})
    return filas


def revisar(filas: list[dict]) -> list[str]:
    """Los capítulos de ingresos suman el total de ingresos de cada municipio y año
    (al peso); los que no, se listan."""
    total: dict = {}
    suma: dict = {}
    for f in filas:
        if f["tema"] != "Ingresos":
            continue
        clave = (f["anio"], f["cve_ent"], f["cve_mun"])
        if f["categoria"] == "Tema":
            total[clave] = f["valor"]
        elif f["categoria"] == "Capítulo":
            suma[clave] = suma.get(clave, 0) + f["valor"]
    return [f"{a} {e}{m}: capítulos {suma.get((a, e, m), 0):,.0f}, total {t:,.0f}"
            for (a, e, m), t in total.items() if abs(suma.get((a, e, m), 0) - t) > 1]


async def cargar(pool: AsyncConnectionPool, ruta: Path) -> dict:
    filas = leer(ruta)
    if len(filas) < 10_000:
        raise ArchivoInvalido(f"solo {len(filas)} renglones: el país tiene más de dos mil municipios por año")
    descuadres = revisar(filas)
    columnas = ["anio", "cve_ent", "cve_mun", "tema", "categoria", "concepto", "valor", "estatus"]
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM fuente_efipem_municipal")
            async with conn.cursor() as cur:
                async with cur.copy(f"COPY fuente_efipem_municipal ({', '.join(columnas)}) FROM STDIN") as copia:
                    for f in filas:
                        await copia.write_row([f[c] for c in columnas])
    anios = sorted({f["anio"] for f in filas})
    return {"anios": anios, "renglones": len(filas),
            "municipios_ultimo": len({(f["cve_ent"], f["cve_mun"]) for f in filas if f["anio"] == anios[-1]}),
            "descuadres": descuadres[:20], "num_descuadres": len(descuadres)}


async def municipio(pool: AsyncConnectionPool, cve_ent: str, cve_mun: str) -> dict | None:
    """El último año reportado del municipio con ingresos y egresos por capítulo, y la
    parte de ingresos propios de cada año. None si EFIPEM no está cargado."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT anio, tema, categoria, concepto, valor, actualizado::date::text
               FROM fuente_efipem_municipal WHERE cve_ent = %s AND cve_mun = %s ORDER BY anio""",
            (cve_ent, cve_mun))
        filas = await cur.fetchall()
        cur = await conn.execute("SELECT max(anio) FROM fuente_efipem_municipal")
        (ultimo_publicado,) = await cur.fetchone()
    if ultimo_publicado is None:
        return None
    if not filas:
        return {"sin_dato": True, "ultimo_publicado": ultimo_publicado}
    por_anio: dict[int, dict] = {}
    for anio, tema, categoria, concepto, valor, _ in filas:
        a = por_anio.setdefault(anio, {"ingresos": {}, "egresos": {}, "total_ingresos": None,
                                       "total_egresos": None, "predial": None})
        if categoria == "Tema":
            a["total_ingresos" if tema == "Ingresos" else "total_egresos"] = valor
        elif concepto == PREDIAL:
            a["predial"] = valor
        else:
            a["ingresos" if tema == "Ingresos" else "egresos"][concepto] = valor

    def parte(a: dict, conceptos: tuple[str, ...]) -> float | None:
        if not a["total_ingresos"]:
            return None
        return round(100 * sum(a["ingresos"].get(c, 0) for c in conceptos) / a["total_ingresos"], 1)

    anio = max(por_anio)
    a = por_anio[anio]
    return {
        "anio": anio,
        "ultimo_publicado": ultimo_publicado,
        "total_ingresos": a["total_ingresos"],
        "total_egresos": a["total_egresos"],
        "predial": a["predial"],
        "ingresos": sorted(a["ingresos"].items(), key=lambda x: -x[1]),
        "egresos": sorted(a["egresos"].items(), key=lambda x: -x[1]),
        "propios_pct": parte(a, PROPIOS),
        "transferencias_pct": parte(a, TRANSFERENCIAS),
        "serie_propios": [{"anio": y, "propios_pct": parte(v, PROPIOS)} for y, v in sorted(por_anio.items())],
        "cargado": filas[-1][5],
    }
