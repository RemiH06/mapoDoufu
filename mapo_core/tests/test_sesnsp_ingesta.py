import csv
import io

import pytest

from mapo_core.sesnsp_ingesta import _int_seguro, _normalizar_fila, cargar_archivo, parsear_archivo

# Filas reales pegadas por el usuario directo del CSV (IDM_NM_dic25.csv),
# mismas que ya usan los tests de Gaiarda.
FILA_REAL_ARMA_FUEGO = {
    "Año": "2015", "Clave_Ent": "1", "Entidad": "Aguascalientes",
    "Cve. Municipio": "1001", "Municipio": "Aguascalientes",
    "Bien jurídico afectado": "La vida y la Integridad corporal",
    "Tipo de delito": "Homicidio", "Subtipo de delito": "Homicidio doloso",
    "Modalidad": "Con arma de fuego",
    "Enero": "2", "Febrero": "0", "Marzo": "1", "Abril": "1", "Mayo": "0", "Junio": "1",
    "Julio": "1", "Agosto": "0", "Septiembre": "2", "Octubre": "1", "Noviembre": "0", "Diciembre": "1",
}

FILA_REAL_TRANSITO = {
    "Año": "2015", "Clave_Ent": "1", "Entidad": "Aguascalientes",
    "Cve. Municipio": "1001", "Municipio": "Aguascalientes",
    "Bien jurídico afectado": "La vida y la Integridad corporal",
    "Tipo de delito": "Homicidio", "Subtipo de delito": "Homicidio culposo",
    "Modalidad": "En accidente de tránsito",
    "Enero": "9", "Febrero": "10", "Marzo": "3", "Abril": "11", "Mayo": "6", "Junio": "4",
    "Julio": "6", "Agosto": "6", "Septiembre": "11", "Octubre": "6", "Noviembre": "3", "Diciembre": "7",
}


def test_cve_municipio_se_descompone_correctamente():
    filas = _normalizar_fila(FILA_REAL_ARMA_FUEGO)
    assert filas[0]["cve_ent"] == "01"
    assert filas[0]["cve_mun"] == "001"


def test_normalizar_fila_regresa_12_meses():
    filas = _normalizar_fila(FILA_REAL_ARMA_FUEGO)
    assert len(filas) == 12
    assert [f["mes"] for f in filas] == list(range(1, 13))


def test_cantidades_por_mes_coinciden_con_el_csv_real():
    filas = _normalizar_fila(FILA_REAL_ARMA_FUEGO)
    cantidades = {f["mes"]: f["cantidad"] for f in filas}
    assert cantidades[1] == 2   # Enero
    assert cantidades[2] == 0   # Febrero
    assert cantidades[9] == 2   # Septiembre
    assert cantidades[12] == 1  # Diciembre


def test_int_seguro_con_valores_raros():
    assert _int_seguro(None) == 0
    assert _int_seguro("") == 0
    assert _int_seguro("7") == 7
    assert _int_seguro("no_es_numero") == 0


def _escribir_csv_real(ruta) -> None:
    with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(FILA_REAL_ARMA_FUEGO.keys()))
        escritor.writeheader()
        escritor.writerow(FILA_REAL_ARMA_FUEGO)
        escritor.writerow(FILA_REAL_TRANSITO)


def test_parsear_archivo_da_24_filas_para_2_delitos(tmp_path):
    ruta = tmp_path / "sesnsp.csv"
    _escribir_csv_real(ruta)

    filas = parsear_archivo(ruta)

    assert len(filas) == 24  # 2 filas del csv * 12 meses cada una


@pytest.mark.asyncio
async def test_cargar_archivo_guarda_en_la_base(tmp_path, conn, pool_de_una_conexion, monkeypatch):
    ruta = tmp_path / "sesnsp.csv"
    _escribir_csv_real(ruta)

    async def _pool_de_prueba():
        return pool_de_una_conexion

    monkeypatch.setattr("mapo_core.sesnsp_ingesta.get_pool", _pool_de_prueba)

    total = await cargar_archivo(ruta)

    assert total == 24

    cursor = await conn.execute(
        "SELECT sum(cantidad) FROM fuente_sesnsp_delitos_municipal WHERE mes = 1 AND cve_ent = '01' AND cve_mun = '001'"
    )
    (suma_enero,) = await cursor.fetchone()
    assert suma_enero == 2 + 9  # arma de fuego enero (2) + transito enero (9)
