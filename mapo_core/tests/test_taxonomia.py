"""Taxonomía de rubros: rasgos, k-means con silueta, nombres de grupo y el CSV."""

import csv
import math

import numpy as np
import pytest

from mapo_core import taxonomia


def _resultado(distancia, azar, plaza, todos, cociente=None):
    return {
        "agrupacion": {"distancia_m": distancia, "al_azar_m": azar},
        "plazas": {"rubro": plaza, "todos": todos} if plaza is not None else None,
        "junto_a": [{"rubro": "dulceria", "cociente": cociente}] if cociente else [],
    }


def test_rasgos_en_log_y_sin_log_de_cero():
    r = taxonomia.rasgos(_resultado(0, 99, 0.0, 0.1, cociente=4.0))

    assert r["agrupacion"] == pytest.approx(math.log(1 / 100))
    assert r["plazas"] == pytest.approx(math.log(0.01 / 0.11))
    assert r["junto_a"] == pytest.approx(math.log(4.0))


def test_sin_marca_de_plaza_ni_colocacion_los_rasgos_son_neutros():
    r = taxonomia.rasgos(_resultado(100, 100, None, None))

    assert (r["plazas"], r["junto_a"]) == (0.0, 0.0)


def test_agrupar_encuentra_tres_grupos_claros():
    rng = np.random.default_rng(0)
    centros = np.array([[-1.0, 1.0, 1.0], [0.0, -1.0, 0.0], [0.5, 0.0, 2.0]])
    x = np.vstack([c + rng.normal(0, 0.05, (20, 3)) for c in centros])

    etiquetas, centros_hallados, silueta = taxonomia.agrupar(x)

    assert len(set(etiquetas.tolist())) == 3
    assert silueta > 0.8
    assert all(len(set(etiquetas[i * 20:(i + 1) * 20].tolist())) == 1 for i in range(3))
    assert np.allclose(sorted(centros_hallados[:, 0]), sorted(centros[:, 0]), atol=0.05)


def test_describir_pone_nombre_al_centro():
    assert taxonomia.describir(np.array([math.log(0.5), math.log(2), math.log(3)])) == (
        "Se agrupa, más en plazas y mercados, junto a otros rubros"
    )
    assert taxonomia.describir(np.array([0.0, math.log(0.5), 0.0])) == (
        "Ni se agrupa ni se reparte, poco en plazas y mercados"
    )
    assert taxonomia.describir(np.array([math.log(1.3), 0.0, 0.0])) == "Se reparte"


def _fila(ent, rubro):
    return dict.fromkeys(taxonomia.COLUMNAS, "") | {"cve_ent": ent, "rubro": rubro}


def test_escribir_reemplaza_solo_el_estado_calculado(tmp_path):
    ruta = tmp_path / "taxonomia.csv"
    taxonomia.escribir([_fila("14", "floreria"), _fila("09", "floreria")], ruta)

    taxonomia.escribir([_fila("14", "dulceria")], ruta)

    with open(ruta, encoding="utf-8") as f:
        assert [(r["cve_ent"], r["rubro"]) for r in csv.DictReader(f)] == [("09", "floreria"), ("14", "dulceria")]
