import pytest

from mapo_core.enigh_resumen import (
    DIAS_POR_TRIMESTRE,
    _percentil_ponderado,
    _promedio_ponderado,
    resumen_por_municipio,
)

# Mismas 5 filas reales de concentradohogar que ya usan los tests de
# Gaiarda (folioviv/factor/gasto_mon confirmados contra una descarga
# real), 4 en el municipio 01001 y 1 en el 01002 para poder probar el
# filtro por municipio.
FILAS_REALES = [
    ("100001901", "01", "001", 207.0, 29582.6),
    ("100001902", "01", "001", 207.0, 22403.7),
    ("100001904", "01", "001", 207.0, 22403.7),
    ("100001905", "01", "001", 207.0, 22768.99),
    ("100002501", "01", "002", 196.0, 35706.51),
]


async def _insertar_concentrado(conn):
    for folioviv, cve_ent, cve_mun, factor, gasto_mon in FILAS_REALES:
        await conn.execute(
            """INSERT INTO fuente_enigh_concentradohogar
                 (folioviv, foliohog, ubica_geo, cve_ent, cve_mun, factor, gasto_mon)
               VALUES (%(folioviv)s, '1', %(ubica_geo)s, %(cve_ent)s, %(cve_mun)s, %(factor)s, %(gasto_mon)s)""",
            {
                "folioviv": folioviv,
                "ubica_geo": cve_ent + cve_mun,
                "cve_ent": cve_ent,
                "cve_mun": cve_mun,
                "factor": factor,
                "gasto_mon": gasto_mon,
            },
        )


def test_percentil_ponderado_caso_simple():
    pares = [(10.0, 1.0), (20.0, 1.0), (30.0, 1.0)]
    assert _percentil_ponderado(pares, 50) == 20.0
    assert _percentil_ponderado(pares, 0) == 10.0


def test_percentil_ponderado_sin_datos():
    assert _percentil_ponderado([], 50) is None


def test_promedio_ponderado_favorece_el_peso_mayor():
    pares = [(10.0, 1.0), (100.0, 99.0)]
    assert _promedio_ponderado(pares) > 90


@pytest.mark.asyncio
async def test_resumen_rechaza_columna_no_permitida(conn):
    with pytest.raises(ValueError):
        await resumen_por_municipio(conn, "01", "001", columna="clave; DROP TABLE x;--")


@pytest.mark.asyncio
async def test_resumen_por_municipio_con_datos_reales(conn):
    await _insertar_concentrado(conn)

    resultado = await resumen_por_municipio(conn, "01", "001", columna="gasto_mon", por_dia=False)

    assert resultado["n_hogares_muestra"] == 4
    assert resultado["periodo"] == "trimestral"
    assert 22403.7 <= resultado["promedio_ponderado"] <= 29582.6
    assert 22403.7 <= resultado["mediana"] <= 29582.6


@pytest.mark.asyncio
async def test_resumen_por_dia_divide_entre_dias_por_trimestre(conn):
    await _insertar_concentrado(conn)

    trimestral = await resumen_por_municipio(conn, "01", "001", columna="gasto_mon", por_dia=False)
    diario = await resumen_por_municipio(conn, "01", "001", columna="gasto_mon", por_dia=True)

    assert diario["periodo"] == "diario"
    assert diario["promedio_ponderado"] == pytest.approx(trimestral["promedio_ponderado"] / DIAS_POR_TRIMESTRE)
    assert diario["n_hogares_muestra"] == trimestral["n_hogares_muestra"]


@pytest.mark.asyncio
async def test_resumen_sin_hogares_muestreados_da_none(conn):
    await _insertar_concentrado(conn)

    resultado = await resumen_por_municipio(conn, "01", "999", columna="gasto_mon")

    assert resultado is None
