import csv
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from mapo_core import iter_downloader as it
from mapo_core.db import get_pool
from mapo_core.server import app

COLUMNAS = ["ENTIDAD", "NOM_ENT", "MUN", "NOM_MUN", "LOC", "NOM_LOC", "LONGITUD", "LATITUD", "ALTITUD", "POBTOT", "TAMLOC"]


def _zip(filas) -> bytes:
    texto = io.StringIO()
    w = csv.writer(texto)
    w.writerow(COLUMNAS)
    w.writerows(filas)
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as z:
        z.writestr(it.CSV, texto.getvalue().encode("utf-8-sig"))
    return salida.getvalue()


def _iter(total_jalisco=3_002):
    return _zip([
        ["00", "Total nacional", "000", "Total nacional", "0000", "Total nacional", "", "", "", "3002", ""],
        ["14", "Jalisco", "000", "Total", "0000", "Total", "", "", "", str(total_jalisco), ""],
        ["14", "Jalisco", "015", "Autlán", "0000", "Total del municipio", "", "", "", "3002", ""],
        ["14", "Jalisco", "015", "Autlán", "0001", "Autlán", "104°21'55.0\" W", "19°46'17.0\" N", "900", "3000", "5"],
        ["14", "Jalisco", "015", "Autlán", "0042", "Rancho", "104°20'00.0\" W", "19°46'17.0\" N", "910", "2", "1"],
        # Resumen de las localidades de dos viviendas: ya vienen una por una.
        ["14", "Jalisco", "015", "Autlán", "9999", "Localidades de dos viviendas", "", "", "", "2", ""],
    ])


def test_a_grados():
    assert it.a_grados("102°17'45.768\" W") == pytest.approx(-102.2960467, abs=1e-6)
    assert it.a_grados("21°52'47.362\" N") == pytest.approx(21.8798228, abs=1e-6)
    assert it.a_grados("") is None


def test_leer_cuadra_sin_contar_dos_veces_los_resumenes():
    localidades, cuadres = it.leer(_iter())
    assert [l["cvegeo"] for l in localidades] == ["140150001", "140150042"]
    assert [l["ambito"] for l in localidades] == ["urbana", "rural"]
    assert cuadres == {"14": (3_002, 3_002)}
    assert localidades[0]["datos"]["NOM_MUN"] == "Autlán"


async def test_si_no_cuadra_no_guarda_nada():
    with pytest.raises(it.ArchivoInvalido, match="no cuadra"):
        await it.descargar(_iter(total_jalisco=9_999))


@pytest.fixture
def cliente(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    yield TestClient(app)
    app.dependency_overrides.clear()


async def _localidad(conn, cvegeo, nombre, ambito, pob, lon, lat):
    await conn.execute(
        """INSERT INTO localidades (cvegeo, cve_ent, cve_mun, cve_loc, nombre, nom_mun, ambito, pobtot, datos, geom)
           VALUES (%s, '14', '015', %s, %s, 'Autlán', %s, %s, '{}', ST_SetSRID(ST_MakePoint(%s, %s), 4326))""",
        (cvegeo, cvegeo[-4:], nombre, ambito, pob, lon, lat),
    )


async def test_endpoint_distancia_a_localidades(conn, cliente):
    await conn.execute("DELETE FROM localidades")
    # A 20° de latitud, 0.001° de longitud son unos 105 m.
    await _localidad(conn, "140150042", "Rancho", "rural", 12, -104.0 + 0.002, 20.0)
    await _localidad(conn, "140150043", "Otro rancho", "rural", 30, -104.0 + 0.004, 20.0)
    await _localidad(conn, "140150001", "Pueblo", "urbana", 3_000, -104.0 + 0.001, 20.0)
    punto = {"type": "Point", "coordinates": [-104.0, 20.0]}

    r = cliente.post("/localidades/distancia", json={"filas": [{"id": 7, "geometria": punto}]}).json()
    assert r["localidades"] == 3
    assert r["filas"] == [
        {"id": 7, "metros": 105, "cvegeo": "140150001", "nombre": "Pueblo", "nom_mun": "Autlán",
         "ambito": "urbana", "pobtot": 3_000, "cuantos": None, "poblacion": None}
    ]

    r = cliente.post(
        "/localidades/distancia",
        json={"filas": [{"id": 7, "geometria": punto}], "radio": 300, "ambito": "rural"},
    ).json()
    assert r["localidades"] == 2
    [fila] = r["filas"]
    assert (fila["nombre"], fila["metros"], fila["cuantos"], fila["poblacion"]) == ("Rancho", 209, 1, 12)


def test_endpoint_rechaza_lo_que_no_es_geometria(cliente):
    assert cliente.post("/localidades/distancia", json={"filas": []}).status_code == 422
    malo = {"filas": [{"id": 1, "geometria": {"type": "Nada"}}]}
    assert cliente.post("/localidades/distancia", json=malo).status_code == 422
