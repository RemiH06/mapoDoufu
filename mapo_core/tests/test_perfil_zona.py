import pytest

from mapo_core.perfil_zona import construir_perfil


class _ClienteFalso:
    def __init__(self, negocios=None, censo=None, consumo=None, delitos=None):
        self._negocios = negocios if negocios is not None else []
        self._censo = censo if censo is not None else []
        self._consumo = consumo if consumo is not None else {}
        self._delitos = delitos if delitos is not None else []

    async def denue(self, cve_ent=None, cve_mun=None, cve_ageb=None, clase_actividad=None):
        return {"type": "FeatureCollection", "features": self._negocios}

    async def censo_poblacion(self, cve_ent=None, cve_mun=None, nivel=None):
        return self._censo

    async def enigh_resumen(self, columna="gasto_mon", cve_ent=None, por_dia=False):
        return self._consumo

    async def sesnsp(self, cve_ent=None, cve_mun=None, anio=None, tipo_delito=None):
        return self._delitos


def _negocio(clase_actividad):
    return {"type": "Feature", "properties": {"id": "1", "clase_actividad": clase_actividad}, "geometry": {}}


@pytest.mark.asyncio
async def test_perfil_junta_las_4_fuentes():
    cliente = _ClienteFalso(
        negocios=[_negocio("papeleria"), _negocio("papeleria"), _negocio("farmacia")],
        censo=[{"cvegeo": "14039", "pobtot": 1500000}],
        consumo={"14039": {"promedio": 5000, "n_hogares_muestra": 40}},
        delitos=[
            {"anio": 2024, "tipo_delito": "robo", "cantidad": 10},
            {"anio": 2024, "tipo_delito": "robo", "cantidad": 5},
            {"anio": 2024, "tipo_delito": "fraude", "cantidad": 2},
            {"anio": 2023, "tipo_delito": "robo", "cantidad": 999},
        ],
    )

    perfil = await construir_perfil(cliente, "14", "039")

    assert perfil.comercio.total_negocios == 3
    assert perfil.comercio.top_clases_actividad[0] == ("papeleria", 2)

    assert perfil.demografia == {"cvegeo": "14039", "pobtot": 1500000}

    assert perfil.consumo == {"promedio": 5000, "n_hogares_muestra": 40}

    assert perfil.seguridad.anio_mas_reciente == 2024
    assert perfil.seguridad.total_incidentes == 17
    assert perfil.seguridad.por_tipo_delito == [("robo", 15), ("fraude", 2)]


@pytest.mark.asyncio
async def test_perfil_con_todo_vacio_no_truena():
    cliente = _ClienteFalso()

    perfil = await construir_perfil(cliente, "14", "999")

    assert perfil.comercio.total_negocios == 0
    assert perfil.comercio.top_clases_actividad == []
    assert perfil.demografia is None
    assert perfil.consumo is None
    assert perfil.seguridad.total_incidentes == 0
    assert perfil.seguridad.anio_mas_reciente is None


@pytest.mark.asyncio
async def test_seguridad_solo_cuenta_el_anio_mas_reciente():
    cliente = _ClienteFalso(
        delitos=[
            {"anio": 2020, "tipo_delito": "robo", "cantidad": 500},
            {"anio": 2024, "tipo_delito": "robo", "cantidad": 3},
        ]
    )

    perfil = await construir_perfil(cliente, "14", "039")

    assert perfil.seguridad.anio_mas_reciente == 2024
    assert perfil.seguridad.total_incidentes == 3
