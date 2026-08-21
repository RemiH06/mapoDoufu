from fastapi.testclient import TestClient

from mapo_core.server import app, get_osrm_client

DEPOSITO = {"lat": 19.4326, "lon": -99.1332}
PUEBLA = {"lat": 19.0414, "lon": -98.2063, "demanda": 5}
TOLUCA = {"lat": 19.2926, "lon": -99.6568, "demanda": 5}


class _OSRMFalso:
    """Sustituye a OSRMClient en los tests: nunca pega a la red."""

    def __init__(self, resultado=None):
        self._resultado = resultado

    async def matriz_carretera(self, coords):
        return self._resultado


def _cliente_con_osrm(osrm_falso) -> TestClient:
    app.dependency_overrides[get_osrm_client] = lambda: osrm_falso
    return TestClient(app)


def test_vrp_calcular_cae_a_linea_recta_si_osrm_no_responde():
    cliente = _cliente_con_osrm(_OSRMFalso(resultado=None))

    respuesta = cliente.post(
        "/vrp/calcular",
        json={
            "paradas": [DEPOSITO, PUEBLA, TOLUCA],
            "capacidades_vehiculos": [100],
        },
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["metodo"] == "linea_recta_aproximada"
    assert len(cuerpo["rutas"]) == 1
    assert set(cuerpo["rutas"][0]["orden_paradas"]) == {0, 1, 2}
    assert cuerpo["distancia_total_km"] > 0
    app.dependency_overrides.clear()


def test_vrp_calcular_usa_carretera_real_si_osrm_responde():
    matriz_osrm = {
        "distancias_km": [[0, 130, 65], [130, 0, 195], [65, 195, 0]],
        "duraciones_min": [[0, 90, 50], [90, 0, 140], [50, 140, 0]],
    }
    cliente = _cliente_con_osrm(_OSRMFalso(resultado=matriz_osrm))

    respuesta = cliente.post(
        "/vrp/calcular",
        json={
            "paradas": [DEPOSITO, PUEBLA, TOLUCA],
            "capacidades_vehiculos": [100],
        },
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["metodo"] == "carretera_real"
    # La distancia real (65+195=260 ida y vuelta a Toluca-Puebla) es
    # distinta a la de linea recta; solo importa que se haya usado la
    # matriz real, no que coincida con un numero exacto.
    assert cuerpo["distancia_total_km"] > 0
    app.dependency_overrides.clear()


def test_vrp_calcular_con_deposito_invalido_da_400():
    cliente = _cliente_con_osrm(_OSRMFalso(resultado=None))

    respuesta = cliente.post(
        "/vrp/calcular",
        json={
            "paradas": [DEPOSITO, PUEBLA],
            "capacidades_vehiculos": [100],
            "deposito": 5,
        },
    )

    assert respuesta.status_code == 400
    app.dependency_overrides.clear()


def test_vrp_calcular_infactible_da_422():
    cliente = _cliente_con_osrm(_OSRMFalso(resultado=None))

    respuesta = cliente.post(
        "/vrp/calcular",
        json={
            "paradas": [DEPOSITO, PUEBLA, TOLUCA],
            "capacidades_vehiculos": [1],
        },
    )

    assert respuesta.status_code == 422
    app.dependency_overrides.clear()
