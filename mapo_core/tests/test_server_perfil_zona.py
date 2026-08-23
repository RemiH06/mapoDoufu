from fastapi.testclient import TestClient

from mapo_core.server import app, get_gaiarda_client


class _ClienteGaiardaFalso:
    async def denue(self, cve_ent=None, cve_mun=None, cve_ageb=None, clase_actividad=None):
        return {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"id": "1", "clase_actividad": "papeleria"}, "geometry": {}}
            ],
        }

    async def censo_poblacion(self, cve_ent=None, cve_mun=None, nivel=None):
        return [{"cvegeo": "14039", "pobtot": 1500000}]

    async def enigh_resumen(self, columna="gasto_mon", cve_ent=None, por_dia=False):
        return {"14039": {"promedio": 5000, "n_hogares_muestra": 40}}

    async def sesnsp(self, cve_ent=None, cve_mun=None, anio=None, tipo_delito=None):
        return [{"anio": 2024, "tipo_delito": "robo", "cantidad": 10}]


def test_perfil_zona_junta_las_4_fuentes():
    app.dependency_overrides[get_gaiarda_client] = lambda: _ClienteGaiardaFalso()
    cliente = TestClient(app)

    respuesta = cliente.get("/perfil_zona", params={"cve_ent": "14", "cve_mun": "039"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["comercio"]["total_negocios"] == 1
    assert cuerpo["demografia"]["pobtot"] == 1500000
    assert cuerpo["consumo"]["promedio"] == 5000
    assert cuerpo["seguridad"]["total_incidentes"] == 10
    assert cuerpo["laboral_disponible"] is False
    app.dependency_overrides.clear()


def test_perfil_zona_requiere_cve_ent_y_cve_mun():
    cliente = TestClient(app)

    respuesta = cliente.get("/perfil_zona")

    assert respuesta.status_code == 422
