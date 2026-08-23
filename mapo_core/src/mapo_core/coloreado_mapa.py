"""Coloreado de mapas tipo "teorema de las 4 colores": asigna un color
(un indice, no un color de verdad) a cada poligono de un mapa para que
dos poligonos vecinos nunca compartan color. Es una necesidad de
presentacion visual (que un mapa categorico se lea bien), no de
analisis: no le dice nada nuevo al usuario sobre los datos, solo evita
que dos regiones vecinas se confundan por tener el mismo color.

El teorema garantiza que 4 colores alcanzan para cualquier mapa plano,
pero encontrar ESA coloracion optima es NP-dificil en general. Aqui se
usa Welsh-Powell (greedy: ordena por numero de vecinos, de mas a
menos, y le da a cada poligono el primer color libre entre sus vecinos
ya coloreados), que es el estandar practico para esto. Casi siempre da
4 colores o cerca para mapas reales, pero no lo garantiza: el
resultado siempre trae `num_colores`, honesto, en vez de asumir que
son 4.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely import STRtree
from shapely.geometry import shape


@dataclass
class PoligonoColoreable:
    id: str
    geometria: dict  # geometria GeoJSON (Polygon o MultiPolygon)


@dataclass
class ResultadoColoreado:
    color_por_id: dict[str, int]
    num_colores: int


def _son_adyacentes(geom_a, geom_b) -> bool:
    """Vecinos de verdad: comparten un tramo de frontera, no solo un
    vertice. Dos poligonos que solo se tocan en una esquina (como en
    un tablero de ajedrez) no cuentan como vecinos para este problema,
    igual que en el mapa de colores clasico."""
    interseccion = geom_a.boundary.intersection(geom_b.boundary)
    return not interseccion.is_empty and interseccion.length > 0


def construir_adyacencias(poligonos: list[PoligonoColoreable]) -> dict[str, set[str]]:
    """Grafo de adyacencia (quien colinda con quien). Usa un indice
    espacial (STRtree) para no comparar cada poligono contra todos los
    demas: con cientos o miles de AGEBs, la comparacion par-a-par
    ingenua se vuelve el cuello de botella."""
    ids = [p.id for p in poligonos]
    formas = [shape(p.geometria) for p in poligonos]
    arbol = STRtree(formas)

    vecinos: dict[str, set[str]] = {id_: set() for id_ in ids}
    for i, geom in enumerate(formas):
        for j in arbol.query(geom):
            if j <= i:
                continue
            if _son_adyacentes(geom, formas[j]):
                vecinos[ids[i]].add(ids[j])
                vecinos[ids[j]].add(ids[i])

    return vecinos


def colorear_mapa(poligonos: list[PoligonoColoreable]) -> ResultadoColoreado:
    if not poligonos:
        return ResultadoColoreado(color_por_id={}, num_colores=0)

    vecinos = construir_adyacencias(poligonos)

    orden = sorted(vecinos.keys(), key=lambda id_: len(vecinos[id_]), reverse=True)

    color_por_id: dict[str, int] = {}
    for id_ in orden:
        colores_vecinos = {color_por_id[v] for v in vecinos[id_] if v in color_por_id}
        color = 0
        while color in colores_vecinos:
            color += 1
        color_por_id[id_] = color

    num_colores = max(color_por_id.values(), default=-1) + 1
    return ResultadoColoreado(color_por_id=color_por_id, num_colores=num_colores)
