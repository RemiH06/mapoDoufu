"""Cálculos del dataset tipo Boston Housing (docs/producto/dataset-vivienda.md)."""

import math

from mapo_core import dataset_vivienda as dv


def test_reservados_del_censo_quedan_vacios():
    assert dv._num({"X": "*"}, "X") is None
    assert dv._num({"X": "N/D"}, "X") is None
    assert dv._num({"X": "12"}, "X") == 12.0
    assert dv._porcentaje(5, 0) is None
    assert dv._porcentaje(None, 10) is None


def test_cuartos_promedio_es_cota_inferior():
    datos = {"VPH_1CUART": "10", "VPH_2CUART": "30", "VPH_3YMASC": "60"}
    assert dv.cuartos_promedio(datos) == 2.5  # (10 + 60 + 180) / 100
    assert dv.cuartos_promedio({**datos, "VPH_1CUART": "*"}) is None


def test_sin_secundaria_suma_los_cuatro_grupos():
    datos = {"P15YM_SE": "5", "P15PRI_IN": "10", "P15PRI_CO": "15", "P15SEC_IN": "20", "P_15YMAS": "200"}
    assert dv.sin_secundaria(datos) == 25.0


def test_centros_de_empleo_separados():
    # Dos focos grandes a 10 km y uno chico pegado al primero: el chico no cuenta.
    negocios = [(-103.35, 20.67, 1000), (-103.35, 20.761, 800), (-103.351, 20.671, 500)]
    centros = dv.centros_de_empleo(negocios, n=3)
    assert len(centros) == 2
    assert centros[0]["personal"] == 1500


def test_distancia_ponderada():
    centros = [{"lon": 0.0, "lat": 0.0, "personal": 1}, {"lon": 0.0, "lat": 0.0, "personal": 3}]
    assert dv.distancia_ponderada_km(0.0, 0.0, centros) == 0
    un_grado = dv.distancia_ponderada_km(0.0, 1.0, centros)
    assert math.isclose(un_grado, 111.19, abs_tol=0.1)
    assert dv.distancia_ponderada_km(0.0, 0.0, []) is None


def test_diccionario_cubre_las_columnas_de_boston_salvo_b():
    boston = {c.boston.split(" ")[0] for c in dv.DICCIONARIO if c.boston}
    assert {"MEDV", "CRIM", "ZN", "INDUS", "CHAS", "NOX", "RM", "AGE", "DIS", "RAD", "TAX", "PTRATIO", "LSTAT"} <= boston
    assert "B" not in boston
