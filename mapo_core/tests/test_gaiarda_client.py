import httpx
import pytest

from mapo_core.gaiarda_client import GaiardaClient


def _cliente_con_respuesta(capturar: dict, cuerpo, status_code: int = 200) -> GaiardaClient:
    """Cliente con un transporte falso que guarda la request recibida en
    `capturar` y siempre responde con `cuerpo` (o el status_code dado)."""

    def handler(request: httpx.Request) -> httpx.Response:
        capturar["metodo"] = request.method
        capturar["path"] = request.url.path
        capturar["params"] = dict(request.url.params)
        return httpx.Response(status_code, json=cuerpo)

    transport = httpx.MockTransport(handler)
    return GaiardaClient(base_url="http://gaiarda.test", transport=transport)


@pytest.mark.asyncio
async def test_status_pega_al_endpoint_correcto():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {"ok": True})

    resultado = await cliente.status()

    assert capturado["path"] == "/status"
    assert resultado == {"ok": True}
    await cliente.aclose()


@pytest.mark.asyncio
async def test_estados_no_manda_parametros():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {"type": "FeatureCollection", "features": []})

    await cliente.estados()

    assert capturado["path"] == "/estados"
    assert capturado["params"] == {}
    await cliente.aclose()


@pytest.mark.asyncio
async def test_municipios_omite_cve_ent_si_no_se_da():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {"type": "FeatureCollection", "features": []})

    await cliente.municipios()

    assert capturado["params"] == {}
    await cliente.aclose()


@pytest.mark.asyncio
async def test_municipios_manda_cve_ent_si_se_da():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {"type": "FeatureCollection", "features": []})

    await cliente.municipios(cve_ent="14")

    assert capturado["params"] == {"cve_ent": "14"}
    await cliente.aclose()


@pytest.mark.asyncio
async def test_agebs_manda_cve_ent_y_cve_mun():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {"type": "FeatureCollection", "features": []})

    await cliente.agebs(cve_ent="14", cve_mun="039")

    assert capturado["path"] == "/agebs"
    assert capturado["params"] == {"cve_ent": "14", "cve_mun": "039"}
    await cliente.aclose()


@pytest.mark.asyncio
async def test_denue_solo_manda_los_filtros_dados():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {"type": "FeatureCollection", "features": []})

    await cliente.denue(cve_ent="14", clase_actividad="papeler")

    assert capturado["path"] == "/fuentes/denue"
    assert capturado["params"] == {"cve_ent": "14", "clase_actividad": "papeler"}
    await cliente.aclose()


@pytest.mark.asyncio
async def test_censo_poblacion_devuelve_lista():
    capturado = {}
    filas = [{"cvegeo": "14039001234", "pobtot": 120}]
    cliente = _cliente_con_respuesta(capturado, filas)

    resultado = await cliente.censo_poblacion(cve_ent="14", nivel="ageb")

    assert capturado["path"] == "/fuentes/censo_poblacion"
    assert capturado["params"] == {"cve_ent": "14", "nivel": "ageb"}
    assert resultado == filas
    await cliente.aclose()


@pytest.mark.asyncio
async def test_choropleth_censo_poblacion_manda_indicador_y_cve_ent():
    capturado = {}
    geojson = {"type": "FeatureCollection", "features": []}
    cliente = _cliente_con_respuesta(capturado, geojson)

    resultado = await cliente.choropleth_censo_poblacion("pobtot", "14")

    assert capturado["path"] == "/choropleth/censo_poblacion"
    assert capturado["params"] == {"indicador": "pobtot", "cve_ent": "14"}
    assert resultado == geojson
    await cliente.aclose()


@pytest.mark.asyncio
async def test_choropleth_censo_poblacion_incluye_cve_mun_si_se_da():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {"type": "FeatureCollection", "features": []})

    await cliente.choropleth_censo_poblacion("pobtot", "14", cve_mun="039")

    assert capturado["params"] == {"indicador": "pobtot", "cve_ent": "14", "cve_mun": "039"}
    await cliente.aclose()


@pytest.mark.asyncio
async def test_sesnsp_manda_filtros_de_anio_como_string():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, [])

    await cliente.sesnsp(cve_ent="14", anio=2025)

    assert capturado["params"] == {"cve_ent": "14", "anio": "2025"}
    await cliente.aclose()


@pytest.mark.asyncio
async def test_enigh_resumen_siempre_manda_por_dia():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {})

    await cliente.enigh_resumen(cve_ent="14")

    assert capturado["path"] == "/fuentes/enigh/resumen"
    assert capturado["params"] == {"columna": "gasto_mon", "cve_ent": "14", "por_dia": "false"}
    await cliente.aclose()


@pytest.mark.asyncio
async def test_respuesta_de_error_truena():
    capturado = {}
    cliente = _cliente_con_respuesta(capturado, {"detail": "no encontrado"}, status_code=404)

    with pytest.raises(httpx.HTTPStatusError):
        await cliente.estados()

    await cliente.aclose()
