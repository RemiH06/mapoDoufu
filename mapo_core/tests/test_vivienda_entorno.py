"""Variables de entorno del dataset de vivienda (mapo_core/vivienda_entorno.py)."""

import csv
import json
import math

import numpy as np
from shapely.geometry import box

from mapo_core import rubros, vivienda_entorno as ve


def test_censo_extra_con_reservados():
    d = {"P_60YMAS": "10", "POBTOT": "100", "POB0_14": "20", "POB65_MAS": "5", "POB15_64": "50",
         "HOGJEF_F": "3", "TOTHOG": "12", "PNACOE": "*", "VIVPARH_CV": "40", "VPH_NODREN": "2"}
    r = ve.censo_extra(d)
    assert r["pct_60ymas"] == 10.0
    assert r["razon_dependencia"] == 50.0  # (20 + 5) / 50
    assert r["pct_jefatura_femenina"] == 25.0
    assert r["pct_nacidos_otra_entidad"] is None  # reservado
    assert r["pct_viv_sin_drenaje"] == 5.0


def test_amenidades_y_diversidad():
    clases = rubros.clases()
    restaurante = next(n for n, c in clases.items() if c.rubro == "restaurante")
    escuela = next(n for n, c in clases.items() if c.sector == "educacion")
    fila = {"lon": -103.35, "lat": 20.67}
    # Dos a ~100 m y uno a ~5 km, que no cuenta.
    negocios = [(None, -103.3505, 20.6705, restaurante, ""), (None, -103.3495, 20.6695, escuela, ""),
                (None, -103.30, 20.67, escuela, "")]
    ve.asignar_amenidades([fila], negocios)
    assert fila["negocios_1km"] == 2
    assert fila["restaurantes_cafes_1km"] == 1 and fila["escuelas_1km"] == 1
    assert math.isclose(fila["diversidad_giros_1km"], round(math.log(2), 4))  # dos sectores, mitad y mitad


def test_transporte_mas_cercano(tmp_path):
    ruta = tmp_path / "t.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["red", "nombre", "lon", "lat", "origen"])
        w.writeheader()
        w.writerow({"red": "Mi Tren", "nombre": "A", "lon": -103.35, "lat": 20.68, "origen": "estacion"})
        w.writerow({"red": "Mi Macro Calzada", "nombre": "B", "lon": -103.30, "lat": 20.67, "origen": "anden"})
    fila = {"lon": -103.35, "lat": 20.67}
    ve.asignar_transporte([fila], ruta)
    assert fila["transporte_red"] == "Mi Tren"
    assert 1.05 < fila["transporte_km"] < 1.16  # 0.01° de latitud ≈ 1.1 km


def test_parques_sin_reservas(tmp_path):
    def way(leisure, x0, y0, x1, y1):
        g = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        return {"type": "way", "tags": {"leisure": leisure}, "geometry": [{"lon": x, "lat": y} for x, y in g]}

    ruta = tmp_path / "p.json"
    ruta.write_text(json.dumps({"elements": [
        way("park", -103.3505, 20.6695, -103.3495, 20.6705),  # ~1 ha junto al punto
        way("garden", -103.3502, 20.6698, -103.3498, 20.6702),  # dentro del parque: no suma
        way("nature_reserve", -103.40, 20.60, -103.36, 20.70),  # reserva grande al oeste
    ]}))
    fila = {"lon": -103.35, "lat": 20.67}
    ve.asignar_parques([fila], ruta)
    assert 0.9 < fila["parques_ha_1km"] < 1.3  # la reserva no cuenta como parque
    assert 0.9 < fila["reserva_km"] < 1.2  # 0.01° de longitud ≈ 1.04 km


def test_media_zonal_ignora_ceros_y_nodata(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    ruta = tmp_path / "r.tif"
    a = np.array([[10, 0], [30, -1]], dtype="float32")
    with rasterio.open(ruta, "w", driver="GTiff", height=2, width=2, count=1, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(-104, 21, 0.5, 0.5), nodata=-1) as r:
        r.write(a, 1)
    fila = {"_geom": box(-104, 20, -103, 21).wkb}
    ve.media_zonal([fila], ruta, "x")
    assert fila["x"] == round((10 + 0 + 30) / 3, 3)  # -1 es sin dato
    ve.media_zonal([fila], ruta, "y", solo_positivos=True)
    assert fila["y"] == 20.0  # el 0 no cuenta
