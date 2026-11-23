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

import json
import math
from dataclasses import dataclass

from mapo_core.osrm_client import OSRMClient

_RADIO_TIERRA_KM = 6371.0
VELOCIDAD_FALLBACK_KMH = 30.0  # asumida solo para el circulo aproximado

# Cada muestra de una direccion queda a este factor de la siguiente: mas
# juntas cerca del origen. El radio supone 90 km/h, y en ciudad se llega a una
# fraccion: con pasos iguales, 5 minutos saltan de 1.25 en 1.25 km y casi
# ninguna direccion alcanza la primera muestra (salia un triangulo).
_FACTOR_MUESTRAS = 0.63


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
    radio_km = VELOCIDAD_FALLBACK_KMH * minutos / 60
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
            distancia_km = radio_maximo_km * _FACTOR_MUESTRAS ** (muestras_por_direccion - muestra)
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


# Isócronas apilables (sesión 29d): cuánta gente vive dentro de cada una, en todas
# (intersección) y en alguna (unión). Una persona se cuenta donde cae el punto de su
# lugar, igual que en /riesgos y /accesibilidad: el punto de dentro del AGEB urbano
# con su censo, o el de la localidad del ITER si su AGEB no está cargado.
MAX_ISOCRONAS = 5

METODO_POBLACION = (
    "Censo 2020: la población de cada AGEB urbana cuenta entera donde cae su punto de dentro, y la de"
    " cada localidad sin AGEB cargada, donde cae su punto (ITER). No se reparte por área: una AGEB"
    " partida por el borde cuenta de un solo lado."
)

_SQL_POBLACION = """
WITH p AS (
    SELECT t.i, ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(t.g), 4326)) AS geom
    FROM unnest(%(gs)s::text[]) WITH ORDINALITY AS t(g, i)
), todo AS MATERIALIZED (SELECT ST_Union(geom) AS geom FROM p),
u AS (
    SELECT 'a' || a.cvegeo AS id, ST_PointOnSurface(a.geom) AS punto, c.pobtot AS pob
    FROM agebs a JOIN fuente_censo_poblacion c ON c.cvegeo = a.cvegeo AND c.nivel = 'ageb', todo
    WHERE a.geom && todo.geom AND ST_Intersects(todo.geom, ST_PointOnSurface(a.geom))
    UNION ALL
    SELECT 'l' || l.cvegeo, l.geom, l.pobtot
    FROM localidades l, todo
    WHERE l.geom && todo.geom AND ST_Intersects(todo.geom, l.geom)
      AND NOT EXISTS (SELECT 1 FROM agebs a WHERE a.geom && l.geom AND ST_Covers(a.geom, l.geom))
)
SELECT u.id, u.pob, array_agg(p.i ORDER BY p.i) AS dentro
FROM u JOIN p ON p.geom && u.punto AND ST_Intersects(p.geom, u.punto)
GROUP BY u.id, u.pob
"""


def _suma(valores: list[int | None]) -> dict:
    # INEGI reserva la población de lugares con muy pocas viviendas: no es cero.
    return {"personas": sum(v for v in valores if v is not None),
            "lugares": len(valores), "reservados": sum(1 for v in valores if v is None)}


async def poblacion(pool, poligonos: list[dict]) -> dict:
    """Personas dentro de cada polígono, en todos y en alguno, con la intersección
    para dibujarla (None si no se tocan todos)."""
    from shapely.geometry import mapping, shape

    if not 1 <= len(poligonos) <= MAX_ISOCRONAS:
        raise ValueError(f"de 1 a {MAX_ISOCRONAS} isócronas")
    formas = [shape(p).buffer(0) for p in poligonos]
    async with pool.connection() as conn:
        cur = await conn.execute(_SQL_POBLACION, {"gs": [json.dumps(p) for p in poligonos]})
        filas = await cur.fetchall()

    n = len(poligonos)
    interseccion = formas[0]
    for f in formas[1:]:
        interseccion = interseccion.intersection(f)
    return {
        "cada_una": [_suma([pob for _id, pob, dentro in filas if i + 1 in dentro]) for i in range(n)],
        "en_todas": _suma([pob for _id, pob, dentro in filas if len(dentro) == n]) if n > 1 else None,
        "en_alguna": _suma([pob for _id, pob, _dentro in filas]) if n > 1 else None,
        "interseccion": mapping(interseccion) if n > 1 and not interseccion.is_empty else None,
        "metodo": METODO_POBLACION,
    }
