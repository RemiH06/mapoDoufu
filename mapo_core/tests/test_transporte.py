"""Transporte público (sesión 27): lectura de un GTFS chico armado aquí (viajes por
horario y por frecuencia, día de referencia, agencias excluidas), la frecuencia de
relleno, el zip de un tercero, las rutas de OSM desde OPL, y la carga y consulta
de un municipio contra la base de test."""

import datetime
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from mapo_core import transporte as tr
from mapo_core import transporte_osm as tosm
from mapo_core.db import get_pool
from mapo_core.server import app

HOY = datetime.date(2026, 11, 22)


def _gtfs(ruta, archivos: dict[str, str]):
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, texto in archivos.items():
            z.writestr(nombre, texto.strip() + "\n")
    return ruta


BASE = {
    "agency.txt": """
agency_id,agency_name,agency_url,agency_timezone
A,Camiones Uno,https://x.test,America/Mexico_City
V,Vieja,https://x.test,America/Mexico_City""",
    "routes.txt": """
route_id,agency_id,route_short_name,route_long_name,route_type
R1,A,C01,Centro,3
R2,A,T1,Tren,1
RV,V,X,Vieja,3""",
    # Entre semana todo 2026; el 2026-11-18 (miércoles) no hay servicio: feriado inventado.
    "calendar.txt": """
service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
LV,1,1,1,1,1,0,0,20260101,20261231
DOM,0,0,0,0,0,0,1,20260101,20261231""",
    "calendar_dates.txt": """
service_id,date,exception_type
LV,20261118,2""",
    # R1: dos viajes por horario a las 7:10 y 8:50, y uno de domingo.
    # R2: un viaje por frecuencia de 6:00 a 10:00 cada 10 minutos.
    "trips.txt": """
route_id,service_id,trip_id,direction_id,shape_id
R1,LV,t1,0,s1
R1,LV,t2,0,s1
R1,DOM,t3,0,s1
R2,LV,f1,0,
RV,LV,v1,0,""",
    "stop_times.txt": """
trip_id,arrival_time,departure_time,stop_id,stop_sequence
t1,07:10:00,07:10:00,P1,1
t1,,,P2,2
t1,07:30:00,07:30:00,P3,3
t2,08:50:00,08:50:00,P1,1
t2,,,P2,2
t2,09:10:00,09:10:00,P3,3
t3,07:10:00,07:10:00,P1,1
t3,07:30:00,07:30:00,P3,3
f1,06:00:00,06:00:00,P1,1
f1,06:05:00,06:05:00,P3,2
v1,07:00:00,07:00:00,P1,1
v1,07:10:00,07:10:00,P3,2""",
    "frequencies.txt": """
trip_id,start_time,end_time,headway_secs
f1,06:00:00,10:00:00,600""",
    "stops.txt": """
stop_id,stop_name,stop_lat,stop_lon,location_type
P1,Uno,20.670,-103.350,0
P2,Dos,20.675,-103.345,0
P3,Tres,20.680,-103.340,0
E1,Estación,20.680,-103.340,1
P9,Fuera,0.0,0.0,0""",
    "shapes.txt": """
shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
s1,20.670,-103.350,1
s1,20.675,-103.346,2
s1,20.680,-103.340,3""",
}


def test_segundos_y_horas_despues_de_medianoche():
    assert tr._segundos("07:10:00") == 7 * 3600 + 600
    assert tr._segundos("25:00:00") == 25 * 3600
    for malo in ("", "7:10", "aa:bb:cc", "07:61:00", "99:00:00"):
        assert tr._segundos(malo) is None


def test_pasadas_en_pico_de_un_viaje_por_frecuencia():
    # De 6 a 10 cada 10 minutos; la parada está 5 minutos después del arranque:
    # pasa a las 7:05, 7:15, ..., 8:55 -> 12 pasadas dentro de [7, 9).
    assert tr.pasadas_en_pico(6 * 3600, 10 * 3600, 600, 300) == 12
    # Desfase 0: 7:00 a 8:50 -> 12; a las 9:00 ya no cuenta.
    assert tr.pasadas_en_pico(6 * 3600, 10 * 3600, 600, 0) == 12
    # Termina a las 7:30: 7:00, 7:10, 7:20.
    assert tr.pasadas_en_pico(6 * 3600, 7 * 3600 + 1800, 600, 0) == 3
    assert tr.pasadas_en_pico(10 * 3600, 11 * 3600, 600, 0) == 0
    assert tr.pasadas_en_pico(6 * 3600, 10 * 3600, 0, 0) == 0


