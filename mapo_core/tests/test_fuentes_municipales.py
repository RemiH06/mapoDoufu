"""Sesión 28: Censos Económicos 2024, EFIPEM, rezago social por AGEB de CONEVAL y los
instrumentos de planeación del CNGMD 2025, con archivos chicos armados aquí con la
forma de los de INEGI y CONEVAL, y lo que llega a /perfil_zona."""

import io
import zipfile

import openpyxl
import pytest
from fastapi.testclient import TestClient

from mapo_core import censos_economicos as ce
from mapo_core import cngmd, efipem, rezago_social
from mapo_core.db import get_pool
from mapo_core.server import app

COLUMNAS_CE = ["E03", "E04", "SECTOR", "SUBSECTOR", "RAMA", "SUBRAMA", "CLASE", "ID_ESTRATO", "CODIGO",
               "UE", "H001A", "J000A", "M000A", "A111A", "A131A"]


def _zip(ruta, archivos: dict[str, str]):
    with zipfile.ZipFile(ruta, "w") as z:
        for nombre, texto in archivos.items():
            z.writestr(nombre, texto)
    return ruta


def _ce(ruta, municipios_ue=(80, 20), estado_ue=100):
    renglones = [",".join(COLUMNAS_CE)]
    renglones.append(f"14,,,,,,,,TOTAL DE SECTOR,{estado_ue},1000,10,100,90,50")
    for i, ue in enumerate(municipios_ue, start=1):
        mun = f"{i:03d}"
        renglones += [
            f"14,{mun},,,,,,,TOTAL DE SECTOR,{ue},{ue * 10},1,10,9,5",
            f"14,{mun},,,,,,1,TOTAL DE SECTOR,{ue - 1},5,0.5,5,4,2",  # estrato: fuera
            f"14,{mun},46 ,,,,,,46 ,{ue // 2},{ue * 6},0.6,6,5,3",
            f"14,{mun},31-33,,,,,,31-33,1,,,,,",  # reservado
            f"14,{mun},46 ,461,,,,,461,3,30,0.1,1,1,1",  # subsector: fuera
        ]
    catalogo = ("CODIGO,DESC_CODIGO,CLASIFICADOR_CODIGO,\n46,Comercio al por menor,Sector,\n"
                "31-33,Industrias manufactureras,Sector,\n461,Abarrotes,Subsector,\n")
    return _zip(ruta, {"conjunto_de_datos/tr_ce_jal_2024.csv": "\n".join(renglones) + "\n",
                       "catalogos/tc_codigo_actividad.csv": catalogo})


def test_censos_economicos_solo_sector_y_reservado_como_null(tmp_path):
    filas, estado = ce.leer(_ce(tmp_path / "ce.zip"), "14")
    assert estado["ue"] == 100
    uno = {f["sector"]: f for f in filas if f["cve_mun"] == "001"}
    assert set(uno) == {"total", "46", "31-33"}
    assert (uno["total"]["ue"], uno["total"]["personal"], uno["46"]["nombre"]) == (80, 800, "Comercio al por menor")
    assert uno["31-33"]["personal"] is None and uno["31-33"]["nombre"] == "Industrias manufactureras"


def test_censos_economicos_rechaza_si_los_municipios_no_suman_el_estado(tmp_path):
    with pytest.raises(ce.ArchivoInvalido, match="suman"):
        ce.leer(_ce(tmp_path / "ce.zip", estado_ue=999), "14")


