from fastapi.testclient import TestClient

from mapo_core.server import app

cliente = TestClient(app)


def test_salud_responde_ok():
    respuesta = cliente.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}