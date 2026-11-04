import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from shapely.geometry import box

from mapo_core import datos_propios as dp
from mapo_core.db import get_pool
from mapo_core.server import app


def _xlsx(filas, hojas=1) -> bytes:
    libro = Workbook()
    for fila in filas:
        libro.active.append(fila)
    for i in range(hojas - 1):
        libro.create_sheet(f"otra{i}")
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def test_csv_de_excel_en_espanol_con_punto_y_coma_y_cp1252():
    tabla = dp.leer("Tienda;Latitud;Longitud\nAñil;20,67;-103,35\n".encode("cp1252"), "csv")
    assert tabla.columnas == ["Tienda", "Latitud", "Longitud"]
    assert tabla.filas == [["Añil", "20,67", "-103,35"]]


def test_csv_utf8_con_bom_y_utf16():
    assert dp.leer("﻿a,b\n1,2\n".encode("utf-8"), "csv").columnas == ["a", "b"]
    assert dp.leer("a\tb\n1\t2\n".encode("utf-16"), "csv").filas == [["1", "2"]]


def test_binario_disfrazado_de_csv_se_rechaza():
    with pytest.raises(dp.ArchivoInvalido, match="no parece de texto"):
        dp.leer(b"PK\x03\x04\x00\x00\x00", "csv")


def test_nul_en_medio_no_llega_a_jsonb():
    relleno = b"a,b\n" + b"1,2\n" * 3000
    tabla = dp.leer(relleno + b"x\x00y,2\n", "csv")
    assert tabla.filas[-1] == ["xy", "2"]


def test_encabezados_vacios_y_repetidos():
    tabla = dp.leer(b"a,,a\n1,2,3\n", "csv")
    assert tabla.columnas == ["a", "columna 2", "a (2)"]


def test_renglones_cortos_largos_y_vacios():
    tabla = dp.leer(b"a,b\n1\n\n1,2,3\n,,\n", "csv")
    assert tabla.filas == [["1", ""], ["1", "2"]]


def test_tope_de_renglones_no_recorta_en_silencio(monkeypatch):
    monkeypatch.setattr(dp, "MAX_FILAS", 2)
    with pytest.raises(dp.ArchivoInvalido, match="renglones"):
        dp.leer(b"a\n1\n2\n3\n", "csv")


def test_tope_de_columnas():
    with pytest.raises(dp.ArchivoInvalido, match="columnas"):
        dp.leer((",".join(f"c{i}" for i in range(101)) + "\n" + "1\n").encode(), "csv")


def test_celda_larga_se_recorta_y_se_avisa():
    tabla = dp.leer(b"a\n" + b"x" * 600 + b"\n", "csv")
    assert len(tabla.filas[0][0]) == 500
    assert "recortaron" in tabla.avisos[0]


def test_solo_encabezado_y_vacio():
    with pytest.raises(dp.ArchivoInvalido):
        dp.leer(b"a,b\n", "csv")
    with pytest.raises(dp.ArchivoInvalido):
        dp.leer(b"", "csv")


def test_xlsx_conserva_claves_enteras_y_avisa_de_otras_hojas():
    tabla = dp.leer(_xlsx([["clave", "ventas", "nota"], [14120, 10.5, None]], hojas=2), "xlsx")
    assert tabla.filas == [["14120", "10.5", ""]]
    assert "primera hoja" in tabla.avisos[0]


def test_xlsx_roto():
    with pytest.raises(dp.ArchivoInvalido, match="No es un XLSX"):
        dp.leer(b"no soy zip", "xlsx")


def test_zip_que_se_infla_se_frena_antes_de_abrirlo(monkeypatch):
    monkeypatch.setattr(dp, "MAX_XLSX_DESCOMPRIMIDO", 1024 * 1024)
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as paquete:
        paquete.writestr("xl/worksheets/sheet1.xml", b"\x00" * (2 * 1024 * 1024))
    assert len(salida.getvalue()) < 50 * 1024
    with pytest.raises(dp.ArchivoInvalido, match="descomprimido"):
        dp.leer(salida.getvalue(), "xlsx")


def test_muchas_piezas(monkeypatch):
    monkeypatch.setattr(dp, "MAX_XLSX_PIEZAS", 2)
    with pytest.raises(dp.ArchivoInvalido, match="piezas"):
        dp.leer(_xlsx([["a"], [1]]), "xlsx")


