"""Índice SHF de Precios de la Vivienda, desde la API del SNIIV (SEDATU).

Trimestral desde 2005-I, base 2018 = 100. Lo territorial (32 estados, 8 zonas
metropolitanas y 74 municipios) solo trae el índice general; lo nacional viene
por categoría (nueva, usada, tipología, clase) y sin serie general. Sale de
avalúos de crédito hipotecario: deja fuera la compra de contado y la informal.
No trae precio en pesos. Ver docs/fuentes/shf.md.

La API territorial regresa el valor "inicial" y "final" entre dos trimestres; con
el mismo trimestre en los dos lados da el índice de ese trimestre.
"""

from __future__ import annotations

import httpx

from mapo_core.db import get_pool

BASE = "https://sniiv.sedatu.gob.mx/api/ShfPriceAPI"
_TIMEOUT = 120.0


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
