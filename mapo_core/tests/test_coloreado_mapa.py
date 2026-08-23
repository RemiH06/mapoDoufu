from shapely.geometry import box

from mapo_core.coloreado_mapa import PoligonoColoreable, colorear_mapa, construir_adyacencias


def _cuadricula(n):
    poligonos = []
    for i in range(n):
        for j in range(n):
            g = box(i, j, i + 1, j + 1)
            poligonos.append(PoligonoColoreable(id=f"{i}-{j}", geometria=g.__geo_interface__))
    return poligonos


def test_lista_vacia():
    resultado = colorear_mapa([])
    assert resultado.color_por_id == {}
    assert resultado.num_colores == 0


def test_un_solo_poligono():
    poligonos = [PoligonoColoreable(id="solo", geometria=box(0, 0, 1, 1).__geo_interface__)]
    resultado = colorear_mapa(poligonos)
    assert resultado.color_por_id == {"solo": 0}
    assert resultado.num_colores == 1


def test_poligonos_que_solo_se_tocan_en_una_esquina_no_son_vecinos():
    a = PoligonoColoreable(id="a", geometria=box(0, 0, 1, 1).__geo_interface__)
    b = PoligonoColoreable(id="b", geometria=box(1, 1, 2, 2).__geo_interface__)

    vecinos = construir_adyacencias([a, b])

    assert vecinos["a"] == set()
    assert vecinos["b"] == set()


def test_poligonos_que_comparten_un_lado_son_vecinos():
    a = PoligonoColoreable(id="a", geometria=box(0, 0, 1, 1).__geo_interface__)
    b = PoligonoColoreable(id="b", geometria=box(1, 0, 2, 1).__geo_interface__)

    vecinos = construir_adyacencias([a, b])

    assert vecinos["a"] == {"b"}
    assert vecinos["b"] == {"a"}


def test_poligonos_separados_no_son_vecinos():
    a = PoligonoColoreable(id="a", geometria=box(0, 0, 1, 1).__geo_interface__)
    b = PoligonoColoreable(id="b", geometria=box(5, 5, 6, 6).__geo_interface__)

    vecinos = construir_adyacencias([a, b])

    assert vecinos["a"] == set()


def test_ningun_par_vecino_comparte_color_en_una_cuadricula():
    poligonos = _cuadricula(4)
    vecinos = construir_adyacencias(poligonos)
    resultado = colorear_mapa(poligonos)

    for id_, vs in vecinos.items():
        for v in vs:
            assert resultado.color_por_id[id_] != resultado.color_por_id[v]


def test_una_cuadricula_tipo_tablero_de_ajedrez_usa_2_colores():
    poligonos = _cuadricula(5)
    resultado = colorear_mapa(poligonos)

    # una cuadricula es bipartita (como un tablero de ajedrez): 2
    # colores siempre alcanzan, muy por debajo del limite de 4 del
    # teorema.
    assert resultado.num_colores == 2


def test_todos_los_poligonos_aparecen_en_el_resultado():
    poligonos = _cuadricula(3)
    resultado = colorear_mapa(poligonos)

    assert set(resultado.color_por_id.keys()) == {p.id for p in poligonos}
