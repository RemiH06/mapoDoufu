"""Perfil de cualquier zona y zonas parecidas (sesión 29h, docs/producto/perfil.md)."""

import json

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from mapo_core import perfil, similares
from mapo_core import zona as zona_comun
from mapo_core.db import get_pool
from mapo_core.perfil import Censo
from mapo_core.server import app


def test_una_razon_solo_usa_los_lugares_que_traen_las_dos_partes():
    censo = Censo([({"VPH_INTER": 50, "TVIVPARHAB": 100}, 1.0), ({"VPH_INTER": "*", "TVIVPARHAB": 100}, 1.0)])
    # Con el denominador del reservado saldría 25 %.
    assert censo.razon("VPH_INTER", "TVIVPARHAB") == 50
    assert censo.total("TVIVPARHAB") == 200
    assert censo.reservados() == 1
    assert censo.total("POBTOT") is None  # ningún lugar lo trae: no es cero


def test_las_sumas_y_promedios_llevan_el_peso_del_lugar():
    censo = Censo([({"POBTOT": 1000, "GRAPROES": "10", "P_15YMAS": 500}, 0.5),
                   ({"POBTOT": 200, "GRAPROES": "6", "P_15YMAS": 250}, 1.0)])
    assert censo.total("POBTOT") == 700
    assert censo.promedio("GRAPROES", "P_15YMAS") == 8


def test_el_error_del_reparto_depende_de_cuanta_gente_resulta():
    assert [perfil.error_reparto(n) for n in (40, 300, 1_000, 3_000, 9_000, 50_000)] == [None, 43, 29, 13, 5, 3]


def test_servicios_separa_lo_lejos_lo_sin_ruta_y_lo_no_calculado():
    lugares = [{"clave": "a" * 13, "tipo": "ageb", "peso": 0.5, "d": {"POBTOT": 100}},
               {"clave": "b" * 13, "tipo": "ageb", "peso": 1.0, "d": {"POBTOT": 40}},
               {"clave": "c" * 13, "tipo": "ageb", "peso": 1.0, "d": {"POBTOT": 10}},
               {"clave": "d" * 9, "tipo": "localidad", "peso": 1.0, "d": {"POBTOT": 5}}]
    minutos = {"centro_salud": {"a" * 13: 15.0, "b" * 13: 22.0, "c" * 13: None}}
    por = {s["clave"]: s for s in perfil.servicios(lugares, minutos)}
    c = por["centro_salud"]
    assert (c["tramos"], c["sin_ruta"], c["sin_calcular"]) == ([50, 40, 0], 10, 5)
    assert c["cerca_pct"] == 55.6
    assert por["supermercado"] == {"clave": "supermercado", "titulo": "Supermercado", "grupo_etiqueta": "personas",
                                   "calculado": False}


def test_con_mas_de_la_mitad_sin_calcular_no_hay_porcentaje():
    lugares = [{"clave": "a" * 13, "tipo": "ageb", "peso": 1.0, "d": {"P_6A11": 10}},
               {"clave": "d" * 9, "tipo": "localidad", "peso": 1.0, "d": {"P_6A11": 90}}]
    s = next(x for x in perfil.servicios(lugares, {"primaria_publica": {"a" * 13: 3.0}})
             if x["clave"] == "primaria_publica")
    assert s["parcial"] and s["cerca_pct"] is None


CENSO = {"POBTOT": 1000, "POBFEM": 520, "POBMAS": 480, "TVIVPARHAB": 250, "VPH_INTER": 200, "VIVTOT": 300}


