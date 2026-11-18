import base64
import io
import json
import sqlite3
import struct
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pytest
import rasterio
import shapefile
import shapely
from fastapi.testclient import TestClient
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from mapo_core import datos_geo as dg
from mapo_core import datos_propios as dp
from mapo_core.db import get_pool
from mapo_core.server import app

GDL = box(-103.4, 20.6, -103.3, 20.7)
# Guadalajara en la Lambert de INEGI (EPSG:6372), en metros.
X_6372, Y_6372 = 2373000, 945000


def _coleccion(*features, **extra):
    return json.dumps({"type": "FeatureCollection", "features": list(features), **extra}).encode()


def _feature(geometria, **propiedades):
    return {"type": "Feature", "properties": propiedades, "geometry": geometria.__geo_interface__}


def _shp(geometrias, prj: str | None = "WGS84", cpg: str | None = None, extras=(), encoding="latin-1") -> bytes:
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    with shapefile.Writer(shp=shp, shx=shx, dbf=dbf, encoding=encoding) as w:
        w.field("NOMBRE", "C")
        w.field("VENTAS", "N")
        for i, g in enumerate(geometrias):
            w.point(g.x, g.y) if g.geom_type == "Point" else w.shape(g.__geo_interface__)
            w.record("Añil", i)
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as z:
        z.writestr("capa.shp", shp.getvalue())
        z.writestr("capa.shx", shx.getvalue())
        z.writestr("capa.dbf", dbf.getvalue())
        if prj == "WGS84":
            z.writestr("capa.prj", rasterio.crs.CRS.from_epsg(4326).to_wkt())
        elif prj:
            z.writestr("capa.prj", prj)
        if cpg:
            z.writestr("capa.cpg", cpg)
        for nombre, datos in extras:
            z.writestr(nombre, datos)
    return salida.getvalue()


def _gpkg(geometrias, srs=4326, definicion=None, tablas=("capa",), vista=False) -> bytes:
    """GeoPackage mínimo, con encabezado y sobre de 32 bytes como el de QGIS."""
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "x.gpkg"
        c = sqlite3.connect(ruta)
        c.execute("CREATE TABLE gpkg_contents (table_name TEXT, data_type TEXT, srs_id INTEGER)")
        c.execute("CREATE TABLE gpkg_geometry_columns (table_name TEXT, column_name TEXT)")
        c.execute("CREATE TABLE gpkg_spatial_ref_sys (srs_id INTEGER, definition TEXT)")
        wkt = definicion or rasterio.crs.CRS.from_epsg(srs).to_wkt()
        c.execute("INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?)", (srs, wkt))
        for t in tablas:
            c.execute(f'CREATE TABLE "{t}" (fid INTEGER PRIMARY KEY, geom BLOB, nombre TEXT, ventas REAL)')
            c.execute("INSERT INTO gpkg_contents VALUES (?, 'features', ?)", (t, srs))
            c.execute("INSERT INTO gpkg_geometry_columns VALUES (?, 'geom')", (t,))
            for i, g in enumerate(geometrias):
                sobre = struct.pack("<4d", *g.bounds)
                blob = b"GP\x00\x03" + struct.pack("<i", srs) + sobre + shapely.to_wkb(g)
                c.execute(f'INSERT INTO "{t}" (geom, nombre, ventas) VALUES (?, ?, ?)', (blob, f"f{i}", i * 1.5))
        if vista:
            c.execute("INSERT INTO gpkg_contents VALUES ('v', 'features', 4326)")
            c.execute("INSERT INTO gpkg_geometry_columns VALUES ('v', 'geom')")
            c.execute("CREATE VIEW v AS SELECT 1 AS geom")
        c.commit()
        c.close()
        return ruta.read_bytes()


def _tiff(datos, crs="EPSG:4326", oeste=-104.0, norte=21.0, paso=0.01, nodata=None) -> bytes:
    datos = np.atleast_3d(datos).transpose(2, 0, 1) if datos.ndim == 2 else datos
    with rasterio.MemoryFile() as memoria:
        with memoria.open(
            driver="GTiff",
            width=datos.shape[2],
            height=datos.shape[1],
            count=datos.shape[0],
            dtype=datos.dtype,
            crs=crs,
            nodata=nodata,
            transform=from_origin(oeste, norte, paso, paso),
        ) as t:
            t.write(datos)
        return memoria.read()


