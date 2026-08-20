import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mapo_core.gaiarda_client import GaiardaClient
from mapo_core.vrp import Parada, Vehiculo, resolver_vrp

app = FastAPI(title="mapo_core")

_gaiarda_client: GaiardaClient | None = None


def get_gaiarda_client() -> GaiardaClient:
    global _gaiarda_client
    if _gaiarda_client is None:
        _gaiarda_client = GaiardaClient()
    return _gaiarda_client


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
def vrp_calcular(solicitud: SolicitudVRP) -> dict:
    """VRP con capacidad y ventanas de tiempo, via OR-Tools. Distancia
    en linea recta (haversine) por ahora, no OSRM todavia (ver
    MAPO_PENDIENTES.md)."""
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

    solucion = resolver_vrp(
        paradas,
        vehiculos,
        deposito=solicitud.deposito,
        velocidad_kmh=solicitud.velocidad_kmh,
    )

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
        "metodo": "linea_recta_aproximada",
    }
