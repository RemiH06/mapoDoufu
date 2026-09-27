import datetime
import io
import struct
import zipfile

import pytest

from mapo_core.enoe_downloader import (
    TRIMESTRES_VALIDOS,
    _calcular_tasas,
    _extraer_sdem,
    url_trimestre,
)


def _construir_dbf(campos: list[tuple[str, str, int]], filas: list[tuple]) -> bytes:
    """Construye un .dbf (dBase III) real, byte por byte, mismo helper
    que ya usan (y confirman contra dbfread de verdad) los tests de
    Gaiarda para esta misma fuente."""
    n_registros = len(filas)
    tam_registro = 1 + sum(largo for _, _, largo in campos)
    tam_encabezado = 32 + 32 * len(campos) + 1

    hoy = datetime.date.today()
    encabezado = struct.pack(
        "<BBBBIHH20x",
        0x03, hoy.year % 100, hoy.month, hoy.day,
        n_registros, tam_encabezado, tam_registro,
    )

    descriptores = b""
    for nombre, tipo, largo in campos:
        nombre_bytes = nombre.encode("ascii")[:10].ljust(11, b"\x00")
        descriptores += struct.pack("<11scI B B 14x", nombre_bytes, tipo.encode(), 0, largo, 0)

    cuerpo = b""
    for fila in filas:
        cuerpo += b" "
        for (_, _, largo), valor in zip(campos, fila):
            cuerpo += str(valor).encode("latin-1")[:largo].ljust(largo, b" ")

    return encabezado + descriptores + b"\x0d" + cuerpo + b"\x1a"


def _zip_sdem(dbf_bytes: bytes, nombre: str = "ENOE_SDEMT325.dbf") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(nombre, dbf_bytes)
    return buf.getvalue()


def test_url_trimestre_usa_el_patron_nuevo_sin_n():
    # Bug real encontrado: Gaiarda usaba enoe_n_{anio}_{trimestre}, que
    # ya no responde para 2023 en adelante. El patron real confirmado
    # contra descargas reales no trae el segmento "_n_".
    assert url_trimestre(2025, "trim3") == (
        "https://www.inegi.org.mx/contenidos/programas/enoe/15ymas/microdatos/"
        "enoe_2025_trim3_dbf.zip"
    )


def test_url_trimestre_rechaza_trimestre_invalido():
    with pytest.raises(ValueError):
        url_trimestre(2025, "trim9")


def test_trimestres_validos_son_los_4():
    assert TRIMESTRES_VALIDOS == {"trim1", "trim2", "trim3", "trim4"}


def test_extraer_sdem_filtra_por_r_def_y_lee_campos_reales():
    campos = [("R_DEF", "C", 2), ("CVE_ENT", "C", 2), ("CLASE1", "N", 1), ("CLASE2", "N", 1), ("FAC_TRI", "N", 5)]
    filas_dbf = [
        ("00", "14", 1, 1, 2015),  # entrevista completa, ocupada
        ("00", "14", 1, 2, 500),   # entrevista completa, desocupada
        ("15", "14", 1, 2, 999),   # entrevista NO completa: se descarta
    ]
    zip_bytes = _zip_sdem(_construir_dbf(campos, filas_dbf))

    filas = _extraer_sdem(zip_bytes)

    assert len(filas) == 2  # la de R_DEF='15' se descarta
    assert filas[0]["cve_ent"] == "14"
    assert filas[0]["clase1"] == 1
    assert filas[1]["fac_tri"] == 500


def test_extraer_sdem_sin_ningun_sdem_en_el_zip_truena():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ENOE_VIVT325.dbf", b"no importa el contenido")

    with pytest.raises(ValueError, match="SDEM"):
        _extraer_sdem(buf.getvalue())


def test_calcular_tasas_formula_ponderada():
    # PEA (clase1=1) = 1000 personas ponderadas, de las cuales 100 desocupadas.
    filas = [
        {"cve_ent": "14", "clase1": 1, "clase2": 1, "fac_tri": 900},  # ocupada
        {"cve_ent": "14", "clase1": 1, "clase2": 2, "fac_tri": 100},  # desocupada
    ]

    resultado = _calcular_tasas(filas)

    assert resultado["14"]["pea_ponderada"] == 1000
    assert resultado["14"]["ocupada_ponderada"] == 900
    assert resultado["14"]["desocupada_ponderada"] == 100
    assert resultado["14"]["tasa_desocupacion"] == pytest.approx(10.0)


def test_calcular_tasas_ignora_pnea():
    filas = [
        {"cve_ent": "14", "clase1": 1, "clase2": 1, "fac_tri": 100},  # PEA ocupada
        {"cve_ent": "14", "clase1": 2, "clase2": 4, "fac_tri": 5000},  # PNEA, no cuenta
    ]

    resultado = _calcular_tasas(filas)

    assert resultado["14"]["pea_ponderada"] == 100  # el PNEA no se suma


def test_calcular_tasas_entidad_sin_pea_se_omite():
    filas = [{"cve_ent": "14", "clase1": 2, "clase2": 4, "fac_tri": 500}]  # solo PNEA

    resultado = _calcular_tasas(filas)

    assert "14" not in resultado  # division entre cero evitada, no se reporta la entidad


def test_calcular_tasas_separa_por_entidad():
    filas = [
        {"cve_ent": "14", "clase1": 1, "clase2": 1, "fac_tri": 100},
        {"cve_ent": "09", "clase1": 1, "clase2": 2, "fac_tri": 50},
    ]

    resultado = _calcular_tasas(filas)

    assert resultado["14"]["tasa_desocupacion"] == 0.0
    assert resultado["09"]["tasa_desocupacion"] == 100.0
