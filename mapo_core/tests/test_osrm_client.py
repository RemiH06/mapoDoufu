import httpx
import pytest

from mapo_core.osrm_client import OSRMClient

CDMX = (19.4326, -99.1332)
PUEBLA = (19.0414, -98.2063)


def _cliente_con_respuesta(capturar: dict, cuerpo, status_code: int = 200) -> OSRMClient:
    def handler(request: httpx.Request) -> httpx.Response:
        capturar["path"] = request.url.path
        capturar["query"] = str(request.url.params)
        return httpx.Response(status_code, json=cuerpo)

    transport = httpx.MockTransport(handler)
    return OSRMClient(base_url="http://osrm.test", transport=transport)


@pytest.mark.asyncio
async def test_matriz_carretera_manda_coordenadas_en_orden_lon_lat():
    capturado = {}
    cuerpo = {"code": "Ok", "distances": [[0, 130000], [130000, 0]], "durations": [[0, 5400], [5400, 0]]}
    cliente = _cliente_con_respuesta(capturado, cuerpo)

    await cliente.matriz_carretera([CDMX, PUEBLA])

    assert capturado["path"] == "/table/v1/driving/-99.1332,19.4326;-98.2063,19.0414"
    await cliente.aclose()


@pytest.mark.asyncio
async def test_matriz_carretera_convierte_metros_a_km_y_segundos_a_minutos():
    capturado = {}
    cuerpo = {"code": "Ok", "distances": [[0, 130000], [130000, 0]], "durations": [[0, 5400], [5400, 0]]}
    cliente = _cliente_con_respuesta(capturado, cuerpo)

    resultado = await cliente.matriz_carretera([CDMX, PUEBLA])

    assert resultado["distancias_km"] == [[0, 130.0], [130.0, 0]]
    assert resultado["duraciones_min"] == [[0, 90.0], [90.0, 0]]
    await cliente.aclose()


@pytest.mark.asyncio
async def test_matriz_carretera_con_un_solo_punto_no_pega_a_la_red():
    llamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        return httpx.Response(200, json={})

    cliente = OSRMClient(base_url="http://osrm.test", transport=httpx.MockTransport(handler))

    resultado = await cliente.matriz_carretera([CDMX])

    assert resultado == {"distancias_km": [[0.0]], "duraciones_min": [[0.0]]}
    assert llamadas == []
    await cliente.aclose()


@pytest.mark.asyncio
async def test_matriz_carretera_regresa_none_si_osrm_no_dice_ok():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {"code": "NoRoute"})

    resultado = await cliente.matriz_carretera([CDMX, PUEBLA])

    assert resultado is None
    await cliente.aclose()


@pytest.mark.asyncio
async def test_matriz_carretera_regresa_none_si_algun_tramo_no_es_alcanzable():
    capturado = {}
    # Un tramo no alcanzable (isla, sin via mapeada): OSRM regresa null ahi.
    cuerpo = {
        "code": "Ok",
        "distances": [[0, None], [None, 0]],
        "durations": [[0, 100], [100, 0]],
    }
    cliente = _cliente_con_respuesta(capturado, cuerpo)

    resultado = await cliente.matriz_carretera([CDMX, PUEBLA])

    assert resultado is None
    await cliente.aclose()


@pytest.mark.asyncio
async def test_matriz_carretera_regresa_none_si_el_servicio_no_responde():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no conecta", request=request)

    cliente = OSRMClient(base_url="http://osrm.test", transport=httpx.MockTransport(handler))

    resultado = await cliente.matriz_carretera([CDMX, PUEBLA])

    assert resultado is None
    await cliente.aclose()


@pytest.mark.asyncio
async def test_matriz_carretera_regresa_none_si_osrm_responde_con_error_http():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {"detail": "error"}, status_code=500)

    resultado = await cliente.matriz_carretera([CDMX, PUEBLA])

    assert resultado is None
    await cliente.aclose()


@pytest.mark.asyncio
async def test_geometria_ruta_regresa_el_linestring():
    capturado = {}
    cuerpo = {
        "code": "Ok",
        "routes": [{"geometry": {"type": "LineString", "coordinates": [[-99.1, 19.4], [-98.2, 19.0]]}}],
    }
    cliente = _cliente_con_respuesta(capturado, cuerpo)

    resultado = await cliente.geometria_ruta([CDMX, PUEBLA])

    assert capturado["path"] == "/route/v1/driving/-99.1332,19.4326;-98.2063,19.0414"
    assert resultado == {"type": "LineString", "coordinates": [[-99.1, 19.4], [-98.2, 19.0]]}
    await cliente.aclose()


@pytest.mark.asyncio
async def test_geometria_ruta_regresa_none_con_un_solo_punto():
    cliente = OSRMClient(base_url="http://osrm.test")

    resultado = await cliente.geometria_ruta([CDMX])

    assert resultado is None
    await cliente.aclose()


@pytest.mark.asyncio
async def test_geometria_ruta_regresa_none_si_no_hay_rutas():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {"code": "Ok", "routes": []})

    resultado = await cliente.geometria_ruta([CDMX, PUEBLA])

    assert resultado is None
    await cliente.aclose()


@pytest.mark.asyncio
async def test_duraciones_desde_manda_sources_0_y_regresa_solo_los_destinos():
    capturado = {}
    # 1 fila (source=0), 3 columnas: origen (siempre 0) + 2 destinos
    cuerpo = {"code": "Ok", "durations": [[0, 600, 1200]]}
    cliente = _cliente_con_respuesta(capturado, cuerpo)

    resultado = await cliente.duraciones_desde(CDMX, [PUEBLA, PUEBLA])

    assert "sources=0" in capturado["query"]
    assert resultado == [10.0, 20.0]
    await cliente.aclose()


@pytest.mark.asyncio
async def test_duraciones_desde_regresa_none_si_algun_destino_no_es_alcanzable():
    capturado = {}
    cuerpo = {"code": "Ok", "durations": [[0, None]]}
    cliente = _cliente_con_respuesta(capturado, cuerpo)

    resultado = await cliente.duraciones_desde(CDMX, [PUEBLA])

    assert resultado is None
    await cliente.aclose()


@pytest.mark.asyncio
async def test_duraciones_desde_regresa_none_si_el_servicio_no_responde():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no conecta", request=request)

    cliente = OSRMClient(base_url="http://osrm.test", transport=httpx.MockTransport(handler))

    resultado = await cliente.duraciones_desde(CDMX, [PUEBLA])

    assert resultado is None
    await cliente.aclose()
