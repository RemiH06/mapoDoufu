"""Accesibilidad a servicios: la curva por minuto, el tramo al camino que suma el
cliente de OSRM, y la carga y consulta de un estado contra la base de test con
un OSRM falso."""

import json

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from mapo_core import accesibilidad as acc
from mapo_core.db import get_pool
from mapo_core.osrm_client import OSRMClient
from mapo_core.server import app
from mapo_core.zonas import minutos_por_calle

PRIMARIA = "Escuelas de educación primaria del sector público"


def test_curva_cuenta_reservados_aparte_y_redondea_hacia_arriba():
    c = acc.curva([(100, 4.2), (50, 5.0), (None, 1.0), (30, None), (20, 500.0)])
    assert c["total"] == 200
    assert c["reservados"] == 1
    assert c["sin_ruta"] == 30
    assert c["dentro"][4] == 0  # 4.2 min cuenta en el minuto 5, no en el 4
    assert c["dentro"][5] == 150
    # Lo que pasa del máximo nunca queda "dentro": total - dentro[120] lo incluye.
    assert c["dentro"][acc.MAX_MINUTOS] == 150
    assert len(c["dentro"]) == acc.MAX_MINUTOS + 1


def test_modo_solo_de_la_lista():
    assert acc.modo_valido("pie") == "pie"
    for m in ("bici", None, "auto; DROP"):
        with pytest.raises(acc.ConsultaInvalida):
            acc.modo_valido(m)


def test_servicios_de_denue_existen_en_el_catalogo():
    from mapo_core import rubros

    clases = rubros.clases()
    for s in acc.SERVICIOS.values():
        if s.fuente == "denue":
            nombres = s.filtro.get("clases") or acc._clases(s.filtro["rubros"])
            assert nombres and all(n in clases for n in nombres), s.clave
    assert PRIMARIA in acc._clases(("primaria",))
    assert "Escuelas de educación primaria del sector privado" not in acc._clases(("primaria",))


@pytest.mark.asyncio
async def test_acercamiento_suma_el_tramo_al_camino_a_paso_de_peaton():
    def handler(request):
        return httpx.Response(200, json={
            "code": "Ok", "durations": [[600.0, None]],
            "sources": [{"distance": 500.0}],
            "destinations": [{"distance": 0.0}, {"distance": 250.0}],
        })

    cliente = OSRMClient(base_url="http://osrm.test", transport=httpx.MockTransport(handler))
    sin = await cliente.duraciones_matriz([(1, 1)], [(2, 2), (3, 3)])
    con = await cliente.duraciones_matriz([(1, 1)], [(2, 2), (3, 3)], acercamiento_kmh=5.0)
    await cliente.aclose()
    assert sin == [[10.0, None]]
    assert con == [[16.0, None]]  # 500 m a 5 km/h son 6 min


class OSRMFalso:
    """Minutos por (lat del origen redondeada, lat del destino); sin entrada, 50."""

    def __init__(self, tabla=None, fallas=0):
        self.tabla = tabla or {}
        self.fallas = fallas
        self.opciones = []

    async def duraciones_matriz(self, origenes, destinos, **opciones):
        self.opciones.append(opciones)
        if self.fallas:
            self.fallas -= 1
            return None
        return [[self.tabla.get((round(o[0], 1), d[0]), 50.0) for d in destinos] for o in origenes]


@pytest.mark.asyncio
async def test_minutos_por_calle_dice_cual_destino_y_reintenta():
    destinos = np.array([(5.0, 0.0), (6.0, 0.0)])
    vecinos = np.array([[0, 1]])
    osrm = OSRMFalso({(1.0, 5.0): 9.0, (1.0, 6.0): 3.0}, fallas=1)
    assert await minutos_por_calle(osrm, [(1.0, 0.0)], destinos, vecinos) is None
    osrm.fallas = 1
    assert await minutos_por_calle(osrm, [(1.0, 0.0)], destinos, vecinos, reintentos=1) == [(3.0, 1)]


def _cuadro(lat, lado=0.01, lon=0.0):
    return json.dumps({"type": "Polygon", "coordinates": [[
        [lon, lat], [lon + lado, lat], [lon + lado, lat + lado], [lon, lat + lado], [lon, lat]]]})


