"""Perfil de una zona (municipio): junta comercio, demografia,
consumo y seguridad en un solo reporte, para responder preguntas de
decision reales (ej. "¿donde conviene poner un negocio?") sin tener
que consultar cada fuente por separado.

Es composicion, no analisis nuevo: cada numero viene directo de
Gaiarda, nada se deriva ni se pondera aqui (ni siquiera un "puntaje de
seguridad" unico, mismo principio que ya aplica Gaiarda). Laboral
(ENOE) queda fuera a proposito: Gaiarda todavia no expone un endpoint
de consulta para esa fuente (solo de descarga), asi que no hay nada
que consumir. Se marca honesto en el resultado, no se omite en
silencio.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from mapo_core.gaiarda_client import GaiardaClient


@dataclass
class PerfilComercio:
    total_negocios: int
    top_clases_actividad: list[tuple[str, int]]


@dataclass
class PerfilSeguridad:
    total_incidentes: int
    anio_mas_reciente: int | None
    por_tipo_delito: list[tuple[str, int]]


@dataclass
class PerfilZona:
    cve_ent: str
    cve_mun: str
    comercio: PerfilComercio
    demografia: dict | None
    consumo: dict | None
    seguridad: PerfilSeguridad


def _resumir_comercio(features: list[dict]) -> PerfilComercio:
    conteo = Counter(
        f["properties"]["clase_actividad"] for f in features if f["properties"].get("clase_actividad")
    )
    return PerfilComercio(total_negocios=len(features), top_clases_actividad=conteo.most_common(10))


def _resumir_seguridad(filas: list[dict]) -> PerfilSeguridad:
    if not filas:
        return PerfilSeguridad(total_incidentes=0, anio_mas_reciente=None, por_tipo_delito=[])

    anio_mas_reciente = max(f["anio"] for f in filas)

    conteo: Counter[str] = Counter()
    for f in filas:
        if f["anio"] == anio_mas_reciente:
            conteo[f["tipo_delito"]] += f["cantidad"] or 0

    return PerfilSeguridad(
        total_incidentes=sum(conteo.values()),
        anio_mas_reciente=anio_mas_reciente,
        por_tipo_delito=conteo.most_common(10),
    )


async def construir_perfil(client: GaiardaClient, cve_ent: str, cve_mun: str) -> PerfilZona:
    negocios = await client.denue(cve_ent=cve_ent, cve_mun=cve_mun)
    censo = await client.censo_poblacion(cve_ent=cve_ent, cve_mun=cve_mun, nivel="municipio")
    consumo_por_municipio = await client.enigh_resumen(cve_ent=cve_ent)
    delitos = await client.sesnsp(cve_ent=cve_ent, cve_mun=cve_mun)

    return PerfilZona(
        cve_ent=cve_ent,
        cve_mun=cve_mun,
        comercio=_resumir_comercio(negocios["features"]),
        demografia=censo[0] if censo else None,
        consumo=consumo_por_municipio.get(f"{cve_ent}{cve_mun}"),
        seguridad=_resumir_seguridad(delitos),
    )
