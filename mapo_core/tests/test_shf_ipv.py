import pytest

from mapo_core import shf_ipv

CONFIG = {
    "periods": [{"year": 2026, "quarter": 1}, {"year": 2026, "quarter": 2}],
    "filterGroups": [
        {"code": "tipo_uso", "options": [{"value": "Nueva"}, {"value": "Usada"}]},
        {"code": "clase", "options": [{"value": "Económica - Social"}]},
    ],
}


def test_periodos_y_categorias():
    assert shf_ipv.periodos(CONFIG) == [(2026, 1), (2026, 2)]
    assert shf_ipv.categorias(CONFIG) == ["Nueva", "Usada", "Económica - Social"]


def test_territorial_usa_claves_y_omite_nulos():
    datos = {
        "states": [{"stateCode": "14", "stateName": "Jalisco", "finalValue": 235.05}],
        "metropolitanAreas": [{"category": "ZM Guadalajara", "name": "ZM Guadalajara", "finalValue": 235.65}],
        "municipalities": [
            {"stateCode": "14", "municipalityCode": "120", "municipalityName": "Zapopan", "finalValue": 234.73},
            {"stateCode": "14", "municipalityCode": "097", "municipalityName": "Tlajomulco", "finalValue": None},
        ],
    }
    filas = shf_ipv.leer_territorial(datos, 2026, 2)
    assert [(f["nivel"], f["clave"], f["indice"]) for f in filas] == [
        ("estado", "14", 235.05), ("zm", "ZM Guadalajara", 235.65), ("municipio", "14120", 234.73),
    ]
    assert {(f["categoria"], f["anio"], f["trimestre"]) for f in filas} == {("General", 2026, 2)}


def test_territorial_sin_estados_es_error():
    with pytest.raises(shf_ipv.RespuestaInvalida):
        shf_ipv.leer_territorial({"states": [], "metropolitanAreas": [], "municipalities": []}, 2026, 2)


def test_nacional_un_valor_por_trimestre():
    datos = {
        "periods": [{"year": 2026, "quarter": 1}, {"year": 2026, "quarter": 2}],
        "series": [{"category": "Nueva", "name": "Nueva", "values": [209.07, 212.18]}],
    }
    filas = shf_ipv.leer_nacional(datos)
    assert [(f["categoria"], f["trimestre"], f["indice"]) for f in filas] == [("Nueva", 1, 209.07), ("Nueva", 2, 212.18)]

    datos["series"][0]["values"] = [209.07]
    with pytest.raises(shf_ipv.RespuestaInvalida):
        shf_ipv.leer_nacional(datos)


def test_zonas_de_la_respuesta_de_la_shf():
    por_zona: dict[str, int] = {}
    for clave, _nombre in shf_ipv.zonas().values():
        por_zona[clave] = por_zona.get(clave, 0) + 1
    assert por_zona == {
        "ZM Tijuana": 3, "ZM Valle México": 76, "ZM León": 2, "ZM Guadalajara": 10, "ZM Toluca": 16,
        "ZM Monterrey": 18, "ZM PueblaTlax": 39, "ZM Querétaro": 5,
    }
    assert shf_ipv.zonas()["14101"] == ("ZM Guadalajara", "Guadalajara")
    assert "14085" not in shf_ipv.zonas()


def test_avaluos_de_zona_municipio_y_estado():
    # 41,514 de la zona menos los de Guadalajara, Zapopan, Tlaquepaque y Tlajomulco.
    assert shf_ipv.avaluos("ZM Guadalajara") == {
        "anio": 2025, "total": 41514, "minimo": {"anio": 2010, "total": 31738},
        "sin_indice": {"municipios": 6, "total": 41514 - 4492 - 10040 - 4110 - 13500},
    }
    # Huejotzingo tiene índice desde 2005, pero en 2008 se apoyó en 36 avalúos.
    assert shf_ipv.avaluos("21074")["minimo"] == {"anio": 2008, "total": 36}
    assert "sin_indice" not in shf_ipv.avaluos("21074")
    assert shf_ipv.avaluos("14") is None


def test_ninguna_zona_tiene_menos_avaluos_que_sus_municipios():
    for clave, _nombre in set(shf_ipv.zonas().values()):
        miembros = [m for m, (z, _n) in shf_ipv.zonas().items() if z == clave]
        for anio, total in shf_ipv._avaluos()[clave].items():
            assert total >= sum(shf_ipv._avaluos().get(m, {}).get(anio, 0) for m in miembros), (clave, anio)
