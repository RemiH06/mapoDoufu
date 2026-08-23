from fastapi.testclient import TestClient

from mapo_core.server import app, get_gaiarda_client

CUADRADO = [
    {"lat": 0.0, "lon": 0.0, "id": "a", "nombre": "A"},
    {"lat": 0.0, "lon": 10.0, "id": "b", "nombre": "B"},
    {"lat": 10.0, "lon": 0.0, "id": "c", "nombre": "C"},
    {"lat": 10.0, "lon": 10.0, "id": "d", "nombre": "D"},
]


def test_voronoi_calcular_sin_limite():
    cliente = TestClient(app)

    respuesta = cliente.post("/voronoi/calcular", json={"puntos": CUADRADO})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["metodo"] == "recortado_a_caja_envolvente"
    assert len(cuerpo["celdas"]["features"]) == 4


def test_voronoi_calcular_con_limite():
    limite = {
        "type": "Polygon",
        "coordinates": [[[-2, -2], [12, -2], [12, 12], [-2, 12], [-2, -2]]],
    }
    cliente = TestClient(app)

    respuesta = cliente.post("/voronoi/calcular", json={"puntos": CUADRADO, "limite": limite})

    assert respuesta.status_code == 200
    assert respuesta.json()["metodo"] == "recortado_a_limite"


def test_voronoi_calcular_con_menos_de_3_puntos_da_422():
    cliente = TestClient(app)

    respuesta = cliente.post("/voronoi/calcular", json={"puntos": CUADRADO[:2]})

    assert respuesta.status_code == 422


def test_voronoi_calcular_con_puntos_colineales_da_422():
    puntos = [{"lat": 0.0, "lon": float(i), "id": str(i)} for i in range(4)]
    cliente = TestClient(app)

    respuesta = cliente.post("/voronoi/calcular", json={"puntos": puntos})

    assert respuesta.status_code == 422


MUNICIPIO_FEATURE = {
    "type": "Feature",
    "properties": {"cvegeo": "14039", "nomgeo": "Guadalajara"},
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[-2, -2], [12, -2], [12, 12], [-2, 12], [-2, -2]]],
    },
}


class _ClienteGaiardaFalso:
    def __init__(self, negocios):
        self._negocios = negocios

    async def municipios(self, cve_ent=None):
        return {"type": "FeatureCollection", "features": [MUNICIPIO_FEATURE]}

    async def denue(self, cve_ent=None, cve_mun=None, cve_ageb=None, clase_actividad=None):
        return {"type": "FeatureCollection", "features": self._negocios}


def _feature_negocio(id_, lat, lon, nombre="negocio"):
    return {
        "type": "Feature",
        "properties": {"id": id_, "nombre": nombre, "clase_actividad": "papeleria", "estrato": "0 a 5"},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def test_voronoi_denue_usa_el_poligono_real_del_municipio():
    negocios = [
        _feature_negocio(1, 0.0, 0.0),
        _feature_negocio(2, 0.0, 10.0),
        _feature_negocio(3, 10.0, 0.0),
        _feature_negocio(4, 10.0, 10.0),
    ]
    app.dependency_overrides[get_gaiarda_client] = lambda: _ClienteGaiardaFalso(negocios)
    cliente = TestClient(app)

    respuesta = cliente.get("/voronoi/denue", params={"cve_ent": "14", "cve_mun": "039"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["metodo"] == "recortado_a_limite"
    assert cuerpo["num_negocios"] == 4
    app.dependency_overrides.clear()


def test_voronoi_denue_municipio_no_encontrado_da_404():
    app.dependency_overrides[get_gaiarda_client] = lambda: _ClienteGaiardaFalso([])
    cliente = TestClient(app)

    respuesta = cliente.get("/voronoi/denue", params={"cve_ent": "14", "cve_mun": "999"})

    assert respuesta.status_code == 404
    app.dependency_overrides.clear()


def test_voronoi_denue_con_pocos_negocios_da_422():
    negocios = [_feature_negocio(1, 0.0, 0.0), _feature_negocio(2, 0.0, 10.0)]
    app.dependency_overrides[get_gaiarda_client] = lambda: _ClienteGaiardaFalso(negocios)
    cliente = TestClient(app)

    respuesta = cliente.get("/voronoi/denue", params={"cve_ent": "14", "cve_mun": "039"})

    assert respuesta.status_code == 422
    app.dependency_overrides.clear()
