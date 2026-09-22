import io
import zipfile

import pytest

from mapo_core.enigh_downloader import _extraer_filas, _float_seguro, _normalizar

# Fila real de concentradohogar (folioviv/factor/gasto_mon/ing_cor
# confirmados por el usuario contra una descarga real, mismos valores
# que ya usan los tests de Gaiarda).
FILA_REAL = {
    "folioviv": "100001901",
    "foliohog": "1",
    "ubica_geo": "1001",
    "factor": "207",
    "gasto_mon": "29582.6",
    "ing_cor": "138232.38",
    "alimentos": "17858.49",
    "vivienda": "6475.63",
    "transporte": "9929.03",
    "educa_espa": "8651.61",
    "salud": "0",
    "vesti_calz": "635.86",
    "transf_gas": "0",
    "percep_tot": "13499.97",
    "erogac_tot": "29582.6",
    "ingtrab": "130518.1",
}


def test_normalizar_deriva_cve_ent_y_cve_mun_de_ubica_geo():
    normalizado = _normalizar(FILA_REAL)
    assert normalizado["cve_ent"] == "01"
    assert normalizado["cve_mun"] == "001"
    assert normalizado["ubica_geo"] == "01001"


def test_normalizar_conserva_los_montos_reales():
    normalizado = _normalizar(FILA_REAL)
    assert normalizado["factor"] == pytest.approx(207.0)
    assert normalizado["gasto_mon"] == pytest.approx(29582.6)
    assert normalizado["ing_cor"] == pytest.approx(138232.38)


def test_normalizar_sin_folioviv_da_none():
    assert _normalizar({**FILA_REAL, "folioviv": ""}) is None


def test_float_seguro_con_valor_invalido_da_none():
    assert _float_seguro("") is None
    assert _float_seguro(None) is None
    assert _float_seguro("no es un numero") is None


def _zip_con_csv(nombre: str, texto_csv: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(nombre, texto_csv)
    return buf.getvalue()


def test_extraer_filas_usa_comas():
    encabezado = ["folioviv", "foliohog", "ubica_geo", "factor"]
    csv_texto = ",".join(encabezado) + "\n100001901,1,01001,207\n"
    zip_bytes = _zip_con_csv("concentradohogar.csv", csv_texto)

    filas = _extraer_filas(zip_bytes)

    assert len(filas) == 1
    assert filas[0]["ubica_geo"] == "01001"


def test_extraer_filas_truena_si_el_delimitador_no_separa_nada():
    # Separado por punto y coma: con el parser de comas no se parte nada,
    # mismo candado de seguridad que ya usa Gaiarda para este bug real.
    csv_texto = "folioviv;foliohog;ubica_geo;factor\n100001901;1;01001;207\n"
    zip_bytes = _zip_con_csv("concentradohogar.csv", csv_texto)

    with pytest.raises(ValueError, match="una sola columna"):
        _extraer_filas(zip_bytes)


def test_extraer_filas_sin_ningun_csv_truena():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "esto no es un csv")

    with pytest.raises(ValueError, match="ningun .csv"):
        _extraer_filas(buf.getvalue())
