import pytest

from mapo_core.denue_downloader import TokenFaltante, _float_seguro, _normalizar, _obtener_token


def test_normalizar_mapea_los_campos_reales_de_inegi():
    registro = {
        "Id": "123",
        "Nombre": "Papelería El Lápiz",
        "Razon_social": "El Lápiz SA de CV",
        "Clase_actividad": "Comercio al por menor de papelería",
        "Estrato": "0 a 5 personas",
        "Calle": "Av. Siempre Viva",
        "Colonia": "Centro",
        "CP": "44100",
        "Ubicacion": "Jalisco, Guadalajara, Centro",
        "Telefono": "3312345678",
        "Correo_e": "contacto@ellapiz.mx",
        "Sitio_internet": "www.ellapiz.mx",
        "Tipo": "Fijo",
        "Latitud": "20.6597",
        "Longitud": "-103.3496",
    }

    normalizado = _normalizar(registro, "14")

    assert normalizado["id"] == "123"
    assert normalizado["nombre"] == "Papelería El Lápiz"
    assert normalizado["clase_actividad"] == "Comercio al por menor de papelería"
    assert normalizado["lat"] == pytest.approx(20.6597)
    assert normalizado["lon"] == pytest.approx(-103.3496)
    assert normalizado["cve_ent"] == "14"


def test_normalizar_sin_id_da_none():
    assert _normalizar({"Nombre": "sin id"}, "14") is None


def test_float_seguro_con_valor_invalido_da_none():
    assert _float_seguro("no es un numero") is None
    assert _float_seguro(None) is None


def test_normalizar_con_lat_lon_invalidos_da_none_en_esos_campos():
    registro = {"Id": "1", "Latitud": "N/D", "Longitud": ""}

    normalizado = _normalizar(registro, "14")

    assert normalizado["lat"] is None
    assert normalizado["lon"] is None


def test_obtener_token_explicito_gana_sobre_env(monkeypatch):
    monkeypatch.setenv("GAIARDA_DENUE_TOKEN", "del-entorno")
    assert _obtener_token("explicito") == "explicito"


def test_obtener_token_usa_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("GAIARDA_DENUE_TOKEN", "del-entorno")
    assert _obtener_token(None) == "del-entorno"


def test_obtener_token_sin_ninguno_truena_claro(monkeypatch):
    monkeypatch.delenv("GAIARDA_DENUE_TOKEN", raising=False)
    with pytest.raises(TokenFaltante):
        _obtener_token(None)