EFIPEM_CSV = """PROD_EST,COBERTURA,ANIO,ID_ENTIDAD,ID_MUNICIPIO,TEMA,CATEGORIA,DESCRIPCION_CATEGORIA,VALOR,ESTATUS
x,Municipal,{a},14,039,Ingresos,Tema,Total de ingresos,1000,Cifras Definitivas
x,Municipal,{a},14,039,Ingresos,Capítulo,Impuestos,300,Cifras Definitivas
x,Municipal,{a},14,039,Ingresos,Partida Genérica,Impuesto predial,200,Cifras Definitivas
x,Municipal,{a},14,039,Ingresos,Concepto,Otra cosa,5,Cifras Definitivas
x,Municipal,{a},14,039,Ingresos,Capítulo,Derechos,100,Cifras Definitivas
x,Municipal,{a},14,039,Ingresos,Capítulo,Participaciones federales,{p},Cifras Definitivas
x,Municipal,{a},14,039,Egresos,Tema,Total de egresos,1000,Cifras Definitivas
x,Municipal,{a},14,039,Egresos,Capítulo,Servicios\xa0personales,700,Cifras Definitivas
"""


def _efipem(ruta, anios=(2021, 2022, 2023), descuadre=None):
    return _zip(ruta, {f"conjunto_de_datos/efipem_municipal_anual_tr_cifra_{a}.csv":
                       EFIPEM_CSV.format(a=a, p=550 if a == descuadre else 600) for a in anios})


def test_efipem_tema_capitulo_y_predial_y_revisa_la_suma(tmp_path):
    filas = efipem.leer(_efipem(tmp_path / "e.zip", descuadre=2022), anios=2)
    assert sorted({f["anio"] for f in filas}) == [2022, 2023]
    assert "Otra cosa" not in {f["concepto"] for f in filas}
    assert "Servicios personales" in {f["concepto"] for f in filas}  # sin espacio duro
    assert [d.split(":")[0] for d in efipem.revisar(filas)] == ["2022 14039"]


COLUMNAS_GRS = (["Clave de la entidad", "Entidad", "Clave del municipio", "Municipio", "Clave de la localidad",
                 "Localidad", "Folio", "Clave de la AGEB", "Población total", "Viviendas"]
                + [f"i{k}" for k in range(17)] + ["Grado de Rezago Social"])


def _grs(ruta, agebs):
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "GRS 2020"
    hoja.append([None])
    hoja.append(["Grado de Rezago Social e indicadores"])
    hoja.append([None])
    hoja.append(COLUMNAS_GRS)
    hoja.append([None] * 10 + ["Población de 15 años o más analfabeta"])
    hoja.append([None])
    for cvegeo, pob, grado, ind in agebs:
        hoja.append(["14", "Jalisco", "14039", "Guadalajara", cvegeo[:9], "Guadalajara", cvegeo[-4:], cvegeo, pob, 10,
                     *([ind] * 17), grado])
    hoja.append(["Nota: para todas las AGEB con menos de 3 viviendas..."])
    libro.save(ruta)
    return ruta


def test_rezago_social_lee_el_grado_y_respeta_la_reserva(tmp_path):
    filas = rezago_social.leer(_grs(tmp_path / "g.xlsx", [("1403900010010", 500, "Bajo", 2.5),
                                                          ("140390001002A", 3, "Muy alto", None)]))
    assert [(f["cvegeo"], f["cve_mun"], f["grado"]) for f in filas] == [
        ("1403900010010", "039", "Bajo"), ("140390001002A", "039", "Muy alto")]
    assert filas[0]["indicadores"]["sin_internet"] == 2.5
    assert all(v is None for v in filas[1]["indicadores"].values())
    with pytest.raises(rezago_social.ArchivoInvalido, match="grado desconocido"):
        rezago_social.leer(_grs(tmp_path / "m.xlsx", [("1403900010010", 5, "Regular", 1)]))


CNGMD_P10 = """cvegeo,cve_ent,cve_mun,instmun_a,rensnn1,rensnn2,rensnn3,vigncia1
14039,14,039,1,1,2,1,2045
14039,14,039,9,9,0,0,NA
14039,14,039,14,1,2,1,INDEFINIDA
14039,14,039,10,2,0,0,NO APLICA
"""
CNGMD_CAT = """instmun_a,descrip
1,Plan o programa de desarrollo urbano del municipio o demarcación territorial
9,Atlas de riesgos del municipio o demarcación territorial
10,Programa de movilidad del municipio o demarcación territorial
14,Programa de mejoramiento o restauración de centro histórico
"""


