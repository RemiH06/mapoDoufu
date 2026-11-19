import datetime as dt

import pytest
from shapely.geometry import GeometryCollection, LineString, Polygon

from mapo_core import ambiental_agua as agua
from mapo_core import ambiental_emisiones as emi
from mapo_core import ambiental_municipal as mun
from mapo_core import crudos as c


def test_numero_no_inventa_el_limite_de_deteccion():
    assert c.numero("<2") is None
    assert c.numero("1,234.5") == 1234.5
    assert c.numero(float("nan")) is None
    assert c.numero(float("inf")) is None
    assert c.numero(True) is None
    assert c.numero(3) == 3.0


def test_a_grados_acepta_decimales_y_grados_minutos_segundos():
    assert c.a_grados("20.5") == 20.5
    assert c.a_grados("20°41'27\"") == pytest.approx(20.690833, abs=1e-6)
    assert c.a_grados("104°21'48.1\" W") == pytest.approx(-104.363361, abs=1e-6)
    assert c.a_grados("-98°55'59\"") == pytest.approx(-98.933056, abs=1e-6)
    assert c.a_grados("sin dato") is None


def test_en_mexico():
    assert c.en_mexico(-103.3, 20.6)
    assert not c.en_mexico(0, 0)
    assert not c.en_mexico(103.3, 20.6)  # longitud sin signo
    assert not c.en_mexico(None, 20.6)


def test_multipoligono_tira_lineas_y_arregla_lo_invalido():
    moño = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
    mp = c.multipoligono(moño)
    assert mp.geom_type == "MultiPolygon" and mp.is_valid and mp.area == pytest.approx(0.5)
    mezcla = GeometryCollection([Polygon([(0, 0), (1, 0), (1, 1)]), LineString([(0, 0), (2, 2)])])
    assert len(c.multipoligono(mezcla).geoms) == 1
    assert c.multipoligono(LineString([(0, 0), (1, 1)])) is None
    assert c.multipoligono(None) is None


def test_ewkb_lleva_srid_4326():
    import shapely

    g = shapely.from_wkb(bytes.fromhex(c.punto_ewkb(-103.3, 20.6)))
    assert shapely.get_srid(g) == 4326


def test_parametros_renameca_empareja_medicion_y_calificacion():
    encabezado = ["CLAVE SITIO", "LATITUD", "AÑO", "DBO_mg/L", "CALIDAD_DBO", "SDT_mg/L", "CALIDAD_SDT_ra",
                  "CALIDAD_SDT_salin", "E_COLI_NMP_100mL", "CALIDAD_E_COLI", "SEMÁFORO"]
    fila = ("X1", 20.1, "2012-2025", "<2", "Excelente", 450, "Excelente para riego", "Potable - Dulce",
            None, None, "VERDE")
    p = agua.parametros(encabezado, fila)
    assert p["DBO_mg/L"] == {"valor": "<2", "calidad": "Excelente"}
    assert p["SDT_mg/L"] == {"valor": 450, "calidad": "Excelente para riego", "calidad_2": "Potable - Dulce"}
    assert "E_COLI_NMP_100mL" not in p  # no se midió: no se inventa
    assert "SEMÁFORO" not in p and "LATITUD" not in p


def test_dms_del_repda():
    assert agua._dms("19", "47", "9.5850") == pytest.approx(19.785996, abs=1e-6)
    assert agua._dms("", "1", "2") is None


def test_unidades_del_retc_a_kg():
    assert emi.a_kg("ton/año") == 1000
    assert emi.a_kg("kg/año") == 1
    assert emi.a_kg("Kg") == 1
    assert emi.a_kg("g") == 0.001
    with pytest.raises(ValueError):
        emi.a_kg("litros")


def test_encabezado_del_retc_salta_titulos_y_renglon_de_grupos():
    filas = [
        (None, None, "Dirección General"),
        ("Datos generales", None, "Sustancias"),
        ("NRA", "Nombre", "Descripción", "Unidad", "Aire"),
        ("AB1", "TALLER", "Plomo", "ton/año", 0.002),
        *[(None,)] * 3,
        ("AB2", "OTRO", "Mercurio", "kg/año", 1),
    ]
    renglones = list(emi._tabla(iter(filas), "NRA"))
    assert [f[0] for _, f in renglones] == ["AB1", "AB2"]
    assert renglones[0][0][:2] == ["NRA", "NOMBRE"]


