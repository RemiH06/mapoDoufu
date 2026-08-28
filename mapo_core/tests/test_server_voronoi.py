import json

import pytest
from fastapi.testclient import TestClient

from mapo_core.db import get_pool
from mapo_core.server import app

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


MUNICIPIO_GEOJSON = {
    "type": "Polygon",
    "coordinates": [[[-2, -2], [12, -2], [12, 12], [-2, 12], [-2, -2]]],
}


@pytest.mark.asyncio
async def test_voronoi_denue_da_501_si_el_municipio_existe_pero_denue_no_esta_portado(conn, pool_de_una_conexion):
    await conn.execute(
        """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)
           VALUES ('14039', '14', '039', 'Guadalajara',
                   ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))""",
        {"geojson": json.dumps(MUNICIPIO_GEOJSON)},
    )
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/voronoi/denue", params={"cve_ent": "14", "cve_mun": "039"})

    assert respuesta.status_code == 501
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_voronoi_denue_municipio_no_encontrado_da_404(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/voronoi/denue", params={"cve_ent": "14", "cve_mun": "999"})

    assert respuesta.status_code == 404
    app.dependency_overrides.clear()
