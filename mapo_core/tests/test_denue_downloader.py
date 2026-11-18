"""Carga de DENUE desde la descarga masiva: normalización del CSV de INEGI,
lectura del ZIP y reemplazo de los negocios del estado en la base."""

import csv
import io
import zipfile

import pytest

from mapo_core import denue_downloader
from mapo_core.denue_downloader import ArchivoInvalido, _float_seguro, _normalizar, leer_zip

# Encabezado real de denue_inegi_14_.csv (mayo de 2026).
CAMPOS = (
    "id,clee,nom_estab,raz_social,codigo_act,nombre_act,per_ocu,tipo_vial,nom_vial,tipo_v_e_1,"
    "nom_v_e_1,tipo_v_e_2,nom_v_e_2,tipo_v_e_3,nom_v_e_3,numero_ext,letra_ext,edificio,edificio_e,"
    "numero_int,letra_int,tipo_asent,nomb_asent,tipoCenCom,nom_CenCom,num_local,cod_postal,cve_ent,"
    "entidad,cve_mun,municipio,cve_loc,localidad,ageb,manzana,telefono,correoelec,www,tipoUniEco,"
    "latitud,longitud,fecha_alta"
).split(",")


def _fila(id_="7", **cambios):
    fila = dict.fromkeys(CAMPOS, "")
    fila.update(
        id=id_,
        clee="14039812210002921000000000U0",
        nom_estab="FLORERIA LA ROSA",
        nombre_act="Comercio al por menor de plantas y flores naturales",
        per_ocu="0 a 5 personas",
        nom_vial="MARIANO BARCENA",
        nomb_asent="MEZQUITAN",
        tipoCenCom="MERCADO PUBLICO ",
        nom_CenCom="MERCADO CORONA",
        num_local="SN",
        cod_postal="44260",
        cve_ent="14",
        entidad="Jalisco",
        municipio="Guadalajara",
        localidad="Guadalajara                    ",
        tipoUniEco="Fijo",
        latitud="20.69001536",
        longitud="-103.35199402",
    )
    fila.update(cambios)
    return fila


def _zip(tmp_path, filas):
    texto = io.StringIO()
    escritor = csv.DictWriter(texto, fieldnames=CAMPOS, quoting=csv.QUOTE_ALL)
    escritor.writeheader()
    escritor.writerows(filas)
    ruta = tmp_path / "denue_14_csv.zip"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("conjunto_de_datos/denue_inegi_14_.csv", texto.getvalue().encode("latin-1"))
        zf.writestr("metadatos/metadatos_denue.txt", "DENUE 05_2026")
    return ruta


def test_normalizar_mapea_los_campos_del_csv_masivo():
    n = _normalizar(_fila(), "14")

    assert n["id"] == "7"
    assert n["clee"] == "14039812210002921000000000U0"
    assert n["nombre"] == "FLORERIA LA ROSA"
    assert n["clase_actividad"] == "Comercio al por menor de plantas y flores naturales"
    assert n["estrato"] == "0 a 5 personas"
    assert (n["calle"], n["colonia"], n["codigo_postal"]) == ("MARIANO BARCENA", "MEZQUITAN", "44260")
    assert (n["tipo_plaza"], n["plaza"], n["numero_local"]) == ("MERCADO PUBLICO", "MERCADO CORONA", "SN")
    assert n["ubicacion"] == "Guadalajara, Guadalajara, Jalisco"
    assert n["lat"] == pytest.approx(20.69001536)
    assert n["lon"] == pytest.approx(-103.35199402)


def test_normalizar_vacio_es_none_y_sin_id_se_descarta():
    n = _normalizar(_fila(tipoCenCom="", nom_CenCom="  ", latitud="N/D"), "14")

    assert (n["tipo_plaza"], n["plaza"], n["lat"]) == (None, None, None)
    assert _normalizar(_fila(id_=""), "14") is None


def test_float_seguro_con_valor_invalido_da_none():
    assert _float_seguro("no es un numero") is None
    assert _float_seguro(None) is None


def test_leer_zip_respeta_acentos_en_latin_1(tmp_path):
    ruta = _zip(tmp_path, [_fila(municipio="Tlajomulco de Zúñiga")])

    (n,) = list(leer_zip(ruta, "14"))

    assert n["ubicacion"] == "Guadalajara, Tlajomulco de Zúñiga, Jalisco"


def test_leer_zip_truena_si_un_id_se_repite(tmp_path):
    ruta = _zip(tmp_path, [_fila("1"), _fila("1")])

    with pytest.raises(ArchivoInvalido, match="dos veces"):
        list(leer_zip(ruta, "14"))


def test_leer_zip_truena_con_otro_estado(tmp_path):
    ruta = _zip(tmp_path, [_fila(cve_ent="15")])

    with pytest.raises(ArchivoInvalido, match="estado 15"):
        list(leer_zip(ruta, "14"))


async def _ids(conn):
    cursor = await conn.execute("SELECT id, tipo_plaza FROM fuente_denue_negocios WHERE cve_ent = '14' ORDER BY id")
    return await cursor.fetchall()


async def _viejo(conn, id_):
    await conn.execute(
        """INSERT INTO fuente_denue_negocios (id, nombre, cve_ent, actualizado)
           VALUES (%s, 'viejo', '14', now() - interval '90 days')""",
        (id_,),
    )


@pytest.mark.asyncio
async def test_cargar_zip_reemplaza_el_estado_y_borra_lo_que_ya_no_viene(
    conn, pool_de_una_conexion, tmp_path, monkeypatch
):
    async def pool():
        return pool_de_una_conexion

    monkeypatch.setattr(denue_downloader, "get_pool", pool)
    for i in range(20):
        await _viejo(conn, f"v{i}")
    await _viejo(conn, "1")
    filas = [_fila("1")] + [_fila(f"v{i}") for i in range(19)]

    guardados, borrados = await denue_downloader.cargar_zip(_zip(tmp_path, filas), "14")

    assert (guardados, borrados) == (20, 1)
    ids = await _ids(conn)
    assert "v19" not in [i for i, _ in ids]
    assert dict(ids)["1"] == "MERCADO PUBLICO"


@pytest.mark.asyncio
async def test_cargar_zip_no_borra_si_falta_demasiado(conn, pool_de_una_conexion, tmp_path, monkeypatch):
    async def pool():
        return pool_de_una_conexion

    monkeypatch.setattr(denue_downloader, "get_pool", pool)
    for i in range(10):
        await _viejo(conn, f"v{i}")

    guardados, borrados = await denue_downloader.cargar_zip(_zip(tmp_path, [_fila("1")]), "14")

    assert (guardados, borrados) == (1, None)
    assert len(await _ids(conn)) == 11
