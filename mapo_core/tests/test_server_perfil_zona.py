import pytest
from fastapi.testclient import TestClient

from mapo_core.db import get_pool
from mapo_core.server import app


async def _insertar_censo_municipio(conn, cve_ent, cve_mun, pobtot):
    await conn.execute(
        """INSERT INTO fuente_censo_poblacion (cvegeo, nivel, cve_ent, cve_mun, pobtot, datos_json)
           VALUES (%(cvegeo)s, 'municipio', %(cve_ent)s, %(cve_mun)s, %(pobtot)s, '{}'::jsonb)""",
        {"cvegeo": f"{cve_ent}{cve_mun}", "cve_ent": cve_ent, "cve_mun": cve_mun, "pobtot": pobtot},
    )


@pytest.mark.asyncio
async def test_perfil_zona_con_censo_trae_demografia(conn, pool_de_una_conexion):
    await _insertar_censo_municipio(conn, "14", "039", pobtot=1500000)
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/perfil_zona", params={"cve_ent": "14", "cve_mun": "039"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["demografia"]["pobtot"] == 1500000
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_perfil_zona_sin_censo_trae_demografia_null(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/perfil_zona", params={"cve_ent": "14", "cve_mun": "999"})

    assert respuesta.status_code == 200
    assert respuesta.json()["demografia"] is None
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_perfil_zona_marca_honesto_lo_que_no_esta_portado(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/perfil_zona", params={"cve_ent": "14", "cve_mun": "039"})

    cuerpo = respuesta.json()
    assert cuerpo["laboral_disponible"] is False
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_perfil_zona_sin_datos_de_enigh_ni_sesnsp_trae_null_no_falso(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/perfil_zona", params={"cve_ent": "14", "cve_mun": "039"})

    cuerpo = respuesta.json()
    assert cuerpo["consumo"] is None
    assert cuerpo["seguridad"] is None
    app.dependency_overrides.clear()


async def _insertar_negocio(conn, id_, clase_actividad, cve_ent="14", cve_mun="039"):
    await conn.execute(
        """INSERT INTO fuente_denue_negocios (id, nombre, clase_actividad, cve_ent, cve_mun)
           VALUES (%(id)s, %(nombre)s, %(clase_actividad)s, %(cve_ent)s, %(cve_mun)s)""",
        {"id": id_, "nombre": f"negocio {id_}", "clase_actividad": clase_actividad, "cve_ent": cve_ent, "cve_mun": cve_mun},
    )


@pytest.mark.asyncio
async def test_perfil_zona_trae_comercio_real(conn, pool_de_una_conexion):
    await _insertar_negocio(conn, "1", "papeleria")
    await _insertar_negocio(conn, "2", "papeleria")
    await _insertar_negocio(conn, "3", "farmacia")

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/perfil_zona", params={"cve_ent": "14", "cve_mun": "039"})

    cuerpo = respuesta.json()
    assert cuerpo["comercio"]["total_negocios"] == 3
    assert cuerpo["comercio"]["top_clases_actividad"][0] == ["papeleria", 2]
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_perfil_zona_sin_negocios_trae_comercio_en_cero_no_null(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/perfil_zona", params={"cve_ent": "14", "cve_mun": "039"})

    cuerpo = respuesta.json()
    assert cuerpo["comercio"]["total_negocios"] == 0
    assert cuerpo["comercio"]["top_clases_actividad"] == []
    app.dependency_overrides.clear()


async def _insertar_hogar_enigh(conn, folioviv, gasto_mon, cve_ent="14", cve_mun="039"):
    await conn.execute(
        """INSERT INTO fuente_enigh_concentradohogar (folioviv, foliohog, ubica_geo, cve_ent, cve_mun, factor, gasto_mon)
           VALUES (%(folioviv)s, '1', %(ubica_geo)s, %(cve_ent)s, %(cve_mun)s, 207, %(gasto_mon)s)""",
        {"folioviv": folioviv, "ubica_geo": cve_ent + cve_mun, "cve_ent": cve_ent, "cve_mun": cve_mun, "gasto_mon": gasto_mon},
    )


@pytest.mark.asyncio
async def test_perfil_zona_trae_consumo_real(conn, pool_de_una_conexion):
    await _insertar_hogar_enigh(conn, "1", 29582.6)
    await _insertar_hogar_enigh(conn, "2", 22403.7)

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/perfil_zona", params={"cve_ent": "14", "cve_mun": "039"})

    cuerpo = respuesta.json()
    assert cuerpo["consumo"]["n_hogares_muestra"] == 2
    assert cuerpo["consumo"]["periodo"] == "diario"
    app.dependency_overrides.clear()


async def _insertar_delito(conn, tipo_delito, cantidad, anio=2024, mes=1, cve_ent="14", cve_mun="039"):
    await conn.execute(
        """INSERT INTO fuente_sesnsp_delitos_municipal
             (anio, mes, cve_ent, cve_mun, tipo_delito, bien_juridico, subtipo_delito, modalidad, cantidad)
           VALUES (%(anio)s, %(mes)s, %(cve_ent)s, %(cve_mun)s, %(tipo_delito)s, 'x', 'x', 'x', %(cantidad)s)""",
        {"anio": anio, "mes": mes, "cve_ent": cve_ent, "cve_mun": cve_mun, "tipo_delito": tipo_delito, "cantidad": cantidad},
    )


@pytest.mark.asyncio
async def test_perfil_zona_trae_seguridad_real_del_anio_mas_reciente(conn, pool_de_una_conexion):
    await _insertar_delito(conn, "Robo", 10, anio=2023)
    await _insertar_delito(conn, "Homicidio", 2, anio=2024)
    await _insertar_delito(conn, "Robo", 5, anio=2024)

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    cliente = TestClient(app)

    respuesta = cliente.get("/perfil_zona", params={"cve_ent": "14", "cve_mun": "039"})

    cuerpo = respuesta.json()
    assert cuerpo["seguridad"]["anio"] == 2024
    assert cuerpo["seguridad"]["total_delitos"] == 7  # solo 2024: Homicidio(2) + Robo(5), no el 2023
    assert cuerpo["seguridad"]["por_tipo"][0] == ["Robo", 5]
    app.dependency_overrides.clear()
