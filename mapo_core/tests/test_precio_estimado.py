import json

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from mapo_core import precio_estimado
from mapo_core.db import get_pool
from mapo_core.server import app

ENCABEZADO = "cvegeo,cve_mun,municipio,fuente,valor,rango_bajo,rango_alto,anio_tabla,cobertura,n_base,metodo,version\n"
CSV = ENCABEZADO + (
    "9903900010010,039,Guadalajara,anuncios,2704000.0,,,2024,,9,mediana,v2\n"
    "9903900010025,039,Guadalajara,modelo,,1030000.0,3300000.0,2024,0.819,550,conformal,v2\n"
    "9909800010030,098,Tlaquepaque,sin_base,,,,,,,sin anuncios,v2\n"
)


def test_leer_separa_clave_y_tipos():
    filas = precio_estimado.leer(CSV)
    assert [f["fuente"] for f in filas] == ["anuncios", "modelo", "sin_base"]
    assert filas[0]["cve_ent"] == "99" and filas[0]["cve_mun"] == "039"
    assert filas[0]["n_base"] == 9 and filas[0]["anio_tabla"] == 2024
    assert filas[2]["valor"] is None and filas[2]["anio_tabla"] is None


@pytest.mark.parametrize("fila, error", [
    ("99039000100,039,G,catastro,3080,,,2020,,3,m,v1\n", "Clave de AGEB"),
    ("9903900010010,039,G,mercado,3080,,,2020,,3,m,v1\n", "Fuente desconocida"),
    ("9903900010010,039,G,catastro,,,,2020,,3,m,v1\n", "catastro sin valor"),
    ("9903900010010,039,G,anuncios,,,,2024,,9,m,v2\n", "anuncios sin valor"),
    ("9903900010010,039,G,modelo,,4500,2000,2020,0.8,600,m,v1\n", "rango"),
    ("9903900010010,039,G,modelo,,2000,4500,2020,,600,m,v1\n", "cobertura"),
])
def test_leer_rechaza_filas_incoherentes(fila, error):
    with pytest.raises(precio_estimado.ArchivoInvalido, match=error):
        precio_estimado.leer(ENCABEZADO + fila)


def test_leer_exige_columnas():
    with pytest.raises(precio_estimado.ArchivoInvalido, match="Faltan columnas"):
        precio_estimado.leer("cvegeo,valor\n9903900010010,1\n")


@pytest.fixture
def cliente(pool_de_una_conexion):
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_precio_por_ageb_con_rango_y_sin_dato(conn, cliente):
    for cve_mun, nombre in [("039", "Guadalajara"), ("098", "Tlaquepaque")]:
        await conn.execute(
            """INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom)
               VALUES (%(c)s, '99', %(m)s, %(n)s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(g)s), 4326)))""",
            {"c": "99" + cve_mun, "m": cve_mun, "n": nombre, "g": json.dumps(box(0, 0, 3, 1).__geo_interface__)},
        )
    for i, f in enumerate(precio_estimado.leer(CSV)):
        await conn.execute(
            """INSERT INTO agebs (cvegeo, cve_ent, cve_mun, cve_loc, cve_ageb, geom)
               VALUES (%(c)s, '99', %(m)s, '0001', %(a)s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(g)s), 4326)))""",
            {"c": f["cvegeo"], "m": f["cve_mun"], "a": f["cvegeo"][9:],
             # La estimada es más chica que la tolerancia de simplificación.
             "g": json.dumps(box(i, 0, i + (0.0002 if f["fuente"] == "modelo" else 1),
                                 0.0002 if f["fuente"] == "modelo" else 1).__geo_interface__)},
        )
        await conn.execute(
            f"INSERT INTO fuente_precio_estimado ({', '.join(precio_estimado.COLUMNAS)}) "
            f"VALUES ({', '.join('%s' for _ in precio_estimado.COLUMNAS)})",
            [f[c] for c in precio_estimado.COLUMNAS],
        )

    cuerpo = cliente.get("/vivienda/municipios", params={"cve_ent": "99", "indicador": "precio_ageb"}).json()

    assert cuerpo["nivel"] == "AGEB" and "no es precio de cierre" in cuerpo["metodo"]
    p = {f["properties"]["cvegeo"]: f["properties"] for f in cuerpo["features"]}
    assert len(p) == 3  # ninguna AGEB se pierde al simplificar
    assert p["9903900010010"]["valor_choropleth"] == 2704000 and p["9903900010010"]["fuente"] == "anuncios"
    assert p["9903900010010"]["nomgeo"] == "AGEB 0010, Guadalajara"
    # Un rango no se vuelve color; viaja completo para la ventana.
    assert "valor_choropleth" not in p["9903900010025"]
    assert p["9903900010025"]["rango_bajo"] == 1030000 and p["9903900010025"]["cobertura"] == pytest.approx(0.819)
    assert "valor_choropleth" not in p["9909800010030"] and p["9909800010030"]["fuente"] == "sin_base"
    # Sin dato, la ventana dice por qué; con dato, el método largo no viaja.
    assert p["9909800010030"]["metodo"] == "sin anuncios" and "metodo" not in p["9903900010010"]


def test_precio_aparece_en_el_catalogo(cliente):
    claves = [i["clave"] for i in cliente.get("/vivienda/catalogo").json()["indicadores"]]
    assert "precio_ageb" in claves and "suelo_ageb" not in claves
