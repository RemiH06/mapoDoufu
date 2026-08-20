from fastapi.testclient import TestClient

from mapo_core.server import app

cliente = TestClient(app)

DEPOSITO = {"lat": 19.4326, "lon": -99.1332}
PUEBLA = {"lat": 19.0414, "lon": -98.2063, "demanda": 5}
TOLUCA = {"lat": 19.2926, "lon": -99.6568, "demanda": 5}


def test_vrp_calcular_devuelve_una_ruta_valida():
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


def test_vrp_calcular_con_deposito_invalido_da_400():
    respuesta = cliente.post(
        "/vrp/calcular",
        json={
            "paradas": [DEPOSITO, PUEBLA],
            "capacidades_vehiculos": [100],
            "deposito": 5,
        },
    )

    assert respuesta.status_code == 400


def test_vrp_calcular_infactible_da_422():
    respuesta = cliente.post(
        "/vrp/calcular",
        json={
            "paradas": [DEPOSITO, PUEBLA, TOLUCA],
            "capacidades_vehiculos": [1],
        },
    )

    assert respuesta.status_code == 422
