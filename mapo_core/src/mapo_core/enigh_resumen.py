"""Resumen ponderado de consumo por municipio, vendorizado de
`gaiarda/src/gaiarda/fuentes/enigh/resumen.py`.

Periodo de las cifras: trimestral (confirmado contra la documentacion
oficial de INEGI). `DIAS_POR_TRIMESTRE` usa 91.25 para la conversion a
"por dia".

ADVERTENCIA sobre el nivel geografico: ENIGH es representativa a nivel
nacional, por entidad, y por dominio rural/urbano. NO declara
representatividad a nivel municipio. Este modulo agrupa por municipio
porque el dato lo permite tecnicamente, pero la muestra real ahi puede
ser chica (a veces un puñado de hogares). Por eso `n_hogares_muestra`
siempre viene en el resultado: no es un adorno, es la señal de que tan
en serio tomarse cada numero. Nunca ocultarlo en la interfaz.

Por que "ponderado": ENIGH es una encuesta, no un censo. Cada hogar
encuestado representa a `factor` hogares reales.
"""
from __future__ import annotations

DIAS_POR_TRIMESTRE = 91.25

COLUMNAS_PERMITIDAS = {
    "ing_cor", "ingtrab", "gasto_mon", "alimentos", "vivienda", "transporte",
    "educa_espa", "salud", "vesti_calz", "transf_gas", "percep_tot", "erogac_tot",
}


def _percentil_ponderado(pares_valor_peso: list[tuple[float, float]], percentil: float) -> float | None:
    if not pares_valor_peso:
        return None
    ordenados = sorted(pares_valor_peso, key=lambda par: par[0])
    peso_total = sum(peso for _, peso in ordenados)
    if peso_total <= 0:
        return None

    objetivo = (percentil / 100) * peso_total
    acumulado = 0.0
    for valor, peso in ordenados:
        acumulado += peso
        if acumulado >= objetivo:
            return valor
    return ordenados[-1][0]


def _promedio_ponderado(pares_valor_peso: list[tuple[float, float]]) -> float | None:
    peso_total = sum(peso for _, peso in pares_valor_peso)
    if peso_total <= 0:
        return None
    return sum(valor * peso for valor, peso in pares_valor_peso) / peso_total


def _dividir(valor: float | None, divisor: float) -> float | None:
    return None if valor is None else valor / divisor


async def resumen_por_municipio(
    conn, cve_ent: str, cve_mun: str, columna: str = "gasto_mon", *, por_dia: bool = True,
) -> dict | None:
    """Regresa el resumen ponderado de `columna` (una de
    `COLUMNAS_PERMITIDAS`) para los hogares de ENIGH ubicados en este
    municipio, o None si no hay ningun hogar muestreado ahi."""
    if columna not in COLUMNAS_PERMITIDAS:
        raise ValueError(f"columna invalida: '{columna}'. Usa una de: {sorted(COLUMNAS_PERMITIDAS)}")

    cursor = await conn.execute(
        f'SELECT factor, "{columna}" FROM fuente_enigh_concentradohogar '
        f"WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s",
        {"cve_ent": cve_ent, "cve_mun": cve_mun},
    )
    filas = await cursor.fetchall()

    pares = [(valor, factor) for factor, valor in filas if factor is not None and valor is not None]
    if not pares:
        return None

    divisor = DIAS_POR_TRIMESTRE if por_dia else 1.0
    return {
        "n_hogares_muestra": len(pares),
        "periodo": "diario" if por_dia else "trimestral",
        "promedio_ponderado": _dividir(_promedio_ponderado(pares), divisor),
        "mediana": _dividir(_percentil_ponderado(pares, 50), divisor),
    }
