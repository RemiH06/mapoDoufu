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
