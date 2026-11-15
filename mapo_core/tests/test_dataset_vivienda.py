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


def _fila(cve_mun, x0, y0):
    from shapely.geometry import box

    return {"cve_mun": cve_mun, "_geom": box(x0, y0, x0 + 1, y0 + 1).wkb}


def test_medv_por_clase_y_sin_relleno():
    filas = [_fila("039", 0, 0), _fila("039", 5, 5), _fila("120", 10, 10)]
    v = lambda clase, valor, x, y: {"municipio": "14039", "anio": 2020, "clase": clase, "valor": valor, "lon": x, "lat": y}
    valores = [v("zona", 100, 0.5, 0.5), v("zona", 300, 0.6, 0.6), v("calle", 900, 0.2, 0.2),
               v("calle", 1000, 0.3, 0.3), v("calle", 1100, 0.4, 0.4), v("calle", 50, 5.5, 5.5)]
    dv.asignar_medv(filas, valores, "14")
    a, b, c = filas
    assert (a["medv"], a["medv_n"], a["medv_calle"], a["medv_calle_n"]) == (200.0, 2, 1000.0, 3)
    # Una sola etiqueta de tramo no basta, y sin zona no se inventa nada.
    assert b["medv"] is None and b["medv_calle"] is None and "sin valor de zona" in b["medv_metodo"]
    # Municipio sin tabla: se dice, no se deja en cero.
    assert c["medv"] is None and c["medv_n"] is None and "sin tabla" in c["medv_metodo"]


def test_chas_y_rad_desde_overpass(tmp_path):
    import json

    def via(tags, puntos):
        return {"type": "way", "tags": tags, "geometry": [{"lon": x, "lat": y} for x, y in puntos]}

    agua = tmp_path / "agua.json"
    agua.write_text(json.dumps({"elements": [
        via({"waterway": "river"}, [(-103.40, 20.600), (-103.40, 20.700)]),
        via({"waterway": "stream"}, [(-103.30, 20.600), (-103.30, 20.700)]),
    ]}))
    vias = tmp_path / "vias.json"
    vias.write_text(json.dumps({"elements": [via({"highway": "motorway"}, [(-103.50, 20.60), (-103.50, 20.70)])]}))
    from shapely.geometry import box

    def fila(x):
        return {"lon": x + 0.005, "lat": 20.655, "_geom": box(x, 20.65, x + 0.01, 20.66).wkb}

    junto_al_rio, junto_al_arroyo = fila(-103.4005), fila(-103.3005)
    dv.asignar_osm([junto_al_rio, junto_al_arroyo], agua, vias)
    assert junto_al_rio["chas"] == 1
    assert junto_al_arroyo["chas"] == 0  # los arroyos no cuentan
    # Del punto (-103.3955) a la vía (-103.50): unos 10.9 km a esa latitud.
    assert 10.5 < junto_al_rio["rad_km"] < 11.3