async def _zona(conn):
    """Un municipio de 0.1 grados con dos AGEB lado a lado (1,000 personas cada una) y una
    colonia que cubre la izquierda entera y un cuarto de la derecha."""
    caja = "ST_Multi(ST_MakeEnvelope(%s, 20.60, %s, 20.61, 4326))"
    await conn.execute("INSERT INTO entidades (cve_ent, nombre, geom) VALUES ('14', 'Jalisco',"
                       " ST_Multi(ST_MakeEnvelope(-104, 20, -103, 21, 4326))) ON CONFLICT DO NOTHING")
    await conn.execute(f"INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)"
                       f" VALUES ('14039', '14', '039', 'Guadalajara', {caja})", (-103.40, -103.30))
    for clave, x in (("1403900010010", -103.40), ("1403900010020", -103.39)):
        await conn.execute(f"INSERT INTO agebs (cvegeo, cve_ent, cve_mun, cve_loc, cve_ageb, geom)"
                           f" VALUES (%s, '14', '039', '0001', %s, {caja})", (clave, clave[-4:], x, x + 0.01))
        await conn.execute("INSERT INTO fuente_censo_poblacion (cvegeo, nivel, cve_ent, cve_mun, pobtot, datos_json)"
                           " VALUES (%s, 'ageb', '14', '039', 1000, %s)", (clave, json.dumps(CENSO)))
    await conn.execute("INSERT INTO fuente_censo_poblacion (cvegeo, nivel, cve_ent, cve_mun, pobtot, datos_json)"
                       " VALUES ('14039', 'municipio', '14', '039', 2500, %s)",
                       (json.dumps({**CENSO, "POBTOT": 2500}),))
    await conn.execute(f"INSERT INTO colonias (cve_col, nombre, nombre_norm, cve_ent, cve_mun, nom_mun, geom)"
                       f" VALUES ('14039_0001', 'Centro', 'centro', '14', '039', 'Guadalajara', {caja})",
                       (-103.40, -103.3875))
    for i, lon in ((1, -103.395), (2, -103.36)):
        await conn.execute("INSERT INTO fuente_denue_negocios (id, clase_actividad, clee, lat, lon, cve_ent, cve_mun)"
                           " VALUES (%s, 'Tacos', '14039722514000000000000000U1', 20.605, %s, '14', '039')",
                           (str(i), lon))


@pytest_asyncio.fixture
async def zona_chica(conn):
    await _zona(conn)
    return conn


@pytest.mark.asyncio
async def test_una_colonia_reparte_la_gente_por_area_y_cuenta_solo_sus_negocios(zona_chica, pool_de_una_conexion):
    r = await perfil.perfil(pool_de_una_conexion, zona_comun.validar("col:14039_0001"))
    assert r["zona"]["entera"] is False
    assert r["demografia"]["pobtot"] == 1250  # una AGEB y un cuarto de la otra
    assert r["demografia"]["estimada"] and r["demografia"]["error_pct"] == 29
    assert r["comercio"]["total_negocios"] == 1
    assert r["comercio"]["sectores"] == [["Alojamiento y comida", 1]]
    internet = next(b for b in r["vivienda"]["bienes"] if b["clave"] == "VPH_INTER")
    assert internet["pct"] == 80
    assert {f["properties"]["c"] for f in r["plano"]["features"]} == {"1403900010010", "1403900010020"}


@pytest.mark.asyncio
async def test_un_municipio_va_por_clave_con_su_renglon_del_censo(zona_chica, pool_de_una_conexion):
    r = await perfil.perfil(pool_de_una_conexion, zona_comun.validar("mun:14039"))
    assert r["demografia"]["pobtot"] == 2500  # no la suma de sus AGEB: deja fuera al campo
    assert r["demografia"]["estimada"] is False and r["demografia"]["error_pct"] is None
    assert r["comercio"]["total_negocios"] == 2


@pytest.mark.asyncio
async def test_la_suma_de_haciendas_solo_lleva_a_quien_reporto_el_ultimo_anio(zona_chica, pool_de_una_conexion):
    await zona_chica.execute(
        "INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom) VALUES ('14120', '14', '120', 'Zapopan',"
        " ST_Multi(ST_MakeEnvelope(-103.5, 20.6, -103.4, 20.61, 4326)))")
    filas = [(2024, "039", "Tema", "Total de ingresos", 1000), (2024, "039", "Capítulo", "Impuestos", 400),
             (2023, "120", "Tema", "Total de ingresos", 500), (2023, "120", "Capítulo", "Derechos", 100)]
    for anio, mun, cat, concepto, valor in filas:
        await zona_chica.execute(
            "INSERT INTO fuente_efipem_municipal (anio, cve_ent, cve_mun, tema, categoria, concepto, valor, estatus)"
            " VALUES (%s, '14', %s, 'Ingresos', %s, %s, %s, 'x')", (anio, mun, cat, concepto, valor))
    r = await perfil.perfil(pool_de_una_conexion, zona_comun.validar("mun:14039,14120"))
    h = r["hacienda"]
    assert (h["reportaron"], h["municipios"], h["total_ingresos"], h["propios_pct"]) == (1, 2, 1000, 40)
    assert [(t["nombre"], t["anio"], t["propios_pct"]) for t in h["tabla"]] == [("Guadalajara", 2024, 40),
                                                                               ("Zapopan", 2023, 20)]


