import io
import json
import zipfile

import pytest
import shapefile
from fastapi.testclient import TestClient

from mapo_core import consultas
from mapo_core import zona as z
from mapo_core.db import get_pool
from mapo_core.server import app

PAPELERIA = "Comercio al por menor de artículos de papelería"


def test_validar_cada_tipo_y_regresar_la_misma_clave():
    casos = {
        "ent:14": {"tipo": "estado", "cve_ent": "14"},
        "mun:14039,14120": {"tipo": "municipios", "cvegeos": ["14039", "14120"]},
        "zm:14.1.01": {"tipo": "metropoli", "clave": "14.1.01"},
        "cp:09700": {"tipo": "cp", "cp": "09700"},
        "col:14098_0135": {"tipo": "colonia", "cve_col": "14098_0135"},
        "cir:-103.35,20.67,2500": {"tipo": "circulo", "lon": -103.35, "lat": 20.67, "radio_m": 2500},
    }
    for clave, esperado in casos.items():
        assert z.validar(clave) == esperado
        assert z.clave(z.validar(clave)) == clave
    pol = z.validar("pol:-103.4,20.66;-103.33,20.66;-103.33,20.7;-103.4,20.7;-103.4,20.66")
    # El anillo cerrado se guarda abierto, y la clave no repite el primero.
    assert pol["vertices"] == [(-103.4, 20.66), (-103.33, 20.66), (-103.33, 20.7), (-103.4, 20.7)]
    assert z.clave(pol) == "pol:-103.4,20.66;-103.33,20.66;-103.33,20.7;-103.4,20.7"


def test_municipios_repetidos_cuentan_una_vez():
    assert z.validar("mun:14039,14039,14120")["cvegeos"] == ["14039", "14120"]


@pytest.mark.parametrize("clave", [
    None, 14, "", "14039", "xyz:1", "ent:33", "ent:1", "mun:", "mun:1403", "mun:14039;DROP", "zm:14.4.01",
    "cp:4561", "col:14098", "cir:-103.35,20.67", "cir:-103.35,20.67,50", "cir:-103.35,20.67,30000",
    "cir:2.35,48.85,1000", "cir:nan,20.67,1000", "cir:-103.35,inf,1000",
    "pol:-103.4,20.66;-103.33,20.66",                          # dos vértices
    "pol:-103.4,20.6;-103.3,20.7;-103.4,20.7;-103.3,20.6",     # moño: se cruza
    "pol:-103.4,20.6;-103.4,20.6;-103.4,20.6",                 # sin área
    "pol:-110,20;-100,20;-100,25;-110,25",                     # más de 10 mil km²
    "pol:-103.4,20.6,1;-103.3,20.6;-103.3,20.7",               # vértice de tres números
    "mun:" + ",".join(f"14{i:03d}" for i in range(101)),       # más de 100 municipios
])
def test_validar_rechaza(clave):
    with pytest.raises(z.ZonaInvalida):
        z.validar(clave)


def test_demasiado_grande():
    assert z.demasiado_grande(z.MAX_KM2_CONSULTA) is None
    assert "km²" in z.demasiado_grande(78_601)


def test_metropolis_del_paquete_son_las_92_del_documento():
    metros = z.leer_metropolis()
    assert len(metros) == 92
    por_tipo = {t: sum(m["tipo"] == t for m in metros) for t in z.TIPOS_METROPOLI.values()}
    assert por_tipo == {"Zona metropolitana": 48, "Metrópoli municipal": 22, "Zona conurbada": 22}
    zmg = next(m for m in metros if m["clave"] == "14.1.01")
    assert sorted(zmg["cvegeos"]) == ["14039", "14051", "14070", "14097", "14098", "14101", "14120"]
    # La que faltaba al sacar los cuadros del PDF.
    assert next(m for m in metros if m["clave"] == "03.2.02")["cvegeos"] == ["03008"]


def _cuadro(lon, lat, lado):
    return json.dumps({"type": "Polygon", "coordinates": [[
        [lon, lat], [lon + lado, lat], [lon + lado, lat + lado], [lon, lat + lado], [lon, lat]]]})