class _Hoja:
    def __init__(self, filas):
        self.filas = filas

    def iter_rows(self, values_only=True):
        return iter(self.filas)


def test_emisiones_convierten_a_kg_y_suman_transferencias():
    hoja = _Hoja([
        ("NRA", "Nombre", "Descripción", "No. CAS", "Unidad", "Aire", "Agua", "Suelo", "Reuso", "Otros"),
        ("AB1", "X", "Plomo", "7439-92-1", "ton/año", 0.002, None, "", 1, 0),
    ])
    (fila,) = list(emi.emisiones(2004, hoja))
    assert fila[:4] == [2004, "AB1", "Plomo", "7439-92-1"]
    assert fila[4] == pytest.approx(2.0) and fila[5] is None and fila[6] is None
    assert fila[7] == '{"reutilizacion": 1000.0}'


def test_establecimientos_del_retc_sin_nombre_y_con_longitud_oeste():
    hoja = _Hoja([
        ("NRA", "NOMBRE", "SCIAN", "DESCRIPCIÓN SCIAN", "SECTOR", "SUBSECTOR", "LATITUD NORTE", "LONGITUD \nOESTE",
         "ESTADO", "MUNICIPIO"),
        ("AB1", "JUANA PÉREZ, GRANJA", 112211, "Porcinos", "Alimenticio", "Matanza", "20°41'27\"", "103°20'57\"",
         "Jalisco", "Guadalajara"),
        ("AB1", "repetido", 1, "", "", "", 1, 1, "", ""),
    ])
    (fila,) = list(emi.establecimientos(2022, hoja))
    assert fila[:7] == [2022, "AB1", "112211", "Porcinos", "Alimenticio", "Jalisco", "Guadalajara"]
    assert "JUANA" not in str(fila)
    import shapely

    p = shapely.from_wkb(bytes.fromhex(fila[7]))
    assert p.x == pytest.approx(-103.349167, abs=1e-5) and p.y > 20


def test_siap_suma_cader_y_tolera_la_columna_renombrada(tmp_path):
    carpeta = tmp_path / "agricultura"
    carpeta.mkdir()
    enc = "Anio,Idestado,Idmunicipio,Nomcicloproductivo,Nommodalidad,Nomunidad,{},Sembrada,Cosechada,Siniestrada,Volumenproduccion,Valorproduccion\n"
    (carpeta / "siap_municipal_2016.csv").write_bytes(
        (enc.format("Nomcultivo Sin Um") + "2016,14,15,Primavera-Verano,Temporal,Tonelada,Maíz grano,10,9,1,30,100\n"
         "2016,14,15,Primavera-Verano,Temporal,Tonelada,Maíz grano,5,5,0,20,50\n").encode("latin-1"))
    (carpeta / "siap_municipal_2024.csv").write_text(
        enc.format("Nomcultivo") + "2024,1,1,Perennes,Riego,Tonelada,Agave,2,2,0,7,9\n", encoding="utf-8")
    filas = {tuple(f[:7]): f[7:] for f in mun.leer_siap(tmp_path)}
    assert filas[(2016, "14", "015", "Primavera-Verano", "Temporal", "Maíz grano", "Tonelada")] == [15, 14, 1, 50, 150]
    assert (2024, "01", "001", "Perennes", "Riego", "Agave", "Tonelada") in filas


def test_sequia_vacio_es_sin_anomalia_y_rechaza_lo_desconocido(tmp_path, monkeypatch):
    (tmp_path / "riesgo").mkdir()
    (tmp_path / "riesgo" / "sequia_municipios.xlsx").write_bytes(b"")
    filas = [("CVE_CONCATENADA", "CVE_ENT", dt.datetime(2024, 4, 30), dt.datetime(2024, 5, 15)),
             ("14015", "14", "D2", None)]
    monkeypatch.setattr(c, "xlsx_filas", lambda *a: iter(filas))
    assert list(mun.leer_sequia(tmp_path)) == [["14", "015", dt.date(2024, 4, 30), "D2"],
                                               ["14", "015", dt.date(2024, 5, 15), "sin"]]
    filas[1] = ("14015", "14", "D7", None)
    with pytest.raises(ValueError):
        list(mun.leer_sequia(tmp_path))


def test_crudo_faltante_dice_que_bajar(tmp_path):
    with pytest.raises(c.CrudoFaltante, match="crudos-ambientales.sh"):
        c.ruta(tmp_path, "agua/no-esta.xlsx")