def test_cngmd_guarda_la_respuesta_tal_cual(tmp_path):
    filas = cngmd.leer(_zip(tmp_path / "c.zip", {"conjunto_de_datos/m2s14p10_cngmd2025.csv": CNGMD_P10,
                                                  "catalogos/instmun_a_cngmd2025.csv": CNGMD_CAT}))
    por = {f["instrumento"]: f for f in filas}
    assert (por[1]["existio"], por[1]["publicado"], por[1]["vigencia"]) == ("sí", "sí", "2045")
    assert por[9]["existio"] == "no se sabe"  # nunca "no"
    assert por[10]["existio"] == "no"


@pytest.mark.asyncio
async def test_perfil_trae_cada_fuente_aparte(conn, pool_de_una_conexion, tmp_path):
    await conn.execute(
        "INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom) SELECT '14' || m, '14', m, 'Mun ' || m,"
        " ST_Multi(ST_MakeEnvelope(-103.4, 20.6, -103.3, 20.7, 4326)) FROM unnest(ARRAY['001', '039']) m")
    await ce.cargar(pool_de_una_conexion, "14", _ce(tmp_path / "ce.zip"))
    for a in (2021, 2022, 2023):
        for f in efipem.leer(_efipem(tmp_path / f"e{a}.zip", anios=(a,)), anios=1):
            await conn.execute(
                "INSERT INTO fuente_efipem_municipal (anio, cve_ent, cve_mun, tema, categoria, concepto, valor, estatus)"
                " VALUES (%(anio)s, %(cve_ent)s, %(cve_mun)s, %(tema)s, %(categoria)s, %(concepto)s, %(valor)s,"
                " %(estatus)s)", f)
    # Otro municipio reportó 2024: el 039 se queda en 2023 y se dice.
    await conn.execute("INSERT INTO fuente_efipem_municipal (anio, cve_ent, cve_mun, tema, categoria, concepto,"
                       " valor, estatus) VALUES (2024, '14', '120', 'Ingresos', 'Tema', 'Total de ingresos', 1, 'x')")
    await conn.execute("INSERT INTO fuente_rezago_social_ageb (cvegeo, cve_ent, cve_mun, pobtot, grado, indicadores)"
                       " VALUES ('1403900010010', '14', '039', 500, 'Bajo', '{}'),"
                       "        ('1403900010029', '14', '039', 300, 'Bajo', '{}'),"
                       "        ('140390001003A', '14', '039', NULL, 'Muy alto', '{}')")
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    try:
        datos = TestClient(app).get("/perfil_zona", params={"cve_ent": "14", "cve_mun": "001"}).json()
        gdl = TestClient(app).get("/perfil_zona", params={"cve_ent": "14", "cve_mun": "039"}).json()
    finally:
        app.dependency_overrides.clear()
    eco = datos["economia"]
    assert eco["total"]["personal"] == 800
    assert [s["sector"] for s in eco["sectores"]] == ["46", "31-33"]  # el reservado al final
    assert eco["reservados"] == 1
    assert gdl["economia"] == {"sin_dato": True}
    h = gdl["hacienda"]
    assert (h["anio"], h["ultimo_publicado"], h["predial"], h["propios_pct"], h["transferencias_pct"]) == (
        2023, 2024, 200, 40.0, 60.0)
    assert [x["anio"] for x in h["serie_propios"]] == [2021, 2022, 2023]
    assert h["ingresos"][0] == ["Participaciones federales", 600]
    assert (datos["hacienda"]["sin_dato"], datos["hacienda"]["estado_sin_datos"]) == (True, False)
    r = gdl["rezago_social"]
    assert [(g["grado"], g["agebs"], g["personas"]) for g in r["grados"]] == [("Bajo", 2, 800), ("Muy alto", 1, None)]
    assert gdl["planeacion"] is None  # el CNGMD no está cargado en la base de prueba
