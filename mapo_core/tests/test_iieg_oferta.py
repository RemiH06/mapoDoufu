import pytest
import shapefile
from openpyxl import Workbook
from shapely.geometry import box

from mapo_core import iieg_oferta as io

ENCABEZADO = ["Inmueble", "Municipio", "Colonia", "Precio", "Metros cuadrados de terreno",
              "Metros cuadrados de construcción"]


def _xlsx(tmp_path, filas, encabezado=ENCABEZADO, hoja="Venta"):
    libro = Workbook()
    h = libro.active
    h.title = hoja
    h.append(encabezado)
    for f in filas:
        h.append(f)
    ruta = tmp_path / "bd.xlsx"
    libro.save(ruta)
    return ruta


def _shp(tmp_path, colonias):
    ruta = tmp_path / "mapa_venta.shp"
    with shapefile.Writer(str(ruta), shapeType=shapefile.POLYGON, encoding="utf-8") as w:
        w.field("COLONIA", "C", 80)
        w.field("NOMBRE_MUN", "C", 40)
        for nombre, mun, (x0, y0, x1, y1) in colonias:
            w.poly([[(x0, y0), (x0, y1), (x1, y1), (x1, y0), (x0, y0)]])
            w.record(nombre, mun)
    (tmp_path / "mapa_venta.cpg").write_text("UTF-8")
    return ruta


def test_normalizar_iguala_enes_y_acentos():
    assert io.normalizar("Niños Héroes") == io.normalizar("NINOS HEROES") == "NINOS HEROES"
    assert io.normalizar("  Villaseñor (Santa Teresita) ") == "VILLASENOR SANTA TERESITA"
    assert io.normalizar(None) is None


def test_leer_anuncios_quita_duplicados_exactos(tmp_path):
    ruta = _xlsx(tmp_path, [
        ["Casa", "ZAPOPAN", "Niños Héroes", 3_000_000, 200, 150],
        ["Casa", "ZAPOPAN", "Niños Héroes", 3_000_000, 200, 150],  # el mismo anuncio, repetido
        ["Departamento", "GUADALAJARA", None, 2_000_000, None, 5],  # 5 m² no es plausible
        ["Casa", "TONALÁ", "Centro", None, None, None],  # sin precio no cuenta
    ])
    a = io.leer_anuncios(ruta)
    assert len(a) == 2
    assert a[0] == io.Anuncio("120", "NINOS HEROES", "Casa", 3_000_000.0, 150.0)
    assert a[1].cve_mun == "039" and a[1].colonia is None and a[1].m2_construccion is None


def test_leer_anuncios_rechaza_lo_desconocido(tmp_path):
    with pytest.raises(io.ArchivoInvalido, match="hoja Venta"):
        io.leer_anuncios(_xlsx(tmp_path, [], hoja="Renta"))
    with pytest.raises(io.ArchivoInvalido, match="columnas"):
        io.leer_anuncios(_xlsx(tmp_path, [], encabezado=["a", "b", "c", "d", "e", "f"]))
    with pytest.raises(io.ArchivoInvalido, match="municipio desconocido"):
        io.leer_anuncios(_xlsx(tmp_path, [["Casa", "ZAPOTLANEJO", "X", 1, None, None]]))


def test_colonias_homonimas_se_unen(tmp_path):
    c = io.leer_colonias(_shp(tmp_path, [("Centro", "ZAPOPAN", (0, 0, 1, 1)),
                                         ("CENTRO", "ZAPOPAN", (2, 0, 3, 1)),
                                         ("Centro", "TONALA", (5, 5, 6, 6))]))
    assert set(c) == {("120", "CENTRO"), ("101", "CENTRO")}
    assert c[("120", "CENTRO")].area == pytest.approx(2.0)


def test_mediana_ponderada():
    assert io.mediana_ponderada([1, 2, 3], [1, 1, 1]) == 2
    assert io.mediana_ponderada([1, 2, 3], [0.1, 0.1, 5]) == 3


def _fila(cve_mun, x0, y0, x1, y1):
    return {"cve_mun": cve_mun, "_geom": box(x0, y0, x1, y1).wkb}


def test_asignar_reparte_por_area_y_no_cruza_municipios():
    colonias = {("120", "A"): box(0, 0, 2, 1), ("039", "B"): box(0, 0, 2, 1)}
    anuncios = [io.Anuncio("120", "A", "Casa", p, 100.0) for p in (1e6, 2e6, 3e6, 4e6, 5e6, 6e6)]
    anuncios += [io.Anuncio("039", "B", "Casa", 9e9, None)] * 6  # misma forma, otro municipio
    anuncios += [io.Anuncio("120", None, "Casa", 9e9, None)]  # sin colonia: no se ubica
    filas = [_fila("120", 0, 0, 1, 1),  # la mitad de A: 3 anuncios efectivos
             _fila("120", 1.8, 0, 3, 1),  # una décima de A: 0.6, no basta
             _fila("124", 0, 0, 1, 1)]  # municipio que el IIEG no cubre
    io.asignar(filas, anuncios, colonias, "2024-07")
    a, b, c = filas
    assert a["medv_n"] == 3.0 and a["medv"] == 3_000_000 and a["medv_m2"] == 30_000
    assert a["pct_departamentos"] == 0.0 and a["medv_periodo"] == "2024-07"
    assert b["medv"] is None and "menos de 3" in b["medv_metodo"]
    assert c["medv"] is None and c["medv_n"] is None and "no publica" in c["medv_metodo"]


def test_resumen_municipal_usa_tambien_los_sin_colonia():
    anuncios = [io.Anuncio("120", "A", "Casa", 1e6, None), io.Anuncio("120", None, "Casa", 3e6, None)]
    (z,) = io.resumen_municipal(anuncios, "2024-07")
    assert (z["cve_mun"], z["anuncios"], z["anuncios_con_colonia"], z["media"]) == ("120", 2, 1, 2_000_000)
