"""Isocronas: el area alcanzable desde un punto en N minutos.

Enfoque: samplear puntos candidatos en varias direcciones alrededor
del origen, pedirle a OSRM la duracion real por carretera a cada uno
(una sola llamada al servicio `table`, `sources=0`, no N llamadas
sueltas), y quedarse con el punto mas lejano alcanzable en cada
direccion para armar un poligono. Es una aproximacion (un poligono de
`num_direcciones` vertices, no el area exacta alcanzable), pero usa
distancia REAL por carretera, no un circulo. Si OSRM no responde, cae
a un circulo aproximado (haversine + velocidad promedio asumida),
igual que el fallback honesto que ya usa el resto del proyecto: el
campo `metodo` de la respuesta siempre dice cual de los dos se uso.

No se metio un motor de isocronas nativo (Valhalla, Openrouteservice)
a proposito: ya tenemos OSRM integrado para VRP, meter un SEGUNDO
motor de ruteo solo para isocronas duplicaria infraestructura (otro
servicio que levantar y mantener) por una ganancia de precision
marginal sobre este metodo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mapo_core.osrm_client import OSRMClient

_RADIO_TIERRA_KM = 6371.0
_VELOCIDAD_FALLBACK_KMH = 30.0  # asumida solo para el circulo aproximado


@dataclass
class ResultadoIsocrona:
    poligono: dict  # GeoJSON Polygon
    metodo: str  # "osrm_real" | "circulo_aproximado"


def _punto_a_distancia_y_rumbo(
    lat: float, lon: float, distancia_km: float, rumbo_grados: float
) -> tuple[float, float]:
    """Punto a `distancia_km` de (lat, lon) en direccion `rumbo_grados`
    (0 = norte, 90 = este). Aproximacion equirectangular: suficiente
    para las distancias cortas de una isocrona, no es una proyeccion
    cartografica real (mismo nivel de aproximacion que el resto de los
    calculos honestos de Mapo/Gaiarda)."""
    rumbo = math.radians(rumbo_grados)
    dlat = (distancia_km / _RADIO_TIERRA_KM) * math.cos(rumbo)
    dlon = (distancia_km / (_RADIO_TIERRA_KM * math.cos(math.radians(lat)))) * math.sin(rumbo)
    return lat + math.degrees(dlat), lon + math.degrees(dlon)


def _anillo_a_poligono(anillo: list[tuple[float, float]]) -> dict:
    cerrado = [*anillo, anillo[0]]
    return {"type": "Polygon", "coordinates": [[[lon, lat] for lat, lon in cerrado]]}


def _circulo_aproximado(lat: float, lon: float, minutos: float, num_direcciones: int) -> dict:
    radio_km = _VELOCIDAD_FALLBACK_KMH * minutos / 60
    anillo = [
        _punto_a_distancia_y_rumbo(lat, lon, radio_km, i * 360 / num_direcciones)
        for i in range(num_direcciones)
    ]
    return _anillo_a_poligono(anillo)


async def calcular_isocrona(
    osrm: OSRMClient,
    lat: float,
    lon: float,
    minutos: float,
    num_direcciones: int = 16,
    muestras_por_direccion: int = 6,
    velocidad_maxima_kmh: float = 90.0,
) -> ResultadoIsocrona:
    """Isocrona real por carretera si OSRM responde; circulo
    aproximado si no. Nunca truena."""
    radio_maximo_km = velocidad_maxima_kmh * minutos / 60

    candidatos: list[tuple[int, float, float, float]] = []  # (direccion, distancia_km, lat, lon)
    for direccion in range(num_direcciones):
        rumbo = direccion * 360 / num_direcciones
        for muestra in range(1, muestras_por_direccion + 1):
            distancia_km = radio_maximo_km * muestra / muestras_por_direccion
            p_lat, p_lon = _punto_a_distancia_y_rumbo(lat, lon, distancia_km, rumbo)
            candidatos.append((direccion, distancia_km, p_lat, p_lon))

    duraciones = await osrm.duraciones_desde((lat, lon), [(c[2], c[3]) for c in candidatos])

    if duraciones is None:
        return ResultadoIsocrona(
            poligono=_circulo_aproximado(lat, lon, minutos, num_direcciones),
            metodo="circulo_aproximado",
        )

    mas_lejano_por_direccion: dict[int, tuple[float, float, float]] = {}
    for (direccion, distancia_km, p_lat, p_lon), duracion_min in zip(candidatos, duraciones):
        if duracion_min > minutos:
            continue
        actual = mas_lejano_por_direccion.get(direccion)
        if actual is None or distancia_km > actual[0]:
            mas_lejano_por_direccion[direccion] = (distancia_km, p_lat, p_lon)

    anillo = []
    for direccion in range(num_direcciones):
        if direccion in mas_lejano_por_direccion:
            _, p_lat, p_lon = mas_lejano_por_direccion[direccion]
        else:
            # nada alcanzable en esa direccion dentro del tiempo dado:
            # se pega al origen en vez de inventar un punto
            p_lat, p_lon = lat, lon
        anillo.append((p_lat, p_lon))

    return ResultadoIsocrona(poligono=_anillo_a_poligono(anillo), metodo="osrm_real")
