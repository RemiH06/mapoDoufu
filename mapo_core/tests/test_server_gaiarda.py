import httpx
from fastapi.testclient import TestClient

from mapo_core.gaiarda_client import GaiardaClient
from mapo_core.server import app, get_gaiarda_client


class _ClienteFalso:
    """Sustituye a GaiardaClient en los tests: mismo contrato async, sin
    pegarle a la red."""

    def __init__(self, error=None):
        self.llamadas = []
        self._error = error

    async def status(self):
        self.llamadas.append(("status", {}))
        if self._error:
            raise self._error
        return {"version": "0.3.0"}

    async def municipios(self, cve_ent=None):
        self.llamadas.append(("municipios", {"cve_ent": cve_ent}))
        return {"type": "FeatureCollection", "features": []}


def _cliente_de_prueba(cliente_falso) -> TestClient:
    app.dependency_overrides[get_gaiarda_client] = lambda: cliente_falso
    return TestClient(app)


def test_gaiarda_status_usa_el_cliente_inyectado():
    falso = _ClienteFalso()
    cliente = _cliente_de_prueba(falso)

    respuesta = cliente.get("/gaiarda/status")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"version": "0.3.0"}
    assert falso.llamadas == [("status", {})]
    app.dependency_overrides.clear()


def test_gaiarda_municipios_pasa_el_query_param():
    falso = _ClienteFalso()
    cliente = _cliente_de_prueba(falso)

    respuesta = cliente.get("/gaiarda/municipios", params={"cve_ent": "14"})

    assert respuesta.status_code == 200
    assert falso.llamadas == [("municipios", {"cve_ent": "14"})]
    app.dependency_overrides.clear()


def test_get_gaiarda_client_devuelve_una_instancia_real():
    app.dependency_overrides.clear()
    assert isinstance(get_gaiarda_client(), GaiardaClient)


def test_gaiarda_inalcanzable_da_502_no_500():
    falso = _ClienteFalso(error=httpx.ConnectError("no conecta"))
    cliente = _cliente_de_prueba(falso)

    respuesta = cliente.get("/gaiarda/status")

    assert respuesta.status_code == 502
    assert respuesta.json()["error"] == "Gaiarda no esta disponible ahorita mismo."
    app.dependency_overrides.clear()


def test_gaiarda_responde_error_da_502_con_el_status_original():
    request = httpx.Request("GET", "http://gaiarda.test/status")
    response = httpx.Response(500, request=request)
    error = httpx.HTTPStatusError("fallo", request=request, response=response)
    falso = _ClienteFalso(error=error)
    cliente = _cliente_de_prueba(falso)

    respuesta = cliente.get("/gaiarda/status")

    assert respuesta.status_code == 502
    assert respuesta.json()["status_gaiarda"] == 500
    app.dependency_overrides.clear()
