"""Diagramas de Voronoi: para cada punto de un conjunto, el area del
plano mas cercana a ese punto que a cualquier otro. Responde preguntas
del tipo "a cual de estos N negocios le queda mas cerca cada lugar"
(area de influencia/cercania), util para el enfoque de comercio.

Usa lat/lon directo como coordenadas planas (x=lon, y=lat), sin
proyectar a un sistema equal-area: para comparar cercania relativa
entre puntos dentro de un mismo municipio o estado la distorsion es
despreciable, y evita meter una dependencia de proyeccion solo para
esto. Si algun dia hace falta precision a escala nacional (comparar
puntos muy separados en latitud), ahi si valdria la pena proyectar
antes de calcular.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import QhullError, Voronoi
from shapely.geometry import Polygon, box, mapping, shape


@dataclass
class PuntoVoronoi:
    lat: float
    lon: float
    id: str
    nombre: str | None = None


@dataclass
class ResultadoVoronoi:
    celdas: dict
    metodo: str  # "recortado_a_limite" | "recortado_a_caja_envolvente"


def _poligonos_finitos(vor: Voronoi, radio: float) -> tuple[list[list[int]], list[list[float]]]:
    """Convierte las regiones de un scipy.spatial.Voronoi (algunas
    infinitas, con el vertice -1 marcando el borde abierto) en
    poligonos finitos, extendiendo cada arista abierta `radio`
    unidades mas alla del vertice finito que sí tiene. Adaptacion
    directa del patron ya documentado para este problema exacto
    (scipy no resuelve esto por su cuenta, es una limitacion conocida
    de representar un diagrama de Voronoi sin fronteras)."""
    if vor.points.shape[1] != 2:
        raise ValueError("Voronoi de 2 dimensiones nada mas")

    nuevas_regiones = []
    nuevos_vertices = vor.vertices.tolist()
    centro = vor.points.mean(axis=0)

    aristas_por_punto: dict[int, list[tuple[int, int, int]]] = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        aristas_por_punto.setdefault(p1, []).append((p2, v1, v2))
        aristas_por_punto.setdefault(p2, []).append((p1, v1, v2))

    for p1, indice_region in enumerate(vor.point_region):
        vertices_region = vor.regions[indice_region]

        if all(v >= 0 for v in vertices_region):
            nuevas_regiones.append(vertices_region)
            continue

        nueva_region = [v for v in vertices_region if v >= 0]

        for p2, v1, v2 in aristas_por_punto[p1]:
            if v2 < 0:
                v1, v2 = v2, v1
            if v1 >= 0:
                continue  # arista ya finita de los dos lados, nada que extender

            tangente = vor.points[p2] - vor.points[p1]
            tangente /= np.linalg.norm(tangente)
            normal = np.array([-tangente[1], tangente[0]])

            punto_medio = vor.points[[p1, p2]].mean(axis=0)
            signo = np.sign(np.dot(punto_medio - centro, normal))
            punto_lejano = vor.vertices[v2] + normal * signo * radio

            nueva_region.append(len(nuevos_vertices))
            nuevos_vertices.append(punto_lejano.tolist())

        vs = np.asarray([nuevos_vertices[v] for v in nueva_region])
        c = vs.mean(axis=0)
        angulos = np.arctan2(vs[:, 1] - c[1], vs[:, 0] - c[0])
        nueva_region = list(np.array(nueva_region)[np.argsort(angulos)])

        nuevas_regiones.append(nueva_region)

    return nuevas_regiones, nuevos_vertices


def calcular_voronoi(
    puntos: list[PuntoVoronoi],
    limite: dict | None = None,
    margen_caja: float = 0.1,
) -> ResultadoVoronoi:
    """Diagrama de Voronoi de `puntos`, recortado a `limite` (geometria
    GeoJSON de un poligono/multipoligono, ej. un municipio) si se da,
    o a la caja envolvente de los puntos con un margen si no. Un punto
    cuya celda queda vacia despues del recorte (puede pasar si cae
    justo en el borde de `limite`) simplemente no aparece en el
    resultado, no se inventa una celda de area cero."""
    if len(puntos) < 3:
        raise ValueError("Se necesitan al menos 3 puntos para un diagrama de Voronoi.")

    coords = np.array([(p.lon, p.lat) for p in puntos])

    try:
        vor = Voronoi(coords)
    except QhullError as exc:
        raise ValueError(
            "Los puntos son colineales o coinciden entre si: no se puede construir un diagrama de Voronoi."
        ) from exc

    if limite is not None:
        area_limite = shape(limite)
        metodo = "recortado_a_limite"
    else:
        minx, miny = coords.min(axis=0)
        maxx, maxy = coords.max(axis=0)
        dx = (maxx - minx) * margen_caja or margen_caja
        dy = (maxy - miny) * margen_caja or margen_caja
        area_limite = box(minx - dx, miny - dy, maxx + dx, maxy + dy)
        metodo = "recortado_a_caja_envolvente"

    limx0, limy0, limx1, limy1 = area_limite.bounds
    radio = ((limx1 - limx0) ** 2 + (limy1 - limy0) ** 2) ** 0.5 * 2

    regiones, vertices = _poligonos_finitos(vor, radio)

    features = []
    for indice_punto, region in enumerate(regiones):
        if len(region) < 3:
            continue

        poligono = Polygon([vertices[v] for v in region])
        recortado = poligono.intersection(area_limite)
        if recortado.is_empty:
            continue

        punto = puntos[indice_punto]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": punto.id,
                    "nombre": punto.nombre,
                    "lat": punto.lat,
                    "lon": punto.lon,
                },
                "geometry": mapping(recortado),
            }
        )

    return ResultadoVoronoi(
        celdas={"type": "FeatureCollection", "features": features},
        metodo=metodo,
    )
