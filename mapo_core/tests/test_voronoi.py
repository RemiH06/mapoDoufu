import pytest
from shapely.geometry import box, shape

from mapo_core.voronoi import PuntoVoronoi, calcular_voronoi


def _cuadrado_de_puntos():
    return [
        PuntoVoronoi(lat=0.0, lon=0.0, id="a", nombre="A"),
        PuntoVoronoi(lat=0.0, lon=10.0, id="b", nombre="B"),
        PuntoVoronoi(lat=10.0, lon=0.0, id="c", nombre="C"),
        PuntoVoronoi(lat=10.0, lon=10.0, id="d", nombre="D"),
    ]


def test_menos_de_3_puntos_lanza_value_error():
    with pytest.raises(ValueError, match="al menos 3 puntos"):
        calcular_voronoi([PuntoVoronoi(lat=0, lon=0, id="1"), PuntoVoronoi(lat=1, lon=1, id="2")])


def test_puntos_colineales_lanza_value_error():
    puntos = [PuntoVoronoi(lat=0, lon=float(i), id=str(i)) for i in range(4)]
    with pytest.raises(ValueError, match="colineales"):
        calcular_voronoi(puntos)


def test_sin_limite_recorta_a_caja_envolvente():
    resultado = calcular_voronoi(_cuadrado_de_puntos())

    assert resultado.metodo == "recortado_a_caja_envolvente"
    assert len(resultado.celdas["features"]) == 4


def test_celdas_no_se_traslapan_y_cubren_exactamente_el_limite():
    limite = box(-2, -2, 12, 12)
    resultado = calcular_voronoi(_cuadrado_de_puntos(), limite=limite.__geo_interface__)

    assert resultado.metodo == "recortado_a_limite"
    poligonos = [shape(f["geometry"]) for f in resultado.celdas["features"]]

    area_total = sum(p.area for p in poligonos)
    assert area_total == pytest.approx(limite.area)

    for i, p1 in enumerate(poligonos):
        for p2 in poligonos[i + 1 :]:
            assert p1.intersection(p2).area == pytest.approx(0, abs=1e-9)


def test_puntos_simetricos_dan_celdas_de_area_igual():
    resultado = calcular_voronoi(_cuadrado_de_puntos())
    areas = [shape(f["geometry"]).area for f in resultado.celdas["features"]]

    for area in areas:
        assert area == pytest.approx(areas[0])


def test_cada_celda_trae_las_propiedades_del_punto_original():
    resultado = calcular_voronoi(_cuadrado_de_puntos())

    por_id = {f["properties"]["id"]: f["properties"] for f in resultado.celdas["features"]}
    assert por_id["a"]["nombre"] == "A"
    assert por_id["a"]["lat"] == 0.0
    assert por_id["a"]["lon"] == 0.0


def test_un_punto_totalmente_fuera_del_limite_no_aparece():
    puntos = _cuadrado_de_puntos() + [PuntoVoronoi(lat=1000.0, lon=1000.0, id="lejos")]
    limite = box(-2, -2, 12, 12)

    resultado = calcular_voronoi(puntos, limite=limite.__geo_interface__)

    ids = {f["properties"]["id"] for f in resultado.celdas["features"]}
    assert "lejos" not in ids
