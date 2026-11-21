"""Una AGEB más chica que la tolerancia de simplificación no se pierde.

Sin `preserveCollapsed`, `ST_Simplify` regresa NULL para ella y el código que
descarta geometrías nulas la tira sin avisar (24 AGEB de la ZMG, visto en la 23d).
"""

import json

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from mapo_core import consultas
from mapo_core.db import get_pool
from mapo_core.server import app


async def _dos_agebs(conn):
    for cvegeo, forma in [("9903900010010", box(0, 0, 1, 1)), ("9903900010025", box(2, 0, 2.0002, 0.0002))]:
        await conn.execute(
            """INSERT INTO agebs (cvegeo, cve_ent, cve_mun, cve_loc, cve_ageb, geom)
               VALUES (%(c)s, '99', '039', '0001', %(a)s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(g)s), 4326)))""",
            {"c": cvegeo, "a": cvegeo[9:], "g": json.dumps(forma.__geo_interface__)},
        )


@pytest.mark.asyncio
async def test_coropleta_no_pierde_la_ageb_chica(conn, pool_de_una_conexion):
    await _dos_agebs(conn)
    filas = await consultas.coropleta(pool_de_una_conexion, "pobtot", "99", None)
    assert [f["properties"]["cvegeo"] for f in filas] == ["9903900010010", "9903900010025"]
    assert all(f["geometry"] for f in filas)


@pytest.mark.asyncio
async def test_geo_agebs_no_pierde_la_ageb_chica(conn, pool_de_una_conexion):
    await _dos_agebs(conn)
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    try:
        cuerpo = TestClient(app).get("/geo/agebs", params={"cve_ent": "99"}).json()
    finally:
        app.dependency_overrides.clear()
    assert len(cuerpo["features"]) == 2
    assert all(f["geometry"] for f in cuerpo["features"])
