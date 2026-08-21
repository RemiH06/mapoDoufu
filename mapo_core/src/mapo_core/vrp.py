"""Motor VRP (ruteo de multiples vehiculos), via OR-Tools.

A diferencia del TSP de Gaiarda (un viajero libre, sin restricciones),
esto resuelve lo que Mapo si necesita: varios vehiculos, cada uno con
capacidad de carga, y paradas con ventana de tiempo de entrega. Se
evaluo escribir el heuristico a mano (como el TSP de Gaiarda, vecino
mas cercano + 2-opt) y se descarto: VRP con capacidad y ventanas de
tiempo es una clase de problema distinta (hay que decidir que parada
va con que vehiculo Y en que orden, con verificacion de factibilidad
en cada movimiento), no una extension menor del TSP. OR-Tools es la
libreria que se usa en produccion para exactamente este problema.

No calcula la matriz de distancias via OSRM todavia (esa pieza sigue
pendiente, ver MAPO_PENDIENTES.md); por ahora usa distancia en linea
recta (formula de haversine), igual que el fallback honesto que ya usa
Gaiarda cuando OSRM no responde. Cuando se vendorice el cliente OSRM,
solo hay que reemplazar `matriz_haversine_km` por una matriz real, la
funcion de resolver no cambia.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

_ESCALA_METROS = 1000  # OR-Tools trabaja con costos enteros; escalamos km -> metros


@dataclass
class Parada:
    lat: float
    lon: float
    demanda: int = 0
    ventana_inicio_min: int | None = None
    ventana_fin_min: int | None = None

    def __post_init__(self) -> None:
        tiene_inicio = self.ventana_inicio_min is not None
        tiene_fin = self.ventana_fin_min is not None
        if tiene_inicio != tiene_fin:
            raise ValueError("ventana_inicio_min y ventana_fin_min van juntas o ninguna")
        if tiene_inicio and self.ventana_inicio_min > self.ventana_fin_min:
            raise ValueError("ventana_inicio_min no puede ser mayor que ventana_fin_min")


@dataclass
class Vehiculo:
    capacidad: int


@dataclass
class RutaVehiculo:
    vehiculo_id: int
    orden_paradas: list[int]  # indices de Parada, en orden de visita (incluye deposito al inicio/fin)
    distancia_km: float


@dataclass
class SolucionVRP:
    rutas: list[RutaVehiculo] = field(default_factory=list)
    distancia_total_km: float = 0.0


def _distancia_haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radio_tierra_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radio_tierra_km * math.asin(math.sqrt(a))


def matriz_haversine_km(paradas: list[Parada]) -> list[list[float]]:
    """Matriz de distancia en linea recta entre cada par de paradas."""
    return [
        [_distancia_haversine_km(a.lat, a.lon, b.lat, b.lon) for b in paradas]
        for a in paradas
    ]


def resolver_vrp(
    paradas: list[Parada],
    vehiculos: list[Vehiculo],
    deposito: int = 0,
    velocidad_kmh: float = 40.0,
    tiempo_limite_segundos: int = 5,
    matriz_km: list[list[float]] | None = None,
    matriz_min: list[list[float]] | None = None,
) -> SolucionVRP | None:
    """Resuelve el VRP. Regresa `None` si no hay solucion factible con
    esas restricciones (ej. la demanda total no cabe en la capacidad
    disponible, o una ventana de tiempo es imposible de cumplir), en
    vez de forzar una respuesta incorrecta.

    `matriz_km`/`matriz_min`: si se dan (ej. del cliente OSRM,
    distancia y duracion real por carretera), se usan tal cual en vez
    de estimarlas. Sin ellas, cae a linea recta (haversine) para
    distancia, y a `distancia / velocidad_kmh` para tiempo, igual que
    el fallback honesto que ya usa Gaiarda cuando OSRM no responde.
    """
    if not paradas or not vehiculos:
        return None

    matriz_km = matriz_km if matriz_km is not None else matriz_haversine_km(paradas)
    n = len(paradas)

    manager = pywrapcp.RoutingIndexManager(n, len(vehiculos), deposito)
    routing = pywrapcp.RoutingModel(manager)

    def distancia_callback(desde_idx: int, hasta_idx: int) -> int:
        desde = manager.IndexToNode(desde_idx)
        hasta = manager.IndexToNode(hasta_idx)
        return round(matriz_km[desde][hasta] * _ESCALA_METROS)

    indice_transito = routing.RegisterTransitCallback(distancia_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(indice_transito)

    def demanda_callback(idx: int) -> int:
        return paradas[manager.IndexToNode(idx)].demanda

    indice_demanda = routing.RegisterUnaryTransitCallback(demanda_callback)
    routing.AddDimensionWithVehicleCapacity(
        indice_demanda,
        0,  # sin holgura de capacidad
        [v.capacidad for v in vehiculos],
        True,  # cada vehiculo arranca vacio
        "Capacidad",
    )

    hay_ventanas = any(p.ventana_inicio_min is not None for p in paradas)
    if hay_ventanas:
        def tiempo_callback(desde_idx: int, hasta_idx: int) -> int:
            desde = manager.IndexToNode(desde_idx)
            hasta = manager.IndexToNode(hasta_idx)
            if matriz_min is not None:
                return round(matriz_min[desde][hasta])
            horas = matriz_km[desde][hasta] / velocidad_kmh
            return round(horas * 60)

        indice_tiempo = routing.RegisterTransitCallback(tiempo_callback)
        horizonte_min = 24 * 60
        routing.AddDimension(
            indice_tiempo,
            horizonte_min,  # holgura maxima (tiempo de espera permitido en una parada)
            horizonte_min,  # tiempo maximo por vehiculo
            False,
            "Tiempo",
        )
        dimension_tiempo = routing.GetDimensionOrDie("Tiempo")
        for i, parada in enumerate(paradas):
            if parada.ventana_inicio_min is None:
                continue
            idx = manager.NodeToIndex(i)
            dimension_tiempo.CumulVar(idx).SetRange(
                parada.ventana_inicio_min, parada.ventana_fin_min
            )

    parametros = pywrapcp.DefaultRoutingSearchParameters()
    parametros.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    parametros.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    parametros.time_limit.FromSeconds(tiempo_limite_segundos)

    solucion = routing.SolveWithParameters(parametros)
    if solucion is None:
        return None

    rutas = []
    distancia_total_km = 0.0
    for vehiculo_id in range(len(vehiculos)):
        idx = routing.Start(vehiculo_id)
        orden = []
        distancia_ruta_km = 0.0
        while not routing.IsEnd(idx):
            orden.append(manager.IndexToNode(idx))
            idx_siguiente = solucion.Value(routing.NextVar(idx))
            distancia_ruta_km += (
                routing.GetArcCostForVehicle(idx, idx_siguiente, vehiculo_id) / _ESCALA_METROS
            )
            idx = idx_siguiente
        orden.append(manager.IndexToNode(idx))

        rutas.append(
            RutaVehiculo(
                vehiculo_id=vehiculo_id,
                orden_paradas=orden,
                distancia_km=round(distancia_ruta_km, 3),
            )
        )
        distancia_total_km += distancia_ruta_km

    return SolucionVRP(rutas=rutas, distancia_total_km=round(distancia_total_km, 3))
