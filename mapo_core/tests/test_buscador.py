"""Modo buscador: el analizador (sin base) y la resolución por endpoint."""

import json

import pytest
from fastapi.testclient import TestClient

from mapo_core import buscador
from mapo_core.db import get_pool
from mapo_core.server import app, get_osrm_client

MUNICIPIOS = [
    ("039", "Guadalajara"),
    ("120", "Zapopan"),
    ("098", "San Pedro Tlaquepaque"),
    ("073", "San Juan de los Lagos"),
    ("053", "Lagos de Moreno"),
    ("058", "Mascota"),
]

FLORES = "Comercio al por menor de plantas y flores naturales"


def _entender(texto):
    return buscador.interpretar(texto, "14", MUNICIPIOS)


# --- Interpretar ---------------------------------------------------------------


def test_preguntas_de_la_especificacion():
    casos = {
        "¿Dónde pongo una floristería en Zapopan?": ("donde_poner", {"rubro": "floreria", "municipios": ["120"]}),
        "¿Cuántos supermercados hay en Guadalajara y Tlaquepaque?": (
            "cuantos",
            {"rubro": "supermercado", "municipios": ["039", "098"]},
        ),
        "¿Cuántas farmacias hay a 10 minutos de aquí?": ("cuantos_cerca", {"rubro": "farmacia", "minutos": 10}),
        "¿Dónde busco gente de 18 a 24 años en Zapopan?": (
            "donde_contratar",
            {"edad": "p_18a24", "municipios": ["120"]},
        ),
        "¿Cómo es Tlaquepaque?": ("perfil", {"municipios": ["098"]}),
        "¿Dónde faltan servicios públicos?": ("donde_poner", {"solo_publicos": True}),
    }
    for texto, (intencion, esperado) in casos.items():
        plantilla = _entender(texto)["plantilla"]
        assert plantilla["intencion"] == intencion, texto
        for clave, valor in esperado.items():
            assert plantilla[clave] == valor, (texto, clave)


def test_lo_que_falta_se_pide():
    assert _entender("¿Cuántas farmacias hay a 10 minutos de aquí?")["faltan"] == ["punto"]
    assert _entender("¿Dónde faltan servicios públicos?")["faltan"] == ["rubro", "municipios"]
    assert _entender("hola")["faltan"] == ["intencion"]


def test_dos_rubros_no_se_elige_uno_en_silencio():
    resultado = _entender("¿dónde abro una papelería o una florería?")
    assert resultado["plantilla"]["rubro"] is None
    assert "varios rubros" in resultado["avisos"][0]


def test_rango_de_edad_que_no_trae_el_censo_se_avisa():
    resultado = _entender("busco gente de 25 a 40 años en Zapopan")
    assert resultado["plantilla"]["edad"] is None
    assert resultado["faltan"] == ["edad"]
    assert "no se aproxima" in resultado["avisos"][0]
    assert _entender("dónde contrato adultos mayores en Zapopan")["plantilla"]["edad"] == "p_60ymas"


def test_gana_el_termino_mas_largo():
    # "San Juan de los Lagos" no es Lagos de Moreno; "tienda de mascotas" no es el municipio.
    assert _entender("consultorios médicos en San Juan de los Lagos")["plantilla"]["municipios"] == ["073"]
    plantilla = _entender("¿cuántas tiendas de mascotas hay en Guadalajara?")["plantilla"]
    assert plantilla["rubro"] == "tienda_de_mascotas"
    assert plantilla["municipios"] == ["039"]


def test_un_rubro_que_dice_publico_no_prende_solo_publicos():
    plantilla = _entender("¿Dónde pongo baños públicos en Zapopan?")["plantilla"]
    assert plantilla["rubro"] == "banos_publicos"
    assert plantilla["solo_publicos"] is False


def test_sector_y_plurales():
    plantilla = _entender("¿Cuántos negocios de salud hay en Zapopan?")["plantilla"]
    assert (plantilla["sector"], plantilla["rubro"]) == ("salud", None)
    assert _entender("cuantos consultorios medicos hay")["plantilla"]["rubro"] == "consultorio_medico"


def test_perfil_de_varios_municipios_pide_uno():
    resultado = _entender("¿cómo es Zapopan o Guadalajara?")
    assert resultado["faltan"] == ["municipio"]
    assert "un municipio" in resultado["avisos"][0]


