import json

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from mapo_core.db import get_pool
from mapo_core.server import app


async def _insertar_estado(conn, cve_ent, nombre, geom):
    await conn.execute(
        """INSERT INTO entidades (cve_ent, nombre, geom)
           VALUES (%(cve_ent)s, %(nombre)s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))""",
        {"cve_ent": cve_ent, "nombre": nombre, "geojson": json.dumps(geom)},
    )


async def _insertar_municipio(conn, cvegeo, cve_ent, cve_mun, nombre, geom):
    await conn.execute(
        """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)
           VALUES (%(cvegeo)s, %(cve_ent)s, %(cve_mun)s, %(nombre)s,
                   ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))""",
        {"cvegeo": cvegeo, "cve_ent": cve_ent, "cve_mun": cve_mun, "nombre": nombre, "geojson": json.dumps(geom)},
    )


async def _insertar_ageb(conn, cvegeo, cve_ent, cve_mun, geom):
    await conn.execute(
        """INSERT INTO agebs (cvegeo, cve_ent, cve_mun, cve_ageb, ambito, geom)
           VALUES (%(cvegeo)s, %(cve_ent)s, %(cve_mun)s, %(cve_ageb)s, 'URBANA',
                   ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))""",
        {
            "cvegeo": cvegeo,
            "cve_ent": cve_ent,
            "cve_mun": cve_mun,
            "cve_ageb": cvegeo[-4:],
            "geojson": json.dumps(geom),
        },
    )


@pytest.mark.asyncio
async def test_geo_estados_trae_los_guardados(conn, pool_de_una_conexion):
    await _insertar_estado(conn, "14", "Jalisco", box(0, 0, 1, 1).__geo_interface__)
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/geo/estados")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    propiedades = [f["properties"] for f in cuerpo["features"]]
    assert {"cvegeo": "14", "nomgeo": "Jalisco"} in [
        {"cvegeo": p["cvegeo"], "nomgeo": p["nomgeo"]} for p in propiedades
    ]
    assert cuerpo["features"][0]["geometry"] is not None
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_geo_municipios_filtra_por_estado(conn, pool_de_una_conexion):
    await _insertar_municipio(conn, "14039", "14", "039", "Guadalajara", box(0, 0, 1, 1).__geo_interface__)
    await _insertar_municipio(conn, "09002", "09", "002", "Azcapotzalco", box(1, 1, 2, 2).__geo_interface__)
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/geo/municipios", params={"cve_ent": "14"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    cvegeos = {f["properties"]["cvegeo"] for f in cuerpo["features"]}
    assert cvegeos == {"14039"}
    assert cuerpo["features"][0]["properties"]["cve_mun"] == "039"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_geo_agebs_requiere_cve_ent(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/geo/agebs")

    assert respuesta.status_code == 422
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_geo_agebs_filtra_por_municipio(conn, pool_de_una_conexion):
    await _insertar_ageb(conn, "140390001001", "14", "039", box(0, 0, 1, 1).__geo_interface__)
    await _insertar_ageb(conn, "140400001002", "14", "040", box(1, 1, 2, 2).__geo_interface__)
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/geo/agebs", params={"cve_ent": "14", "cve_mun": "039"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert {f["properties"]["cvegeo"] for f in cuerpo["features"]} == {"140390001001"}
    app.dependency_overrides.clear()