def test_leer_cuenta_la_hora_pico_y_evita_el_feriado(tmp_path):
    lec = tr.leer(_gtfs(tmp_path / "f.zip", BASE), excluir_agencias=("V",), hoy=HOY)
    # El miércoles más cercano a hoy con servicio completo: el 18 no (feriado), el 25 sí.
    assert lec.fecha_ref == datetime.date(2026, 11, 25)
    assert set(lec.rutas) == {"R1", "R2"}  # la de la agencia vieja fuera
    assert any("fuera" in a for a in lec.avisos)
    r1, r2 = lec.rutas["R1"], lec.rutas["R2"]
    # R1: el de las 7:10 pasa por las tres paradas en pico; el de las 8:50 solo por P1
    # (P2 interpolada a las 9:00, P3 a las 9:10). Más servida: P1 con 2.
    assert (r1.viajes_dia, r1.salidas_pico, r1.modo) == (2, 2, "autobus")
    assert r1.lineas == [[(20.670, -103.350), (20.675, -103.346), (20.680, -103.340)]]
    # R2 por frecuencia: 24 salidas al día, 12 en pico; sin shapes, trazo por paradas.
    assert (r2.viajes_dia, r2.salidas_pico, r2.modo, r2.frecuencia_estimada) == (24, 12, "metro", True)
    assert r2.lineas == [[(20.670, -103.350), (20.680, -103.340)]]
    assert tr.intervalo_min(r2.salidas_pico) == 10.0 and tr.intervalo_min(0) is None
    # Paradas: P1 la tocan R1 y R2; P9 (fuera de México) y E1 (estación) no entran.
    assert set(lec.paradas) == {"P1", "P2", "P3"}
    p1 = lec.paradas["P1"]
    assert (p1.pasadas_ruta_max, p1.pasadas, p1.rutas) == (12, 14, {"R1", "R2"})
    assert lec.paradas["P2"].pasadas == 1  # solo el de las 7:10 (interpolada 7:20)
    assert lec.frecuencia_util


def test_feed_vencido_usa_su_vigencia_y_lo_dice(tmp_path):
    viejo = {**BASE, "calendar.txt": BASE["calendar.txt"].replace("20261231", "20250630").replace("20260101", "20250101"),
             "calendar_dates.txt": "service_id,date,exception_type"}
    lec = tr.leer(_gtfs(tmp_path / "v.zip", viejo), hoy=HOY)
    assert lec.fecha_ref.weekday() == 2 and lec.fecha_ref <= datetime.date(2025, 6, 30)
    assert any(a.startswith("vencido") for a in lec.avisos)


def test_frecuencia_de_relleno():
    assert tr.frecuencia_util([24] * 9)  # pocas rutas: no se juzga
    assert not tr.frecuencia_util([24] * 9 + [12])  # 90 % igual
    assert tr.frecuencia_util([24] * 7 + [12, 8, 4])  # 70 %


