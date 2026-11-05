"""Cruce de una capa contra fuentes públicas, en la base de test."""

import json

import pytest
from fastapi.testclient import TestClient

from mapo_core.db import get_pool
from mapo_core.server import app, get_osrm_client

ZAPOPAN_A = "1412000010001"
ZAPOPAN_B = "1412000010002"
TONALA = "1410100010003"


class OSRMFalso:
    def __init__(self, falla=False):
        self.falla = falla

    async def duraciones_matriz(self, origenes, destinos):
        return None if self.falla else [[7.0 for _ in destinos] for _ in origenes]


def _cuadro(lon, lat, lado=0.01):
    anillo = [[lon, lat], [lon + lado, lat], [lon + lado, lat + lado], [lon, lat + lado], [lon, lat]]
    return json.dumps({"type": "Polygon", "coordinates": [anillo]})


async def _marco(conn):
    """Dos AGEB pegados en Zapopan, uno en Tonalá y Tala sin AGEB."""
    for cve_mun, nombre, lon in [("120", "Zapopan", 0), ("101", "Tonalá", 1), ("083", "Tala", 2)]:
        await conn.execute(
            """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)
               VALUES (%s, '14', %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))""",
            (f"14{cve_mun}", cve_mun, nombre, _cuadro(lon, 0, 0.5)),
        )
        await conn.execute(
            """INSERT INTO fuente_censo_poblacion (cvegeo, nivel, cve_ent, cve_mun, pobtot, graproes, datos_json)
               VALUES (%s, 'municipio', '14', %s, 5000, 9.5, '{}'::jsonb)""",
            (f"14{cve_mun}0000", cve_mun),
        )
    for cvegeo, lon, pobtot in [(ZAPOPAN_A, 0, 100), (ZAPOPAN_B, 0.01, None), (TONALA, 1, 300)]:
        await conn.execute(
            """INSERT INTO agebs (cvegeo, cve_ent, cve_mun, cve_ageb, ambito, geom)
               VALUES (%s, '14', %s, %s, 'URBANA', ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))""",
            (cvegeo, cvegeo[2:5], cvegeo[9:], _cuadro(lon, 0)),
        )
        await conn.execute(
            """INSERT INTO fuente_censo_poblacion (cvegeo, nivel, cve_ent, cve_mun, pobtot, graproes, datos_json)
               VALUES (%s, 'ageb', '14', %s, %s, 11.25, '{}'::jsonb)""",
            (cvegeo, cvegeo[2:5], pobtot),
        )
    for i, (ageb, clase) in enumerate([("0001", "Una"), ("0001", "Otra"), ("0002", "Otra")]):
        await conn.execute(
            """INSERT INTO fuente_denue_negocios (id, clase_actividad, lat, lon, cve_ent, cve_mun, cve_ageb)
               VALUES (%s, %s, 0.005, 0.005, '14', '120', %s)""",
            (f"t{i}", clase, ageb),
        )


