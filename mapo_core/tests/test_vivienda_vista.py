import json

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from mapo_core.db import get_pool
from mapo_core.server import app


async def _municipios(conn):
    for cve_mun, nombre, x in [("039", "Guadalajara", 0), ("098", "Tlaquepaque", 1), ("120", "Zapopan", 2)]:
        await conn.execute(
            """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)
               VALUES (%(cvegeo)s, '99', %(cve_mun)s, %(nombre)s,
                       ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(g)s), 4326)))""",
            {"cvegeo": "99" + cve_mun, "cve_mun": cve_mun, "nombre": nombre,
             "g": json.dumps(box(x, 0, x + 1, 1).__geo_interface__)},
        )


async def _fuentes(conn):
    await conn.execute(
        """INSERT INTO fuente_eic2025_vivienda
             (cvegeo, nivel, cve_ent, cve_mun, cve_loc, nombre, indicador, valor, cv, lim_inf, lim_sup, nota)
           VALUES ('99039', 'municipio', '99', '039', '0000', 'Guadalajara', 'PCN_VPH_ALQUI', 34.1, 3.3, 32.2, 36.0, NULL),
                  ('99098', 'municipio', '99', '098', '0000', 'Tlaquepaque', 'PCN_VPH_ALQUI', NULL, NULL, NULL, NULL, 'MI')"""
    )
    await conn.execute(
        """INSERT INTO fuente_sniiv_financiamiento
             (anio, meses, cve_ent, cve_mun, organismo, destino_credito, valor_vivienda, acciones, monto)
           VALUES (2025, 12, '99', '039', 'INFONAVIT', 'Vivienda nueva', 'Media', 10, 10000000),
                  (2025, 12, '99', '039', 'BANCA (CNBV)', 'Vivienda nueva', 'Residencial', 5, 15000000),
                  (2025, 12, '99', '039', 'INFONAVIT', 'Mejoramientos', 'Media', 90, 0),
                  (2025, 12, '99', '000', 'CONAVI', 'Mejoramientos', 'No disponible', 99, 1),
                  (2026, 8, '99', '039', 'INFONAVIT', 'Vivienda nueva', 'Media', 3, 3000000)"""
    )
    await conn.execute(
        """INSERT INTO fuente_shf_ipv (nivel, clave, nombre, categoria, anio, trimestre, indice)
           VALUES ('municipio', '99039', 'Guadalajara', 'General', 2025, 2, 200),
                  ('municipio', '99039', 'Guadalajara', 'General', 2026, 2, 220),
                  ('estado', '99', 'Prueba', 'General', 2025, 2, 150),
                  ('estado', '99', 'Prueba', 'General', 2026, 2, 165)"""
    )
    await conn.execute(
        """INSERT INTO fuente_envi2020_entidad (cve_ent, indicador, valor, error_estandar, n_muestra)
           VALUES ('99', 'renta_mensual_mediana', 2000, NULL, 500),
                  ('99', 'pct_rentadas', 26.2, 1.3, 2000)"""
    )


@pytest.fixture
def cliente(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    yield TestClient(app)
    app.dependency_overrides.clear()


def _valores(cuerpo):
    return {f["properties"]["cve_mun"]: f["properties"] for f in cuerpo["features"]}


@pytest.mark.asyncio
async def test_eic_trae_cv_y_deja_mi_sin_dato(conn, cliente):
    await _municipios(conn)
    await _fuentes(conn)

    cuerpo = cliente.get("/vivienda/municipios", params={"cve_ent": "99", "indicador": "eic_alqui"}).json()

    v = _valores(cuerpo)
    assert v["039"]["valor_choropleth"] == pytest.approx(34.1)
    assert v["039"]["cv"] == pytest.approx(3.3)
    assert v["098"]["valor_choropleth"] is None and v["098"]["nota"] == "MI"
    assert v["120"]["valor_choropleth"] is None  # sin fila: sin dato, no cero
    assert cuerpo["nivel"] == "municipio" and "coeficiente de variación" in cuerpo["metodo"]


@pytest.mark.asyncio
async def test_sniiv_toma_el_ultimo_anio_completo_y_filtra_segmento(conn, cliente):
    await _municipios(conn)
    await _fuentes(conn)

    todo = cliente.get("/vivienda/municipios", params={"cve_ent": "99", "indicador": "sniiv_acciones"}).json()
    media = cliente.get(
        "/vivienda/municipios", params={"cve_ent": "99", "indicador": "sniiv_promedio", "segmento": "Media"}
    ).json()
    parcial = cliente.get(
        "/vivienda/municipios", params={"cve_ent": "99", "indicador": "sniiv_acciones", "anio": 2026}
    ).json()

    assert todo["anio"] == 2025 and _valores(todo)["039"]["valor_choropleth"] == 105
    # Los 90 mejoramientos sin monto no bajan el promedio.
    assert _valores(media)["039"]["valor_choropleth"] == pytest.approx(1_000)
    assert "8 de 12 meses" in parcial["metodo"]


@pytest.mark.asyncio
async def test_shf_es_cambio_anual_solo_donde_se_publica(conn, cliente):
    await _municipios(conn)
    await _fuentes(conn)

    v = _valores(cliente.get("/vivienda/municipios", params={"cve_ent": "99", "indicador": "shf_anual"}).json())

    assert v["039"]["valor_choropleth"] == pytest.approx(10.0)
    assert v["098"]["valor_choropleth"] is None


@pytest.mark.asyncio
async def test_ficha_separa_fuentes_y_dice_el_nivel(conn, cliente):
    await _municipios(conn)
    await _fuentes(conn)

    gdl = cliente.get("/vivienda/ficha", params={"cve_ent": "99", "cve_mun": "039"}).json()
    tlq = cliente.get("/vivienda/ficha", params={"cve_ent": "99", "cve_mun": "098"}).json()

    assert gdl["shf"]["nivel"] == "municipio" and gdl["shf"]["variacion_anual"] == pytest.approx(10.0)
    assert tlq["shf"]["nivel"] == "estado" and tlq["shf"]["variacion_anual"] == pytest.approx(10.0)
    assert [s["segmento"] for s in gdl["sniiv"]["segmentos"]] == ["Media", "Residencial"]
    media = gdl["sniiv"]["segmentos"][0]
    assert media["acciones"] == 100 and media["promedio"] == pytest.approx(1_000_000)
    assert gdl["sniiv"]["anio"] == 2025
    assert tlq["sniiv"] is None
    assert tlq["eic"][0]["nota"] == "MI"
    assert {e["indicador"] for e in gdl["envi"]} == {"pct_rentadas", "renta_mensual_mediana"}


@pytest.mark.asyncio
async def test_rechaza_indicador_segmento_y_claves_raras(conn, cliente):
    await _municipios(conn)

    assert cliente.get("/vivienda/municipios", params={"cve_ent": "99", "indicador": "precio"}).status_code == 400
    assert cliente.get(
        "/vivienda/municipios", params={"cve_ent": "99", "indicador": "sniiv_acciones", "segmento": "x'"}
    ).status_code == 400
    assert cliente.get("/vivienda/municipios", params={"cve_ent": "9;", "indicador": "eic_alqui"}).status_code == 422
    assert cliente.get("/vivienda/ficha", params={"cve_ent": "99", "cve_mun": "777"}).status_code == 404
