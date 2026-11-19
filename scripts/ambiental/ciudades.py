# /// script
# requires-python = ">=3.11"
# dependencies = ["rasterio", "numpy", "shapely>=2", "pandas", "xlrd", "geopandas>=1.0", "pyogrio", "scipy"]
# ///
"""Calor, arbolado, población y marginación por AGEB urbano de varias metrópolis, para
compararlas. Ver docs/producto/comparacion-ciudades.md.

Pasos por ciudad (cada uno se salta si su salida ya existe, así que se puede relanzar):

    agebs    AGEB urbanos de los municipios de la metrópoli, con su censo 2020, desde la
             base de Mapo (`docker exec` a la base), y la marginación de CONAPO por AGEB.
    dosel    Cobertura de dosel a 10 m desde los mosaicos de ~1 m de Meta y WRI: % del área
             con árboles de 3 m o más, y su altura media.
    zonal    Promedio de cada ráster por AGEB (temperatura, NDVI, dosel), con el número de
             celdas usadas. Sale de los mismos rásteres que se entregan: ArcGIS da lo mismo
             con Zonal Statistics as Table.
    resumen  Tabla comparativa por ciudad.

La temperatura y el NDVI los hace `imagenes.py` (Landsat y Sentinel-2 de Planetary
Computer); este script solo los convierte a unidades reales. `ciudades.sh` corre todo.

    uv run --script scripts/ambiental/ciudades.py --base DIR --paso agebs --ciudad zmg
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).parent
MUNICIPIOS = AQUI / "metropolis_2020_municipios.csv"
FUENTE_METROPOLIS = "https://www.gob.mx/cms/uploads/sedatu/MM2020_06022024.pdf"

# clave: (clave de la metrópoli en Metrópolis de México 2020, nombre corto, EPSG UTM, grupo)
CIUDADES = {
    "zmg": ("14.1.01", "Guadalajara", 32613, "objetivo"),
    "mty": ("19.1.01", "Monterrey", 32614, "similar"),
    "pue": ("21.1.01", "Puebla-Tlaxcala", 32614, "similar"),
    "leo": ("11.1.02", "León", 32614, "similar"),
    "mer": ("31.1.01", "Mérida", 32616, "distinta"),
    "hmo": ("26.2.03", "Hermosillo", 32612, "distinta"),
    "cdmx": ("09.1.01", "Ciudad de México", 32614, "distinta"),
}

# Variables del censo 2020 por AGEB (nombres de INEGI) que viajan a la tabla.
CENSO = ["POBTOT", "POB0_14", "P_0A2", "P_3A5", "P_60YMAS", "POB65_MAS", "PCON_DISC", "PSINDER", "GRAPROES",
         "TVIVPARHAB", "PROM_OCUP", "VPH_AGUAFV", "VPH_NODREN", "VPH_REFRI", "VPH_INTER"]
# Componentes de la marginación urbana de CONAPO 2020 (porcentajes) y el índice y grado.
CONAPO = ["P6A14NAE", "SBASC", "PSDSS", "OVSDE", "OVSEE", "OVSAE", "OVPT", "OVHAC", "OVSREF", "OVSINT", "OVSCEL",
          "IM_2020", "GM_2020", "IMN_2020"]

DOSEL = "https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float"
ALTURA_ARBOL = 3  # m: lo que cuenta como árbol (arbustos y pasto quedan fuera)
AGREGA = 8  # 8 x 8 píxeles de 1.19 m en EPSG:3857 ≈ 9 m en el suelo a 20° de latitud


def municipios(ciudad: str) -> list[str]:
    clave = CIUDADES[ciudad][0]
    with open(MUNICIPIOS, encoding="utf-8") as f:
        return sorted({r["cvegeo"] for r in csv.DictReader(f) if r["clave_metropoli"] == clave})


def carpeta(base: Path, ciudad: str) -> Path:
    c = base / ciudad
    c.mkdir(parents=True, exist_ok=True)
    return c


# --- agebs -----------------------------------------------------------------
def paso_agebs(base: Path, ciudad: str, contenedor: str, usuario: str, bd: str, imu: Path) -> None:
    import geopandas as gpd
    import pandas as pd
    import zipfile

    destino = carpeta(base, ciudad) / "agebs_base.gpkg"
    if destino.exists():
        return
    muns = municipios(ciudad)
    lista = ",".join(f"'{m}'" for m in muns)  # claves de 5 dígitos de nuestro propio CSV
    sql = (
        "SELECT json_build_object('type','FeatureCollection','features',json_agg(json_build_object("
        "'type','Feature','geometry',ST_AsGeoJSON(a.geom,7)::json,'properties',json_build_object("
        "'cvegeo',a.cvegeo,'cve_ent',a.cve_ent,'cve_mun',a.cve_mun,'cve_loc',a.cve_loc,'censo',c.datos_json)))) "
        "FROM agebs a LEFT JOIN fuente_censo_poblacion c ON c.cvegeo = a.cvegeo "
        f"WHERE a.cve_ent || a.cve_mun IN ({lista})"
    )
    salida = subprocess.run(["docker", "exec", contenedor, "psql", "-U", usuario, "-d", bd, "-At", "-c", sql],
                            check=True, capture_output=True, text=True).stdout
    datos = json.loads(salida)
    if not datos["features"]:
        sys.exit(f"{ciudad}: la base no tiene AGEB de {muns}; cargar el estado con cli agebs y censo_poblacion")
    filas = []
    for f in datos["features"]:
        p = f["properties"]
        censo = p.pop("censo") or {}
        for v in CENSO:
            crudo = censo.get(v)
            try:
                p[v.lower()] = float(crudo) if crudo not in (None, "", "*", "N/D") else None
            except ValueError:
                p[v.lower()] = None
        p["censo_reservados"] = sum(1 for v in CENSO if censo.get(v) in ("*", "N/D"))
        filas.append(f)
    g = gpd.GeoDataFrame.from_features(filas, crs="EPSG:4326")
    with zipfile.ZipFile(imu) as z:
        conapo = pd.read_excel(z.open("IMU_2020.xls"), sheet_name="IMU_2020", dtype={"CVE_AGEB": str})
    conapo = conapo.rename(columns={"CVE_AGEB": "cvegeo"})[["cvegeo"] + CONAPO]
    conapo.columns = ["cvegeo"] + [c.lower() for c in CONAPO]
    g = g.merge(conapo, on="cvegeo", how="left")
    utm = CIUDADES[ciudad][2]
    g["area_ha"] = g.to_crs(utm).area / 1e4
    g["densidad_hab_ha"] = g["pobtot"] / g["area_ha"]
    g.insert(0, "ciudad", CIUDADES[ciudad][1])
    g.to_file(destino, driver="GPKG")
    o, s, e, n = g.total_bounds
    caja = [round(o - 0.01, 4), round(s - 0.01, 4), round(e + 0.01, 4), round(n + 0.01, 4)]
    (carpeta(base, ciudad) / "ciudad.json").write_text(json.dumps({
        "ciudad": ciudad, "nombre": CIUDADES[ciudad][1], "clave_metropoli": CIUDADES[ciudad][0],
        "grupo": CIUDADES[ciudad][3], "epsg": utm, "caja": caja, "municipios": muns, "agebs": len(g),
        "con_censo": int(g["pobtot"].notna().sum()), "con_conapo": int(g["im_2020"].notna().sum()),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{ciudad}: {len(g)} AGEB, {int(g['pobtot'].sum()):,} habitantes, caja {caja}", flush=True)


def info(base: Path, ciudad: str) -> dict:
    return json.loads((base / ciudad / "ciudad.json").read_text(encoding="utf-8"))


# --- dosel -----------------------------------------------------------------
def paso_dosel(base: Path, ciudad: str) -> None:
    import rasterio
    import urllib.request
    from rasterio.warp import Resampling, reproject, transform_bounds
    from shapely.geometry import box, shape

    c = carpeta(base, ciudad)
    destino = c / "dosel_cobertura_10m.tif"
    if destino.exists():
        return
    meta = info(base, ciudad)
    caja = tuple(meta["caja"])
    with urllib.request.urlopen(f"{DOSEL}/tiles.geojson", timeout=300) as r:
        indice = json.load(r)
    nombres = sorted(f["properties"]["tile"] for f in indice["features"] if shape(f["geometry"]).intersects(box(*caja)))
    o3, s3, e3, n3 = transform_bounds("EPSG:4326", "EPSG:3857", *caja)
    res = None
    cobertura = altura = None
    leidos = []
    env = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="8", GDAL_HTTP_RETRY_DELAY="5")
    with rasterio.Env(**env):
        for t in nombres:
            with rasterio.open(f"/vsicurl/{DOSEL}/chm/{t}.tif") as src:
                if res is None:
                    res = src.transform.a
                    # Rejilla común en 3857, alineada a los píxeles de los mosaicos.
                    x0 = math.floor(o3 / res) * res
                    y0 = math.ceil(n3 / res) * res
                    ancho = int(math.ceil((e3 - x0) / res / AGREGA))
                    alto = int(math.ceil((y0 - s3) / res / AGREGA))
                    suma_arbol = np.zeros((alto, ancho), np.float32)
                    suma_valido = np.zeros((alto, ancho), np.float32)
                    suma_altura = np.zeros((alto, ancho), np.float32)
                ventana = rasterio.windows.from_bounds(max(x0, src.bounds.left), max(s3, src.bounds.bottom),
                                                       min(e3, src.bounds.right), min(y0, src.bounds.top), src.transform)
                ventana = ventana.round_offsets().round_lengths()
                if ventana.width <= 0 or ventana.height <= 0:
                    continue
                # Que la ventana empiece en un múltiplo de AGREGA de la rejilla común.
                col0 = int(round((src.transform.c + ventana.col_off * res - x0) / res))
                fila0 = int(round((y0 - (src.transform.f - ventana.row_off * res)) / res))
                ajuste_c, ajuste_f = (-col0) % AGREGA, (-fila0) % AGREGA
                col_off, row_off = ventana.col_off + ajuste_c, ventana.row_off + ajuste_f
                w = (ventana.width - ajuste_c) // AGREGA * AGREGA
                h_total = (ventana.height - ajuste_f) // AGREGA * AGREGA
                gc, gf = (col0 + ajuste_c) // AGREGA, (fila0 + ajuste_f) // AGREGA
                paso = AGREGA * 128
                for f in range(0, h_total, paso):
                    h = min(paso, h_total - f)
                    bloque = src.read(1, window=rasterio.windows.Window(col_off, row_off + f, w, h))
                    b = bloque.reshape(h // AGREGA, AGREGA, w // AGREGA, AGREGA)
                    # Los mosaicos no declaran nodata; 0 es "sin dosel". 255 nunca aparece en
                    # alturas reales (el modelo llega a ~60 m), se trata como sin dato por si acaso.
                    valido = b != 255
                    arbol = (b >= ALTURA_ARBOL) & valido
                    f0, c0 = gf + f // AGREGA, gc
                    # Recortar lo que quede fuera de la rejilla común (redondeos en el borde).
                    nf = max(0, min(h // AGREGA, alto - f0))
                    nc = max(0, min(w // AGREGA, ancho - c0))
                    if nf == 0 or nc == 0:
                        continue
                    sel = (slice(f0, f0 + nf), slice(c0, c0 + nc))
                    suma_arbol[sel] += arbol.sum(axis=(1, 3))[:nf, :nc]
                    suma_valido[sel] += valido.sum(axis=(1, 3))[:nf, :nc]
                    suma_altura[sel] += np.where(arbol, b, 0).sum(axis=(1, 3))[:nf, :nc]
                leidos.append(t)
                print(f"  {ciudad} dosel: mosaico {t} listo", flush=True)
    if res is None:
        sys.exit(f"{ciudad}: ningún mosaico de dosel toca la caja")
    with np.errstate(invalid="ignore", divide="ignore"):
        cobertura = np.where(suma_valido > 0, 100 * suma_arbol / suma_valido, np.nan).astype(np.float32)
        altura = np.where(suma_arbol > 0, suma_altura / suma_arbol, np.nan).astype(np.float32)
    t3857 = rasterio.transform.from_origin(x0, y0, res * AGREGA, res * AGREGA)
    utm = meta["epsg"]
    o, s, e, n = transform_bounds("EPSG:4326", f"EPSG:{utm}", *caja)
    tu = rasterio.transform.from_origin(math.floor(o / 10) * 10, math.ceil(n / 10) * 10, 10, 10)
    wu, hu = int(math.ceil((e - tu.c) / 10)), int(math.ceil((tu.f - s) / 10))
    for arr, ruta, desc in ((cobertura, destino, "% del área con dosel de 3 m o más"),
                            (altura, c / "dosel_altura_media_10m.tif", "altura media del dosel de 3 m o más (m)")):
        salida = np.full((hu, wu), np.nan, np.float32)
        reproject(arr, salida, src_transform=t3857, src_crs="EPSG:3857", src_nodata=np.nan, dst_transform=tu,
                  dst_crs=f"EPSG:{utm}", dst_nodata=np.nan, resampling=Resampling.bilinear)
        perfil = dict(driver="GTiff", width=wu, height=hu, count=1, dtype="float32", crs=f"EPSG:{utm}",
                      transform=tu, nodata=-9999, compress="deflate", predictor=3, tiled=True)
        with rasterio.open(ruta.with_suffix(".tmp.tif"), "w", **perfil) as dst:
            dst.write(np.where(np.isnan(salida), -9999, salida), 1)
            dst.set_band_description(1, desc)
        ruta.with_suffix(".tmp.tif").replace(ruta)
    with open(c / "procedencia_dosel.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mosaico", "url", "licencia"])
        for t in leidos:
            w.writerow([t, f"{DOSEL}/chm/{t}.tif", "CC BY 4.0, Meta y WRI (Tolan et al. 2024)"])


# --- rásteres en unidades reales --------------------------------------------
def unidades_reales(base: Path, ciudad: str, anio: int, meses: list[str]) -> None:
    """lst_secas_AAAA.tif (°C x 100) a °C y la mediana de los NDVI mensuales a NDVI."""
    import rasterio

    c = carpeta(base, ciudad)
    im = c / "imagenes"
    lst = c / f"temperatura_superficie_secas_{anio}_C.tif"
    if not lst.exists() and (im / f"lst_secas_{anio}.tif").exists():
        with rasterio.open(im / f"lst_secas_{anio}.tif") as src:
            d = src.read(1).astype(np.float32)
            d = np.where(d == src.nodata, -9999, d / 100)
            perfil = src.profile | {"dtype": "float32", "nodata": -9999, "compress": "deflate", "predictor": 3}
        with rasterio.open(lst, "w", **perfil) as dst:
            dst.write(d, 1)
            dst.set_band_description(1, f"Temperatura de superficie (°C), mediana de marzo a mayo de {anio}, Landsat 8 y 9")
    ndvi = c / f"ndvi_secas_{anio}.tif"
    if not ndvi.exists():
        capas = []
        perfil = None
        for m in meses:
            p = im / f"s2_indices_{m}.tif"
            if p.exists():
                with rasterio.open(p) as src:
                    d = src.read(1).astype(np.float32)
                    capas.append(np.where(d == src.nodata, np.nan, d / 10000))
                    perfil = src.profile
        if capas:
            with np.errstate(all="ignore"):
                med = np.nanmedian(np.stack(capas), axis=0)
            perfil = perfil | {"count": 1, "dtype": "float32", "nodata": -9999, "compress": "deflate", "predictor": 3}
            with rasterio.open(ndvi, "w", **perfil) as dst:
                dst.write(np.where(np.isnan(med), -9999, med).astype(np.float32), 1)
                dst.set_band_description(1, f"NDVI, mediana de los compuestos mensuales {', '.join(meses)} (Sentinel-2)")


# --- zonal -----------------------------------------------------------------
def promedio_por_ageb(gdf, ruta: Path):
    """Media de las celdas cuyo centro cae en cada AGEB (la regla de Zonal Statistics de
    ArcGIS) y cuántas celdas fueron."""
    import rasterio
    from rasterio.features import rasterize

    with rasterio.open(ruta) as src:
        d = src.read(1)
        g = gdf.to_crs(src.crs)
        ids = rasterize(((geom, i + 1) for i, geom in enumerate(g.geometry)), out_shape=d.shape,
                        transform=src.transform, fill=0, dtype="int32")
        valido = (d != src.nodata) & ~np.isnan(d) & (ids > 0)
        n = np.bincount(ids[valido], minlength=len(g) + 1)[1:]
        s = np.bincount(ids[valido], weights=d[valido].astype(np.float64), minlength=len(g) + 1)[1:]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, s / n, np.nan), n


def paso_zonal(base: Path, ciudad: str, anio: int) -> None:
    import geopandas as gpd

    c = carpeta(base, ciudad)
    destino = c / f"agebs_{ciudad}.gpkg"
    g = gpd.read_file(c / "agebs_base.gpkg")
    for campo, archivo in (("lst_c", f"temperatura_superficie_secas_{anio}_C.tif"), ("ndvi", f"ndvi_secas_{anio}.tif"),
                           ("dosel_pct", "dosel_cobertura_10m.tif"), ("dosel_altura_m", "dosel_altura_media_10m.tif")):
        if (c / archivo).exists():
            g[campo], g[f"{campo}_celdas"] = promedio_por_ageb(g, c / archivo)
        else:
            g[campo], g[f"{campo}_celdas"] = np.nan, 0
    # Contra la propia ciudad: cuánto más caliente que la AGEB mediana de su metrópoli.
    g["lst_vs_mediana_ciudad_c"] = g["lst_c"] - g["lst_c"].median()
    g.to_file(destino, driver="GPKG")
    g.drop(columns="geometry").to_csv(c / f"agebs_{ciudad}.csv", index=False, encoding="utf-8")
    print(f"{ciudad}: zonal listo ({g['lst_c'].notna().sum()} con temperatura, {g['dosel_pct'].notna().sum()} con dosel)", flush=True)


# --- colonias (solo la ciudad objetivo) ----------------------------------------
def paso_colonias(base: Path, ciudad: str, anio: int, imc: Path) -> None:
    """Colonias de CONAPO (índice de marginación urbana 2020 por colonia) de los
    municipios de la metrópoli, con los mismos promedios que los AGEB. Es la única
    cartografía pública de colonias con nombre."""
    import geopandas as gpd
    import zipfile

    c = carpeta(base, ciudad)
    muns = municipios(ciudad)
    with zipfile.ZipFile(imc) as z:
        shp = next(n for n in z.namelist() if n.lower().endswith(".shp"))
    g = gpd.read_file(f"zip://{imc}!{shp}")
    # CVE_COL es EEMMM_NNNN: el municipio son sus primeros 5 dígitos.
    g = g[g["CVE_COL"].astype(str).str[:5].isin(muns)].to_crs(CIUDADES[ciudad][2])
    g["area_ha"] = g.area / 1e4
    for campo, archivo in (("lst_c", f"temperatura_superficie_secas_{anio}_C.tif"), ("ndvi", f"ndvi_secas_{anio}.tif"),
                           ("dosel_pct", "dosel_cobertura_10m.tif"), ("dosel_altura_m", "dosel_altura_media_10m.tif")):
        g[campo], g[f"{campo}_celdas"] = promedio_por_ageb(g, c / archivo)
    g["lst_vs_mediana_ciudad_c"] = g["lst_c"] - g["lst_c"].median()
    g.to_file(c / f"colonias_{ciudad}.gpkg", driver="GPKG")
    g.drop(columns="geometry").to_csv(c / f"colonias_{ciudad}.csv", index=False, encoding="utf-8")
    print(f"{ciudad}: {len(g)} colonias", flush=True)


# --- resumen ---------------------------------------------------------------
def paso_resumen(base: Path, anio: int) -> None:
    import geopandas as gpd
    import pandas as pd
    from scipy.stats import spearmanr

    filas = []
    for ciudad, (clave, nombre, _, grupo) in CIUDADES.items():
        p = base / ciudad / f"agebs_{ciudad}.gpkg"
        if not p.exists():
            continue
        g = gpd.read_file(p)
        g = g[g["pobtot"].fillna(0) > 0].copy()
        # En el índice de CONAPO 2020, más alto es MENOS marginado (grado "Muy bajo" ~125,
        # "Muy alto" ~113). Para que las correlaciones se lean derecho, se invierte.
        g["marginacion"] = -g["im_2020"]
        pob = g["pobtot"]

        def pond(campo):
            ok = g[campo].notna()
            return float(np.average(g.loc[ok, campo], weights=pob[ok])) if ok.any() else None

        def rho(a, b):
            ok = g[a].notna() & g[b].notna()
            return round(float(spearmanr(g.loc[ok, a], g.loc[ok, b]).statistic), 2) if ok.sum() > 10 else None

        q = g.dropna(subset=["marginacion", "lst_c"])
        # Quintil 4 = el quinto de AGEB más marginado; 0 = el menos marginado.
        quintil = pd.qcut(q["marginacion"], 5, labels=False, duplicates="drop") if len(q) >= 25 else None
        filas.append({
            "ciudad": nombre, "grupo": grupo, "clave_metropoli": clave, "agebs_con_poblacion": len(g),
            "poblacion": int(pob.sum()),
            "lst_c_mediana_agebs": round(float(g["lst_c"].median()), 2),
            "lst_c_ponderada_poblacion": round(pond("lst_c"), 2) if pond("lst_c") is not None else None,
            "lst_c_p90_menos_p10": round(float(g["lst_c"].quantile(0.9) - g["lst_c"].quantile(0.1)), 2),
            "dosel_pct_mediana_agebs": round(float(g["dosel_pct"].median()), 2),
            "dosel_pct_ponderado_poblacion": round(pond("dosel_pct"), 2) if pond("dosel_pct") is not None else None,
            "poblacion_en_agebs_con_dosel_menor_a_5pct": int(pob[g["dosel_pct"] < 5].sum()),
            "ndvi_mediana_agebs": round(float(g["ndvi"].median()), 3),
            "spearman_dosel_vs_lst": rho("dosel_pct", "lst_c"),
            "spearman_ndvi_vs_lst": rho("ndvi", "lst_c"),
            "spearman_marginacion_vs_lst": rho("marginacion", "lst_c"),
            "spearman_marginacion_vs_dosel": rho("marginacion", "dosel_pct"),
            "lst_c_quintil_mas_marginado_menos_menos_marginado": (
                round(float(q.loc[quintil == quintil.max(), "lst_c"].median() - q.loc[quintil == 0, "lst_c"].median()), 2)
                if quintil is not None else None),
            "dosel_pct_quintil_mas_marginado_menos_menos_marginado": (
                round(float(q.loc[quintil == quintil.max(), "dosel_pct"].median() - q.loc[quintil == 0, "dosel_pct"].median()), 2)
                if quintil is not None else None),
            "anio_imagenes": anio,
        })
    pd.DataFrame(filas).to_csv(base / "comparacion_ciudades.csv", index=False, encoding="utf-8")
    print(pd.DataFrame(filas).to_string(), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--paso", required=True, choices=["agebs", "dosel", "reales", "zonal", "colonias", "resumen"])
    ap.add_argument("--ciudad", choices=list(CIUDADES))
    ap.add_argument("--anio", type=int, default=2025)
    ap.add_argument("--meses", default="2025-03,2025-04,2025-05")
    ap.add_argument("--contenedor", default="mapo-prod-db-1")
    ap.add_argument("--usuario", default="mapo")
    ap.add_argument("--bd", default="mapo_prod")
    ap.add_argument("--imc", type=Path, default=Path.home() / "srv/mapo-crudos/ambiental/marginacion/imc_2020_colonias_shp.zip")
    ap.add_argument("--imu", type=Path, default=Path.home() / "srv/mapo-crudos/ambiental/marginacion/imu_2020_ageb.zip")
    a = ap.parse_args()
    if a.paso == "resumen":
        paso_resumen(a.base, a.anio)
        return
    if not a.ciudad:
        sys.exit("--ciudad es obligatorio para este paso")
    if a.paso == "agebs":
        paso_agebs(a.base, a.ciudad, a.contenedor, a.usuario, a.bd, a.imu)
    elif a.paso == "dosel":
        paso_dosel(a.base, a.ciudad)
    elif a.paso == "colonias":
        paso_colonias(a.base, a.ciudad, a.anio, a.imc)
    elif a.paso == "reales":
        unidades_reales(a.base, a.ciudad, a.anio, a.meses.split(","))
    else:
        paso_zonal(a.base, a.ciudad, a.anio)


if __name__ == "__main__":
    main()