async def _base(conn):
    await conn.execute("INSERT INTO entidades (cve_ent, nombre, geom) VALUES ('14', 'Jalisco',"
                       " ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))", (_cuadro(-104, 20, 1),))
    for cvegeo, nombre, lon in (("14039", "Guadalajara", -103.4), ("14120", "Zapopan", -103.3)):
        await conn.execute(
            "INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, pob_total, geom) VALUES (%s, '14', %s, %s, 1,"
            " ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))", (cvegeo, cvegeo[2:], nombre, _cuadro(lon, 20.6, 0.1)))
    await conn.execute("INSERT INTO metropolis (clave, nombre, tipo, cvegeos) VALUES"
                       " ('14.1.01', 'Zona metropolitana de Guadalajara', 'Zona metropolitana', '{14039,14120,14070}')")
    await conn.execute(
        "INSERT INTO colonias (cve_col, nombre, nombre_norm, cve_ent, cve_mun, nom_mun, clasif, pobtot, geom)"
        " VALUES ('14039_0001', 'López Cotilla', 'lopez cotilla', '14', '039', 'Guadalajara', 'Colonia', 100,"
        " ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))", (_cuadro(-103.38, 20.62, 0.01),))


@pytest.mark.asyncio
async def test_resolver_cada_tipo(conn):
    await _base(conn)
    dos = await z.resolver(conn, z.validar("mun:14039,14120"))
    assert dos["nombre"] == "Guadalajara y Zapopan" and dos["estados"] == ["14"] and dos["faltan"] == []
    assert 230 < dos["km2"] < 250  # dos cuadros de 0.1° en el paralelo 20.6

    zm = await z.resolver(conn, z.validar("zm:14.1.01"))
    assert zm["nombre"] == "Zona metropolitana de Guadalajara" and zm["fuente"] == z.FUENTE_METROPOLIS
    assert zm["faltan"] == ["14070"] and "no están cargados" in zm["aviso"]

    col = await z.resolver(conn, z.validar("col:14039_0001"))
    assert col["nombre"] == "López Cotilla" and col["detalle"] == "Colonia · Guadalajara, Jalisco"
    assert [m["cvegeo"] for m in col["municipios"]] == ["14039"]

    # Un polígono que toca los dos municipios, y otro que apenas toca uno (menos de 5 % del área).
    pol = await z.resolver(conn, z.validar("pol:-103.35,20.62;-103.2001,20.62;-103.2001,20.65;-103.35,20.65"))
    assert [m["cvegeo"] for m in pol["municipios"]] == ["14039", "14120"]
    roza = await z.resolver(conn, z.validar("pol:-103.304,20.62;-103.2,20.62;-103.2,20.65;-103.304,20.65"))
    assert [m["cvegeo"] for m in roza["municipios"]] == ["14120"]

    assert await z.resolver(conn, z.validar("mun:99999")) is None
    assert await z.resolver(conn, z.validar("cp:44160")) is None


@pytest.mark.asyncio
async def test_buscar(conn):
    await _base(conn)
    r = (await z.buscar(conn, "guadal"))["resultados"]
    assert [x["clave"] for x in r] == ["zm:14.1.01", "mun:14039"]
    r = (await z.buscar(conn, "LÓPEZ cot"))["resultados"]
    assert [(x["clave"], x["detalle"]) for x in r] == [("col:14039_0001", "Colonia · Guadalajara, Jalisco")]
    # Sin CP de SEPOMEX cargados, cinco dígitos lo dicen en vez de no dar nada.
    assert (await z.buscar(conn, "44160")) == {"resultados": [], "aviso": z.SIN_CP}
    assert (await z.buscar(conn, "j")) == {"resultados": [], "aviso": None}