def _franja():
    # Angosta: un municipio de 10° por 10° pasaría el tope de área de una consulta.
    return json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [0.02, 0], [0.02, 10], [0, 10], [0, 0]]]})


async def _estado(conn):
    await conn.execute(
        "INSERT INTO entidades (cve_ent, nombre, geom) VALUES ('14', 'Jalisco',"
        " ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))", (_cuadro(0, 10),))
    await conn.execute(
        "INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom) VALUES ('14120', '14', '120', 'Zapopan',"
        " ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))", (_franja(),))
    for sufijo, lat, ninos in (("0001", 1.0, "300"), ("0002", 2.0, "*")):
        cvegeo = f"14120{sufijo}"
        await conn.execute(
            "INSERT INTO agebs (cvegeo, cve_ent, cve_mun, cve_ageb, ambito, geom) VALUES (%s, '14', '120', %s,"
            " 'URBANA', ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))", (cvegeo, sufijo, _cuadro(lat)))
        await conn.execute(
            "INSERT INTO fuente_censo_poblacion (cvegeo, nivel, cve_ent, cve_mun, pobtot, datos_json)"
            " VALUES (%s, 'ageb', '14', '120', 1000, %s)",
            (cvegeo, json.dumps({"POBTOT": "1000", "P_6A11": ninos})))
    # Una ranchería sin AGEB.
    await conn.execute(
        "INSERT INTO localidades (cvegeo, cve_ent, cve_mun, cve_loc, nombre, pobtot, datos, geom)"
        " VALUES ('141200099', '14', '120', '0099', 'Rancho', 40, %s, ST_SetSRID(ST_MakePoint(0.005, 7), 4326))",
        (json.dumps({"POBTOT": 40, "P_6A11": 8}),))
    await conn.execute(
        "INSERT INTO fuente_denue_negocios (id, nombre, clase_actividad, lat, lon, cve_ent, cve_mun)"
        " VALUES ('p1', 'Primaria Uno', %s, 5.0, 0.005, '14', '120'),"
        "        ('p2', 'Primaria Fuera', %s, 50.0, 0.005, '14', '120')", (PRIMARIA, PRIMARIA))


