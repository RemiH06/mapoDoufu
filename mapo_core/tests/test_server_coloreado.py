import json

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from mapo_core.db import get_pool
from mapo_core.server import app

CUADRICULA_2X2 = [
    {"id": "0-0", "geometria": box(0, 0, 1, 1).__geo_interface__},
    {"id": "1-0", "geometria": box(1, 0, 2, 1).__geo_interface__},
    {"id": "0-1", "geometria": box(0, 1, 1, 2).__geo_interface__},
    {"id": "1-1", "geometria": box(1, 1, 2, 2).__geo_interface__},
]


def test_coloreado_calcular_ningun_vecino_comparte_color():
    cliente = TestClient(app)

    respuesta = cliente.post("/coloreado/calcular", json={"poligonos": CUADRICULA_2X2})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    # 0-0 y 1-0 comparten lado; 0-0 y 0-1 tambien; 0-0 y 1-1 solo tocan
    # en una esquina (no son vecinos).
    assert cuerpo["color_por_id"]["0-0"] != cuerpo["color_por_id"]["1-0"]
    assert cuerpo["color_por_id"]["0-0"] != cuerpo["color_por_id"]["0-1"]


def test_coloreado_calcular_lista_vacia():
    cliente = TestClient(app)

    respuesta = cliente.post("/coloreado/calcular", json={"poligonos": []})

    assert respuesta.status_code == 200
    assert respuesta.json() == {"color_por_id": {}, "num_colores": 0}


@pytest.mark.asyncio
async def test_coloreado_municipios_agrega_color_indice_a_cada_feature(conn, pool_de_una_conexion):
    for cvegeo, cve_mun, nombre, geom in [
        ("14001", "001", "A", box(0, 0, 1, 1).__geo_interface__),
        ("14002", "002", "B", box(1, 0, 2, 1).__geo_interface__),
    ]:
        await conn.execute(
            """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)
               VALUES (%(cvegeo)s, '14', %(cve_mun)s, %(nombre)s,
                       ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))""",
            {"cvegeo": cvegeo, "cve_mun": cve_mun, "nombre": nombre, "geojson": json.dumps(geom)},
        )

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/coloreado/municipios", params={"cve_ent": "14"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    colores = {f["properties"]["cvegeo"]: f["properties"]["color_indice"] for f in cuerpo["features"]}
    assert colores["14001"] != colores["14002"]
    assert cuerpo["num_colores"] == 2
    app.dependency_overrides.clear()
