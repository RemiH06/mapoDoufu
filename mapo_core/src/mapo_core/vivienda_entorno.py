"""Variables de entorno del dataset de vivienda que Boston no tiene: más censo,
amenidades de DENUE, transporte masivo, parques, relieve, altura de edificios,
verde urbano y temperatura de superficie. Cada función llena columnas de las
filas de `dataset_vivienda`; el diccionario de columnas vive allá.

Todo se mide desde el punto dentro de la AGEB (lon, lat) o sobre su polígono, y
nada se suma en un índice (RNF5).
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from shapely import wkb
from shapely.geometry import mapping

from mapo_core import rubros

RADIO_AMENIDADES_M = 1000

# Amenidades: columna -> clases de DENUE (por sector o por rubro de rubros/*.csv).
AMENIDADES = {
    "escuelas_1km": {"sector": "educacion"},
    "salud_1km": {"sector": "salud"},
    "supermercados_1km": {"rubros": ["supermercado"]},
    "restaurantes_cafes_1km": {"rubros": ["restaurante", "cafeteria_y_neveria"]},
}


def _num(datos: dict, clave: str) -> float | None:
    try:
        return float(datos.get(clave))
    except (TypeError, ValueError):
        return None


def _pct(n: float | None, d: float | None) -> float | None:
    return round(100 * n / d, 2) if n is not None and d else None


def censo_extra(d: dict) -> dict:
    """Columnas adicionales del censo 2020; '*' y 'N/D' quedan vacíos."""
    con_carac = _num(d, "VIVPARH_CV")
    p0_14, p65, p15_64 = _num(d, "POB0_14"), _num(d, "POB65_MAS"), _num(d, "POB15_64")
    return {
        "pct_60ymas": _pct(_num(d, "P_60YMAS"), _num(d, "POBTOT")),
        "razon_dependencia": round(100 * (p0_14 + p65) / p15_64, 2) if None not in (p0_14, p65, p15_64) and p15_64 else None,
        "pct_jefatura_femenina": _pct(_num(d, "HOGJEF_F"), _num(d, "TOTHOG")),
        "pct_nacidos_otra_entidad": _pct(_num(d, "PNACOE"), _num(d, "POBTOT")),
        "pct_con_discapacidad": _pct(_num(d, "PCON_DISC"), _num(d, "POBTOT")),
        "pct_viv_uso_temporal": _pct(_num(d, "VIVPAR_UT"), _num(d, "TVIVPAR")),
        "pct_viv_agua_fuera": _pct(_num(d, "VPH_AGUAFV"), con_carac),
        "pct_viv_sin_drenaje": _pct(_num(d, "VPH_NODREN"), con_carac),
    }


def _metros(lon: np.ndarray, lat: np.ndarray, lat0: float) -> np.ndarray:
    """Equirrectangular local: a la escala de una ciudad, el error es de metros."""
    return np.column_stack([lon * 111_320 * math.cos(math.radians(lat0)), lat * 110_540])


def asignar_amenidades(filas: list[dict], negocios: list[tuple]) -> None:
    """Conteos de DENUE a menos de 1 km del punto de la AGEB y diversidad de giros
    (entropía de Shannon de los sectores, en nats: 0 si todo es de un sector)."""
    if not filas or not negocios:
        return
    clases = rubros.clases()
    lat0 = float(np.median([f["lat"] for f in filas]))
    pts = _metros(np.array([n[1] for n in negocios]), np.array([n[2] for n in negocios]), lat0)
    sector = [clases[n[3]].sector if n[3] in clases else "otro" for n in negocios]
    rubro = [clases[n[3]].rubro if n[3] in clases else "" for n in negocios]
    arbol = cKDTree(pts)
    agebs = _metros(np.array([f["lon"] for f in filas]), np.array([f["lat"] for f in filas]), lat0)
    for f, cerca in zip(filas, arbol.query_ball_point(agebs, RADIO_AMENIDADES_M)):
        f["negocios_1km"] = len(cerca)
        for col, regla in AMENIDADES.items():
            if "sector" in regla:
                f[col] = sum(1 for i in cerca if sector[i] == regla["sector"])
            else:
                f[col] = sum(1 for i in cerca if rubro[i] in regla["rubros"])
        cuenta = Counter(sector[i] for i in cerca)
        total = sum(cuenta.values())
        f["diversidad_giros_1km"] = round(-sum(c / total * math.log(c / total) for c in cuenta.values()), 4) if total else None


def asignar_transporte(filas: list[dict], ruta: Path) -> None:
    """Distancia en línea recta a la estación de transporte masivo más cercana."""
    with open(ruta, encoding="utf-8") as fh:
        est = list(csv.DictReader(fh))
    if not est or not filas:
        return
    lat0 = float(np.median([f["lat"] for f in filas]))
    arbol = cKDTree(_metros(np.array([float(e["lon"]) for e in est]), np.array([float(e["lat"]) for e in est]), lat0))
    dist, idx = arbol.query(_metros(np.array([f["lon"] for f in filas]), np.array([f["lat"] for f in filas]), lat0))
    for f, d, i in zip(filas, dist, idx):
        f["transporte_km"] = round(float(d) / 1000, 3)
        f["transporte_red"] = est[i]["red"]


def _a_utm(geom, lon0: float):
    from rasterio.warp import transform_geom
    from shapely.geometry import shape

    return shape(transform_geom("EPSG:4326", f"EPSG:{32600 + int((lon0 + 180) // 6) + 1}", mapping(geom)))


def _poligonos_osm(ruta: Path) -> list[tuple[str, object]]:
    """(valor de leisure, polígono) de ways cerrados y anillos exteriores de relaciones."""
    from shapely.geometry import Polygon

    salida = []
    for el in json.loads(Path(ruta).read_text(encoding="utf-8"))["elements"]:
        leisure = el.get("tags", {}).get("leisure", "")
        anillos = [el["geometry"]] if el["type"] == "way" and "geometry" in el else             [m["geometry"] for m in el.get("members", []) if m.get("role") == "outer" and "geometry" in m]
        for g in anillos:
            if len(g) >= 4 and g[0] == g[-1]:
                p = Polygon([(c["lon"], c["lat"]) for c in g])
                if p.is_valid and p.area > 0:
                    salida.append((leisure, p))
    return salida


def asignar_parques(filas: list[dict], ruta: Path) -> None:
    """Hectáreas de parque urbano (OSM leisure=park|garden) a menos de 1 km del
    punto de la AGEB, y distancia a la reserva natural más cercana
    (leisure=nature_reserve). Van separadas: una reserva como La Primavera mide
    30,000 ha y llenaba el círculo de 1 km de cualquier AGEB vecina. Los
    polígonos se unen antes: un jardín dentro de un parque no cuenta dos veces."""
    from shapely import STRtree
    from shapely.geometry import Point
    from shapely.ops import unary_union

    poligonos = _poligonos_osm(ruta)
    if not poligonos or not filas:
        return
    lon0 = float(np.median([f["lon"] for f in filas]))
    parques = [p for l, p in poligonos if l in ("park", "garden")]
    reservas = [p for l, p in poligonos if l == "nature_reserve"]
    if parques:
        union = _a_utm(unary_union(parques), lon0)
        partes = list(getattr(union, "geoms", [union]))
        arbol = STRtree(partes)
    reserva = _a_utm(unary_union(reservas), lon0) if reservas else None
    for f in filas:
        punto = _a_utm(Point(f["lon"], f["lat"]), lon0)
        if parques:
            circulo = punto.buffer(RADIO_AMENIDADES_M)
            area = sum(partes[int(i)].intersection(circulo).area for i in arbol.query(circulo, predicate="intersects"))
            f["parques_ha_1km"] = round(area / 10_000, 3)
        if reserva is not None:
            f["reserva_km"] = round(punto.distance(reserva) / 1000, 3)


def media_zonal(filas: list[dict], ruta: Path, columna: str, escala: float = 1.0, solo_positivos: bool = False,
                decimales: int = 3) -> None:
    """Media del ráster sobre el polígono de cada AGEB (píxeles cuyo centro cae
    dentro; si la AGEB es más chica que un píxel, los que toca). `solo_positivos`
    ignora ceros (altura de edificios: 0 es "sin edificio", no altura cero)."""
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom
    from rasterio.windows import Window, from_bounds
    from shapely.geometry import shape

    with rasterio.open(ruta) as r:
        nodata = r.nodata
        for f in filas:
            g = transform_geom("EPSG:4326", r.crs, mapping(wkb.loads(f["_geom"])))
            v = from_bounds(*shape(g).bounds, transform=r.transform).round_offsets().round_lengths()
            v = Window(v.col_off, v.row_off, max(int(v.width), 1), max(int(v.height), 1))
            dentro = ~geometry_mask([g], out_shape=(int(v.height), int(v.width)), transform=r.window_transform(v))
            if not dentro.any():
                dentro = ~geometry_mask([g], out_shape=(int(v.height), int(v.width)),
                                        transform=r.window_transform(v), all_touched=True)
            a = r.read(1, window=v, boundless=True, fill_value=nodata if nodata is not None else 0).astype("float64")
            valido = dentro & np.isfinite(a)
            if nodata is not None and not (isinstance(nodata, float) and math.isnan(nodata)):
                valido &= a != nodata
            if solo_positivos:
                valido &= a > 0
            f[columna] = round(float(a[valido].mean()) * escala, decimales) if valido.any() else None


def asignar_relieve(filas: list[dict], ruta: Path) -> None:
    """Altitud media (m) y pendiente media (grados) de la AGEB con un DEM en grados
    (Copernicus GLO-30). La pendiente se calcula en la ventana de cada AGEB con el
    tamaño del píxel en metros a esa latitud."""
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, from_bounds
    from shapely.geometry import shape

    media_zonal(filas, ruta, "altitud_m", decimales=1)
    with rasterio.open(ruta) as r:
        rx, ry = abs(r.transform.a), abs(r.transform.e)
        for f in filas:
            geom = wkb.loads(f["_geom"])
            o, s, e, n = geom.bounds
            v = from_bounds(o - rx, s - ry, e + rx, n + ry, transform=r.transform).round_offsets().round_lengths()
            v = Window(v.col_off, v.row_off, max(int(v.width), 3), max(int(v.height), 3))
            z = r.read(1, window=v, boundless=True, fill_value=0).astype("float64")
            dx = rx * 111_320 * math.cos(math.radians(f["lat"]))
            dy = ry * 110_540
            gy, gx = np.gradient(z, dy, dx)
            pendiente = np.degrees(np.arctan(np.hypot(gx, gy)))
            dentro = ~geometry_mask([mapping(geom)], out_shape=z.shape, transform=r.window_transform(v), all_touched=True)
            f["pendiente_grados"] = round(float(pendiente[dentro].mean()), 2) if dentro.any() else None
