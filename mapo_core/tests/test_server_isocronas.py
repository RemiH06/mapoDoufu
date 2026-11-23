import pytest

from mapo_core.db import get_pool
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


def _caja(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


@pytest.mark.asyncio
async def test_poblacion_de_isocronas_cada_una_en_todas_y_en_alguna(conn, pool_de_una_conexion):
    # Tres AGEB en fila: la de en medio queda en las dos isócronas.
    for i, (x, pob) in enumerate([(-103.40, 100), (-103.38, 20), (-103.36, None)]):
        cvegeo = f"140390001000{i}"
        await conn.execute(
            "INSERT INTO agebs (cvegeo, cve_ent, cve_mun, cve_ageb, geom) VALUES"
            " (%(c)s, '14', '039', %(a)s, ST_Multi(ST_MakeEnvelope(%(x)s, 20.60, %(x)s + 0.005, 20.605, 4326)))",
            {"c": cvegeo, "a": cvegeo[-4:], "x": x})
        await conn.execute(
            "INSERT INTO fuente_censo_poblacion (cvegeo, nivel, cve_ent, cve_mun, pobtot, datos_json)"
            " VALUES (%(c)s, 'ageb', '14', '039', %(p)s, '{}'::jsonb)", {"c": cvegeo, "p": pob})

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    try:
        cliente = TestClient(app)
        dos = cliente.post("/isocronas/poblacion", json={"poligonos": [
            _caja(-103.41, 20.59, -103.37, 20.61), _caja(-103.39, 20.59, -103.35, 20.61)]})
        una = cliente.post("/isocronas/poblacion", json={"poligonos": [_caja(-103.41, 20.59, -103.37, 20.61)]})
        ninguna = cliente.post("/isocronas/poblacion", json={"poligonos": []})
        punto = cliente.post("/isocronas/poblacion", json={"poligonos": [{"type": "Point", "coordinates": [0, 0]}]})
    finally:
        app.dependency_overrides.clear()

    r = dos.json()
    assert [c["personas"] for c in r["cada_una"]] == [120, 20]
    # La tercera tiene la población reservada: se dice, no se cuenta como cero.
    assert r["cada_una"][1]["reservados"] == 1
    assert (r["en_todas"]["personas"], r["en_alguna"]["personas"]) == (20, 120)
    assert r["interseccion"]["type"] == "Polygon"
    assert una.json()["en_todas"] is None and una.json()["interseccion"] is None
    assert (ninguna.status_code, punto.status_code) == (422, 422)
