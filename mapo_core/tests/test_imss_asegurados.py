import datetime
from pathlib import Path

import pytest

from mapo_core import imss_asegurados as im
from mapo_core import rubros

CABECERA = (
    "cve_delegacion|cve_subdelegacion|cve_entidad|cve_municipio|sector_economico_1|sector_economico_2|"
    "sector_economico_4|tamaño_patron|sexo|rango_edad|rango_salarial|rango_uma|asegurados|no_trabajadores|"
    "ta|teu|tec|tpu|tpc|ta_sal|teu_sal|tec_sal|tpu_sal|tpc_sal|masa_sal_ta|masa_sal_teu|masa_sal_tec|"
    "masa_sal_tpu|masa_sal_tpc"
)


def _renglon(ent="14", mun="Z29", s1="8", s2="87", uma="W3", ta=10, tpu=8, teu=2, masa=5000.0, sin=0):
    return (f"20|34|{ent}|{mun}|{s1}|{s2}|8701|S3|1|E4|NA|{uma}|{ta + sin}|{sin}|{ta}|{teu}|0|{tpu}|0|"
            f"{ta}|{teu}|0|{tpu}|0|{masa}|0|0|0|0")


def test_periodo_de_lee_el_nombre_del_archivo():
    assert im.periodo_de(Path("data/asg-2024-12-31.csv.gz")) == datetime.date(2024, 12, 31)
    assert im.periodo_de(Path("asg-2024-02-29.csv")) == datetime.date(2024, 2, 29)
    with pytest.raises(im.ArchivoInvalido):
        im.periodo_de(Path("asegurados_diciembre.csv"))


def test_leer_suma_por_municipio_y_grupo_y_cuenta_el_rango_del_tope():
    lineas = [CABECERA, _renglon(), _renglon(uma="W25", ta=1, tpu=1, teu=0, masa=2700.0),
              _renglon(mun="NA", ent="9"), _renglon(s1="", s2="", ta=0, tpu=0, teu=0, masa=0.0, sin=4)]
    suma = im.leer(lineas)
    asegurados, sin_empleo, puestos, perm, event, con_sal, masa, tope = suma[("14", "Z29", "8", "87")]
    assert (puestos, perm, event, con_sal, masa, tope) == (11, 9, 2, 11, 7700.0, 1)
    assert ("09", "NA", "8", "87") in suma  # la entidad sale con dos dígitos
    assert suma[("14", "Z29", "", "")][1] == 4  # asegurados sin empleo, sin división


def test_leer_rechaza_un_archivo_sin_las_columnas():
    with pytest.raises(im.ArchivoInvalido, match="faltan columnas"):
        im.leer(["cve_entidad|cve_municipio|ta", "14|A01|3"])


def test_municipio_de_usa_la_equivalencia_y_cae_en_000():
    assert im.municipio_de("14", "Z29") == "120"
    assert im.municipio_de("14", "Z60") == "120"  # clave nueva, comprobada con el IIEG
    assert im.municipio_de("14", "Z62") == "039"
    assert im.municipio_de("09", "NA") == "000"  # la CDMX no se reparte por alcaldía
    assert im.municipio_de("16", "Z45") == "000"  # sin equivalencia comprobada
    assert im.municipio_de("15", "Z29") == "000"  # la clave es de otro estado


def test_la_equivalencia_es_de_claves_de_inegi_validas():
    eq = im.equivalencia()
    assert len(eq) > 2400
    assert all(len(e) == 2 and len(m) == 3 and m.isdigit() and m != "000" for e, m in eq.values())
    guadalajara = sorted(k for k, v in eq.items() if v == ("14", "039"))
    assert guadalajara == ["B90", "R12", "R13", "R14", "R15", "Z62"]


def test_anio_antes():
    assert im._anio_antes(datetime.date(2024, 12, 31)) == datetime.date(2023, 12, 31)
    assert im._anio_antes(datetime.date(2024, 2, 29)) == datetime.date(2023, 2, 28)
    assert im._anio_antes(datetime.date(2024, 1, 31)) == datetime.date(2023, 1, 31)


