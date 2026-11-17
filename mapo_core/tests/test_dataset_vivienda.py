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


def test_tablas_de_predial_cuadran_tramo_a_tramo():
    # La cuota fija de cada tramo es la del anterior más su ancho por su tasa:
    # así se comprobó la transcripción de cada ley (docs/producto/dataset-vivienda.md).
    for clave, t in dv.tablas_predial().items():
        for (li, cf, tasa), (li2, cf2, _) in zip(t["tramos"], t["tramos"][1:]):
            assert abs(cf + (li2 - li) * tasa - cf2) <= max(1.5, 0.002 * cf2), (clave, li2)


def test_tax_de_guadalajara():
    # VF 1,000,000 cae en el tramo 776,142.91: (223,857.09 × 0.000254 + 197.15) × 6 = 1,524.06
    tax = dv.tax_por_municipio("14", dv.tablas_predial())
    assert tax["039"] == (15.24, 2026)
    # Tasa al millar: 0.23 al millar más 38.40 por bimestre.
    assert tax["124"][0] == round(6 * (1_000_000 * 0.00023 + 38.40) / 1_000_000 * 10_000, 2)


def test_ptratio_publico_y_todas(tmp_path):
    ruta = tmp_path / "sep.csv"
    ruta.write_text(
        "municipio,ciclo,nivel,control,localidades,escuelas,alumnos,docentes\n"
        "14039,2025-2026,basica,todos,1,1436,227087,13205\n"
        "14039,2025-2026,basica,publico,1,873,170305,9878\n"
        "15001,2025-2026,basica,publico,1,1,10,1\n",
        encoding="utf-8",
    )
    r = dv.leer_ptratio(ruta, "14")
    assert r == {"039": {"ptratio": 17.24, "ptratio_todas": 17.2, "ptratio_ciclo": "2025-2026"}}


def test_nox_toma_la_celda_del_punto(tmp_path):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    ruta = tmp_path / "no2.tif"
    media = np.array([[10.0, np.nan], [30.0, 40.0]], dtype="float32")
    obs = np.array([[5, 0], [7, 8]], dtype="float32")
    with rasterio.open(ruta, "w", driver="GTiff", height=2, width=2, count=2, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(-104, 21, 0.5, 0.5), nodata=np.nan) as r:
        r.write(media, 1)
        r.write(obs, 2)
    # Celdas de 0.5° desde (-104, 21): la columna 2 empieza en -103.5 y el renglón 2 en 20.5.
    filas = [{"lon": -103.9, "lat": 20.9}, {"lon": -103.4, "lat": 20.9}, {"lon": -103.4, "lat": 20.4}]
    dv.asignar_no2(filas, ruta)
    assert (filas[0]["nox"], filas[0]["nox_obs"]) == (10.0, 5)
    assert filas[1]["nox"] is None and filas[1]["nox_obs"] is None  # celda sin observaciones
    assert (filas[2]["nox"], filas[2]["nox_obs"]) == (40.0, 8)


def test_medv_mismo_anio_solo_ese_anio():
    filas = [_fila("039", 0, 0), _fila("124", 5, 5)]
    v = lambda anio, valor: {"municipio": "14039", "anio": anio, "clase": "", "valor": valor, "lon": 0.5, "lat": 0.5}
    dv.asignar_medv_mismo_anio(filas, [v(2026, 100), v(2026, 200), v(2026, 300), v(2020, 9999)], "14", 2026)
    assert (filas[0]["medv_2026"], filas[0]["medv_2026_n"]) == (200.0, 3)  # el de 2020 no entra
    assert filas[1]["medv_2026"] is None and filas[1]["medv_2026_n"] is None  # municipio sin tabla 2026


def test_medv_no_cruza_limites_municipales():
    # Etiqueta de la tabla de Guadalajara que cae en una AGEB de Tlaquepaque.
    filas = [_fila("098", 0, 0)]
    v = {"municipio": "14039", "anio": 2020, "clase": "zona", "valor": 5000, "lon": 0.5, "lat": 0.5}
    dv.asignar_medv(filas, [v], "14")
    assert filas[0]["medv"] is None and "sin tabla" in filas[0]["medv_metodo"]
    dv.asignar_medv_mismo_anio(filas, [{**v, "anio": 2026}] * 3, "14", 2026)
    assert filas[0]["medv_2026"] is None
