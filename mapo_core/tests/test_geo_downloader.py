from mapo_core.geo_downloader import _int_seguro


def test_int_seguro_con_numero():
    assert _int_seguro("1234") == 1234


def test_int_seguro_con_guion_da_none():
    """El API de INEGI usa '-' como marcador de dato no disponible."""
    assert _int_seguro("-") is None


def test_int_seguro_con_vacio_da_none():
    assert _int_seguro("") is None
    assert _int_seguro(None) is None


def test_int_seguro_con_basura_da_none_no_truena():
    assert _int_seguro("no es un numero") is None
