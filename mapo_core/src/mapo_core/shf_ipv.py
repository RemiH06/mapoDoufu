"""Índice SHF de Precios de la Vivienda, desde la API del SNIIV (SEDATU).

Trimestral desde 2005-I, base 2018 = 100. Lo territorial (32 estados, 8 zonas
metropolitanas y 74 municipios) solo trae el índice general; lo nacional viene
por categoría (nueva, usada, tipología, clase) y sin serie general. Sale de
avalúos de crédito hipotecario: deja fuera la compra de contado y la informal.
No trae precio en pesos. Ver docs/fuentes/shf.md.

Qué municipios forman cada zona y con cuántos avalúos se calcula cada serie no
están en la API: son la respuesta de la SHF por transparencia (2026-11-20), en
`shf_zonas.csv` y `shf_avaluos.csv` (scripts/shf/extraer.py).

La API territorial regresa el valor "inicial" y "final" entre dos trimestres; con
el mismo trimestre en los dos lados da el índice de ese trimestre.
"""

from __future__ import annotations

import csv
from functools import cache
from pathlib import Path

import httpx

from mapo_core.db import get_pool

BASE = "https://sniiv.sedatu.gob.mx/api/ShfPriceAPI"
_TIMEOUT = 120.0
_AQUI = Path(__file__).parent
# La respuesta llega a 2026, pero ese año está a medias: no se compara con los demás.
ULTIMO_ANIO_COMPLETO = 2025


class RespuestaInvalida(Exception):
    pass


def periodos(configuracion: dict) -> list[tuple[int, int]]:
    return [(p["year"], p["quarter"]) for p in configuracion["periods"]]


def categorias(configuracion: dict) -> list[str]:
    return [o["value"] for g in configuracion["filterGroups"] for o in g["options"]]


def leer_territorial(datos: dict, anio: int, trimestre: int) -> list[dict]:
    """Un trimestre de `GetTerritorialVariation` (base = final) a filas."""
    filas = []
    for e in datos["states"]:
        filas.append({"nivel": "estado", "clave": e["stateCode"], "nombre": e["stateName"],
                      "indice": e["finalValue"]})
    for z in datos["metropolitanAreas"]:
        filas.append({"nivel": "zm", "clave": z["category"], "nombre": z["name"], "indice": z["finalValue"]})
    for m in datos["municipalities"]:
        filas.append({"nivel": "municipio", "clave": m["stateCode"] + m["municipalityCode"],
                      "nombre": m["municipalityName"], "indice": m["finalValue"]})
    if not datos["states"]:
        raise RespuestaInvalida(f"{anio}-{trimestre}: la API no regresó estados.")
    return [{**f, "categoria": "General", "anio": anio, "trimestre": trimestre}
            for f in filas if f["indice"] is not None]


def leer_nacional(datos: dict) -> list[dict]:
    """`GetNationalPrices` (una serie por categoría) a filas."""
    trimestres = [(p["year"], p["quarter"]) for p in datos["periods"]]
    filas = []
    for serie in datos["series"]:
        if len(serie["values"]) != len(trimestres):
            raise RespuestaInvalida(f"La serie {serie['name']} no trae un valor por trimestre.")
        for (anio, trimestre), valor in zip(trimestres, serie["values"]):
            if valor is not None:
                filas.append({"nivel": "nacional", "clave": "00", "nombre": "Nacional",
                              "categoria": serie["category"], "anio": anio, "trimestre": trimestre,
                              "indice": valor})
    return filas


async def descargar() -> dict[str, int]:
    """Baja la serie completa y reemplaza la tabla en una transacción.
    Regresa cuántas filas quedaron por nivel."""
    async with httpx.AsyncClient(base_url=BASE, timeout=_TIMEOUT) as cliente:
        async def pedir(ruta: str, **params) -> dict:
            r = await cliente.get(ruta, params=params)
            r.raise_for_status()
            return r.json()

        config = await pedir("/GetConfiguration")
        trimestres = periodos(config)
        filas = []
        for anio, trimestre in trimestres:
            datos = await pedir("/GetTerritorialVariation", baseYear=anio, baseQuarter=trimestre,
                                finalYear=anio, finalQuarter=trimestre)
            filas += leer_territorial(datos, anio, trimestre)
        (a0, t0), (a1, t1) = trimestres[0], trimestres[-1]
        filas += leer_nacional(await pedir(
            "/GetNationalPrices", startYear=a0, startQuarter=t0, endYear=a1, endQuarter=t1,
            categories=",".join(categorias(config)), metric="index",
        ))

    columnas = ["nivel", "clave", "nombre", "categoria", "anio", "trimestre", "indice"]
    pool = await get_pool()
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("DELETE FROM fuente_shf_ipv")
        async with conn.cursor().copy(f"COPY fuente_shf_ipv ({', '.join(columnas)}) FROM STDIN") as copia:
            for f in filas:
                await copia.write_row([f[c] for c in columnas])

    conteo: dict[str, int] = {}
    for f in filas:
        conteo[f["nivel"]] = conteo.get(f["nivel"], 0) + 1
    return conteo


@cache
def zonas() -> dict[str, tuple[str, str]]:
    """cvegeo -> (clave de la zona en la serie, nombre), según el SUN 2018."""
    with open(_AQUI / "shf_zonas.csv", encoding="utf-8", newline="") as f:
        return {r["cvegeo"]: (r["clave"], r["nombre"]) for r in csv.DictReader(f)}


@cache
def _avaluos() -> dict[str, dict[int, int]]:
    series: dict[str, dict[int, int]] = {}
    with open(_AQUI / "shf_avaluos.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if int(r["anio"]) <= ULTIMO_ANIO_COMPLETO:
                series.setdefault(r["clave"], {})[int(r["anio"])] = int(r["avaluos"])
    return series


def avaluos(clave: str) -> dict | None:
    """Avalúos detrás de la serie de un municipio o de una zona: los del último año
    completo y los del año con menos. En una zona, además cuántos son de sus
    municipios sin índice propio. None si la SHF no los dio (estados)."""
    serie = _avaluos().get(clave)
    if serie is None:
        return None
    minimo = min(serie, key=serie.__getitem__)
    datos = {
        "anio": ULTIMO_ANIO_COMPLETO,
        "total": serie[ULTIMO_ANIO_COMPLETO],
        "minimo": {"anio": minimo, "total": serie[minimo]},
    }
    miembros = [m for m, (z, _nombre) in zonas().items() if z == clave]
    if miembros:
        propios = [m for m in miembros if m in _avaluos()]
        datos["sin_indice"] = {
            "municipios": len(miembros) - len(propios),
            "total": datos["total"] - sum(_avaluos()[m][ULTIMO_ANIO_COMPLETO] for m in propios),
        }
    return datos
