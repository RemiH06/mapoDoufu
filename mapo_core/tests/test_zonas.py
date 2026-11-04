"""Zonas candidatas: criterios a la vista contra la base de test, con un OSRM
falso que dice cuántos minutos hay de cada AGEB a cada negocio."""

import json

import pytest
from fastapi.testclient import TestClient

from mapo_core import zonas
from mapo_core.db import get_pool
from mapo_core.server import app, get_osrm_client

FLORES = "Comercio al por menor de plantas y flores naturales"
DONDE_PONER = {"intencion": "donde_poner", "rubro": "floreria", "municipios": ["120"]}


class OSRMFalso:
    """Minutos por (lat del origen, lat del destino); sin entrada, 50 minutos.
    `None` en la tabla es un tramo sin ruta."""

    def __init__(self, tabla=None, falla=False):
        self.tabla = tabla or {}
        self.falla = falla
        self.llamadas = 0

    async def duraciones_matriz(self, origenes, destinos):
        self.llamadas += 1
        if self.falla:
            return None
        return [[self.tabla.get((round(o[0], 2), d[0]), 50.0) for d in destinos] for o in origenes]


@pytest.fixture(autouse=True)
def _sin_minutos_guardados():
    zonas._guardados.clear()
    yield
    zonas._guardados.clear()


def _cuadro(lat, lado=0.01):
    return {
        "type": "Polygon",
        "coordinates": [[[0, lat], [lado, lat], [lado, lat + lado], [0, lat + lado], [0, lat]]],
    }


async def _municipio(conn, cve_mun="120", nombre="Zapopan"):
    await conn.execute(
        """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)
           VALUES (%(cvegeo)s, '14', %(cve_mun)s, %(nombre)s,
                   ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))""",
        {"cvegeo": f"14{cve_mun}", "cve_mun": cve_mun, "nombre": nombre, "geojson": json.dumps(_cuadro(0, 10))},
    )


async def _ageb(conn, sufijo, lat, pobtot, cve_mun="120"):
    cvegeo = f"14{cve_mun}{sufijo}"
    await conn.execute(
        """INSERT INTO agebs (cvegeo, cve_ent, cve_mun, cve_ageb, ambito, geom)
           VALUES (%(cvegeo)s, '14', %(cve_mun)s, %(sufijo)s, 'URBANA',
                   ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))""",
        {"cvegeo": cvegeo, "cve_mun": cve_mun, "sufijo": sufijo, "geojson": json.dumps(_cuadro(lat))},
    )
    if pobtot is not None:
        await conn.execute(
            """INSERT INTO fuente_censo_poblacion (cvegeo, nivel, cve_ent, cve_mun, pobtot, datos_json)
               VALUES (%(cvegeo)s, 'ageb', '14', %(cve_mun)s, %(pobtot)s, '{}'::jsonb)""",
            {"cvegeo": cvegeo, "cve_mun": cve_mun, "pobtot": pobtot},
        )
    return cvegeo


async def _negocio(conn, id_, lat, clase=FLORES, cve_mun="120"):
    await conn.execute(
        """INSERT INTO fuente_denue_negocios (id, nombre, clase_actividad, lat, lon, cve_ent, cve_mun)
           VALUES (%(id)s, %(id)s, %(clase)s, %(lat)s, 0.005, '14', %(cve_mun)s)""",
        {"id": id_, "clase": clase, "lat": lat, "cve_mun": cve_mun},
    )


def _pedir(pool, osrm, plantilla=DONDE_PONER, **criterios):
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_osrm_client] = lambda: osrm
    try:
        return TestClient(app).post(
            "/buscador/zonas", json={"cve_ent": "14", "plantilla": plantilla, **criterios}
        )
    finally:
        app.dependency_overrides.clear()


async def _tres_agebs(conn):
    await _municipio(conn)
    await _ageb(conn, "0001", 1.0, 5000)
    await _ageb(conn, "0002", 2.0, 3000)
    await _ageb(conn, "0003", 3.0, 100)
    await _negocio(conn, "n1", 5.0)
    return OSRMFalso({(1.0, 5.0): 2.0, (2.0, 5.0): 9.0, (3.0, 5.0): 12.0})


async def _lat(conn, sufijo):
    cursor = await conn.execute("SELECT ST_Y(ST_PointOnSurface(geom)) FROM agebs WHERE cve_ageb = %s", (sufijo,))
    return round((await cursor.fetchone())[0], 2)


