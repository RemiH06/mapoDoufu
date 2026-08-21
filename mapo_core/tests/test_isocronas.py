import math

import pytest

from mapo_core.isocronas import calcular_isocrona

CDMX = (19.4326, -99.1332)


def _distancia_km_independiente(lat1, lon1, lat2, lon2) -> float:
    """Haversine calculada aparte del codigo bajo prueba, para no
    validar el modulo contra su propia implementacion."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class _OSRMFalso:
    def __init__(self, resultado=None, duracion_por_punto=None):
        self._resultado = resultado
        self._duracion_por_punto = duracion_por_punto

    async def duraciones_desde(self, origen, destinos):
        if self._duracion_por_punto is not None:
            return [self._duracion_por_punto(lat, lon) for lat, lon in destinos]
        return self._resultado


def _extraer_anillo(poligono: dict) -> list[tuple[float, float]]:
    # coordinates: [[[lon, lat], ...]] -> [(lat, lon), ...]
    return [(lat, lon) for lon, lat in poligono["coordinates"][0]]


@pytest.mark.asyncio
async def test_cae_a_circulo_aproximado_si_osrm_no_responde():
    osrm = _OSRMFalso(resultado=None)

    resultado = await calcular_isocrona(osrm, *CDMX, minutos=10, num_direcciones=8)

    assert resultado.metodo == "circulo_aproximado"
    anillo = _extraer_anillo(resultado.poligono)
    assert len(anillo) == 9  # 8 direcciones + se repite la primera para cerrar
    assert anillo[0] == anillo[-1]


@pytest.mark.asyncio
async def test_todo_alcanzable_llega_hasta_el_radio_maximo():
    osrm = _OSRMFalso(duracion_por_punto=lambda lat, lon: 0.0)  # todo "instantaneo"

    resultado = await calcular_isocrona(
        osrm, *CDMX, minutos=10, num_direcciones=8, velocidad_maxima_kmh=60.0
    )

    assert resultado.metodo == "osrm_real"
    radio_esperado_km = 60.0 * 10 / 60  # velocidad_maxima_kmh * minutos / 60
    anillo = _extraer_anillo(resultado.poligono)[:-1]
    for lat, lon in anillo:
        distancia = _distancia_km_independiente(*CDMX, lat, lon)
        assert distancia == pytest.approx(radio_esperado_km, rel=0.02)


@pytest.mark.asyncio
async def test_nada_alcanzable_colapsa_al_origen():
    osrm = _OSRMFalso(duracion_por_punto=lambda lat, lon: 9999.0)  # nada alcanzable

    resultado = await calcular_isocrona(osrm, *CDMX, minutos=10, num_direcciones=6)

    assert resultado.metodo == "osrm_real"
    anillo = _extraer_anillo(resultado.poligono)[:-1]
    for lat, lon in anillo:
        assert (lat, lon) == CDMX


@pytest.mark.asyncio
async def test_reparto_asimetrico_hace_el_poligono_mas_ancho_hacia_donde_es_rapido():
    # Al este (longitud mayor) todo es "rapido"; al oeste, todo "lento".
    def duracion(lat, lon):
        return 1.0 if lon >= CDMX[1] else 9999.0

    osrm = _OSRMFalso(duracion_por_punto=duracion)
    num_direcciones = 8

    resultado = await calcular_isocrona(
        osrm, *CDMX, minutos=10, num_direcciones=num_direcciones
    )

    # Separar por el rumbo de cada vertice (conocido de antemano), no
    # por su coordenada resultante: un vertice "nada alcanzable" se
    # colapsa exactamente al origen, con la misma longitud que CDMX,
    # lo que haria ambiguo filtrar por lon despues del hecho.
    anillo = _extraer_anillo(resultado.poligono)[:-1]
    distancias_este = []
    distancias_oeste = []
    for i, (lat, lon) in enumerate(anillo):
        rumbo = i * 360 / num_direcciones
        distancia = _distancia_km_independiente(*CDMX, lat, lon)
        if 0 < rumbo < 180:  # componente este (sin(rumbo) > 0)
            distancias_este.append(distancia)
        elif 180 < rumbo < 360:  # componente oeste
            distancias_oeste.append(distancia)

    assert max(distancias_este) > max(distancias_oeste)


@pytest.mark.asyncio
async def test_num_direcciones_minimo_produce_un_triangulo_cerrado():
    # calcular_isocrona no valida el minimo (eso lo hace el endpoint,
    # ver test_server_isocronas.py); aqui solo se confirma que con el
    # minimo razonable (3) sigue armando un poligono cerrado valido.
    osrm = _OSRMFalso(resultado=None)

    resultado = await calcular_isocrona(osrm, *CDMX, minutos=10, num_direcciones=3)

    anillo = _extraer_anillo(resultado.poligono)
    assert len(anillo) == 4
    assert anillo[0] == anillo[-1]
