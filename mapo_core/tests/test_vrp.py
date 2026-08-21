import pytest

from mapo_core.vrp import Parada, Vehiculo, matriz_haversine_km, resolver_vrp

# Puntos reales de referencia: CDMX (deposito) y 4 ciudades cercanas,
# todas al este/sureste, para que un solver razonable las reparta en
# un patron predecible entre 2 vehiculos.
DEPOSITO = Parada(lat=19.4326, lon=-99.1332)  # CDMX
PUEBLA = Parada(lat=19.0414, lon=-98.2063, demanda=5)
TOLUCA = Parada(lat=19.2926, lon=-99.6568, demanda=5)
CUERNAVACA = Parada(lat=18.9242, lon=-99.2216, demanda=5)
QUERETARO = Parada(lat=20.5888, lon=-100.3899, demanda=5)


def test_matriz_haversine_es_simetrica_y_diagonal_cero():
    paradas = [DEPOSITO, PUEBLA, TOLUCA]
    matriz = matriz_haversine_km(paradas)

    assert matriz[0][0] == 0
    assert matriz[1][1] == 0
    assert matriz[0][1] == pytest.approx(matriz[1][0])
    assert matriz[0][1] > 0


def test_matriz_haversine_distancia_cdmx_puebla_es_realista():
    matriz = matriz_haversine_km([DEPOSITO, PUEBLA])
    # CDMX-Puebla en linea recta ronda 100km (por carretera son ~130km)
    assert 90 < matriz[0][1] < 115


def test_parada_rechaza_ventana_a_medias():
    with pytest.raises(ValueError):
        Parada(lat=0, lon=0, ventana_inicio_min=10, ventana_fin_min=None)


def test_parada_rechaza_ventana_invertida():
    with pytest.raises(ValueError):
        Parada(lat=0, lon=0, ventana_inicio_min=100, ventana_fin_min=10)


def test_un_vehiculo_visita_todas_las_paradas():
    paradas = [DEPOSITO, PUEBLA, TOLUCA, CUERNAVACA]
    vehiculos = [Vehiculo(capacidad=100)]

    solucion = resolver_vrp(paradas, vehiculos)

    assert solucion is not None
    assert len(solucion.rutas) == 1
    ruta = solucion.rutas[0]
    # visita las 4 paradas (el deposito aparece al inicio y al final)
    assert set(ruta.orden_paradas) == {0, 1, 2, 3}
    assert ruta.orden_paradas[0] == 0
    assert ruta.orden_paradas[-1] == 0
    assert ruta.distancia_km > 0
    assert solucion.distancia_total_km == ruta.distancia_km


def test_capacidad_insuficiente_reparte_entre_dos_vehiculos():
    paradas = [DEPOSITO, PUEBLA, TOLUCA, CUERNAVACA, QUERETARO]  # demanda total = 20
    vehiculos = [Vehiculo(capacidad=10), Vehiculo(capacidad=10)]

    solucion = resolver_vrp(paradas, vehiculos)

    assert solucion is not None
    assert len(solucion.rutas) == 2
    todas_las_paradas_visitadas = set()
    for ruta in solucion.rutas:
        demanda_ruta = sum(paradas[i].demanda for i in ruta.orden_paradas)
        assert demanda_ruta <= 10
        todas_las_paradas_visitadas.update(ruta.orden_paradas)
    assert todas_las_paradas_visitadas == {0, 1, 2, 3, 4}


def test_demanda_total_excede_capacidad_total_no_tiene_solucion():
    paradas = [DEPOSITO, PUEBLA, TOLUCA, CUERNAVACA, QUERETARO]  # demanda total = 20
    vehiculos = [Vehiculo(capacidad=5)]  # ni cerca de alcanzar

    solucion = resolver_vrp(paradas, vehiculos)

    assert solucion is None


def test_sin_paradas_o_sin_vehiculos_no_tiene_solucion():
    assert resolver_vrp([], [Vehiculo(capacidad=10)]) is None
    assert resolver_vrp([DEPOSITO, PUEBLA], []) is None


def test_ventana_de_tiempo_imposible_no_tiene_solucion():
    lejos = Parada(lat=20.5888, lon=-100.3899, ventana_inicio_min=0, ventana_fin_min=1)
    paradas = [DEPOSITO, lejos]
    vehiculos = [Vehiculo(capacidad=10)]

    solucion = resolver_vrp(paradas, vehiculos, velocidad_kmh=40.0)

    assert solucion is None


def test_ventana_de_tiempo_holgada_si_tiene_solucion():
    paradas = [
        DEPOSITO,
        Parada(lat=19.0414, lon=-98.2063, ventana_inicio_min=0, ventana_fin_min=600),
    ]
    vehiculos = [Vehiculo(capacidad=10)]

    solucion = resolver_vrp(paradas, vehiculos)

    assert solucion is not None


def test_matriz_km_precalculada_se_usa_en_vez_de_haversine():
    # Distancia real muy distinta a la haversine (~100km), a proposito,
    # para poder confirmar que sí se uso la matriz dada.
    paradas = [DEPOSITO, PUEBLA]
    vehiculos = [Vehiculo(capacidad=10)]
    matriz_falsa = [[0, 999], [999, 0]]

    solucion = resolver_vrp(paradas, vehiculos, matriz_km=matriz_falsa)

    assert solucion is not None
    assert solucion.distancia_total_km == pytest.approx(999 * 2, abs=0.01)


def test_matriz_min_precalculada_se_usa_para_ventanas_de_tiempo():
    # Con la matriz de distancia normal, a 40km/h esta parada es
    # alcanzable en la ventana. Si en vez de eso se manda una matriz de
    # tiempo (matriz_min) que dice que tarda mucho mas, debe volverse
    # infactible: confirma que si se esta usando matriz_min y no
    # recalculando desde matriz_km/velocidad_kmh.
    lejos = Parada(lat=19.0414, lon=-98.2063, ventana_inicio_min=0, ventana_fin_min=60)
    paradas = [DEPOSITO, lejos]
    vehiculos = [Vehiculo(capacidad=10)]
    matriz_km = matriz_haversine_km(paradas)
    matriz_min_lenta = [[0, 500], [500, 0]]  # muy por encima de la ventana de 60 min

    solucion = resolver_vrp(
        paradas, vehiculos, matriz_km=matriz_km, matriz_min=matriz_min_lenta
    )

    assert solucion is None
