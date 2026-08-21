import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mapo_core.gaiarda_client import GaiardaClient
from mapo_core.isocronas import calcular_isocrona
from mapo_core.osrm_client import OSRMClient
from mapo_core.vrp import Parada, Vehiculo, resolver_vrp

app = FastAPI(title="mapo_core")

_gaiarda_client: GaiardaClient | None = None
_osrm_client: OSRMClient | None = None


def get_gaiarda_client() -> GaiardaClient:
    global _gaiarda_client
    if _gaiarda_client is None:
        _gaiarda_client = GaiardaClient()
    return _gaiarda_client


def get_osrm_client() -> OSRMClient:
    global _osrm_client
    if _osrm_client is None:
        _osrm_client = OSRMClient()
    return _osrm_client


@app.exception_handler(httpx.TransportError)
async def gaiarda_no_disponible(request: Request, exc: httpx.TransportError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"error": "Gaiarda no esta disponible ahorita mismo.", "detalle": str(exc)},
    )


@app.exception_handler(httpx.HTTPStatusError)
async def gaiarda_respondio_error(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": "Gaiarda respondio con un error.",
            "status_gaiarda": exc.response.status_code,
        },
    )


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}


@app.get("/gaiarda/status")
async def gaiarda_status(client: GaiardaClient = Depends(get_gaiarda_client)) -> dict:
    """Prueba viva de la conexion: le pasa directo el /status de Gaiarda."""
    return await client.status()


@app.get("/gaiarda/municipios")
async def gaiarda_municipios(
    cve_ent: str | None = None, client: GaiardaClient = Depends(get_gaiarda_client)
) -> dict:
    return await client.municipios(cve_ent=cve_ent)


class ParadaEntrada(BaseModel):
    lat: float
    lon: float
    demanda: int = 0
    ventana_inicio_min: int | None = None
    ventana_fin_min: int | None = None


class SolicitudVRP(BaseModel):
    paradas: list[ParadaEntrada]
    capacidades_vehiculos: list[int]
    deposito: int = 0
    velocidad_kmh: float = 40.0


@app.post("/vrp/calcular")
async def vrp_calcular(
    solicitud: SolicitudVRP, osrm: OSRMClient = Depends(get_osrm_client)
) -> dict:
    """VRP con capacidad y ventanas de tiempo, via OR-Tools. Intenta
    distancia y duracion real por carretera (OSRM) primero; si el
    servicio no responde o algun tramo no es alcanzable, cae de vuelta
    a linea recta (haversine), igual que el fallback honesto que ya
    usa Gaiarda. El campo `metodo` de la respuesta siempre dice cual
    de los dos se uso, nunca se le hace pasar una aproximacion por un
    dato confirmado."""
    if solicitud.deposito < 0 or solicitud.deposito >= len(solicitud.paradas):
        raise HTTPException(400, "deposito debe ser un indice valido de paradas")

    paradas = [
        Parada(
            lat=p.lat,
            lon=p.lon,
            demanda=p.demanda,
            ventana_inicio_min=p.ventana_inicio_min,
            ventana_fin_min=p.ventana_fin_min,
        )
        for p in solicitud.paradas
    ]
    vehiculos = [Vehiculo(capacidad=c) for c in solicitud.capacidades_vehiculos]

    resultado_osrm = await osrm.matriz_carretera([(p.lat, p.lon) for p in paradas])

    if resultado_osrm is not None:
        solucion = resolver_vrp(
            paradas,
            vehiculos,
            deposito=solicitud.deposito,
            matriz_km=resultado_osrm["distancias_km"],
            matriz_min=resultado_osrm["duraciones_min"],
        )
        metodo = "carretera_real"
    else:
        solucion = resolver_vrp(
            paradas,
            vehiculos,
            deposito=solicitud.deposito,
            velocidad_kmh=solicitud.velocidad_kmh,
        )
        metodo = "linea_recta_aproximada"

    if solucion is None:
        raise HTTPException(
            422, "No se encontro una solucion factible con esas restricciones."
        )

    return {
        "rutas": [
            {
                "vehiculo_id": r.vehiculo_id,
                "orden_paradas": r.orden_paradas,
                "distancia_km": r.distancia_km,
            }
            for r in solucion.rutas
        ],
        "distancia_total_km": solucion.distancia_total_km,
        "metodo": metodo,
    }


class SolicitudIsocrona(BaseModel):
    lat: float
    lon: float
    minutos: float
    num_direcciones: int = 16


@app.post("/isocronas/calcular")
async def isocronas_calcular(
    solicitud: SolicitudIsocrona, osrm: OSRMClient = Depends(get_osrm_client)
) -> dict:
    """Poligono del area alcanzable desde (lat, lon) en `minutos`,
    por carretera real (OSRM) si esta disponible; circulo aproximado
    si no. El campo `metodo` siempre dice cual de los dos se uso."""
    if solicitud.minutos <= 0:
        raise HTTPException(400, "minutos debe ser mayor que 0")
    if solicitud.num_direcciones < 3:
        raise HTTPException(400, "num_direcciones debe ser al menos 3")

    resultado = await calcular_isocrona(
        osrm,
        solicitud.lat,
        solicitud.lon,
        solicitud.minutos,
        num_direcciones=solicitud.num_direcciones,
    )

    return {"poligono": resultado.poligono, "metodo": resultado.metodo}
