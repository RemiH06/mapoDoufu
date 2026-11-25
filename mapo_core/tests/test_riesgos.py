import pytest

from mapo_core import riesgos as r


def test_zona_por_municipio_solo_con_claves_bien_formadas():
    assert r.zona_valida("14", "015") == {"tipo": "municipios", "cvegeos": ["14015"]}
    assert r.zona_valida(clave="zm:14.1.01") == {"tipo": "metropoli", "clave": "14.1.01"}
    for e, m in (("14", "15"), ("1a", "015"), ("14", "015; DROP"), (14, "015")):
        with pytest.raises(r.ZonaInvalida):
            r.zona_valida(e, m)


def test_zona_por_circulo_dentro_de_mexico_y_con_radio_acotado():
    assert r.zona_valida(lon="-104.3", lat="19.7", radio_m="2500") == {
        "tipo": "circulo", "lon": -104.3, "lat": 19.7, "radio_m": 2500}
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


def test_sin_lugares_cerca_es_cero_y_con_lugares_reservados_es_sin_dato():
    # Nadie vive cerca: la suma de SQL sale NULL, pero lo cierto es cero.
    assert r._grupos({"agebs": 0, "localidades": 0, "POBTOT": None})["POBTOT"]["valor"] == 0
    # Hay lugares y todos traen '*': eso sí es "sin dato".
    assert r._grupos({"agebs": 2, "localidades": 0, "POBTOT": None})["POBTOT"]["valor"] is None


def _lugar(mun, lon, lat, pob, tipo="ageb"):
    return {"mun": mun, "tipo": tipo, "d": {"POBTOT": pob}, "lon": lon, "lat": lat}


def test_cerca_mide_en_metros_sobre_el_terreno():
    # A 20.7 grados, 0.009 grados de longitud son unos 938 m y 0.0096, unos 1,000 m.
    foco = [{"lon": -103.35, "lat": 20.7}]
    u = [_lugar("14039", -103.35 + 0.0095, 20.7, 10), _lugar("14039", -103.35 + 0.0097, 20.7, 20)]
    assert r.cerca_de(u, foco, 1000) == [u[0]]
    assert r.cerca_de(u, foco, 2000) == u
    assert r.cerca_de(u, [], 1000) == []
    assert r.cerca_de([], foco, 1000) == []


def test_la_medida_se_parte_por_municipio_y_suma_la_zona():
    foco = [{"lon": -103.35, "lat": 20.7}]
    todas = [_lugar("14039", -103.35, 20.7, 300), _lugar("14039", -103.25, 20.7, "100"),
             _lugar("14120", -103.351, 20.7, "*"), _lugar("14097", -103.2, 20.5, 50)]
    m = r.medida_gente({"todas": todas, "municipios": ["14039", "14120", "14097", "14070"]}, foco, 1000)
    assert m["zona"] == {"personas": 300, "total": 450, "pct": 66.6667}
    assert m["municipios"]["14039"] == {"personas": 300, "total": 400, "pct": 75.0}
    # Puros reservados: no se sabe, ni cuántos ni qué parte.
    assert m["municipios"]["14120"] == {"personas": None, "total": None, "pct": None}
    assert m["municipios"]["14097"]["pct"] == 0
    # Sin nadie no hay porcentaje (no es 0 %).
    assert m["municipios"]["14070"] == {"personas": 0, "total": 0, "pct": None}


def test_la_zona_solo_tiene_categoria_de_sequia_si_sus_municipios_coinciden():
    def fila(mun, categoria):
        return {"cve_ent": "14", "cve_mun": mun, "actual": categoria, "severa": 3, "cortes": 119, "ultima": "2026-10-31"}

    una = r.medida_sequia([fila("039", "D1")])
    assert una["zona"]["categoria"] == "D1" and una["zona"]["detalle"] == "3 de 119 en D2+"
    igual = r.medida_sequia([fila("039", "D1"), fila("120", "D1")])
    assert igual["zona"]["categoria"] == "D1"
    distinta = r.medida_sequia([fila("039", "sin"), fila("120", "D2"), fila("097", "D0")])
    assert distinta["zona"]["categoria"] is None and distinta["zona"]["rango"] == ["sin", "D2"]
    assert distinta["municipios"]["14120"]["texto"] == "sequía severa"


def test_peligros_solo_del_catalogo():
    assert r.peligros_validos("fuego,anp,fuego") == ["fuego", "anp"]
    for v in ("", "fuego,", "defunciones", "fuego;DROP"):
        with pytest.raises(r.ZonaInvalida):
            r.peligros_validos(v)


def test_cada_ficha_trae_lo_que_se_cita():
    assert set(r.PELIGROS) <= set(r.FICHAS)
    for ficha in r.FICHAS.values():
        assert all(ficha[k] for k in ("titulo", "fuente", "nivel", "metodo"))