def test_cada_sector_de_mapo_lleva_grupos_del_imss_que_existen():
    for sector in rubros.sectores():
        grupos = rubros.grupos_imss(sector=sector)
        assert grupos and all(g in im.grupos() for g in grupos), sector
    assert rubros.grupos_imss(rubro="taqueria") == ["87"]


async def _insertar(conn, periodo, cve_mun, clave, division, grupo, puestos, masa, tope=0):
    await conn.execute(
        """INSERT INTO fuente_imss_asegurados (periodo, cve_ent, cve_mun, clave_imss, division, grupo,
               asegurados, sin_empleo, puestos, permanentes, eventuales, puestos_con_salario, masa_salarial,
               puestos_rango_tope)
           VALUES (%s, '14', %s, %s, %s, %s, %s, 0, %s, %s, 0, %s, %s, %s)""",
        (periodo, cve_mun, clave, division, grupo, puestos, puestos, puestos, puestos, masa, tope),
    )


@pytest.mark.asyncio
async def test_empleo_municipio_sin_anio_anterior_no_inventa_variacion(conn, pool_de_una_conexion):
    await _insertar(conn, "2024-12-31", "120", "Z29", "8", "87", 100, 40000.0, tope=5)
    await _insertar(conn, "2024-12-31", "120", "C16", "6", "61", 300, 150000.0)
    await _insertar(conn, "2024-01-31", "120", "Z29", "8", "87", 90, 30000.0)

    e = await im.empleo_municipio(pool_de_una_conexion, "14", "120")

    assert e["periodo"] == "2024-12-31" and e["puestos"] == 400
    assert e["salario_diario"] == 475.0
    assert e["parte_rango_tope"] == 1.25
    assert [d["division"] for d in e["por_division"]] == ["6", "8"]
    assert e["anual"] is None  # enero no es el mismo mes del año anterior


@pytest.mark.asyncio
async def test_empleo_municipio_con_el_mismo_mes_del_anio_anterior(conn, pool_de_una_conexion):
    await _insertar(conn, "2024-12-31", "120", "Z29", "8", "87", 110, 1.0)
    await _insertar(conn, "2023-12-31", "120", "Z29", "8", "87", 100, 1.0)
    await _insertar(conn, "2024-12-31", "000", "Z99", "8", "87", 7, 1.0)

    e = await im.empleo_municipio(pool_de_una_conexion, "14", "120")

    assert e["anual"] == {"periodo": "2023-12-31", "puestos": 100, "variacion": 10.0}
    assert e["puestos_estado_sin_municipio"] == 7


@pytest.mark.asyncio
async def test_empleo_municipio_sin_datos_del_estado_es_none(pool_de_una_conexion):
    assert await im.empleo_municipio(pool_de_una_conexion, "31", "050") is None


@pytest.mark.asyncio
async def test_empleo_por_grupos_separa_el_rubro_del_resto(conn, pool_de_una_conexion):
    await _insertar(conn, "2024-12-31", "039", "R12", "8", "87", 20, 6000.0)
    await _insertar(conn, "2024-12-31", "039", "R13", "8", "87", 5, 1500.0)
    await _insertar(conn, "2024-12-31", "039", "R12", "6", "61", 75, 1.0)

    r = await im.empleo_por_grupos(pool_de_una_conexion, "14", ["039", "120"], ["87"])

    assert r["periodo_anual"] is None
    assert r["grupos"] == [{"grupo": "87", "nombre": "Preparación y servicio de alimentos y bebidas"}]
    gdl, zap = r["municipios"]
    assert (gdl["puestos_rubro"], gdl["puestos_total"], gdl["salario_diario_rubro"]) == (25, 100, 300.0)
    assert (zap["puestos_rubro"], zap["puestos_total"], zap["salario_diario_rubro"]) == (0, 0, None)