def test_minutos_sin_palabra_de_intencion_es_cuantos_cerca():
    plantilla = _entender("taquerías a media hora de aquí")["plantilla"]
    assert (plantilla["intencion"], plantilla["minutos"]) == ("cuantos_cerca", 30)


def test_catalogo_no_ofrece_sectores_no_buscables():
    sectores = {s["sector"] for s in buscador.catalogo()["sectores"]}
    assert "industria" not in sectores
    assert "salud" in sectores


# --- Resolver ------------------------------------------------------------------

CUADRADO = {"type": "Polygon", "coordinates": [[[-2, -2], [12, -2], [12, 12], [-2, 12], [-2, -2]]]}
ESQUINAS = [(0.0, 0.0), (0.0, 10.0), (10.0, 0.0), (10.0, 10.0)]


async def _municipio(conn, cve_mun="120", nombre="Zapopan", pobtot=1000):
    await conn.execute(
        """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)
           VALUES (%(cvegeo)s, '14', %(cve_mun)s, %(nombre)s,
                   ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))""",
        {"cvegeo": f"14{cve_mun}", "cve_mun": cve_mun, "nombre": nombre, "geojson": json.dumps(CUADRADO)},
    )
    if pobtot is not None:
        await conn.execute(
            """INSERT INTO fuente_censo_poblacion (cvegeo, nivel, cve_ent, cve_mun, pobtot, p_18a24, datos_json)
               VALUES (%(cvegeo)s, 'municipio', '14', %(cve_mun)s, %(pobtot)s, %(jovenes)s, '{}'::jsonb)""",
            {"cvegeo": f"14{cve_mun}", "cve_mun": cve_mun, "pobtot": pobtot, "jovenes": pobtot // 10},
        )


async def _negocio(conn, id_, lat, lon, clase=FLORES, cve_mun="120"):
    await conn.execute(
        """INSERT INTO fuente_denue_negocios (id, nombre, clase_actividad, lat, lon, cve_ent, cve_mun)
           VALUES (%(id)s, %(nombre)s, %(clase)s, %(lat)s, %(lon)s, '14', %(cve_mun)s)""",
        {"id": id_, "nombre": f"negocio {id_}", "clase": clase, "lat": lat, "lon": lon, "cve_mun": cve_mun},
    )


def _resolver(pool, plantilla, osrm=None):
    app.dependency_overrides[get_pool] = lambda: pool
    if osrm:
        app.dependency_overrides[get_osrm_client] = lambda: osrm
    try:
        return TestClient(app).post("/buscador/resolver", json={"cve_ent": "14", "plantilla": plantilla})
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_donde_poner_da_habitantes_por_negocio_con_formula_y_capas(conn, pool_de_una_conexion):
    await _municipio(conn)
    for i, (lat, lon) in enumerate(ESQUINAS):
        await _negocio(conn, f"f{i}", lat, lon)
    await _negocio(conn, "p0", 5.0, 5.0, clase="Comercio al por menor de artículos de papelería")

    respuesta = _resolver(
        pool_de_una_conexion, {"intencion": "donde_poner", "rubro": "floreria", "municipios": ["120"]}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    cifras = cuerpo["cifras"]
    assert cifras["municipios"][0] == {
        "cve_mun": "120",
        "nombre": "Zapopan",
        "negocios": 4,
        "poblacion": 1000,
        "habitantes_por_negocio": 250,
    }
    assert cifras["habitantes_por_negocio"] == 250
    assert "÷" in cifras["formula"]
    assert len(cuerpo["capas"]["voronoi"]["celdas"]["features"]) == 4
    assert cuerpo["capas"]["coropleta"]["indicador"] == "pobtot"


@pytest.mark.asyncio
async def test_donde_poner_con_pocos_negocios_avisa_y_da_las_cifras(conn, pool_de_una_conexion):
    await _municipio(conn)
    await _negocio(conn, "f0", 0.0, 0.0)

    cuerpo = _resolver(
        pool_de_una_conexion, {"intencion": "donde_poner", "rubro": "floreria", "municipios": ["120"]}
    ).json()

    assert cuerpo["capas"]["voronoi"] is None
    assert any("al menos 3" in a for a in cuerpo["avisos"])
    assert cuerpo["cifras"]["habitantes_por_negocio"] == 1000


@pytest.mark.asyncio
async def test_sin_poblacion_la_razon_es_null(conn, pool_de_una_conexion):
    await _municipio(conn, pobtot=None)
    await _negocio(conn, "f0", 0.0, 0.0)

    cuerpo = _resolver(
        pool_de_una_conexion, {"intencion": "donde_poner", "rubro": "floreria", "municipios": ["120"]}
    ).json()

    assert cuerpo["cifras"]["municipios"][0]["habitantes_por_negocio"] is None
    assert cuerpo["cifras"]["habitantes_por_negocio"] is None


@pytest.mark.asyncio
async def test_cuantos_por_municipio_con_puntos(conn, pool_de_una_conexion):
    await _municipio(conn)
    await _municipio(conn, "039", "Guadalajara")
    await _negocio(conn, "f0", 0.0, 0.0)
    await _negocio(conn, "f1", 1.0, 1.0, cve_mun="039")
    await _negocio(conn, "f2", None, None, cve_mun="039")

    cuerpo = _resolver(
        pool_de_una_conexion, {"intencion": "cuantos", "rubro": "floreria", "municipios": ["120", "039"]}
    ).json()

    assert [m["negocios"] for m in cuerpo["cifras"]["municipios"]] == [1, 2]
    assert cuerpo["cifras"]["total_negocios"] == 3
    assert len(cuerpo["capas"]["puntos"]) == 2
    assert any("no traen ubicación" in a for a in cuerpo["avisos"])


@pytest.mark.asyncio
async def test_solo_publicos_sin_clases_publicas_avisa(conn, pool_de_una_conexion):
    await _municipio(conn)
    await _negocio(conn, "f0", 0.0, 0.0)

    cuerpo = _resolver(
        pool_de_una_conexion,
        {"intencion": "cuantos", "rubro": "floreria", "municipios": ["120"], "solo_publicos": True},
    ).json()

    assert cuerpo["cifras"]["total_negocios"] == 0
    assert any("sector público" in a for a in cuerpo["avisos"])


class _OSRMTodoAlcanzable:
    async def duraciones_desde(self, origen, destinos):
        return [1.0 for _ in destinos]


@pytest.mark.asyncio
async def test_cuantos_cerca_cuenta_lo_que_cae_en_la_isocrona(conn, pool_de_una_conexion):
    # 10 minutos a 90 km/h como máximo: unos 15 km alrededor del punto.
    await _negocio(conn, "cerca", 20.67, -103.35)
    await _negocio(conn, "lejos", 21.5, -103.35)

    cuerpo = _resolver(
        pool_de_una_conexion,
        {"intencion": "cuantos_cerca", "rubro": "floreria", "minutos": 10, "lat": 20.67, "lon": -103.36},
        osrm=_OSRMTodoAlcanzable(),
    ).json()

    assert cuerpo["cifras"]["total_negocios"] == 1
    assert cuerpo["cifras"]["metodo"] == "osrm_real"
    assert cuerpo["capas"]["isocrona"]["poligono"]["type"] == "Polygon"
    assert [p["nombre"] for p in cuerpo["capas"]["puntos"]] == ["negocio cerca"]


@pytest.mark.asyncio
async def test_donde_contratar_dice_que_la_enoe_es_estatal(conn, pool_de_una_conexion):
    await _municipio(conn)

    cuerpo = _resolver(
        pool_de_una_conexion, {"intencion": "donde_contratar", "edad": "p_18a24", "municipios": ["120"]}
    ).json()

    assert cuerpo["cifras"]["municipios"][0]["poblacion"] == 100
    assert cuerpo["cifras"]["laboral"] is None
    assert any("ENOE" in a for a in cuerpo["avisos"])


def test_perfil_regresa_a_donde_ir(pool_de_una_conexion):
    cuerpo = _resolver(pool_de_una_conexion, {"intencion": "perfil", "municipios": ["098"]}).json()
    assert cuerpo["perfil"] == {"cve_ent": "14", "cve_mun": "098"}


def test_plantilla_incompleta_o_invalida_da_422(pool_de_una_conexion):
    respuesta = _resolver(pool_de_una_conexion, {"intencion": "donde_poner", "rubro": "floreria"})
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["faltan"] == ["municipios"]

    respuesta = _resolver(pool_de_una_conexion, {"intencion": "cuantos", "rubro": "inventado", "municipios": ["120"]})
    assert respuesta.status_code == 422


@pytest.mark.asyncio
async def test_municipio_que_no_esta_da_422(conn, pool_de_una_conexion):
    respuesta = _resolver(pool_de_una_conexion, {"intencion": "cuantos", "rubro": "floreria", "municipios": ["999"]})
    assert respuesta.status_code == 422
