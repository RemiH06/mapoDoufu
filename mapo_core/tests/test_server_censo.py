import json

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from mapo_core.db import get_pool
from mapo_core.server import app


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


async def _insertar_censo_ageb(conn, cvegeo, cve_ent, cve_mun, pobtot):
    await conn.execute(
        """INSERT INTO fuente_censo_poblacion (cvegeo, nivel, cve_ent, cve_mun, pobtot, datos_json)
           VALUES (%(cvegeo)s, 'ageb', %(cve_ent)s, %(cve_mun)s, %(pobtot)s, '{}'::jsonb)""",
        {"cvegeo": cvegeo, "cve_ent": cve_ent, "cve_mun": cve_mun, "pobtot": pobtot},
    )


@pytest.mark.asyncio
async def test_censo_choropleth_indicador_invalido_da_400(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/censo/choropleth", params={"indicador": "algo_inventado", "cve_ent": "14"})

    assert respuesta.status_code == 400
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_censo_choropleth_cruza_ageb_con_censo(conn, pool_de_una_conexion):
    await _insertar_ageb(conn, "140390001001", "14", "039", box(0, 0, 1, 1).__geo_interface__)
    await _insertar_censo_ageb(conn, "140390001001", "14", "039", pobtot=1234)

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/censo/choropleth", params={"indicador": "pobtot", "cve_ent": "14"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    propiedades = cuerpo["features"][0]["properties"]
    assert propiedades["valor_choropleth"] == 1234
    assert propiedades["indicador"] == "pobtot"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_censo_choropleth_ageb_sin_censo_trae_null_no_cero(conn, pool_de_una_conexion):
    await _insertar_ageb(conn, "140390001002", "14", "039", box(1, 1, 2, 2).__geo_interface__)
    # sin insertar fila de censo para esta AGEB a proposito

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/censo/choropleth", params={"indicador": "pobtot", "cve_ent": "14"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    propiedades = cuerpo["features"][0]["properties"]
    assert propiedades["valor_choropleth"] is None
    app.dependency_overrides.clear()