@pytest.mark.asyncio
async def test_un_dibujo_demasiado_grande_dice_por_que(zona_chica, pool_de_una_conexion):
    await zona_chica.execute(
        "INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom) VALUES ('14099', '14', '099', 'Enorme',"
        " ST_Multi(ST_MakeEnvelope(-104, 20, -103, 21, 4326)))")
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    try:
        c = TestClient(app)
        # 0.85 por 0.85 grados: unos 8,300 km².
        r = c.get("/perfil_zona", params={"zona": "pol:-103.9,20.1;-103.05,20.1;-103.05,20.95;-103.9,20.95"})
        assert r.status_code == 422 and "km²" in r.json()["detail"]
        assert c.get("/perfil_zona", params={"zona": "mun:abc"}).status_code == 422
        assert c.get("/perfil_zona", params={"zona": "mun:14120"}).status_code == 404
        assert c.get("/perfil_zona").status_code == 422
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------- similares

DENSIDAD = next(v for v in similares.VARIABLES if v.clave == "densidad")
INTERNET = next(v for v in similares.VARIABLES if v.clave == "internet")


def test_la_banda_es_una_fraccion_del_rango_intercuartil():
    b = similares.banda(INTERNET, 50.0, [float(x) for x in range(0, 101)], 0.5)
    assert (b["bajo"], b["alto"]) == (25.0, 75.0)
    assert similares.comparar(INTERNET, 50.0, 75.0, b)[0] == "parecida"
    assert similares.comparar(INTERNET, 50.0, 76.0, b)[0] == "mayor"
    assert similares.comparar(INTERNET, 50.0, 20.0, b)[0] == "menor"
    assert similares.comparar(INTERNET, 50.0, None, b)[0] == "sin_dato"
    # Un porcentaje no pasa de 100 ni baja de 0.
    assert similares.banda(INTERNET, 95.0, [float(x) for x in range(0, 101)], 0.5)["alto"] == 100


def test_la_densidad_se_compara_en_proporcion():
    b = similares.banda(DENSIDAD, 1000.0, [10.0 ** (x / 10) for x in range(0, 41)], 0.5)
    assert b["bajo"] * b["alto"] == pytest.approx(1000.0 ** 2)
    # Lo mismo por arriba que por abajo: el doble y la mitad.
    assert similares.comparar(DENSIDAD, 1000.0, 2000.0, b)[1] == pytest.approx(
        similares.comparar(DENSIDAD, 1000.0, 500.0, b)[1])


def test_sin_dispersion_solo_es_parecido_lo_identico():
    b = similares.banda(INTERNET, 0.0, [0.0] * 30, 0.5)
    assert similares.comparar(INTERNET, 0.0, 0.0, b)[0] == "parecida"
    assert similares.comparar(INTERNET, 0.0, 1.0, b)[0] == "mayor"


def test_con_que_nivel_se_compara_cada_zona():
    nivel = lambda clave: similares.nivel_de(zona_comun.validar(clave))[0]  # noqa: E731
    assert nivel("mun:14039") == "municipio"
    assert nivel("col:14039_0001") == nivel("cp:44100") == nivel("cir:-103.35,20.67,800") == "colonia"
    assert nivel("mun:14039,14120") is nivel("ent:14") is nivel("zm:14.1.01") is None


def test_el_porcentaje_de_un_punado_de_negocios_no_se_da():
    censo = Censo([({"POBTOT": 1000}, 1.0)])
    v = similares.valores(censo, 2.0, {"total": 5, "Comercio al por menor": 5}, [])
    assert v["negocios_mil"] == 5 and v["comercio"] is None
    assert similares.valores(censo, 2.0, None, [])["negocios_mil"] is None
    assert v["densidad"] == 500
    assert "poblacion" not in v  # solo por municipio


