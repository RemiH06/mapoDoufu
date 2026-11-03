"""Fase 7: los casos de docs/producto/rubros.md, en los dos modos. Las
preguntas son las que se probaron contra los datos reales de Jalisco."""

import json

import pytest
from fastapi.testclient import TestClient

from mapo_core import buscador, rubros
from mapo_core.db import get_pool
from mapo_core.server import app

MUNICIPIOS = [("120", "Zapopan"), ("039", "Guadalajara"), ("101", "Tonalá"), ("097", "Tlajomulco de Zúñiga")]


def _entender(texto):
    return buscador.interpretar(texto, "14", MUNICIPIOS)


@pytest.mark.parametrize(
    "texto,rubro",
    [
        ("¿Dónde pongo una floristería en Zapopan?", "floreria"),
        ("¿dónde vendo flores en Tonalá?", "floreria"),
        ("¿Dónde conviene abrir un centro de llamadas en Zapopan?", "call_center"),
        ("¿dónde pongo un contact center en Zapopan?", "call_center"),
        ("¿cuántos súpers hay en Zapopan?", "supermercado"),
        ("dónde abrir un autoservicio en Tonalá", "supermercado"),
        ("¿cuántas clínicas hay en Zapopan?", "consultorio_medico"),
        ("¿Cuántos hospitales hay en Guadalajara?", "hospital"),
        ("¿Dónde faltan estaciones de policía en Tlajomulco?", "seguridad_publica"),
        ("¿cuántas comisarías hay en Zapopan?", "seguridad_publica"),
        ("¿cuántas comandancias hay en Tonalá?", "seguridad_publica"),
    ],
)
def test_cada_caso_llega_a_su_rubro(texto, rubro):
    assert _entender(texto)["plantilla"]["rubro"] == rubro


def test_centro_de_salud_es_el_consultorio_publico_no_todo_el_sector():
    plantilla = _entender("¿cuántos centros de salud hay en Tonalá?")["plantilla"]
    assert (plantilla["rubro"], plantilla["sector"]) == ("consultorio_medico", None)
    assert plantilla["solo_publicos"] is True


def test_consultorio_contra_hospital_no_se_mezclan():
    assert not set(rubros.clases_de(rubro="consultorio_medico")) & set(rubros.clases_de(rubro="hospital"))


@pytest.mark.parametrize("texto", ["cuantos oxxos hay en Guadalajara", "cuantos walmart hay en Guadalajara"])
def test_una_marca_avisa_que_la_cifra_es_del_giro(texto):
    resultado = _entender(texto)
    assert resultado["plantilla"]["rubro"] is not None
    assert any("no por marca" in a for a in resultado["avisos"])


def test_un_nombre_de_rubro_no_avisa_de_marca():
    assert not _entender("¿cuántos súpers hay en Zapopan?")["avisos"]


def test_el_rubro_en_donde_contratar_se_quita_y_se_dice():
    resultado = _entender("¿Dónde busco gente de 18 a 24 años para un call center en Guadalajara?")
    assert resultado["plantilla"]["rubro"] is None
    assert resultado["faltan"] == []
    assert any("Call center" in a for a in resultado["avisos"])


# --- El filtro "giro" del modo técnico ---------------------------------------


@pytest.mark.parametrize(
    "texto,nombre",
    [
        ("florería", "Florería"),
        ("floristerias", "Florería"),
        ("call center", "Call center"),
        ("súper", "Supermercado"),
        ("policía", "Seguridad pública"),
        ("salud", "Salud y asistencia"),
    ],
)
def test_el_giro_tecnico_entiende_las_palabras_del_buscador(texto, nombre):
    clases, filtro = buscador.giro_tecnico(texto)
    assert clases
    assert filtro == nombre


def test_el_giro_tecnico_no_confunde_super_con_minisuper():
    clases, _ = buscador.giro_tecnico("súper")
    assert clases == ["Comercio al por menor en supermercados"]


def test_el_giro_que_no_es_termino_busca_en_las_clases_sin_acentos():
    clases, filtro = buscador.giro_tecnico("recepcion de llamadas")
    assert clases == ["Servicios de recepción de llamadas telefónicas y promoción por teléfono"]
    assert filtro is None


def test_el_giro_sin_coincidencia_cae_al_texto():
    assert buscador.giro_tecnico("clase de otro estado") == (None, None)


# --- Los dos modos dan lo mismo --------------------------------------------------

CUADRADO = {"type": "Polygon", "coordinates": [[[-2, -2], [12, -2], [12, 12], [-2, 12], [-2, -2]]]}
ESQUINAS = [(0.0, 0.0), (0.0, 10.0), (10.0, 0.0), (10.0, 10.0)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "palabra,rubro,clase",
    [
        ("florería", "floreria", "Comercio al por menor de plantas y flores naturales"),
        ("call center", "call_center", "Servicios de recepción de llamadas telefónicas y promoción por teléfono"),
        ("supermercado", "supermercado", "Comercio al por menor en supermercados"),
        ("hospital", "hospital", "Hospitales generales del sector público"),
        ("policía", "seguridad_publica", "Mantenimiento de la seguridad y el orden público"),
    ],
)
async def test_los_dos_modos_cuentan_lo_mismo(conn, pool_de_una_conexion, palabra, rubro, clase):
    await conn.execute(
        """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)
           VALUES ('14120', '14', '120', 'Zapopan',
                   ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)))""",
        {"geojson": json.dumps(CUADRADO)},
    )
    for i, (lat, lon) in enumerate(ESQUINAS):
        await conn.execute(
            """INSERT INTO fuente_denue_negocios (id, nombre, clase_actividad, lat, lon, cve_ent, cve_mun)
               VALUES (%(id)s, 'x', %(clase)s, %(lat)s, %(lon)s, '14', '120')""",
            {"id": str(i), "clase": clase, "lat": lat, "lon": lon},
        )
    # Una de otra clase, que ninguno de los dos modos debe contar.
    await conn.execute(
        """INSERT INTO fuente_denue_negocios (id, nombre, clase_actividad, lat, lon, cve_ent, cve_mun)
           VALUES ('otro', 'x', 'Comercio al por menor en minisupers', 5, 5, '14', '120')"""
    )

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    try:
        cliente = TestClient(app)
        tecnico = cliente.get(
            "/voronoi/denue", params={"cve_ent": "14", "cve_mun": "120", "clase_actividad": palabra}
        ).json()
        plantilla = {"intencion": "cuantos", "rubro": rubro, "municipios": ["120"]}
        resuelto = cliente.post("/buscador/resolver", json={"cve_ent": "14", "plantilla": plantilla}).json()
    finally:
        app.dependency_overrides.clear()

    assert tecnico["num_negocios"] == resuelto["cifras"]["total_negocios"] == 4


def test_policia_no_se_llama_negocio():
    plantilla = buscador.Plantilla(intencion="cuantos", rubro="seguridad_publica", municipios=["120"])
    assert buscador._unidad(plantilla)[0] == "unidades"
    plantilla = buscador.Plantilla(intencion="cuantos", rubro="hospital", municipios=["120"], solo_publicos=True)
    assert buscador._unidad(plantilla)[0] == "unidades"
    plantilla = buscador.Plantilla(intencion="cuantos", rubro="hospital", municipios=["120"])
    assert buscador._unidad(plantilla)[0] == "negocios"
