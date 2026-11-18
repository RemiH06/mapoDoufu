"""Patrones de un rubro: agrupación, plazas y colocación con datos hechos a
mano (sin base), y los focos con DBSCAN contra la base de test."""

import pytest
from fastapi.testclient import TestClient

from mapo_core import patrones
from mapo_core.db import get_pool
from mapo_core.server import app

FLORES = "Comercio al por menor de plantas y flores naturales"
ABARROTES = "Comercio al por menor en tiendas de abarrotes, ultramarinos y misceláneas"
DULCES = "Comercio al por menor de dulces y materias primas para repostería"
PASO = 0.002  # unos 220 m


@pytest.fixture(autouse=True)
def _sin_guardados():
    patrones._guardados.clear()
    yield
    patrones._guardados.clear()


def _reticula(n=30, clase=ABARROTES):
    """Fondo: n x n abarroteras a 220 m una de otra."""
    return [(20 + i * PASO, -103 + j * PASO, clase, None) for i in range(n) for j in range(n)]


def _juntos(clase, k=20, lat=20.03, lon=-102.97, plaza=None):
    """k negocios a menos de 20 m uno de otro."""
    return [(lat + (i % 5) * 0.00004, lon + (i // 5) * 0.00004, clase, plaza) for i in range(k)]


def _regados(clase, k=20):
    """k negocios repartidos por toda la retícula, sin juntarse."""
    return [(20 + (i * 7 % 30) * PASO + PASO / 2, -103 + (i * 11 % 30) * PASO + PASO / 2, clase, None) for i in range(k)]


def test_un_rubro_amontonado_se_agrupa():
    r = patrones.analizar(_reticula() + _juntos(FLORES), [FLORES])

    assert r["negocios"] == 20
    assert r["agrupacion"]["patron"] == "se_agrupa"
    assert r["agrupacion"]["distancia_m"] < 20
    assert r["agrupacion"]["al_azar_m"] > 100
    assert r["agrupacion"]["p_agrupa"] < patrones.ALFA


def test_un_rubro_regado_no_se_agrupa():
    r = patrones.analizar(_reticula() + _regados(FLORES), [FLORES])

    assert r["agrupacion"]["patron"] != "se_agrupa"


def test_la_misma_pregunta_da_la_misma_respuesta():
    negocios = _reticula() + _regados(FLORES)

    assert patrones.analizar(negocios, [FLORES]) == patrones.analizar(negocios, [FLORES])


def test_con_pocos_negocios_no_hay_patron_y_se_dice():
    r = patrones.analizar(_reticula() + _juntos(FLORES, k=3), [FLORES])

    assert r["agrupacion"] is None
    assert "Con menos de 5" in r["nota"]


def test_sin_marca_de_plaza_en_la_carga_se_dice_en_vez_de_cero():
    r = patrones.analizar(_reticula() + _juntos(FLORES), [FLORES])

    assert r["plazas"] is None
    assert "marca de plaza" in r["nota"]


def test_un_rubro_metido_en_mercados_sale_mas_en_plazas():
    fondo = _reticula()
    fondo[:50] = [(lat, lon, c, "CENTRO Y PLAZA COMERCIAL") for lat, lon, c, _ in fondo[:50]]
    r = patrones.analizar(fondo + _regados(FLORES) + _juntos(FLORES, plaza="MERCADO PUBLICO"), [FLORES])

    assert r["plazas"]["patron"] == "mas_en_plazas"
    assert r["plazas"]["rubro"] == 0.5
    assert r["plazas"]["tipos"] == [{"tipo": "MERCADO PUBLICO", "negocios": 20}]


def test_colocacion_dice_junto_a_que_rubro_y_es_asimetrica():
    # Junto a cada florería hay tres dulcerías pegadas entre sí: la florería
    # tiene de vecina a una dulcería, pero cada dulcería tiene a otra dulcería.
    sitios = []
    for i in range(30):
        lat, lon = 20 + (i * 7 % 30) * PASO + PASO / 2, -103 + (i * 11 % 30) * PASO + PASO / 2
        sitios.append((lat, lon, FLORES, None))
        sitios += [(lat + 0.00003 + d * 0.00001, lon, DULCES, None) for d in range(3)]
    negocios = _reticula() + sitios

    florerias = patrones.analizar(negocios, [FLORES])
    dulcerias = patrones.analizar(negocios, [DULCES])

    # 30 de 30 florerías junto a dulcería, contra 90 dulcerías de 1,019 vecinos posibles.
    assert florerias["junto_a"][0]["rubro"] == "dulceria"
    assert florerias["junto_a"][0]["cociente"] == pytest.approx((30 / 30) / (90 / 1019), abs=0.1)
    assert all(f["rubro"] != "floreria" for f in florerias["junto_a"])
    assert all(f["rubro"] != "floreria" for f in dulcerias["junto_a"])


async def _negocios(conn, filas):
    for i, (lat, lon, clase, plaza) in enumerate(filas):
        await conn.execute(
            """INSERT INTO fuente_denue_negocios (id, nombre, clase_actividad, tipo_plaza, colonia, lat, lon, cve_ent, cve_mun)
               VALUES (%(id)s, %(id)s, %(clase)s, %(plaza)s, %(colonia)s, %(lat)s, %(lon)s, '14', '120')""",
            {"id": f"t{i}", "clase": clase, "plaza": plaza, "lat": lat, "lon": lon,
             "colonia": "MEZQUITAN" if clase == FLORES and lat > 20.02 else "OTRA"},
        )


def _pedir(pool, plantilla):
    app.dependency_overrides[get_pool] = lambda: pool
    try:
        return TestClient(app).post("/buscador/patron", json={"cve_ent": "14", "plantilla": plantilla})
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_si_se_agrupa_encuentra_el_foco_y_su_colonia(conn, pool_de_una_conexion):
    await _negocios(conn, _reticula() + _juntos(FLORES) + _regados(FLORES, k=6))

    r = _pedir(pool_de_una_conexion, {"intencion": "donde_poner", "rubro": "floreria", "municipios": ["120"]})

    assert r.status_code == 200
    datos = r.json()
    assert datos["agrupacion"]["patron"] == "se_agrupa"
    assert datos["focos"]["total"] == 1
    foco = datos["focos"]["lista"][0]
    assert (foco["negocios"], foco["colonia"]) == (20, "MEZQUITAN")
    assert '"Polygon"' in foco["geojson"]
    assert datos["focos"]["radio_m"] >= patrones.MIN_RADIO_M
    assert datos["que"] == "Florería"
    assert "puntaje" not in datos


@pytest.mark.asyncio
async def test_si_no_se_agrupa_no_busca_focos(conn, pool_de_una_conexion):
    await _negocios(conn, _reticula() + _regados(FLORES))

    datos = _pedir(pool_de_una_conexion, {"intencion": "cuantos", "rubro": "floreria", "municipios": ["120"]}).json()

    assert datos["agrupacion"]["patron"] != "se_agrupa"
    assert datos["focos"] == {"radio_m": None, "minimo": 5, "total": 0, "en_focos": 0, "lista": []}


@pytest.mark.asyncio
async def test_patron_solo_para_donde_poner_y_cuantos(conn, pool_de_una_conexion):
    r = _pedir(pool_de_una_conexion, {"intencion": "perfil", "municipios": ["120"]})

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_demasiados_negocios_se_rechazan_con_el_motivo(conn, pool_de_una_conexion, monkeypatch):
    monkeypatch.setattr(patrones, "MAX_NEGOCIOS", 10)
    await _negocios(conn, _juntos(FLORES))

    r = _pedir(pool_de_una_conexion, {"intencion": "cuantos", "rubro": "floreria", "municipios": ["120"]})

    assert r.status_code == 422
    assert "Elige menos municipios" in r.json()["detail"]["mensaje"]