async def _tabla(conn, n=40):
    """n municipios con internet de 0 a 100 parejo y la misma escolaridad."""
    for i in range(n):
        valores = {"internet": 100 * i / (n - 1), "escolaridad": 9.0, "automovil": None}
        await conn.execute(
            "INSERT INTO similares_zonas (nivel, clave, nombre, detalle, cve_ent, mun, pobtot, valores)"
            " VALUES ('municipio', %s, %s, 'Jalisco', '14', %s, 5000, %s)",
            (f"mun:14{i:03d}", f"Mun {i}", f"14{i:03d}", json.dumps(valores)))


@pytest.mark.asyncio
async def test_buscar_ordena_por_cuantas_variables_caen_y_da_el_desglose(conn, pool_de_una_conexion):
    await _tabla(conn)
    z = zona_comun.validar("mun:14020")
    r = await similares.buscar(pool_de_una_conexion, z, areas=["vivienda", "poblacion"], margen="muy_cerca")
    assert r["motivo"] is None and r["comparadas"] == 39
    # El más cercano en internet va primero, y la referencia no sale.
    assert {x["nombre"] for x in r["resultados"][:2]} == {"Mun 19", "Mun 21"}
    primero = r["resultados"][0]
    assert (primero["parecidas"], primero["con_dato"]) == (2, 2)
    assert primero["valores"]["internet"]["estado"] == "parecida"
    assert primero["valores"]["automovil"] == {"valor": None, "estado": "sin_dato"}
    # Nada que se parezca a un puntaje sale a la vista.
    assert not {"puntaje", "distancia", "score", "similitud"} & set(primero)
    de = {v["clave"]: v for v in r["variables"]}
    assert de["automovil"]["banda"] is None and de["internet"]["banda"]["comparadas"] == 40
    assert [a["clave"] for a in r["areas"]][:2] == ["poblacion", "vivienda"]


@pytest.mark.asyncio
async def test_buscar_dice_por_que_no_hay(conn, pool_de_una_conexion):
    await _tabla(conn, 5)
    z = zona_comun.validar("mun:14001")
    r = await similares.buscar(pool_de_una_conexion, z, areas=[])
    assert r["resultados"] == [] and "con qué comparar" in r["motivo"]
    r = await similares.buscar(pool_de_una_conexion, zona_comun.validar("ent:14"), areas=[])
    assert "estado" in r["motivo"]
    with pytest.raises(similares.ConsultaInvalida):
        await similares.buscar(pool_de_una_conexion, z, areas=["inventada"])
    with pytest.raises(similares.ConsultaInvalida):
        await similares.buscar(pool_de_una_conexion, z, areas=[], margen="x")


@pytest.mark.asyncio
async def test_cargar_estado_calcula_municipios_y_colonias(zona_chica, pool_de_una_conexion):
    class Pool:
        def connection(self):
            return pool_de_una_conexion.connection()

    r = await similares.cargar_estado(Pool(), "14")
    assert (r["municipios"], r["colonias"], r["colonias_comparables"]) == (1, 1, 1)
    cur = await zona_chica.execute("SELECT nivel, clave, pobtot, valores FROM similares_zonas ORDER BY nivel")
    filas = {f[0]: f for f in await cur.fetchall()}
    assert filas["colonia"][1:3] == ("col:14039_0001", 1250)
    assert filas["colonia"][3]["internet"] == 80
    assert filas["municipio"][3]["poblacion"] == 2500
    assert filas["municipio"][3]["negocios_mil"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_un_dibujo_se_calcula_igual_que_una_colonia_de_la_tabla(zona_chica, pool_de_una_conexion):
    class Pool:
        def connection(self):
            return pool_de_una_conexion.connection()

    await similares.cargar_estado(Pool(), "14")
    cur = await zona_chica.execute("SELECT valores FROM similares_zonas WHERE nivel = 'colonia'")
    (de_tabla,) = await cur.fetchone()
    z = zona_comun.validar("pol:-103.40,20.60;-103.3875,20.60;-103.3875,20.61;-103.40,20.61")
    ref = await similares._referencia(zona_chica, z, "colonia")
    assert ref["pobtot"] == 1250
    for clave in ("internet", "negocios_mil", "densidad"):
        assert ref["valores"][clave] == pytest.approx(de_tabla[clave], rel=1e-3), clave
