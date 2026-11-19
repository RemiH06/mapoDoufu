import csv
import io
import zipfile

import pytest

from mapo_core import eic2025

ENCABEZADO = ["CVEGEO", "CVE_ENT", "NOM_ENT", "CVE_MUN", "NOM_MUN", "CVE_LOC", "NOM_LOC", "ESTIMADOR",
              "POBTOT", "VIVPARHAB", "PCN_VPH_ALQUI"]
ESTIMADORES = ["Valor", "Error estándar", "Límite inferior de confianza",
               "Límite superior de confianza", "Coeficiente de variación"]


def _zona(cvegeo, ent, nom_ent, mun, nom_mun, loc, nom_loc, valores):
    """`valores`: una pareja (VIVPARHAB, PCN_VPH_ALQUI) por estimador."""
    return [[cvegeo, ent, nom_ent, mun, nom_mun, loc, nom_loc, e, "1", *v] for e, v in zip(ESTIMADORES, valores)]


def _zip(estados=32, municipio_mi=False):
    filas = _zona("000000000", "00", "Estados Unidos Mexicanos", "000", "Total nacional", "0000", "Total nacional",
                  [("100", "19.26"), ("1", "0.1"), ("98", "19.0"), ("102", "19.5"), ("1", "0.6")])
    for n in range(1, estados + 1):
        ent = f"{n:02d}"
        filas += _zona(f"{ent}0000000", ent, f"Estado {ent}", "000", "Total de la entidad", "0000",
                       "Total de la entidad", [("10", "20")] * 5)
    alquiler = "MI" if municipio_mi else "34.13"
    filas += _zona("140390000", "14", "Jalisco", "039", "Guadalajara *", "0000", "Total del municipio",
                   [("384117", alquiler), ("15428.46", alquiler), ("358640.7", alquiler),
                    ("409593.3", alquiler), ("4.02", alquiler)])
    texto = io.StringIO()
    csv.writer(texto).writerows([ENCABEZADO, *filas])
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as z:
        z.writestr(eic2025.CSV, texto.getvalue().encode("latin-1"))
    return salida.getvalue()


def test_junta_los_cinco_estimadores_y_solo_el_bloque_de_vivienda():
    filas = eic2025.leer(_zip())
    gdl = {f["indicador"]: f for f in filas if f["cvegeo"] == "140390000"}
    assert set(gdl) == {"VIVPARHAB", "PCN_VPH_ALQUI"}  # POBTOT queda fuera
    alq = gdl["PCN_VPH_ALQUI"]
    assert (alq["valor"], alq["cv"], alq["nota"]) == (34.13, 34.13, None)
    assert gdl["VIVPARHAB"]["error_estandar"] == 15428.46
    assert alq["nombre"] == "Guadalajara" and alq["nivel"] == "municipio"
    nacional = next(f for f in filas if f["nivel"] == "nacional")
    assert nacional["nombre"] == "Estados Unidos Mexicanos"
    assert next(f for f in filas if f["cvegeo"] == "140000000")["nombre"] == "Estado 14"


def test_muestra_insuficiente_es_nulo_con_nota_no_cero():
    alq = next(f for f in eic2025.leer(_zip(municipio_mi=True))
               if f["cvegeo"] == "140390000" and f["indicador"] == "PCN_VPH_ALQUI")
    assert alq["valor"] is None and alq["cv"] is None
    assert alq["nota"] == "MI"


def test_sin_los_32_estados_no_carga():
    with pytest.raises(eic2025.ArchivoInvalido, match="32 estados"):
        eic2025.leer(_zip(estados=31))
