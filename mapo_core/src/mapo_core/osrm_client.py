"""Cliente del motor de ruteo real por carretera (OSRM).

Vendorizado y adaptado de Gaiarda (`gaiarda/src/gaiarda/ruteo_osrm.py`):
la API HTTP de OSRM es identica self-hosted o demo publico, asi que
este cliente funciona igual apuntando a cualquiera de los dos.

Diferencias deliberadas contra la version de Gaiarda (no es una copia
literal, es una adaptacion a como ya esta armado mapo_core):
- httpx async, no requests sincrono (mapo_core ya es async de punta a
  punta, ver gaiarda_client.py).
- Variable de entorno propia (MAPO_OSRM_URL), independiente de la de
  Gaiarda (GAIARDA_OSRM_URL): mapo_core no depende del codigo de
  Gaiarda para nada (mapo <-> mapo_core <-> Gaiarda, cada quien su
  propia config), aunque en la practica apunten al mismo servidor.
- Duraciones en minutos, no horas: vrp.py ya trabaja las ventanas de
  tiempo en minutos.

Mismo principio honesto que el original: nunca inventa una distancia.
Si el servicio no responde, o un tramo no es alcanzable por carretera
(OSRM regresa null en esa celda), regresa `None` completo (una matriz
a medias no sirve para el VRP), y quien llama decide si cae de vuelta
a haversine.
"""

from __future__ import annotations

import os

import httpx

OSRM_URL_ENV_VAR = "MAPO_OSRM_URL"
OSRM_BASE_URL_DEMO = "https://router.project-osrm.org"
TIMEOUT_SEGUNDOS = 15.0


def _url_por_defecto() -> str:
    return os.environ.get(OSRM_URL_ENV_VAR, OSRM_BASE_URL_DEMO).rstrip("/")


def _coords_url(coords: list[tuple[float, float]]) -> str:
    # OSRM espera "lon,lat;lon,lat;...": al reves del orden (lat, lon)
    # que usa el resto de mapo_core (ver vrp.Parada).
    return ";".join(f"{lon},{lat}" for lat, lon in coords)


class OSRMClient:
    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or _url_por_defecto(),
            transport=transport,
            timeout=TIMEOUT_SEGUNDOS,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def matriz_carretera(self, coords: list[tuple[float, float]]) -> dict | None:
        """Matriz real de distancias (km) y duraciones (min) por
        carretera entre TODOS los pares de puntos, en una sola llamada
        al servicio `table` de OSRM (no N^2 llamadas sueltas).

        `None` si el servicio no responde, o si algun tramo no es
        alcanzable por carretera (una matriz incompleta rompe las
        sumas del VRP, se descarta entera en vez de repararla).
        """
        if len(coords) < 2:
            return {"distancias_km": [[0.0]], "duraciones_min": [[0.0]]}

        try:
            respuesta = await self._client.get(
                f"/table/v1/driving/{_coords_url(coords)}",
                params={"annotations": "distance,duration"},
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
        except (httpx.HTTPError, ValueError):
            return None

        if datos.get("code") != "Ok":
            return None

        distancias_m = datos.get("distances")
        duraciones_s = datos.get("durations")
        if distancias_m is None or duraciones_s is None:
            return None
        if any(d is None for fila in distancias_m for d in fila):
            return None
        if any(d is None for fila in duraciones_s for d in fila):
            return None

        return {
            "distancias_km": [[round(d / 1000, 3) for d in fila] for fila in distancias_m],
            "duraciones_min": [[round(d / 60, 2) for d in fila] for fila in duraciones_s],
        }

    async def duraciones_desde(
        self, origen: tuple[float, float], destinos: list[tuple[float, float]]
    ) -> list[float] | None:
        """Duracion (minutos) desde `origen` a cada punto de `destinos`,
        en una sola llamada al servicio `table` de OSRM con `sources=0`.

        A diferencia de `matriz_carretera` (que pide la matriz completa
        NxN entre todos los pares), esto solo pide una fila: mucho mas
        barato cuando el origen es fijo y solo interesa que tan lejos
        se llega desde ahi (isocronas). `None` si el servicio no
        responde o algun destino no es alcanzable.
        """
        coords = [origen, *destinos]
        try:
            respuesta = await self._client.get(
                f"/table/v1/driving/{_coords_url(coords)}",
                params={"sources": "0", "annotations": "duration"},
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
        except (httpx.HTTPError, ValueError):
            return None

        if datos.get("code") != "Ok":
            return None

        duraciones_s = datos.get("durations")
        if not duraciones_s:
            return None
        fila = duraciones_s[0]
        if any(d is None for d in fila):
            return None

        return [round(d / 60, 2) for d in fila[1:]]

    async def geometria_ruta(self, coords_en_orden: list[tuple[float, float]]) -> dict | None:
        """GeoJSON LineString de la ruta real por carretera, siguiendo
        el orden de visita ya decidido (no solo tramos rectos entre
        paradas). `None` si el servicio no responde o no hay una ruta
        continua entre todos los puntos en ese orden.
        """
        if len(coords_en_orden) < 2:
            return None

        try:
            respuesta = await self._client.get(
                f"/route/v1/driving/{_coords_url(coords_en_orden)}",
                params={"overview": "full", "geometries": "geojson"},
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
        except (httpx.HTTPError, ValueError):
            return None

        if datos.get("code") != "Ok" or not datos.get("routes"):
            return None
        return datos["routes"][0]["geometry"]
