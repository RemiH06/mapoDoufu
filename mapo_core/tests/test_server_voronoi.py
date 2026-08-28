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


async def _insertar_municipio_guadalajara(conn):
    await conn.execute(
        """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)
           VALUES ('14039', '14', '039', 'Guadalajara',
                   ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))""",
        {"geojson": json.dumps(MUNICIPIO_GEOJSON)},
    )


async def _insertar_negocio(conn, id_, lat, lon, clase_actividad="papeleria"):
    await conn.execute(
        """INSERT INTO fuente_denue_negocios (id, nombre, clase_actividad, lat, lon, cve_ent, cve_mun)
           VALUES (%(id)s, %(nombre)s, %(clase_actividad)s, %(lat)s, %(lon)s, '14', '039')""",
        {"id": id_, "nombre": f"negocio {id_}", "clase_actividad": clase_actividad, "lat": lat, "lon": lon},
    )


@pytest.mark.asyncio
async def test_voronoi_denue_usa_negocios_reales_y_el_poligono_real_del_municipio(conn, pool_de_una_conexion):
    await _insertar_municipio_guadalajara(conn)
    for id_, lat, lon in [("1", 0.0, 0.0), ("2", 0.0, 10.0), ("3", 10.0, 0.0), ("4", 10.0, 10.0)]:
        await _insertar_negocio(conn, id_, lat, lon)

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/voronoi/denue", params={"cve_ent": "14", "cve_mun": "039"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["metodo"] == "recortado_a_limite"
    assert cuerpo["num_negocios"] == 4
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_voronoi_denue_filtra_por_clase_actividad(conn, pool_de_una_conexion):
    await _insertar_municipio_guadalajara(conn)
    for id_, lat, lon in [("1", 0.0, 0.0), ("2", 0.0, 10.0), ("3", 10.0, 0.0)]:
        await _insertar_negocio(conn, id_, lat, lon, clase_actividad="papeleria")
    for id_, lat, lon in [("4", 5.0, 5.0), ("5", 6.0, 6.0), ("6", 7.0, 7.0)]:
        await _insertar_negocio(conn, id_, lat, lon, clase_actividad="farmacia")

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get(
        "/voronoi/denue", params={"cve_ent": "14", "cve_mun": "039", "clase_actividad": "papel"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["num_negocios"] == 3
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_voronoi_denue_con_pocos_negocios_da_422(conn, pool_de_una_conexion):
    await _insertar_municipio_guadalajara(conn)
    await _insertar_negocio(conn, "1", 0.0, 0.0)

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/voronoi/denue", params={"cve_ent": "14", "cve_mun": "039"})

    assert respuesta.status_code == 422
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_voronoi_denue_municipio_no_encontrado_da_404(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/voronoi/denue", params={"cve_ent": "14", "cve_mun": "999"})

    assert respuesta.status_code == 404
    app.dependency_overrides.clear()