@pytest.mark.asyncio
async def test_aplica_los_dos_criterios_y_dice_que_descarto_cada_uno(conn, pool_de_una_conexion):
    await _municipio(conn)
    tabla = {}
    for sufijo, lat, pobtot, minutos in [("0001", 1.0, 5000, 2.0), ("0002", 2.0, 3000, 9.0), ("0003", 3.0, 100, 12.0)]:
        await _ageb(conn, sufijo, lat, pobtot)
        tabla[(await _lat(conn, sufijo), 5.0)] = minutos
    await _negocio(conn, "n1", 5.0)

    r = _pedir(pool_de_una_conexion, OSRMFalso(tabla), minimo=1000, minutos=5)

    assert r.status_code == 200
    datos = r.json()
    assert datos["metodo"] == "carretera_real"
    assert [f["ageb"] for f in datos["filas"]] == ["0002"]
    assert datos["filas"][0]["municipio"] == "Zapopan"
    assert datos["filas"][0]["minutos"] == 9.0
    assert (datos["total"], datos["total_candidatas"]) == (3, 1)
    assert datos["descartes"] == {"sin_dato": 0, "por_indicador": 1, "por_minutos": 1}
    assert datos["cvegeos"] == ["141200002"]
    assert "puntaje" not in datos


@pytest.mark.asyncio
async def test_sin_criterios_arranca_en_la_mediana_y_lo_regresa(conn, pool_de_una_conexion):
    await _municipio(conn)
    tabla = {}
    for sufijo, lat, pobtot, minutos in [("0001", 1.0, 5000, 2.0), ("0002", 2.0, 3000, 9.0), ("0003", 3.0, 100, 12.0)]:
        await _ageb(conn, sufijo, lat, pobtot)
        tabla[(await _lat(conn, sufijo), 5.0)] = minutos
    await _negocio(conn, "n1", 5.0)

    datos = _pedir(pool_de_una_conexion, OSRMFalso(tabla)).json()

    assert datos["criterios"] == {"minimo": 3000, "minutos": 9.0, "orden": "indicador"}
    assert [f["ageb"] for f in datos["filas"]] == ["0002"]


@pytest.mark.asyncio
async def test_se_ordena_por_el_criterio_elegido(conn, pool_de_una_conexion):
    await _municipio(conn)
    tabla = {}
    for sufijo, lat, pobtot, minutos in [("0001", 1.0, 5000, 3.0), ("0002", 2.0, 3000, 9.0)]:
        await _ageb(conn, sufijo, lat, pobtot)
        tabla[(await _lat(conn, sufijo), 5.0)] = minutos
    await _negocio(conn, "n1", 5.0)
    osrm = OSRMFalso(tabla)

    por_valor = _pedir(pool_de_una_conexion, osrm, minimo=0, minutos=0).json()
    por_minutos = _pedir(pool_de_una_conexion, osrm, minimo=0, minutos=0, orden="minutos").json()

    assert [f["ageb"] for f in por_valor["filas"]] == ["0001", "0002"]
    assert [f["ageb"] for f in por_minutos["filas"]] == ["0002", "0001"]


@pytest.mark.asyncio
async def test_gana_el_negocio_mas_cercano_por_calle_no_en_linea_recta(conn, pool_de_una_conexion):
    await _municipio(conn)
    await _ageb(conn, "0001", 1.0, 5000)
    lat = await _lat(conn, "0001")
    await _negocio(conn, "cerca_en_recta", 1.1)
    await _negocio(conn, "cerca_por_calle", 1.5)

    osrm = OSRMFalso({(lat, 1.1): 30.0, (lat, 1.5): 4.0})
    datos = _pedir(pool_de_una_conexion, osrm, minimo=0, minutos=0).json()

    assert datos["filas"][0]["minutos"] == 4.0


@pytest.mark.asyncio
async def test_un_negocio_de_otro_municipio_tambien_cuenta(conn, pool_de_una_conexion):
    await _municipio(conn)
    await _municipio(conn, "039", "Guadalajara")
    await _ageb(conn, "0001", 1.0, 5000)
    await _negocio(conn, "enfrente", 1.1, cve_mun="039")

    lat = await _lat(conn, "0001")
    datos = _pedir(pool_de_una_conexion, OSRMFalso({(lat, 1.1): 1.5}), minimo=0, minutos=0).json()

    assert datos["filas"][0]["minutos"] == 1.5


