import pytest

from mapo_core import riesgos as r


def test_zona_por_municipio_solo_con_claves_bien_formadas():
    assert r.zona_valida("14", "015") == {"tipo": "municipio", "cve_ent": "14", "cve_mun": "015"}
    for e, m in (("14", "15"), ("1a", "015"), ("14", "015; DROP"), (14, "015")):
        with pytest.raises(r.ZonaInvalida):
            r.zona_valida(e, m)


def test_zona_por_circulo_dentro_de_mexico_y_con_radio_acotado():
    assert r.zona_valida(lon="-104.3", lat="19.7", radio_m="2500") == {
        "tipo": "circulo", "lon": -104.3, "lat": 19.7, "radio_m": 2500.0}
    for lon, lat, radio in ((-104.3, 19.7, 50), (-104.3, 19.7, 30_000), (2.35, 48.85, 1000), ("x", 19.7, 1000),
                            (None, None, None), (float("nan"), 19.7, 1000)):
        with pytest.raises(r.ZonaInvalida):
            r.zona_valida(lon=lon, lat=lat, radio_m=radio)


def test_cerca_solo_de_la_lista():
    assert r.cerca_valido("1000") == 1000
    for v in ("999", "abc", None, "1e3"):
        with pytest.raises(r.ZonaInvalida):
            r.cerca_valido(v)


def test_frases():
    assert r._cuenta(1, "sitio", "sitios") == "1 sitio"
    assert r._cuenta(1200, "sitio", "sitios") == "1,200 sitios"
    assert r._masa(43.6) == "43.6 kg"
    assert r._masa(217_273_158.1) == "217,273 t"
    assert r._n(None) == "sin dato"



def test_nombres_de_parametros():
    assert r.nombre_parametro("COLI_FEC_NMP_100mL") == "coliformes fecales"
    assert r.nombre_parametro("OD_PORC_SUP") == "oxígeno disuelto"
    assert r.nombre_parametro("AS_TOT_mg/L") == "arsénico"
    assert r.nombre_parametro("NUEVO_X") == "NUEVO_X"
