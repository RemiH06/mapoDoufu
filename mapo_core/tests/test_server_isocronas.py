from fastapi.testclient import TestClient

from mapo_core.server import app, get_osrm_client


class _OSRMFalso:
    async def duraciones_desde(self, origen, destinos):
        return [1.0 for _ in destinos]  # todo alcanzable


def _cliente_con_osrm_falso() -> TestClient:
    app.dependency_overrides[get_osrm_client] = lambda: _OSRMFalso()
    return TestClient(app)


def test_isocronas_calcular_devuelve_un_poligono():
    cliente = _cliente_con_osrm_falso()

    respuesta = cliente.post(
        "/isocronas/calcular",
        json={"lat": 19.4326, "lon": -99.1332, "minutos": 10},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["metodo"] == "osrm_real"
    assert cuerpo["poligono"]["type"] == "Polygon"
    anillo = cuerpo["poligono"]["coordinates"][0]
    assert anillo[0] == anillo[-1]
    app.dependency_overrides.clear()


def test_isocronas_calcular_con_minutos_invalidos_da_400():
    cliente = _cliente_con_osrm_falso()

    respuesta = cliente.post(
        "/isocronas/calcular",
        json={"lat": 19.4326, "lon": -99.1332, "minutos": 0},
    )

    assert respuesta.status_code == 400
    app.dependency_overrides.clear()


def test_isocronas_calcular_con_pocas_direcciones_da_400():
    cliente = _cliente_con_osrm_falso()

    respuesta = cliente.post(
        "/isocronas/calcular",
        json={"lat": 19.4326, "lon": -99.1332, "minutos": 10, "num_direcciones": 2},
    )

    assert respuesta.status_code == 400
    app.dependency_overrides.clear()