@pytest.mark.asyncio
async def test_lo_que_falta_se_cuenta_y_no_se_vuelve_cero(conn, pool_de_una_conexion):
    await _municipio(conn)
    await _ageb(conn, "0001", 1.0, 5000)
    await _ageb(conn, "0002", 2.0, None)
    await _ageb(conn, "0003", 3.0, 4000)
    await _negocio(conn, "n1", 5.0)
    osrm = OSRMFalso({(await _lat(conn, "0001"), 5.0): 8.0, (await _lat(conn, "0003"), 5.0): None})

    datos = _pedir(pool_de_una_conexion, osrm, minimo=0, minutos=0).json()

    assert [f["ageb"] for f in datos["filas"]] == ["0001"]
    assert datos["descartes"]["sin_dato"] == 2


@pytest.mark.asyncio
async def test_sin_osrm_cae_a_linea_recta_y_lo_dice_sin_guardarlo(conn, pool_de_una_conexion):
    await _municipio(conn)
    await _ageb(conn, "0001", 1.0, 5000)
    await _negocio(conn, "n1", 1.5)

    datos = _pedir(pool_de_una_conexion, OSRMFalso(falla=True), minimo=0, minutos=0).json()

    assert datos["metodo"] == "linea_recta_aproximada"
    assert any("línea recta" in a for a in datos["avisos"])
    assert datos["filas"][0]["minutos"] > 0
    assert zonas._guardados == {}


@pytest.mark.asyncio
async def test_mover_un_criterio_no_vuelve_a_preguntarle_a_osrm(conn, pool_de_una_conexion):
    await _municipio(conn)
    await _ageb(conn, "0001", 1.0, 5000)
    await _negocio(conn, "n1", 5.0)
    osrm = OSRMFalso()

    primera = _pedir(pool_de_una_conexion, osrm, minimo=0, minutos=0).json()
    segunda = _pedir(pool_de_una_conexion, osrm, minimo=0, minutos=60).json()

    assert osrm.llamadas == 1
    assert segunda["criterios"]["minutos"] == 60
    assert isinstance(segunda["criterios"]["minutos"], int)
    assert primera["total_candidatas"] == 1
    assert segunda["total_candidatas"] == 0
    assert segunda["descartes"]["por_minutos"] == 1


@pytest.mark.asyncio
async def test_sin_negocios_la_distancia_no_descarta_y_se_avisa(conn, pool_de_una_conexion):
    await _municipio(conn)
    await _ageb(conn, "0001", 1.0, 5000)

    datos = _pedir(pool_de_una_conexion, OSRMFalso(), minimo=0).json()

    assert datos["metodo"] == "sin_negocios"
    assert datos["criterios"]["minutos"] is None
    assert datos["total_candidatas"] == 1
    assert "no descarta" in datos["avisos"][0]


@pytest.mark.asyncio
async def test_lotes_respetan_el_limite_de_osrm(conn, pool_de_una_conexion, monkeypatch):
    await _municipio(conn)
    for i in range(5):
        await _ageb(conn, f"{i:04d}", 1.0 + i / 10, 100)
    await _negocio(conn, "n1", 5.0)
    monkeypatch.setattr(zonas, "AGEBS_POR_LOTE", 2)
    osrm = OSRMFalso()

    datos = _pedir(pool_de_una_conexion, osrm, minimo=0, minutos=0).json()

    assert osrm.llamadas == 3
    assert datos["total_candidatas"] == 5


@pytest.mark.asyncio
async def test_demasiadas_agebs_se_rechazan_con_el_motivo(conn, pool_de_una_conexion, monkeypatch):
    await _tres_agebs(conn)
    monkeypatch.setattr(zonas, "MAX_AGEBS", 2)

    r = _pedir(pool_de_una_conexion, OSRMFalso())

    assert r.status_code == 422
    assert "Elige menos municipios" in r.json()["detail"]["mensaje"]


@pytest.mark.asyncio
async def test_solo_para_donde_poner_y_con_indicadores_conocidos(conn, pool_de_una_conexion):
    otra = {"intencion": "cuantos", "rubro": "floreria", "municipios": ["120"]}

    assert _pedir(pool_de_una_conexion, OSRMFalso(), otra).status_code == 422
    r = _pedir(pool_de_una_conexion, OSRMFalso(), indicador="pobtot; drop table agebs")
    assert r.status_code == 422
    assert "Indicador desconocido" in r.json()["detail"]["mensaje"]
