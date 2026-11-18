from fastapi.testclient import TestClient

from mapo_core.server import app

cliente = TestClient(app)


def test_salud_responde_ok():
    respuesta = cliente.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}

def test_sin_documentacion_publica_de_la_api():
    for ruta in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(ruta).status_code == 404


def test_base_caida_no_filtra_la_conexion():
    import psycopg

    @app.get("/_prueba_base_caida")
    def caida():
        raise psycopg.OperationalError('connection to server at "db", user "mapo" failed')

    respuesta = cliente.get("/_prueba_base_caida")
    assert respuesta.status_code == 503
    assert "mapo" not in respuesta.text.replace("mapo_core", "")
