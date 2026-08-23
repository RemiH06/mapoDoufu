from fastapi.testclient import TestClient
from shapely.geometry import box

from mapo_core.server import app, get_gaiarda_client

CUADRICULA_2X2 = [
    {"id": "0-0", "geometria": box(0, 0, 1, 1).__geo_interface__},
    {"id": "1-0", "geometria": box(1, 0, 2, 1).__geo_interface__},
    {"id": "0-1", "geometria": box(0, 1, 1, 2).__geo_interface__},
    {"id": "1-1", "geometria": box(1, 1, 2, 2).__geo_interface__},
]


def test_coloreado_calcular_ningun_vecino_comparte_color():
    cliente = TestClient(app)

    respuesta = cliente.post("/coloreado/calcular", json={"poligonos": CUADRICULA_2X2})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    # 0-0 y 1-0 comparten lado; 0-0 y 0-1 tambien; 0-0 y 1-1 solo tocan
    # en una esquina (no son vecinos).
    assert cuerpo["color_por_id"]["0-0"] != cuerpo["color_por_id"]["1-0"]
    assert cuerpo["color_por_id"]["0-0"] != cuerpo["color_por_id"]["0-1"]


def test_coloreado_calcular_lista_vacia():
    cliente = TestClient(app)

    respuesta = cliente.post("/coloreado/calcular", json={"poligonos": []})

    assert respuesta.status_code == 200
    assert respuesta.json() == {"color_por_id": {}, "num_colores": 0}


MUNICIPIOS_FC = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"cvegeo": "14001", "cve_mun": "001", "nomgeo": "A"},
            "geometry": box(0, 0, 1, 1).__geo_interface__,
        },
        {
            "type": "Feature",
            "properties": {"cvegeo": "14002", "cve_mun": "002", "nomgeo": "B"},
            "geometry": box(1, 0, 2, 1).__geo_interface__,
        },
    ],
}


class _ClienteGaiardaFalso:
    async def municipios(self, cve_ent=None):
        return MUNICIPIOS_FC


def test_coloreado_municipios_agrega_color_indice_a_cada_feature():
    app.dependency_overrides[get_gaiarda_client] = lambda: _ClienteGaiardaFalso()
    cliente = TestClient(app)

    respuesta = cliente.get("/coloreado/municipios", params={"cve_ent": "14"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    colores = {f["properties"]["cvegeo"]: f["properties"]["color_indice"] for f in cuerpo["features"]}
    assert colores["14001"] != colores["14002"]
    assert cuerpo["num_colores"] == 2
    app.dependency_overrides.clear()