def test_zip_que_no_es_gtfs_o_viene_inflado(tmp_path):
    malo = tmp_path / "x.zip"
    malo.write_bytes(b"no es zip")
    with pytest.raises(tr.ArchivoInvalido):
        tr.leer(malo, hoy=HOY)
    with pytest.raises(tr.ArchivoInvalido, match="falta routes.txt"):
        tr.leer(_gtfs(tmp_path / "y.zip", {"agency.txt": BASE["agency.txt"]}), hoy=HOY)
    bomba = tmp_path / "b.zip"
    with zipfile.ZipFile(bomba, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("stop_times.txt", "0" * (60 * 1024 * 1024))
    with pytest.raises(tr.ArchivoInvalido, match="compresión"):
        tr.abrir(bomba)


def test_modos_basicos_y_extendidos():
    assert [tr.modo(x) for x in ("3", "1", "0", "11", "6", "700", "900", "1300", "x")] == [
        "autobus", "metro", "tren_ligero", "trolebus", "cable", "autobus", "tren_ligero", "cable", "otro"]


OPL = """n1 v1 dV c0 t2026-01-01T00:00:00Z i0 u Tpublic_transport=platform,name=Parada%20%Uno x-103.35 y20.67
n2 v1 dV c0 t2026-01-01T00:00:00Z i0 u Thighway=traffic_signals x-103.34 y20.68
w10 v1 dV c0 t2026-01-01T00:00:00Z i0 u Thighway=primary Nn5x-103.35y20.67,n6x-103.34y20.68
w11 v1 dV c0 t2026-01-01T00:00:00Z i0 u Thighway=primary Nn7,n8
r100 v1 dV c0 t2026-01-01T00:00:00Z i0 u Ttype=route,route=bus,ref=C01,name=Centro%20%%3d%>%20%Norte,network=Mi%20%Red Mw10@,w11@,n1@platform,n2@stop
r101 v1 dV c0 t2026-01-01T00:00:00Z i0 u Ttype=route,route=hiking,name=Sendero Mw10@
r102 v1 dV c0 t2026-01-01T00:00:00Z i0 u Ttype=route,route=share_taxi,name=Combi Mw11@
"""


def test_osm_desde_opl(tmp_path):
    archivo = tmp_path / "rutas-261120.opl"
    archivo.write_text(OPL, encoding="utf-8")
    rutas, paradas, avisos = tosm.leer(archivo)
    # La de senderismo no es transporte; la combi solo trae una vía sin coordenadas.
    assert [(r["route_id"], r["modo"], r["nombre_corto"], r["nombre_largo"], r["agencia"]) for r in rutas] == [
        ("r100", "autobus", "C01", "Centro => Norte", "Mi Red")]
    assert rutas[0]["geom"] == "SRID=4326;MULTILINESTRING((-103.350000 20.670000,-103.340000 20.680000))"
    assert avisos == ["1 relaciones sin vías con coordenadas (incompletas en el extracto): no se guardan"]
    # n2 es parada de la ruta pero solo si trae etiqueta: la trae (semáforo), cuenta con su punto.
    assert sorted((p["stop_id"], p["nombre"]) for p in paradas) == [("n1", "Parada Uno"), ("n2", "")]
    assert tosm.fecha_extracto(archivo.name) == "2026-11-20"
    assert tosm.fecha_extracto("rutas.opl") is None


async def _municipio(conn):
    await conn.execute(
        "INSERT INTO municipios (cvegeo, cve_ent, cve_mun, nombre, geom) VALUES"
        " ('14039', '14', '039', 'Guadalajara',"
        "  ST_Multi(ST_MakeEnvelope(-103.36, 20.66, -103.33, 20.69, 4326))),"
        " ('14015', '14', '015', 'Autlán', ST_Multi(ST_MakeEnvelope(-104.40, 19.70, -104.30, 19.80, 4326)))")


@pytest.mark.asyncio
async def test_carga_y_consulta_de_un_municipio(conn, pool_de_una_conexion, tmp_path):
    await _municipio(conn)
    feed = tr.FEEDS["jal-setran"]
    resumen = await tr.cargar_feed(pool_de_una_conexion, feed, _gtfs(tmp_path / "f.zip", BASE), "local", hoy=HOY)
    assert (resumen["rutas"], resumen["paradas"], resumen["rutas_frecuentes"]) == (3, 3, 1)
    cur = await conn.execute("SELECT stop_id, cve_mun FROM transporte_paradas ORDER BY stop_id")
    assert await cur.fetchall() == [("P1", "039"), ("P2", "039"), ("P3", "039")]
    # Recargar reemplaza el feed, no lo duplica.
    await tr.cargar_feed(pool_de_una_conexion, feed, _gtfs(tmp_path / "f.zip", BASE), "local", hoy=HOY)
    cur = await conn.execute("SELECT count(*) FROM transporte_rutas WHERE feed = 'jal-setran'")
    assert (await cur.fetchone())[0] == 3

    archivo = tmp_path / "rutas-261120.opl"
    archivo.write_text(OPL, encoding="utf-8")
    rutas, paradas, _ = tosm.leer(archivo)
    await tr.guardar(pool_de_una_conexion, {
        "feed": "osm", "titulo": "OSM", "productor": "OSM", "licencia": "ODbL-1.0", "pagina": "x", "url": "x",
        "via": "x", "sha256": "x", "bytes": 1, "vigencia_ini": None, "vigencia_fin": None, "fecha_ref": None,
        "viajes_dia": 0, "rutas": 1, "paradas": 2, "avisos": [], "nota": "", "frecuencia_util": False},
        rutas, paradas)

    app.dependency_overrides[get_pool] = lambda: pool_de_una_conexion
    try:
        cliente = TestClient(app)
        r = cliente.get("/transporte/zona", params={"cve_ent": "14", "cve_mun": "039"})
        sin = cliente.get("/transporte/zona", params={"cve_ent": "14", "cve_mun": "015"})
        nada = cliente.get("/transporte/zona", params={"cve_ent": "14", "cve_mun": "999"})
        malo = cliente.get("/transporte/zona", params={"cve_ent": "14", "cve_mun": "39; x"})
    finally:
        app.dependency_overrides.clear()
    assert (nada.status_code, malo.status_code) == (404, 422)
    datos = r.json()
    # Hay GTFS: las rutas de OSM del mismo lugar no se mezclan.
    assert datos["origen"] == "gtfs"
    props = {f["properties"]["id"]: f["properties"] for f in datos["rutas"]["features"]}
    assert set(props) == {"R1", "R2", "RV"}
    assert (props["R2"]["int"], props["R2"]["c"], props["R1"]["c"]) == (10.0, "10", "mas")
    # Lo masivo se pinta encima: va al final.
    assert datos["rutas"]["features"][-1]["properties"]["modo"] == "metro"
    assert datos["feeds"][0]["licencia"] is None and datos["feeds"][0]["fecha_ref"] == "2026-11-25"
    assert datos["resumen"]["por_clase"] == {"mas": 2, "10": 1}
    # Autlán: ni GTFS ni OSM, pero se dice de dónde se buscó.
    vacio = sin.json()
    assert (vacio["origen"], vacio["resumen"]["rutas"], [f["feed"] for f in vacio["feeds"]]) == ("osm", 0, ["osm"])