def test_geojson_con_atributos_y_geometria():
    tabla = dg.leer(_coleccion(_feature(GDL, nombre="a", ventas=5), _feature(GDL, nombre="b")), "geojson")
    assert tabla.columnas == ["nombre", "ventas"]
    assert tabla.filas == [["a", "5"], ["b", ""]]
    r = dg.ubicar_vector(tabla)
    assert r["tipo"] == "vector"
    assert r["numericas"] == ["ventas"]
    assert r["filas"][1]["datos"]["ventas"] is None
    assert r["filas"][0]["geometria"]["type"] == "Polygon"


def test_geojson_solo_de_puntos_es_una_capa_de_puntos():
    r = dg.ubicar_vector(dg.leer(_coleccion(_feature(Point(-103.3, 20.6), n=1)), "geojson"))
    assert r["tipo"] == "puntos"
    assert (r["filas"][0]["lat"], r["filas"][0]["lon"]) == (20.6, -103.3)


def test_geojson_declara_otra_proyeccion_como_las_capas_de_inegi():
    crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::6372"}}
    tabla = dg.leer(_coleccion(_feature(Point(X_6372, Y_6372)), crs=crs), "geojson")
    r = dg.ubicar_vector(tabla)
    assert 19 < r["filas"][0]["lat"] < 22
    assert -105 < r["filas"][0]["lon"] < -101


def test_metros_sin_proyeccion_no_se_dibujan_en_otro_lado():
    r = dg.ubicar_vector(dg.leer(_coleccion(_feature(Point(X_6372, Y_6372))), "geojson"))
    assert r["filas"] == []
    assert r["descartes"]["fuera_de_mexico"] == 1


