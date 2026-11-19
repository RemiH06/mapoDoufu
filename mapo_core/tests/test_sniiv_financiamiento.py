from mapo_core import sniiv_financiamiento as sn


def _fila(**cambios):
    fila = {"año": 2024, "municipio": "Zapopan", "clave_municipio": "120", "organismo": "INFONAVIT",
            "destino_credito": "Vivienda nueva", "valor_vivienda": "Media", "acciones": 10, "monto": 1_000_000.5}
    return {**fila, **cambios}


def test_url():
    assert sn.url(2013, 2026, "14") == (
        "https://sniiv.sedatu.gob.mx/api/CuboAPI/GetFinanciamiento/2013,2026/14/000/"
        "anio,municipio,organismo,destino_credito,valor_vivienda"
    )


def test_leer_suma_llaves_repetidas_y_toma_el_anio():
    filas = sn.leer([_fila(), _fila(acciones=5, monto=None), _fila(clave_municipio="000", monto=0.0)], "14")
    por_mun = {f["cve_mun"]: f for f in filas}
    assert por_mun["120"]["acciones"] == 15
    assert por_mun["120"]["monto"] == 1_000_000.5
    assert por_mun["120"]["anio"] == 2024 and por_mun["120"]["cve_ent"] == "14"
    assert por_mun["000"]["acciones"] == 10


def test_meses_por_anio_marca_el_anio_a_medias():
    datos = [{"año": 2025, "mes": m} for m in ["enero", "febrero", "marzo"] * 2] + [{"año": 2024, "mes": "enero"}]
    assert sn.meses_por_anio(datos) == {2025: 3, 2024: 1}