def test_entidad_xml_que_se_expande_no_pasa():
    # Billion laughs: con defusedxml, openpyxl rechaza entidades.
    copia = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(_xlsx([["a"], [1]]))) as origen, zipfile.ZipFile(copia, "w") as destino:
        for pieza in origen.infolist():
            datos = origen.read(pieza.filename)
            if pieza.filename == "xl/workbook.xml":
                datos = b'<!DOCTYPE b [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]>' + datos.split(b"?>", 1)[-1]
            destino.writestr(pieza, datos)
    with pytest.raises(dp.ArchivoInvalido):
        dp.leer(copia.getvalue(), "xlsx")


@pytest.mark.parametrize(
    "crudo,esperado",
    [("1,234.5", 1234.5), ("12,5", 12.5), ("$ 80", 80.0), ("-3", -3.0), ("abc", None), ("nan", None), ("inf", None)],
)
def test_numero(crudo, esperado):
    assert dp.numero(crudo) == esperado


@pytest.mark.parametrize(
    "crudo,nivel,esperado",
    [
        ("14120", "municipio", "14120"),
        ("1001", "municipio", "01001"),
        ("14-120", "municipio", "14120"),
        ("123", "municipio", None),
        ("1412000011234", "ageb", "1412000011234"),
        ("141200001123a", "ageb", "141200001123A"),
        ("100100011234", "ageb", "0100100011234"),
        ("1.412E+12", "ageb", None),
    ],
)
def test_clave(crudo, nivel, esperado):
    assert dp.clave(crudo, nivel) == esperado


def test_sugerencias():
    assert dp.sugerir(dp.leer("Latitud,Longitud\n20,-103\n".encode(), "csv")) == {
        "tipo": "puntos",
        "lat": "Latitud",
        "lon": "Longitud",
    }
    assert dp.sugerir(dp.leer(b"cve_mun,ventas\n14120,5\n", "csv")) == {"tipo": "municipio", "clave": "cve_mun"}
    assert dp.sugerir(dp.leer(b"CVEGEO,v\n1412000011234,5\n", "csv")) == {"tipo": "ageb", "clave": "CVEGEO"}
    assert dp.sugerir(dp.leer(b"ventas,otra\n14120,5\n", "csv")) is None


def test_puntos_clasifica_descartes_y_tipa_numeros():
    tabla = dp.leer(
        b'lat,lon,ventas,nombre\n20.6,-103.3,"1,000",a\n,-103,5,b\nx,-103,5,c\n20.6,103.3,5,d\n40,-74,,e\n',
        "csv",
    )
    r = dp.ubicar_puntos(tabla, "lat", "lon")
    assert r["descartes"] == {"sin_dato": 1, "no_es_numero": 1, "fuera_de_mexico": 2}
    assert len(r["filas"]) == 1
    ventas = r["filas"][0]["datos"]["ventas"]
    assert ventas == 1000 and isinstance(ventas, int)
    assert "ventas" in r["numericas"] and "nombre" not in r["numericas"]


def test_coordenada_con_coma_y_tres_decimales_no_son_miles():
    # Salió con DENUE real: 41 de 3,000 renglones caían "fuera de México".
    tabla = dp.leer("lat;lon\n20,671;-103,350\n".encode(), "csv")
    r = dp.ubicar_puntos(tabla, "lat", "lon")
    assert (r["filas"][0]["lat"], r["filas"][0]["lon"]) == (20.671, -103.35)


def test_una_clave_no_es_numero():
    tabla = dp.leer(b"CVEGEO,lote,ventas\n14039,007,5\n14120,008,6\n", "csv")
    assert dp.columnas_numericas(tabla) == ["ventas"]


def test_celda_vacia_es_none_no_cero():
    tabla = dp.leer(b"lat,lon,ventas\n20.6,-103.3,\n21,-103,4\n", "csv")
    assert dp.ubicar_puntos(tabla, "lat", "lon")["filas"][0]["datos"]["ventas"] is None


def test_claves_clasifica_y_cuenta_repetidas():
    tabla = dp.leer(b"cve,v\n14120,1\n14120,2\n1001,3\n99999,4\nabc,5\n,6\n", "csv")
    assert dp.claves_de(tabla, ["cve"], "municipio") == {"14120", "01001", "99999"}
    r = dp.ubicar_claves(tabla, ["cve"], "municipio", {"14120", "01001"})
    assert [f["clave"] for f in r["filas"]] == ["14120", "14120", "01001"]
    assert r["repetidas"] == 1
    assert r["descartes"] == {"sin_dato": 1, "clave_invalida": 1, "clave_desconocida": 1}


