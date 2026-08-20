import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from mapo_core.gaiarda_client import GaiardaClient

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