@pytest.mark.asyncio
async def test_carga_y_consulta_de_un_municipio(conn, pool_de_una_conexion):
    await _estado(conn)
    osrm = OSRMFalso({(1.0, 5.0): 4.0, (2.0, 5.0): 25.0, (7.0, 5.0): None})
    avisos = []
    resumen = await acc.cargar_estado(pool_de_una_conexion, "14", {"pie": osrm}, servicios=["primaria_publica"],
                                      avisar=avisos.append)

    # Primaria: solo desde los AGEB (DENUE casi no tiene escuelas del campo).
    assert [(r["servicio"], r["modo"], r["origenes"], r["destinos"], r["sin_ruta"]) for r in resumen] == [
        ("primaria_publica", "pie", 2, 1, 0)]
    assert resumen[0]["avisos"] == ["1 con la coordenada fuera de su lugar, descartados: p2"]
    assert all(o == {"acercamiento_kmh": acc.ACERCAMIENTO_KMH} for o in osrm.opciones)
    cur = await conn.execute("SELECT clave, minutos, destino FROM accesibilidad_minutos ORDER BY clave")
    assert await cur.fetchall() == [("141200001", 4.0, "p1"), ("141200002", 25.0, "p1")]
    # Un servicio de todos los lugares sí sale de la ranchería, y sin ruta se queda en null.
    await conn.execute(
        "INSERT INTO fuente_denue_negocios (id, nombre, clase_actividad, lat, lon, cve_ent, cve_mun)"
        " VALUES ('s1', 'Súper', 'Comercio al por menor en supermercados', 5.0, 0.005, '14', '120')")
    await acc.cargar_estado(pool_de_una_conexion, "14", {"pie": osrm}, servicios=["supermercado"],
                            avisar=avisos.append)
    cur = await conn.execute("SELECT clave, minutos FROM accesibilidad_minutos WHERE servicio = 'supermercado'"
                             " ORDER BY clave")
    assert await cur.fetchall() == [("141200001", 4.0), ("141200002", 25.0), ("141200099", None)]

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    try:
        r = TestClient(app).get("/accesibilidad/zona", params={"cve_ent": "14", "cve_mun": "120", "modo": "pie"})
        malo = TestClient(app).get("/accesibilidad/zona", params={"cve_ent": "14", "cve_mun": "120", "modo": "bici"})
        nada = TestClient(app).get("/accesibilidad/zona", params={"cve_ent": "14", "cve_mun": "999"})
    finally:
        app.dependency_overrides.clear()
    assert malo.status_code == 422
    assert nada.status_code == 404
    datos = r.json()
    primaria = next(s for s in datos["servicios"] if s["clave"] == "primaria_publica")
    # 300 niños a 4 min; el AGEB con '*' no cuenta como cero; la ranchería no se calcula y se dice.
    assert (primaria["total"], primaria["reservados"], primaria["sin_ruta"]) == (300, 1, 0)
    assert (primaria["sin_calcular"], primaria["sin_calcular_lugares"]) == (8, 1)
    super_ = next(s for s in datos["servicios"] if s["clave"] == "supermercado")
    assert (super_["total"], super_["sin_ruta"], super_["sin_calcular"]) == (2040, 40, 0)
    assert primaria["dentro"][3] == 0 and primaria["dentro"][4] == 300
    assert primaria["destinos_zona"] == 1
    assert "DENUE" in primaria["fuente"] and "foot.lua" in primaria["red"]
    # Lo que no se calculó lo dice, no sale en cero.
    assert next(s for s in datos["servicios"] if s["clave"] == "centro_salud")["calculado"] is False
    # En auto no hay estación de transporte masivo.
    assert "transporte_masivo" in [s["clave"] for s in datos["servicios"]]
    props = {f["properties"]["c"]: f["properties"] for f in datos["plano"]["features"]}
    assert props["141200001"]["m"] == {"primaria_publica": 4.0, "supermercado": 4.0}
    assert props["141200099"]["t"] == "localidad"
    assert sorted(f["properties"]["n"] for f in datos["destinos"]["features"]) == ["Primaria Uno", "Súper"]


@pytest.mark.asyncio
async def test_si_osrm_no_responde_no_se_guarda_nada_a_medias(conn, pool_de_una_conexion, monkeypatch):
    await _estado(conn)
    monkeypatch.setattr("asyncio.sleep", _sin_espera)
    with pytest.raises(acc.ErrorDeRed):
        await acc.cargar_estado(pool_de_una_conexion, "14", {"pie": OSRMFalso(fallas=10)},
                                servicios=["primaria_publica"], avisar=lambda _: None)
    cur = await conn.execute("SELECT count(*) FROM accesibilidad_minutos")
    assert (await cur.fetchone())[0] == 0


async def _sin_espera(_segundos):
    return None


@pytest.mark.asyncio
async def test_clues_descarta_coordenadas_fuera_de_su_municipio_salvo_por_nombre(conn, pool_de_una_conexion):
    await _estado(conn)
    await conn.execute(
        "INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom) VALUES ('14110', '14', '110', 'Unión de Tula',"
        " ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))", (_cuadro(0, 1, lon=20),))
    filas = [
        ("JCSSA1", "SSA", "120", "CENTRO DE SALUD UNO", 3.0, 0.01, ""),
        # Clave de Zapopan, coordenada en Unión de Tula y lo dice su nombre: se queda.
        ("JCIMS82", "IMS", "120", "UMF 82 UNION DE TULA", 0.5, 20.5, ""),
        ("JCSSA2", "SSA", "110", "CENTRO DE SALUD LEJOS", 3.0, 0.01, ""),  # dice Unión de Tula, cae en Zapopan
        ("JCSSA3", "SSA", "120", "CARAVANA", 3.0, 0.01, "CARAVANA"),  # unidad móvil
        ("JCSMP1", "SMP", "120", "CONSULTORIO PRIVADO", 3.0, 0.01, ""),
    ]
    for clues, inst, mun, nombre, lat, lon, movil in filas:
        await conn.execute(
            "INSERT INTO fuente_clues (clues, cve_institucion, institucion, cve_ent, cve_mun, cve_loc, tipo, tipologia,"
            " subtipologia, nombre, estatus, nivel, estrato, unidad_movil, publica, lat, lon, geom, corte)"
            " VALUES (%s, %s, '', '14', %s, '0001', 'DE CONSULTA EXTERNA', '', '', %s, 'EN OPERACION', '', '', %s,"
            " true, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), '2026-10')",
            (clues, inst, mun, nombre, movil, lat, lon, lon, lat))

    centro, fuente, avisos = await acc.destinos(pool_de_una_conexion, "14", acc.SERVICIOS["centro_salud"])
    imss, _, _ = await acc.destinos(pool_de_una_conexion, "14", acc.SERVICIOS["umf_imss"])

    assert [d["id"] for d in centro] == ["JCSSA1"]
    assert avisos == ["1 con la coordenada fuera de su lugar, descartados: JCSSA2"]
    assert "corte 2026-10" in fuente
    assert [d["id"] for d in imss] == ["JCIMS82"]


