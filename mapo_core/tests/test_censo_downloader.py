import io
import zipfile

import pytest

from mapo_core.censo_downloader import _nivel_y_cvegeo, _normalizar, _num, extraer_csv


def test_num_entero_valido():
    assert _num("1500000", int) == 1500000


def test_num_valores_marcadores_de_dato_faltante_dan_none():
    """'*' (confidencialidad), 'N/D', '-' y vacio son marcadores
    oficiales de dato no disponible en el censo, no ceros."""
    for marcador in ("", "*", "N/D", "-"):
        assert _num(marcador, int) is None


def test_num_real():
    assert _num("9.5", float) == 9.5


def test_nivel_y_cvegeo_entidad():
    fila = {"ENTIDAD": "14", "MUN": "000", "LOC": "0000", "AGEB": "0000", "MZA": "000"}
    assert _nivel_y_cvegeo(fila) == ("entidad", "14")


def test_nivel_y_cvegeo_municipio():
    fila = {"ENTIDAD": "14", "MUN": "039", "LOC": "0000", "AGEB": "0000", "MZA": "000"}
    assert _nivel_y_cvegeo(fila) == ("municipio", "14039")


def test_nivel_y_cvegeo_localidad():
    fila = {"ENTIDAD": "14", "MUN": "039", "LOC": "0001", "AGEB": "0000", "MZA": "000"}
    assert _nivel_y_cvegeo(fila) == ("localidad", "140390001")


def test_nivel_y_cvegeo_ageb():
    fila = {"ENTIDAD": "14", "MUN": "039", "LOC": "0001", "AGEB": "1234", "MZA": "000"}
    assert _nivel_y_cvegeo(fila) == ("ageb", "1403900011234")


def test_nivel_y_cvegeo_manzana_se_descarta():
    """Las filas de manzana no se descargan a proposito (serian
    cientos de miles de filas extra por estado grande, y nada en Mapo
    las necesita)."""
    fila = {"ENTIDAD": "14", "MUN": "039", "LOC": "0001", "AGEB": "1234", "MZA": "001"}
    assert _nivel_y_cvegeo(fila) is None


def test_normalizar_ageb_guarda_los_27_indicadores_y_el_resto_en_json():
    fila = {
        "ENTIDAD": "14", "MUN": "039", "LOC": "0001", "AGEB": "1234", "MZA": "000",
        "NOM_LOC": "Guadalajara", "POBTOT": "1500", "POBFEM": "800", "POBMAS": "700",
        "GRAPROES": "10.5", "ALGUN_OTRO_CAMPO_NO_MAPEADO": "valor cualquiera",
    }

    normalizado = _normalizar(fila)

    assert normalizado["nivel"] == "ageb"
    assert normalizado["cvegeo"] == "1403900011234"
    assert normalizado["nombre"] == "Guadalajara"
    assert normalizado["pobtot"] == 1500
    assert normalizado["pobfem"] == 800
    assert normalizado["graproes"] == 10.5
    assert "ALGUN_OTRO_CAMPO_NO_MAPEADO" in normalizado["datos_json"]


def test_normalizar_manzana_da_none():
    fila = {"ENTIDAD": "14", "MUN": "039", "LOC": "0001", "AGEB": "1234", "MZA": "001"}
    assert _normalizar(fila) is None


def _zip_con_csv(nombre_archivo: str, contenido: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(nombre_archivo, contenido)
    return buffer.getvalue()


def test_extraer_csv_encuentra_el_archivo_esperado():
    csv_texto = "ENTIDAD,MUN,LOC,AGEB,MZA,POBTOT\n14,039,0000,0000,000,1500000\n"
    zip_bytes = _zip_con_csv(
        "ageb_mza_urbana_14_cpv2020/conjunto_de_datos/conjunto_de_datos_ageb_urbana_14_cpv2020.csv",
        csv_texto,
    )

    filas = extraer_csv(zip_bytes, "14")

    assert len(filas) == 1
    assert filas[0]["POBTOT"] == "1500000"


def test_extraer_csv_con_delimitador_equivocado_truena_con_mensaje_claro():
    """Bug real ya encontrado del lado de Gaiarda con este mismo CSV:
    con el delimitador equivocado, DictReader regresa una sola columna
    gigante en vez de tronar; se guardaba basura en silencio. Este
    candado existe para que eso truene claro en vez de colarse."""
    csv_texto = "ENTIDAD\tMUN\tLOC\tAGEB\tMZA\tPOBTOT\n14\t039\t0000\t0000\t000\t1500000\n"
    zip_bytes = _zip_con_csv("archivo.csv", csv_texto)

    with pytest.raises(ValueError, match="no parseo columnas reales"):
        extraer_csv(zip_bytes, "14")