@pytest.fixture
def pedir(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    app.dependency_overrides[get_osrm_client] = lambda: OSRMFalso()
    yield lambda **cuerpo: TestClient(app).post("/cruce/calcular", json=cuerpo)
    app.dependency_overrides.clear()


PUNTOS = [
    {"lat": 0.005, "lon": 0.005, "valores": {"ventas": 10}},
    {"lat": 0.006, "lon": 0.005, "valores": {"ventas": 20}},
    {"lat": 0.007, "lon": 0.005, "valores": {"ventas": None}},
    {"lat": 0.005, "lon": 1.005, "valores": {"ventas": 3}},
]


def _por_clave(datos):
    return {f["clave"]: f["datos"] for f in datos["filas"]}


async def test_puntos_por_ageb_incluye_las_zonas_vacias_del_municipio(conn, pedir):
    await _marco(conn)
    r = pedir(tipo="puntos", nivel="ageb", filas=PUNTOS, agregaciones={"ventas": "suma"}, censo=["pobtot"])
    assert r.status_code == 200
    datos = r.json()
    zonas = _por_clave(datos)
    assert zonas[ZAPOPAN_A] == {
        "municipio": "Zapopan",
        "ageb": "0001",
        "renglones": 3,
        "ventas_suma": 30,
        "pobtot": 100,
    }
    vacia = zonas[ZAPOPAN_B]
    assert vacia["renglones"] == 0
    assert vacia["ventas_suma"] is None, "una suma de nada no es cero"
    assert vacia["pobtot"] is None, "censo reservado sigue sin dato"
    assert any(a.startswith("pobtot: 1 ") for a in datos["avisos"])
    assert datos["filas"][0]["datos"]["renglones"] == 3
    assert datos["zonas_con_renglones"] == 2
    assert datos["columnas"] == ["municipio", "ageb", "renglones", "ventas_suma", "pobtot"]
    assert datos["numericas"] == ["renglones", "ventas_suma", "pobtot"]
    assert any(m.startswith("ventas_suma:") for m in datos["metodo"])


async def test_punto_en_la_frontera_cuenta_una_vez(conn, pedir):
    await _marco(conn)
    r = pedir(tipo="puntos", nivel="ageb", filas=[{"lat": 0.005, "lon": 0.01, "valores": {}}])
    assert sum(f["datos"]["renglones"] for f in r.json()["filas"]) == 1


@pytest.mark.parametrize(("agregacion", "esperado"), [("promedio", 15), ("mediana", 15), ("suma", 30)])
async def test_agregaciones_ignoran_celdas_vacias(conn, pedir, agregacion, esperado):
    await _marco(conn)
    r = pedir(tipo="puntos", nivel="ageb", filas=PUNTOS, agregaciones={"ventas": agregacion})
    assert _por_clave(r.json())[ZAPOPAN_A][f"ventas_{agregacion}"] == esperado


async def test_por_municipio_lee_el_censo_municipal_y_trae_todo_el_estado(conn, pedir):
    await _marco(conn)
    r = pedir(tipo="puntos", nivel="municipio", filas=PUNTOS, censo=["pobtot", "graproes"])
    zonas = _por_clave(r.json())
    assert set(zonas) == {"14120", "14101", "14083"}
    assert zonas["14120"]["renglones"] == 3
    assert zonas["14120"]["pobtot"] == 5000, "con población rural, no la suma de AGEB"
    assert zonas["14120"]["graproes"] == 9.5
    assert zonas["14083"]["renglones"] == 0


async def test_capa_por_ageb_sube_a_municipio(conn, pedir):
    await _marco(conn)
    filas = [{"clave": ZAPOPAN_A, "valores": {"v": 1}}, {"clave": ZAPOPAN_B, "valores": {"v": 2}}]
    r = pedir(tipo="ageb", nivel="municipio", filas=filas, agregaciones={"v": "suma"})
    assert _por_clave(r.json())["14120"]["v_suma"] == 3


async def test_capa_por_municipio_no_se_parte_en_ageb(conn, pedir):
    await _marco(conn)
    assert pedir(tipo="municipio", nivel="ageb", filas=[{"clave": "14120"}]).status_code == 422


async def test_renglones_fuera_del_marco_se_dicen(conn, pedir):
    await _marco(conn)
    filas = PUNTOS + [{"lat": 0.4, "lon": 0.4, "valores": {}}]
    datos = pedir(tipo="puntos", nivel="ageb", filas=filas).json()
    assert datos["sin_zona"] == 1
    assert datos["renglones"] == 4
    assert any("no cayeron" in a for a in datos["avisos"])


async def test_nada_en_el_marco_es_un_error_claro(conn, pedir):
    await _marco(conn)
    r = pedir(tipo="puntos", nivel="ageb", filas=[{"lat": 30, "lon": 30, "valores": {}}])
    assert r.status_code == 422
    assert "Ningún renglón" in r.json()["detail"]


async def test_negocios_de_denue_por_ageb_y_municipio(conn, pedir):
    await _marco(conn)
    por_ageb = _por_clave(pedir(tipo="puntos", nivel="ageb", filas=PUNTOS, denue="todos").json())
    assert por_ageb[ZAPOPAN_A]["negocios_denue"] == 2
    assert por_ageb[ZAPOPAN_B]["negocios_denue"] == 1
    assert por_ageb[TONALA]["negocios_denue"] == 0
    por_mun = _por_clave(pedir(tipo="puntos", nivel="municipio", filas=PUNTOS, denue="todos").json())
    assert por_mun["14120"]["negocios_denue"] == 3


async def test_rechaza_lo_que_no_esta_en_las_listas(conn, pedir):
    await _marco(conn)
    base = {"tipo": "puntos", "nivel": "ageb", "filas": PUNTOS}
    assert pedir(**base, censo=["pobtot; DROP TABLE agebs"]).status_code == 422
    assert pedir(**base, denue="no_existe").status_code == 422
    assert pedir(**base, denue="todos", minutos=True).status_code == 422
    assert pedir(**base, agregaciones={"ventas": "maximo"}).status_code == 422


async def test_minutos_por_calle_y_sin_osrm(conn, pedir):
    await _marco(conn)
    await conn.execute(
        """INSERT INTO fuente_denue_negocios (id, clase_actividad, lat, lon, cve_ent, cve_mun, cve_ageb)
           VALUES ('f1', 'Comercio al por menor de plantas y flores naturales', 0.1, 0.1, '14', '120', '0001')"""
    )
    base = {"tipo": "puntos", "nivel": "ageb", "filas": PUNTOS, "denue": "floreria", "minutos": True}
    datos = pedir(**base).json()
    assert _por_clave(datos)[ZAPOPAN_A]["minutos_floreria"] == 7.0
    assert _por_clave(datos)[ZAPOPAN_A]["negocios_floreria"] == 1
    assert any("por calle" in m for m in datos["metodo"])

    app.dependency_overrides[get_osrm_client] = lambda: OSRMFalso(falla=True)
    datos = pedir(**base).json()
    assert any("línea recta" in a for a in datos["avisos"])
    assert any("línea recta" in m for m in datos["metodo"])
