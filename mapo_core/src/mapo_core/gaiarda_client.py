"""Cliente HTTP hacia la API de Gaiarda.

Gaiarda ya descarga y normaliza los datos; mapo_core no vuelve a
implementar nada de eso, solo consume su API REST. Ver
GAIARDA_ESTADO.md (fuera de este repo) para la referencia completa de
endpoints; los que cubre este cliente son los que ya respaldan los
enfoques de Mapo (comercio, demografia, seguridad, consumo).
"""

from __future__ import annotations

import os

import httpx


def _url_por_defecto() -> str:
    return os.environ.get("GAIARDA_API_URL", "http://localhost:8420")


def _sin_none(**kwargs) -> dict:
    return {clave: valor for clave, valor in kwargs.items() if valor is not None}


class GaiardaClient:
    """Cliente async hacia la API de Gaiarda.

    Reutiliza un solo `httpx.AsyncClient` (pool de conexiones), no crear
    una instancia nueva por request.
    """

    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or _url_por_defecto(),
            transport=transport,
            timeout=10.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def status(self) -> dict:
        return await self._get("/status")

    async def estados(self) -> dict:
        """FeatureCollection de los estados (con poligono)."""
        return await self._get("/estados")

    async def municipios(self, cve_ent: str | None = None) -> dict:
        """FeatureCollection de municipios, opcionalmente filtrada por estado."""
        return await self._get("/municipios", params=_sin_none(cve_ent=cve_ent))

    async def agebs(self, cve_ent: str, cve_mun: str | None = None) -> dict:
        """FeatureCollection de AGEBs. `cve_ent` es obligatorio en la API real."""
        return await self._get("/agebs", params=_sin_none(cve_ent=cve_ent, cve_mun=cve_mun))

    async def denue(
        self,
        cve_ent: str | None = None,
        cve_mun: str | None = None,
        cve_ageb: str | None = None,
        clase_actividad: str | None = None,
    ) -> dict:
        """Negocios de DENUE (comercio) como FeatureCollection de puntos."""
        return await self._get(
            "/fuentes/denue",
            params=_sin_none(
                cve_ent=cve_ent,
                cve_mun=cve_mun,
                cve_ageb=cve_ageb,
                clase_actividad=clase_actividad,
            ),
        )

    async def censo_poblacion(
        self,
        cve_ent: str | None = None,
        cve_mun: str | None = None,
        nivel: str | None = None,
    ) -> list[dict]:
        """Indicadores del censo (demografia). Sin geometria propia."""
        return await self._get(
            "/fuentes/censo_poblacion",
            params=_sin_none(cve_ent=cve_ent, cve_mun=cve_mun, nivel=nivel),
        )

    async def sesnsp(
        self,
        cve_ent: str | None = None,
        cve_mun: str | None = None,
        anio: int | None = None,
        tipo_delito: str | None = None,
    ) -> list[dict]:
        """Incidencia delictiva (seguridad). Sin puntaje unico, a proposito."""
        return await self._get(
            "/fuentes/sesnsp",
            params=_sin_none(cve_ent=cve_ent, cve_mun=cve_mun, anio=anio, tipo_delito=tipo_delito),
        )

    async def enigh_resumen(
        self,
        columna: str = "gasto_mon",
        cve_ent: str | None = None,
        por_dia: bool = False,
    ) -> dict:
        """Estadisticos ponderados de ENIGH (consumo) por municipio.

        Cada municipio trae su propio `n_hogares_muestra`: ENIGH es
        representativo a nivel estado, no a nivel municipio. Nunca
        ocultar ese numero en lo que consuma esta funcion.
        """
        params = _sin_none(columna=columna, cve_ent=cve_ent)
        params["por_dia"] = por_dia
        return await self._get("/fuentes/enigh/resumen", params=params)

    async def _get(self, path: str, params: dict | None = None):
        respuesta = await self._client.get(path, params=params)
        respuesta.raise_for_status()
        return respuesta.json()