def test_geometria_vacia_o_rota_cuenta_como_sin_dato():
    rota = {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": "x"}}
    nula = {"type": "Feature", "properties": {}, "geometry": None}
    r = dg.ubicar_vector(dg.leer(_coleccion(_feature(GDL), rota, nula), "geojson"))
    assert len(r["filas"]) == 1
    assert r["descartes"]["sin_dato"] == 2


def test_propiedades_anidadas_son_texto_y_nul_no_pasa():
    tabla = dg.leer(_coleccion(_feature(GDL, a={"b": 1}, c="x\x00y")), "geojson")
    assert tabla.filas == [['{"b": 1}', "xy"]]


def test_geojson_invalido():
    for malo in (b"no", b"[1]", b'{"type":"Otro"}', b'{"type":"FeatureCollection","features":3}', b"[" * 100000):
        with pytest.raises(dp.ArchivoInvalido):
            dg.leer(malo, "geojson")


def test_tope_de_vertices(monkeypatch):
    monkeypatch.setattr(dg, "MAX_VERTICES", 3)
    with pytest.raises(dp.ArchivoInvalido, match="vértices"):
        dg.leer(_coleccion(_feature(GDL)), "geojson")


def test_tope_de_poligonos(monkeypatch):
    monkeypatch.setattr(dp, "MAX_POLIGONOS", 1)
    with pytest.raises(dp.ArchivoInvalido, match="polígonos"):
        dg.ubicar_vector(dg.leer(_coleccion(_feature(GDL), _feature(GDL)), "geojson"))


def test_poligono_invalido_se_repara():
    moño = shapely.Polygon([(-103.4, 20.6), (-103.3, 20.7), (-103.3, 20.6), (-103.4, 20.7)])
    r = dg.ubicar_vector(dg.leer(_coleccion(_feature(moño)), "geojson"))
    assert shapely.is_valid(shapely.geometry.shape(r["filas"][0]["geometria"]))


def test_shapefile_latin1_con_prj():
    tabla = dg.leer(_shp([GDL]), "zip")
    assert tabla.columnas == ["NOMBRE", "VENTAS"]
    assert tabla.filas[0][0] == "Añil"
    assert tabla.geometrias[0].bounds == pytest.approx(GDL.bounds)


def test_shapefile_utf8_sin_cpg():
    # Así vienen los de CONABIO: UTF-8 sin .cpg. El encabezado binario del .dbf
    # no es UTF-8 válido, así que la prueba mira solo los registros.
    archivo = _shp([GDL], encoding="utf-8")
    dbf = zipfile.ZipFile(io.BytesIO(archivo)).read("capa.dbf")
    assert dg._codificacion(None, dbf[:4] + bytes([0x97]) + dbf[5:]) == "utf-8"
    assert dg.leer(archivo, "zip").filas[0][0] == "Añil"


def test_shapefile_en_la_lambert_de_inegi():
    prj = rasterio.crs.CRS.from_epsg(6372).to_wkt()
    r = dg.ubicar_vector(dg.leer(_shp([Point(X_6372, Y_6372)], prj=prj), "zip"))
    assert 19 < r["filas"][0]["lat"] < 22


def test_shapefile_sin_prj_avisa():
    tabla = dg.leer(_shp([GDL], prj=None), "zip")
    assert "no trae .prj" in tabla.avisos[0]


def test_proyeccion_ilegible():
    with pytest.raises(dp.ArchivoInvalido, match="proyección"):
        dg.leer(_shp([GDL], prj="basura"), "zip")


def test_proyeccion_con_url_no_sale_a_la_red():
    """GDAL pide la URL si se le pasa a `from_user_input`: eso sería SSRF."""
    import socket

    with socket.create_server(("127.0.0.1", 0)) as servidor:
        servidor.setblocking(False)
        url = f"http://127.0.0.1:{servidor.getsockname()[1]}/x.prj"
        for archivo, formato in ((_shp([GDL], prj=url), "zip"), (_gpkg([GDL], srs=9999, definicion=url), "gpkg")):
            with pytest.raises(dp.ArchivoInvalido, match="proyección"):
                dg.leer(archivo, formato)
        with pytest.raises(BlockingIOError):
            servidor.accept()


def test_shapefile_incompleto_y_zip_ajeno():
    with pytest.raises(dp.ArchivoInvalido, match="ningún .shp"):
        salida = io.BytesIO()
        with zipfile.ZipFile(salida, "w") as z:
            z.writestr("hola.txt", "x")
        dg.leer(salida.getvalue(), "zip")

    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as z:
        z.writestr("a.shp", b"x")
    with pytest.raises(dp.ArchivoInvalido, match="le falta"):
        dg.leer(salida.getvalue(), "zip")


def test_shapefile_dañado():
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as z:
        for e in ("shp", "shx", "dbf"):
            z.writestr(f"a.{e}", b"basura")
    with pytest.raises(dp.ArchivoInvalido, match="dañado"):
        dg.leer(salida.getvalue(), "zip")


def test_zip_inflado_se_frena_antes_de_leer(monkeypatch):
    monkeypatch.setattr(dp, "MAX_XLSX_DESCOMPRIMIDO", 1024)
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("a.shp", b"\x00" * 1_000_000)
    with pytest.raises(dp.ArchivoInvalido, match="descomprimido"):
        dg.leer(salida.getvalue(), "zip")


def test_ruta_con_puntos_en_el_zip_no_sale_de_memoria():
    # Nada se extrae a disco: el nombre es solo una llave.
    tabla = dg.leer(_shp([GDL], extras=[("../../etc/passwd", b"x")]), "zip")
    assert len(tabla.filas) == 1


def test_geopackage():
    tabla = dg.leer(_gpkg([GDL, GDL]), "gpkg")
    assert tabla.columnas == ["fid", "nombre", "ventas"]
    assert tabla.filas[1] == ["2", "f1", "1.5"]
    assert tabla.geometrias[0].bounds == pytest.approx(GDL.bounds)


def test_geopackage_varias_capas_y_vistas():
    tabla = dg.leer(_gpkg([GDL], tablas=("a", "b"), vista=True), "gpkg")
    assert "2 capas" in tabla.avisos[0]


def test_geopackage_en_lambert():
    r = dg.ubicar_vector(dg.leer(_gpkg([Point(X_6372, Y_6372)], srs=6372), "gpkg"))
    assert 19 < r["filas"][0]["lat"] < 22


def test_geopackage_que_no_lo_es():
    with pytest.raises(dp.ArchivoInvalido):
        dg.leer(b"no soy sqlite" * 100, "gpkg")


def test_sqlite_sin_tablas_de_geopackage():
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "x.db"
        c = sqlite3.connect(ruta)
        c.execute("CREATE TABLE t (a)")
        c.commit()
        c.close()
        with pytest.raises(dp.ArchivoInvalido, match="GeoPackage"):
            dg.leer(ruta.read_bytes(), "gpkg")


def test_raster_quintiles_png_y_nodata():
    datos = np.arange(10_000, dtype="float32").reshape(100, 100)
    datos[0, :] = -9999
    r = dg.ubicar_raster(_tiff(datos, nodata=-9999))["raster"]

    assert r["limites"][0] >= 100
    assert r["limites"][-1] == 9999
    assert r["oeste"] == pytest.approx(-104, abs=0.02)
    assert r["norte"] == pytest.approx(21, abs=0.02)

    with rasterio.MemoryFile(base64.b64decode(r["png"])) as memoria, memoria.open() as png:
        alfa = png.read(4)
    assert alfa[0, 0] == 0
    assert set(np.unique(alfa)) == {0, 30, 66, 107, 153, 204}


def test_raster_en_lambert_cae_en_mexico():
    r = dg.ubicar_raster(_tiff(np.ones((50, 50), "uint8"), crs="EPSG:6372", oeste=X_6372, norte=Y_6372, paso=100))
    assert 19 < r["raster"]["sur"] < 22


def test_raster_grande_se_reduce():
    r = dg.ubicar_raster(_tiff(np.ones((30, 3000), "uint8"), paso=0.001))
    with rasterio.MemoryFile(base64.b64decode(r["raster"]["png"])) as memoria, memoria.open() as png:
        assert max(png.width, png.height) <= dg.MAX_LADO_IMAGEN


def test_raster_sin_proyeccion_fuera_de_mexico_o_vacio():
    with pytest.raises(dp.ArchivoInvalido, match="proyección"):
        dg.leer_raster(_tiff(np.ones((5, 5), "uint8"), crs=None))
    with pytest.raises(dp.ArchivoInvalido, match="fuera de México"):
        dg.ubicar_raster(_tiff(np.ones((5, 5), "uint8"), oeste=2.0, norte=48.0))
    with pytest.raises(dp.ArchivoInvalido, match="ningún valor"):
        dg.ubicar_raster(_tiff(np.zeros((5, 5), "uint8"), nodata=0))


def test_raster_inflado_se_frena_sin_decodificar(monkeypatch):
    monkeypatch.setattr(dg, "MAX_PIXELES", 10)
    with pytest.raises(dp.ArchivoInvalido, match="píxeles"):
        dg.leer_raster(_tiff(np.ones((5, 5), "uint8")))


def test_raster_varias_bandas_avisa():
    r = dg.leer_raster(_tiff(np.ones((3, 5, 5), "uint8")))
    assert "3 bandas" in r["avisos"][0]


def test_otro_formato_disfrazado_de_tiff():
    vrt = b'<VRTDataset rasterXSize="1" rasterYSize="1"><VRTRasterBand dataType="Byte" band="1"/></VRTDataset>'
    with pytest.raises(dp.ArchivoInvalido, match="GeoTIFF"):
        dg.leer_raster(vrt)


@pytest.fixture
def cliente():
    # Vector y ráster no tocan la base, pero /datos/ubicar pide el pool.
    app.dependency_overrides[get_pool] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoints(cliente):
    leido = cliente.post("/datos/leer?formato=geojson", content=_coleccion(_feature(GDL, a=1)))
    assert leido.json()["sugerencia"] == {"tipo": "vector"}

    r = cliente.post("/datos/ubicar?formato=geojson&tipo=vector", content=_coleccion(_feature(GDL, a=1)))
    assert r.json()["tipo"] == "vector"

    tif = _tiff(np.arange(100, dtype="float32").reshape(10, 10))
    assert cliente.post("/datos/leer?formato=tif", content=tif).json()["sugerencia"] == {"tipo": "raster"}
    assert cliente.post("/datos/ubicar?formato=tif&tipo=raster", content=tif).json()["tipo"] == "raster"

    assert cliente.post("/datos/ubicar?formato=csv&tipo=vector", content=b"a\n1\n").status_code == 422


async def _valor(conn, teselas, lon, lat):
    """Lo que PostGIS lee en ese punto de las teselas, como lo leería Mapo."""
    await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis_raster")
    for t in teselas:
        cursor = await conn.execute(
            "SELECT ST_Value(ST_RastFromWKB(%s), ST_SetSRID(ST_MakePoint(%s, %s), 4326))", (t, lon, lat)
        )
        valor = (await cursor.fetchone())[0]
        if valor is not None:
            return valor
    return None


async def test_valores_raster_postgis_lee_cada_pixel(conn):
    datos = np.arange(90_000, dtype="float32").reshape(300, 300)
    datos[0, :] = -9999
    info, teselas = dg.valores_raster(_tiff(datos, nodata=-9999))

    assert info["tipo"] == "float32" and info["nodata"] == -9999
    assert info["reducido"] is None and info["metros_pixel"] == pytest.approx(1105.7, abs=1)
    # 300 x 300 en teselas de 256: cuatro.
    assert len(teselas) == 4
    # Fila 5, columna 7, y una que cae en la segunda tesela de abajo.
    assert await _valor(conn, teselas, -104 + 0.075, 21 - 0.055) == 5 * 300 + 7
    assert await _valor(conn, teselas, -104 + 0.0105 * 100 + 0.0005, 21 - 0.01 * 280 - 0.005) == 280 * 300 + 105
    # El nodata no es valor.
    assert await _valor(conn, teselas, -104 + 0.075, 21 - 0.005) is None


async def test_valores_raster_sin_nodata_conserva_el_cero(conn):
    info, teselas = dg.valores_raster(_tiff(np.zeros((10, 10), "uint8")))
    assert info["tipo"] == "int16" and info["nodata"] == -32768
    assert await _valor(conn, teselas, -103.995, 20.995) == 0


def test_nodata_que_no_cabe_en_la_banda_no_sirve():
    assert not dg._cabe(-9999, "uint8")
    assert not dg._cabe(float("nan"), "float32")
    assert dg._cabe(0, "uint8") and dg._cabe(-9999, "int16")


def test_valores_raster_grande_se_reduce(monkeypatch):
    monkeypatch.setattr(dg, "MAX_PIXELES_VALORES", 2_500)
    info, teselas = dg.valores_raster(_tiff(np.ones((100, 100), "uint8")))
    assert info["reducido"] == 2.0 and info["ancho"] * info["alto"] <= 2_500
    assert len(teselas) == 1


def test_valores_raster_en_lambert_quedan_en_grados():
    info, _ = dg.valores_raster(_tiff(np.ones((50, 50), "uint8"), crs="EPSG:6372", oeste=X_6372, norte=Y_6372, paso=100))
    assert info["metros_pixel"] == pytest.approx(100, rel=0.2)


def test_endpoint_raster_valores(cliente):
    r = cliente.post("/datos/raster_valores", content=_tiff(np.ones((5, 5), "uint8")))
    cuerpo = r.content
    largo = int.from_bytes(cuerpo[:4], "big")
    info = json.loads(cuerpo[4 : 4 + largo])
    resto = cuerpo[4 + largo :]
    tesela = int.from_bytes(resto[:4], "big")
    assert info["ancho"] == 5 and len(resto) == 4 + tesela

    malo = cliente.post("/datos/raster_valores", content=b"no es tiff")
    assert malo.status_code == 422