async def _paradas(conn):
    """Un GTFS con dos paradas en Zapopan, en el mismo punto (como los feeds que dan
    una por ruta), una frecuente y otra no, y una de un feed de frecuencia de relleno."""
    for feed, util in (("jal-setran", True), ("relleno", False)):
        await conn.execute(
            "INSERT INTO transporte_feeds (feed, titulo, productor, pagina, url, via, sha256, bytes, fecha_ref,"
            " viajes_dia, rutas, paradas, frecuencia_util) VALUES (%s, 't', 'p', 'x', 'x', 'x', 'x', 1, '2026-11-25',"
            " 1, 1, 1, %s)", (feed, util))
    await conn.execute(
        "INSERT INTO transporte_paradas (feed, stop_id, nombre, lat, lon, cve_ent, cve_mun, pasadas_ruta_max,"
        " pasadas, rutas) VALUES"
        " ('jal-setran', 'a', 'Parada', 5.0, 0.005, '14', '120', 12, 12, 1),"
        " ('jal-setran', 'b', 'Parada', 5.00001, 0.00501, '14', '120', 2, 2, 1),"
        " ('jal-setran', 'c', 'Lenta', 6.0, 0.005, '14', '120', 2, 2, 1),"
        " ('relleno', 'd', 'Relleno', 3.0, 0.005, '14', '120', 24, 24, 1)")


@pytest.mark.asyncio
async def test_paradas_del_gtfs_juntan_el_mismo_punto_y_solo_frecuentes_utiles(conn, pool_de_una_conexion):
    await _estado(conn)
    await _paradas(conn)
    todas, fuente, _ = await acc.destinos(pool_de_una_conexion, "14", acc.SERVICIOS["parada_transporte"])
    frecuentes, _, _ = await acc.destinos(pool_de_una_conexion, "14", acc.SERVICIOS["parada_frecuente"])
    # a y b son el mismo punto a ~10 m; la de relleno cuenta como parada, no como frecuente.
    assert sorted(d["nombre"] for d in todas) == ["Lenta", "Parada", "Relleno"]
    assert [d["nombre"] for d in frecuentes] == ["Parada"]
    assert "jal-setran (frecuencias del 2026-11-25)" in fuente
    assert await acc.cobertura(pool_de_una_conexion, "14") == {"120"}


@pytest.mark.asyncio
async def test_sin_gtfs_en_el_municipio_no_se_calcula_y_se_dice(conn, pool_de_una_conexion):
    await _estado(conn)
    avisos = []
    resumen = await acc.cargar_estado(pool_de_una_conexion, "14", {"pie": OSRMFalso({})},
                                      servicios=["parada_transporte"], avisar=avisos.append)
    assert resumen == [] and "ningún municipio del estado tiene paradas" in avisos[0]
    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    try:
        datos = TestClient(app).get("/accesibilidad/zona", params={"cve_ent": "14", "cve_mun": "120"}).json()
    finally:
        app.dependency_overrides.clear()
    parada = next(s for s in datos["servicios"] if s["clave"] == "parada_transporte")
    assert (parada["calculado"], parada["sin_cobertura"]) == (False, True)