def _zip_cp(registros, prj=None) -> bytes:
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    w.field("d_cp", "C", 5)
    for cp, (lon, lat) in registros:
        w.poly([[[lon, lat], [lon, lat + 0.01], [lon + 0.01, lat + 0.01], [lon + 0.01, lat], [lon, lat]]])
        w.record(cp)
    w.close()
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as zz:
        zz.writestr("CP_14.shp", shp.getvalue())
        zz.writestr("CP_14.shx", shx.getvalue())
        zz.writestr("CP_14.dbf", dbf.getvalue())
        zz.writestr("CP_14.prj", prj or 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984"]]')
    return salida.getvalue()


@pytest.mark.asyncio
async def test_codigos_postales_de_sepomex_y_su_prueba_con_denue(conn, pool_de_una_conexion, tmp_path):
    await _base(conn)
    ruta = tmp_path / "CP_14.zip"
    # 44160 en dos pedazos (se unen) y un CP de la Ciudad de México sin su cero.
    ruta.write_bytes(_zip_cp([("44160", (-103.39, 20.61)), ("44160", (-103.38, 20.61)), ("9700", (-103.36, 20.61))]))
    await conn.execute(
        "INSERT INTO fuente_denue_negocios (id, nombre, clase_actividad, lat, lon, cve_ent, cve_mun, codigo_postal)"
        " VALUES ('a', 'dentro', 'x', 20.615, -103.385, '14', '039', '44160'),"
        "        ('b', 'fuera de su CP', 'x', 20.615, -103.355, '14', '039', '44160')")
    resumen = await z.cargar_codigos_postales(pool_de_una_conexion, ruta)
    assert resumen["poligonos"] == 3 and resumen["cps"] == 2
    assert (resumen["denue_negocios"], resumen["denue_en_su_cp"], resumen["denue_parte"]) == (2, 1, 0.5)
    cp = await z.resolver(conn, z.validar("cp:44160"))
    assert cp["fuente"] == z.FUENTE_CP and 2.2 < cp["km2"] < 2.4  # dos cuadros de 0.01°
    assert (await z.buscar(conn, "09700"))["resultados"][0]["clave"] == "cp:09700"

    otro = tmp_path / "CP_14b.zip"
    otro.write_bytes(_zip_cp([("44160", (-103.39, 20.61))], prj='PROJCS["UTM_13N",GEOGCS["x"]]'))
    with pytest.raises(z.ZonaInvalida, match="proyección"):
        await z.cargar_codigos_postales(pool_de_una_conexion, otro)


@pytest.mark.asyncio
async def test_endpoints(conn, pool_de_una_conexion):
    await _base(conn)
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    try:
        c = TestClient(app)
        assert c.get("/zona/buscar", params={"q": "zapo"}).json()["resultados"][0]["clave"] == "mun:14120"
        ok = c.get("/zona/resolver", params={"clave": "mun:14120"})
        malo = c.get("/zona/resolver", params={"clave": "mun:1412"})
        nada = c.get("/zona/resolver", params={"clave": "col:14039_9999"})
    finally:
        app.dependency_overrides.clear()
    assert ok.status_code == 200 and ok.json()["geojson"]["type"] in ("Polygon", "MultiPolygon")
    assert malo.status_code == 422
    assert nada.status_code == 404


@pytest.mark.asyncio
async def test_voronoi_cuenta_la_competencia_del_otro_lado_del_limite(conn, pool_de_una_conexion):
    await _base(conn)
    # Tres farmacias en Guadalajara, lejos del límite con Zapopan (-103.3), y una en
    # Zapopan pegada a él: antes no contaba y la de Guadalajara se quedaba con el borde.
    for i, (lat, lon) in enumerate(((20.62, -103.39), (20.68, -103.39), (20.65, -103.36), (20.65, -103.299))):
        await conn.execute(
            "INSERT INTO fuente_denue_negocios (id, nombre, clase_actividad, lat, lon, cve_ent, cve_mun)"
            " VALUES (%s, %s, %s, %s, %s, '14', %s)",
            (f"n{i}", f"n{i}", PAPELERIA, lat, lon, "120" if i == 3 else "039"))
    puntos, sin_denue = await consultas.negocios_de_zona(pool_de_una_conexion, z.validar("mun:14039"),
                                                        patron="papeler")
    assert sorted((p.id, p.fuera) for p in puntos) == [("n0", False), ("n1", False), ("n2", False), ("n3", True)]
    assert sin_denue == []

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    try:
        r = TestClient(app).get("/voronoi/denue", params={"zona": "mun:14039", "clase_actividad": "papelería"})
    finally:
        app.dependency_overrides.clear()
    datos = r.json()
    assert r.status_code == 200, datos
    assert (datos["num_negocios"], datos["num_fuera"]) == (3, 1)
    fuera = [f for f in datos["celdas"]["features"] if f["properties"]["fuera"]]
    # La de Zapopan se queda con una franja de Guadalajara junto al límite.
    assert [f["properties"]["id"] for f in fuera] == ["n3"]
