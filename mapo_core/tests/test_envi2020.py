import csv
import io
import zipfile

import pytest

from mapo_core import envi2020


def _zip(filas):
    columnas = ["FOLIO", "ENT", "EST_DIS", "UPM_DIS", "FACTOR", "P5_1", "P5_2", "P5_4", "P5_9"]
    texto = io.StringIO()
    w = csv.writer(texto)
    w.writerow(columnas)
    w.writerows(filas)
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as z:
        z.writestr(envi2020.CSV, texto.getvalue().encode("utf-8"))
    return salida.getvalue()


# Un estrato, dos UPM. Dos rentadas (una con contrato), una propia y una con renta "no responde".
MUESTRA = _zip([
    ["1", "14", "001", "1", "1", "1", "000002000", "1", ""],
    ["2", "14", "001", "2", "3", "1", "000004000", "2", ""],
    ["3", "14", "001", "1", "1", "5", "", "", "000700000"],
    ["4", "14", "001", "2", "1", "1", "999999999", "2", ""],
])


def test_razon_con_error_por_conglomerado_ultimo():
    filas = [{"estrato": "A", "upm": "1", "w": 1.0, "y": 1}, {"estrato": "A", "upm": "2", "w": 1.0, "y": 0}]
    r, ee, n = envi2020.razon(filas, lambda f: f["y"], lambda f: True)
    # z = ±0.25 por UPM; var = 2/1 · (0.0625 + 0.0625) = 0.25
    assert (r, ee, n) == (0.5, pytest.approx(0.5), 2)


def test_razon_sin_casos_es_nula():
    assert envi2020.razon([{"estrato": "A", "upm": "1", "w": 1.0}], lambda f: 1, lambda f: False) == (None, None, 0)


def test_mediana_ponderada():
    filas = [{"v": 1000, "w": 1.0}, {"v": 5000, "w": 3.0}]
    assert envi2020.mediana(filas, lambda f: f["v"], lambda f: True) == (5000.0, 2)


def test_indicadores_excluyen_no_responde_y_no_inventan_error_de_la_mediana():
    salida = {(f["cve_ent"], f["indicador"]): f for f in envi2020.indicadores(envi2020.leer(MUESTRA))}
    assert salida[("14", "viviendas")]["valor"] == 6
    assert salida[("14", "pct_rentadas")]["valor"] == pytest.approx(500 / 6)
    # Renta válida solo en las dos primeras: (1·2000 + 3·4000) / 4
    media = salida[("14", "renta_mensual_media")]
    assert (media["valor"], media["n_muestra"]) == (3500, 2)
    mediana = salida[("14", "renta_mensual_mediana")]
    assert (mediana["valor"], mediana["error_estandar"]) == (4000.0, None)
    assert salida[("14", "valor_estimado_mediana")]["valor"] == 700_000.0
    assert salida[("14", "pct_rentadas_con_contrato")]["valor"] == pytest.approx(20.0)
    assert salida[("00", "viviendas")]["valor"] == 6


def test_sin_columnas_no_carga():
    with pytest.raises(envi2020.ArchivoInvalido, match="P5_2"):
        envi2020.leer(_zip([]))
