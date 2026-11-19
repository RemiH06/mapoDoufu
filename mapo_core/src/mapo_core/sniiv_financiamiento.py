"""Financiamientos para vivienda del SNIIV (SEDATU), por municipio y año.

Número de acciones y monto en pesos por organismo (INFONAVIT, FOVISSSTE, banca,
CONAVI...), destino del crédito (vivienda nueva, existente, mejoramiento...) y
segmento de valor de la vivienda (económica a residencial plus). No es precio:
el segmento es una categoría, y el monto es lo prestado. Ver docs/fuentes/sniiv.md.

La API acepta hasta 5 dimensiones; se usan año, municipio, organismo, destino y
valor, así que el mes queda fuera. Para no confundir un año a medias con una caída,
cada fila guarda cuántos meses tiene publicados su año (una consulta nacional por
mes aparte).
"""

from __future__ import annotations

import datetime

import httpx

from mapo_core.db import get_pool

BASE = "https://sniiv.sedatu.gob.mx/api/CuboAPI/GetFinanciamiento"
DIMENSIONES = "anio,municipio,organismo,destino_credito,valor_vivienda"
DESDE = 2013
ESTADOS = [f"{n:02d}" for n in range(1, 33)]
_TIMEOUT = 300.0
_LLAVE = ("anio", "cve_mun", "organismo", "destino_credito", "valor_vivienda")


def url(desde: int, hasta: int, cve_ent: str, dimensiones: str = DIMENSIONES) -> str:
    return f"{BASE}/{desde},{hasta}/{cve_ent}/000/{dimensiones}"


def _anio(fila: dict) -> int:
    # La llave del año es "año"; se busca por forma para no depender del acento.
    for llave, valor in fila.items():
        if llave in ("anio", "año"):
            return int(valor)
    raise KeyError("la fila no trae año")


def leer(datos: list[dict], cve_ent: str) -> list[dict]:
    """Respuesta de la API a filas, sumando las que repitan llave."""
    suma: dict[tuple, dict] = {}
    for d in datos:
        fila = {
            "anio": _anio(d),
            "cve_mun": d["clave_municipio"],
            "organismo": d["organismo"],
            "destino_credito": d["destino_credito"],
            "valor_vivienda": d["valor_vivienda"],
        }
        llave = tuple(fila[c] for c in _LLAVE)
        acumulada = suma.setdefault(llave, {**fila, "cve_ent": cve_ent, "acciones": 0, "monto": 0.0})
        acumulada["acciones"] += int(d["acciones"])
        acumulada["monto"] += float(d["monto"] or 0)
    return list(suma.values())


def meses_por_anio(datos: list[dict]) -> dict[int, int]:
    """De una consulta `anio,mes`: cuántos meses trae cada año."""
    meses: dict[int, set] = {}
    for d in datos:
        meses.setdefault(_anio(d), set()).add(d["mes"])
    return {a: len(m) for a, m in meses.items()}


async def descargar(estados: list[str] | None = None, hasta: int | None = None) -> dict[str, int]:
    """Baja los estados pedidos (default: los 32) y reemplaza sus filas, cada estado
    en su transacción. Regresa filas por estado."""
    estados = estados or ESTADOS
    hasta = hasta or datetime.date.today().year
    async with httpx.AsyncClient(timeout=_TIMEOUT) as cliente:
        async def pedir(direccion: str) -> list[dict]:
            r = await cliente.get(direccion)
            r.raise_for_status()
            return r.json()

        meses = meses_por_anio(await pedir(url(DESDE, hasta, "00", "anio,mes")))
        conteo = {}
        pool = await get_pool()
        for cve_ent in estados:
            filas = leer(await pedir(url(DESDE, hasta, cve_ent)), cve_ent)
            columnas = ["anio", "meses", "cve_ent", "cve_mun", "organismo", "destino_credito",
                        "valor_vivienda", "acciones", "monto"]
            async with pool.connection() as conn, conn.transaction():
                await conn.execute("DELETE FROM fuente_sniiv_financiamiento WHERE cve_ent = %s", (cve_ent,))
                async with conn.cursor().copy(
                    f"COPY fuente_sniiv_financiamiento ({', '.join(columnas)}) FROM STDIN"
                ) as copia:
                    for f in filas:
                        await copia.write_row([meses.get(f["anio"], 0) if c == "meses" else f[c]
                                               for c in columnas])
            conteo[cve_ent] = len(filas)
    return conteo