def test_tope_de_poligonos(monkeypatch):
    monkeypatch.setattr(dp, "MAX_POLIGONOS", 1)
    with pytest.raises(dp.ArchivoInvalido, match="zonas"):
        dp.claves_de(dp.leer(b"c\n14120\n14121\n", "csv"), ["c"], "municipio")


def test_columna_inexistente():
    with pytest.raises(dp.ArchivoInvalido, match="no tiene la columna"):
        dp.ubicar_puntos(dp.leer(b"a,b\n1,2\n", "csv"), "lat", "b")


def test_clave_partida_como_los_tabulados_de_inegi():
    tabla = dp.leer(b"ENTIDAD,MUN,LOC,AGEB,POBTOT\n1,1,1,18A,5\n14,120,1,1234,6\n14,120,1,,7\n", "csv")
    sugerida = dp.sugerir(tabla)
    assert sugerida == {"tipo": "ageb", "partes": ["ENTIDAD", "MUN", "LOC", "AGEB"]}

    claves = dp.claves_de(tabla, sugerida["partes"], "ageb")
    assert claves == {"010010001018A", "1412000011234"}
    r = dp.ubicar_claves(tabla, sugerida["partes"], "ageb", claves)
    assert len(r["filas"]) == 2
    assert r["descartes"]["sin_dato"] == 1


def test_ageb_de_tabulado_no_se_confunde_con_municipio_de_4_digitos():
    tabla = dp.leer(b"ENTIDAD,MUN,LOC,AGEB,POBTOT\n14,39,1,0026,5\n14,39,1,0030,6\n", "csv")
    assert dp.sugerir(tabla)["tipo"] == "ageb"


def test_municipio_partido_y_nombres_en_lugar_de_claves():
    tabla = dp.leer(b"ent,mun,v\n1,1,5\n", "csv")
    assert dp.sugerir(tabla) == {"tipo": "municipio", "partes": ["ent", "mun"]}
    assert dp.claves_de(tabla, ["ent", "mun"], "municipio") == {"01001"}
    assert dp.sugerir(dp.leer(b"entidad,municipio\n14,Zapopan\n", "csv")) is None


def test_clave_partida_con_columnas_de_mas():
    with pytest.raises(dp.ArchivoInvalido, match="se arma con"):
        dp.claves_de(dp.leer(b"a,b,c\n1,2,3\n", "csv"), ["a", "b", "c"], "municipio")


@pytest.fixture
def cliente(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    yield TestClient(app)
    app.dependency_overrides.clear()


def _municipio(conn, cvegeo):
    return conn.execute(
        """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)
           VALUES (%(c)s, %(e)s, %(m)s, 'X', ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(g)s), 4326)))""",
        {"c": cvegeo, "e": cvegeo[:2], "m": cvegeo[2:], "g": json.dumps(box(0, 0, 1, 1).__geo_interface__)},
    )


@pytest.mark.asyncio
async def test_endpoint_leer(cliente):
    r = cliente.post("/datos/leer?formato=csv", content=b"lat,lon\n20,-103\n")
    assert r.status_code == 200
    assert r.json()["sugerencia"]["tipo"] == "puntos"
    assert r.json()["num_filas"] == 1


@pytest.mark.asyncio
async def test_endpoint_leer_invalido_y_demasiado_grande(cliente, monkeypatch):
    assert cliente.post("/datos/leer?formato=csv", content=b"").status_code == 422
    monkeypatch.setattr(dp, "MAX_BYTES", 3)
    assert cliente.post("/datos/leer?formato=csv", content=b"a\n1\n2").status_code == 413


@pytest.mark.asyncio
async def test_endpoint_ubicar_contra_el_marco(cliente, conn):
    await _municipio(conn, "14120")
    r = cliente.post("/datos/ubicar?formato=csv&tipo=municipio&clave=c", content=b"c,v\n14120,1\n01001,2\n").json()
    assert [f["clave"] for f in r["filas"]] == ["14120"]
    assert r["descartes"]["clave_desconocida"] == 1


@pytest.mark.asyncio
async def test_geo_por_clave_solo_lo_que_existe(cliente, conn):
    await _municipio(conn, "14120")
    r = cliente.post("/geo/por_clave", json={"nivel": "municipio", "claves": ["14120", "01001"]})
    assert [f["properties"]["cvegeo"] for f in r.json()["features"]] == ["14120"]
