# /// script
# requires-python = ">=3.11"
# dependencies = ["rasterio", "numpy", "shapely>=2", "pandas", "xlrd", "geopandas>=1.0", "pyogrio", "scipy", "odc-stac", "planetary-computer", "pystac-client", "rioxarray", "dask"]
# ///
"""Entrega en shapefile, solo con datos de 2020: marginación (CONAPO) y temperatura de
superficie (Landsat 8) por AGEB urbano de Guadalajara, Monterrey y Querétaro.
Ver docs/producto/comparacion-ciudades.md, sección "Entrega 2020".

    uv run --script scripts/ambiental/ciudades_2020.py base --crudos DIR --base DIR
    uv run --script scripts/ambiental/ciudades_2020.py lst     --base DIR
    uv run --script scripts/ambiental/ciudades_2020.py entrega --base DIR --salida DIR

`--crudos` trae, bajados del productor: mg_14_jalisco.zip, mg_19_nuevoleon.zip y
mg_22_queretaro.zip (INEGI, Marco Geoestadístico del censo 2020), censo_14.zip,
censo_19.zip y censo_22.zip (INEGI, censo 2020 por AGEB) e IMU_2020.zip (CONAPO).
No usa la base de Mapo.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI))
from ciudades import MUNICIPIOS, promedio_por_ageb  # noqa: E402

ANIO = 2020
# sigla: (clave de Metrópolis de México 2020, nombre, EPSG UTM, entidad, zip del marco)
CIUDADES = {
    "GDL": ("14.1.01", "Guadalajara", 32613, "14", "mg_14_jalisco.zip"),
    "MTY": ("19.1.01", "Monterrey", 32614, "19", "mg_19_nuevoleon.zip"),
    "QRO": ("22.1.01", "Querétaro", 32614, "22", "mg_22_queretaro.zip"),
}
INDICADORES = ["P6A14NAE", "SBASC", "PSDSS", "OVSDE", "OVSEE", "OVSAE", "OVPT", "OVSREF", "OVSINT", "OVSCEL", "OVHAC"]
CONAPO = INDICADORES + ["IM_2020", "GM_2020", "IMN_2020"]
GRADOS = {"Muy bajo": 1, "Bajo": 2, "Medio": 3, "Alto": 4, "Muy alto": 5}


def municipios(sigla: str) -> list[str]:
    with open(MUNICIPIOS, encoding="utf-8") as f:
        return sorted(r["cvegeo"] for r in csv.DictReader(f) if r["clave_metropoli"] == CIUDADES[sigla][0])


def marco(crudos: Path, sigla: str, capa: str) -> gpd.GeoDataFrame:
    _, _, epsg, ent, archivo = CIUDADES[sigla]
    ruta = (crudos / archivo).as_posix()
    g = gpd.read_file(f"zip://{ruta}!conjunto_de_datos/{ent}{capa}.shp")
    g = g[(g["CVE_ENT"] + g["CVE_MUN"]).isin(municipios(sigla))].copy()
    # El marco viene en Lambert ITRF2008: es EPSG:6372 con otra cabecera.
    g = g.set_crs(6372, allow_override=True).to_crs(epsg)
    g["geometry"] = g.geometry.make_valid()
    return g


def censo(crudos: Path, ent: str) -> pd.DataFrame:
    with zipfile.ZipFile(crudos / f"censo_{ent}.zip") as z:
        nombre = next(n for n in z.namelist() if n.endswith(f"conjunto_de_datos_ageb_urbana_{ent}_cpv2020.csv"))
        # Unos estados vienen en UTF-8 con BOM y otros en Latin-1; solo se leen claves y números.
        d = pd.read_csv(z.open(nombre), dtype=str, encoding="latin-1")
    d.columns = [c.replace("ï»¿", "") for c in d.columns]
    d = d[(d["MZA"] == "000") & (d["AGEB"] != "0000")]  # renglón de total del AGEB
    return pd.DataFrame({"CVEGEO": d["ENTIDAD"] + d["MUN"] + d["LOC"] + d["AGEB"], "POBTOT": d["POBTOT"].astype(int)})


def conapo(crudos: Path) -> pd.DataFrame:
    with zipfile.ZipFile(crudos / "IMU_2020.zip") as z:
        d = pd.read_excel(z.open("IMU_2020.xls"), sheet_name="IMU_2020", dtype={"CVE_AGEB": str})
    return d.rename(columns={"CVE_AGEB": "CVEGEO"})[["CVEGEO", "POB_TOTAL"] + CONAPO]


def paso_base(crudos: Path, base: Path) -> None:
    imu = conapo(crudos)
    for s, (_, _, epsg, ent, _) in CIUDADES.items():
        c = base / s
        c.mkdir(parents=True, exist_ok=True)
        mun = marco(crudos, s, "mun")
        assert len(mun) == len(municipios(s)), s
        g = marco(crudos, s, "a")
        g["CVE_MUN"] = g["CVE_ENT"] + g["CVE_MUN"]
        g["NOM_MUN"] = g["CVE_MUN"].map(dict(zip(mun["CVEGEO"], mun["NOMGEO"])))
        g["CIUDAD"] = s
        g = g[["CVEGEO", "CIUDAD", "CVE_MUN", "NOM_MUN", "geometry"]]
        assert g["CVEGEO"].is_unique
        g = g.merge(censo(crudos, ent), on="CVEGEO", how="left").merge(imu, on="CVEGEO", how="left")
        fuera = imu[imu["CVEGEO"].str[:5].isin(municipios(s)) & ~imu["CVEGEO"].isin(g["CVEGEO"])]
        ok = g["POB_TOTAL"].notna()
        print(f"{s}: {len(g)} AGEB, {int(g['POBTOT'].sum()):,} hab, {int(g['POBTOT'].isna().sum())} sin censo, "
              f"{int(ok.sum())} con CONAPO, {len(fuera)} de CONAPO sin polígono, "
              f"{int((g.loc[ok, 'POBTOT'] != g.loc[ok, 'POB_TOTAL']).sum())} con población distinta entre INEGI y CONAPO")
        g["AREA_HA"] = g.area / 1e4
        g["DENS_HA"] = g["POBTOT"] / g["AREA_HA"]
        g["GM_NUM"] = g["GM_2020"].map(GRADOS)
        g["MARG"] = -g["IM_2020"]
        g.drop(columns="POB_TOTAL").to_file(c / "agebs.gpkg", driver="GPKG")
        mun[["CVEGEO", "NOMGEO", "geometry"]].to_file(c / "municipios.gpkg", driver="GPKG")
        o, sur, e, n = g.to_crs(4326).total_bounds
        caja = [round(o - 0.01, 4), round(sur - 0.01, 4), round(e + 0.01, 4), round(n + 0.01, 4)]
        (c / "ciudad.json").write_text(json.dumps({"caja": caja, "epsg": epsg}), encoding="utf-8")


# --- temperatura -------------------------------------------------------------
# Época cálida antes de que cierren las lluvias. Con marzo a mayo y la mediana por píxel de
# `imagenes.py`, Monterrey juntaba 2 fechas despejadas por píxel, distintas según la nube y
# de 28 a 48 °C: la mediana pintaba la nubosidad, no la ciudad.
PERIODO = ("2020-03-01", "2020-06-30")
DESPEJADO_MINIMO = 0.98  # de los píxeles de la mancha urbana (AGEB con índice)
DESPEJADO_TABLA = 0.90  # desde aquí una fecha entra a la tabla de correlación por fecha
ORBITA = {"GDL": "029", "MTY": "028", "QRO": "027"}  # la que cubre la ciudad completa
MALOS = 0b11110  # QA_PIXEL: nube dilatada (1), cirros (2), nube (3), sombra (4)


def leer_fecha(items, caja, epsg):
    import planetary_computer
    from odc.stac import load

    ds = load(items, bands=["lwir11", "qa_pixel"], bbox=caja, crs=f"EPSG:{epsg}", resolution=30, groupby="solar_day",
              patch_url=planetary_computer.sign, fail_on_error=True, chunks={}).compute()
    assert ds.sizes["time"] == 1
    dn, qa = ds.lwir11.values[0], ds.qa_pixel.values[0]
    c = dn.astype(np.float32) * 0.00341802 + 149.0 - 273.15
    c[(qa & MALOS > 0) | (dn == 0)] = np.nan
    return c, ds.odc.geobox.transform


def paso_lst(base: Path) -> None:
    import pystac_client
    import rasterio
    from rasterio.features import rasterize
    from scipy.stats import spearmanr

    catalogo = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    for s, (_, nombre, epsg, _, _) in CIUDADES.items():
        caja = json.loads((base / s / "ciudad.json").read_text(encoding="utf-8"))["caja"]
        g = gpd.read_file(base / s / "agebs.gpkg")
        g = g[g["IM_2020"].notna()].reset_index(drop=True)
        items = list(catalogo.search(
            collections=["landsat-c2-l2"], bbox=caja, datetime=f"{ANIO}-01-01/{ANIO}-12-31",
            query={"platform": {"eq": "landsat-8"}, "landsat:wrs_path": {"eq": ORBITA[s]}, "eo:cloud_cover": {"lt": 80}}).items())
        filas, usadas, ids = [], [], None
        for dia in sorted({i.datetime.date() for i in items}):
            escenas = [i for i in items if i.datetime.date() == dia]
            c, t = leer_fecha(escenas, caja, epsg)
            if ids is None:
                ids = rasterize(((x, i + 1) for i, x in enumerate(g.geometry)), out_shape=c.shape, transform=t, fill=0, dtype="int32")
                total = np.bincount(ids[ids > 0], minlength=len(g) + 1)[1:]
            f = (ids > 0) & np.isfinite(c)
            n = np.bincount(ids[f], minlength=len(g) + 1)[1:]
            suma = np.bincount(ids[f], weights=c[f], minlength=len(g) + 1)[1:]
            fraccion = float(f.sum() / (ids > 0).sum())
            usa = PERIODO[0] <= str(dia) <= PERIODO[1] and fraccion >= DESPEJADO_MINIMO
            if usa:
                usadas.append(c)
            if fraccion >= DESPEJADO_TABLA:
                m = n >= 0.9 * np.maximum(total, 1)
                z = suma[m] / n[m]
                filas.append({"ciudad": nombre, "fecha": dia, "urbano_despejado_pct": round(100 * fraccion, 1),
                              "usada_en_LST_C": "sí" if usa else "no", "agebs": int(m.sum()),
                              "lst_c_mediana": round(float(np.median(z)), 2),
                              "spearman_marginacion": round(float(spearmanr(g.loc[m, "MARG"], z).statistic), 3),
                              "escenas": " ".join(sorted(i.id for i in escenas))})
        # Promedio simple de las fechas usadas, solo donde todas tienen dato (np.mean
        # deja NaN si falta una).
        comp = np.mean(np.stack(usadas), axis=0)
        sin_dato = float(np.isnan(comp[ids > 0]).mean())
        perfil = dict(driver="GTiff", width=comp.shape[1], height=comp.shape[0], count=1, dtype="float32", crs=f"EPSG:{epsg}",
                      transform=t, nodata=-9999, compress="deflate", predictor=3, tiled=True)
        with rasterio.open(base / s / "lst.tif", "w", **perfil) as dst:
            dst.write(np.where(np.isnan(comp), -9999, comp).astype(np.float32), 1)
            dst.set_band_description(1, f"Temperatura de superficie (°C), promedio de {len(usadas)} fechas de marzo a junio de {ANIO}, Landsat 8")
        pd.DataFrame(filas).to_csv(base / s / "fechas.csv", index=False, encoding="utf-8")
        print(f"{s}: {len(usadas)} fechas, {sin_dato:.1%} de la mancha urbana sin dato", flush=True)


# Campo (máximo 10 letras, por el formato shapefile): descripción, fuente.
CAMPOS = {
    "CVEGEO": ("Clave del AGEB urbano (13 caracteres)", "INEGI, Marco Geoestadístico 2020"),
    "CIUDAD": ("GDL, MTY o QRO", "SEDATU, CONAPO e INEGI, Metrópolis de México 2020"),
    "CVE_MUN": ("Clave del municipio (entidad y municipio, 5 dígitos)", "INEGI, Marco Geoestadístico 2020"),
    "NOM_MUN": ("Nombre del municipio", "INEGI, Marco Geoestadístico 2020"),
    "POBTOT": ("Población total", "INEGI, censo 2020"),
    "AREA_HA": ("Área del AGEB (ha), en la UTM de la ciudad", "Calculado"),
    "DENS_HA": ("Habitantes por hectárea", "Calculado: POBTOT / AREA_HA"),
    "IM_2020": ("Índice de marginación urbana 2020. Más ALTO es MENOS marginado", "CONAPO, IMU 2020"),
    "IMN_2020": ("Índice normalizado (0 a 1). Más alto es menos marginado", "CONAPO, IMU 2020"),
    "GM_2020": ("Grado de marginación (texto)", "CONAPO, IMU 2020"),
    "GM_NUM": ("Grado como número: 1 muy bajo, 2 bajo, 3 medio, 4 alto, 5 muy alto", "Calculado de GM_2020"),
    "MARG": ("IM_2020 con el signo invertido: más alto es MÁS marginado", "Calculado: -IM_2020"),
    "LST_C": ("Temperatura de superficie promedio del AGEB (°C); promedio de las fechas despejadas de marzo a junio de 2020", "USGS, Landsat 8 C2 L2"),
    "LST_CELDAS": ("Píxeles de 30 m promediados en LST_C", "Calculado"),
    "LST_DIF": ("LST_C menos la mediana de los AGEB de su ciudad (°C)", "Calculado"),
    "P6A14NAE": ("% de población de 6 a 14 años que no asiste a la escuela", "CONAPO, IMU 2020"),
    "SBASC": ("% de población de 15 años o más sin educación básica", "CONAPO, IMU 2020"),
    "PSDSS": ("% de población sin derechohabiencia a los servicios de salud", "CONAPO, IMU 2020"),
    "OVSDE": ("% de ocupantes en viviendas sin drenaje ni excusado", "CONAPO, IMU 2020"),
    "OVSEE": ("% de ocupantes en viviendas sin energía eléctrica", "CONAPO, IMU 2020"),
    "OVSAE": ("% de ocupantes en viviendas sin agua entubada", "CONAPO, IMU 2020"),
    "OVPT": ("% de ocupantes en viviendas con piso de tierra", "CONAPO, IMU 2020"),
    "OVSREF": ("% de ocupantes en viviendas sin refrigerador", "CONAPO, IMU 2020"),
    "OVSINT": ("% de ocupantes en viviendas sin internet", "CONAPO, IMU 2020"),
    "OVSCEL": ("% de ocupantes en viviendas sin celular", "CONAPO, IMU 2020"),
    "OVHAC": ("% de ocupantes en viviendas con hacinamiento", "CONAPO, IMU 2020"),
}
DECIMALES = {"AREA_HA": 4, "DENS_HA": 2, "IM_2020": 6, "IMN_2020": 6, "MARG": 6, "LST_C": 3, "LST_DIF": 3} | {
    k: 4 for k in INDICADORES}

MG = "https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/bvinegi/productos/geografia/marcogeo/889463807469/"
CENSO = "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/ageb_manzana/ageb_mza_urbana_EE_cpv2020_csv.zip"
FUENTES = [
    ("Qué municipios forman cada metrópoli", "SEDATU, CONAPO e INEGI, Metrópolis de México 2020 (edición 2024)",
     "https://www.gob.mx/cms/uploads/sedatu/MM2020_06022024.pdf", "Cuadros A del PDF; copia en municipios_por_ciudad.csv"),
    ("Polígonos de AGEB urbanos y municipios", "INEGI, Marco Geoestadístico, Censo de Población y Vivienda 2020",
     f"{MG}14_jalisco.zip ; {MG}19_nuevoleon.zip ; {MG}22_queretaro.zip", "Capas EEa.shp y EEmun.shp. Términos de libre uso de INEGI"),
    ("Población por AGEB", "INEGI, Censo de Población y Vivienda 2020", CENSO,
     "EE = 14, 19 y 22. Renglón de total del AGEB (MZA = 000), columna POBTOT. Términos de libre uso de INEGI"),
    ("Marginación por AGEB", "CONAPO, Índice de marginación urbana 2020",
     "https://conapo.segob.gob.mx/work/models/CONAPO/Datos_Abiertos/Marginacion/IMU_2020.zip",
     "sha256 17fdd6a31a57d4deb5519fe1e7bd58e7e52d115cf0474d6b59fbf9a52cde26b9. Datos abiertos"),
    ("Temperatura de superficie", "USGS, Landsat 8 Collection 2 Level-2, banda térmica ST_B10",
     "https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2 (mismos productos que https://earthexplorer.usgs.gov)",
     "Copia del producto del USGS en Microsoft Planetary Computer. K = DN × 0.00341802 + 149.0; sin nubes, cirros ni sombras "
     "(QA_PIXEL bits 1 a 4). Promedio de las fechas de marzo a junio de 2020 con 98 % o más de la mancha urbana despejada, "
     "una sola órbita por ciudad (GDL 029, MTY 028, QRO 027), solo píxeles limpios en todas las fechas. "
     "Escenas en escenas_landsat.csv. Dominio público"),
]


def n_efectivo(x, y, xy, clases: int = 30) -> float:
    """Tamaño de muestra efectivo con autocorrelación espacial (Clifford, Richardson y
    Hémon 1989; Dutilleul 1993): 1 + n² / traza(Rx Ry), con los correlogramas por clases
    de distancia."""
    from scipy.spatial.distance import pdist

    n = len(x)
    zx, zy = (x - x.mean()) / x.std(), (y - y.mean()) / y.std()
    d = pdist(xy)
    i, j = np.triu_indices(n, 1)
    # Hasta la mitad de la distancia máxima: más allá hay pocos pares y solo hay ruido.
    clase = np.digitize(d, np.linspace(0, d.max() / 2, clases + 1)) - 1
    traza = float(n)  # distancia 0: cada AGEB consigo mismo
    for k in range(clases):
        m = clase == k
        pares = int(m.sum())
        if pares:
            traza += 2 * pares * np.mean(zx[i[m]] * zx[j[m]]) * np.mean(zy[i[m]] * zy[j[m]])
    return float(np.clip(1 + n ** 2 / traza, 3, n)) if traza > 0 else float(n)


def fila_correlacion(nombre: str, g: gpd.GeoDataFrame) -> dict:
    from scipy.stats import pearsonr, rankdata, spearmanr, t

    x, y = g["MARG"].to_numpy(), g["LST_C"].to_numpy()
    r = float(spearmanr(x, y).statistic)
    xy = np.c_[g.geometry.centroid.x, g.geometry.centroid.y]
    ne = n_efectivo(rankdata(x), rankdata(y), xy)
    p = float(2 * t.sf(abs(r) * np.sqrt((ne - 2) / (1 - r ** 2)), ne - 2))
    q = pd.qcut(g["MARG"], 5, labels=False)
    mas, menos = g.loc[q == 4, "LST_C"].median(), g.loc[q == 0, "LST_C"].median()
    return {"ciudad": nombre, "agebs": len(g), "poblacion": int(g["POBTOT"].sum()),
            "lst_c_mediana": round(float(g["LST_C"].median()), 2),
            "spearman": round(r, 3), "pearson": round(float(pearsonr(x, y).statistic), 3),
            "n_efectivo": round(ne), "p_ajustada": float(f"{p:.2g}"),
            "lst_c_quinto_mas_marginado": round(float(mas), 2),
            "lst_c_quinto_menos_marginado": round(float(menos), 2), "diferencia_c": round(float(mas - menos), 2)}


def escribir_shp(g: gpd.GeoDataFrame, ruta: Path) -> None:
    g = g.copy()
    for c in g.columns:
        if c in DECIMALES:
            g[c] = g[c].round(DECIMALES[c])
    g.to_file(ruta, driver="ESRI Shapefile", encoding="utf-8", promote_to_multi=True)


def paso_entrega(base: Path, salida: Path) -> None:
    if salida.exists():
        sys.exit(f"{salida} ya existe: borrarla o dar otra --salida")
    for sub in ("shapefiles", "rasters", "tablas", "procedencia"):
        (salida / sub).mkdir(parents=True)
    todas, completas, correl, grados, fechas = [], [], [], [], []
    for s, (_, nombre, _, _, _) in CIUDADES.items():
        c = base / s
        tif = salida / "rasters" / f"LST_{s}_2020_C.tif"
        shutil.copy(c / "lst.tif", tif)
        g = gpd.read_file(c / "agebs.gpkg")
        g["LST_C"], g["LST_CELDAS"] = promedio_por_ageb(g, tif)
        ok = g["IM_2020"].notna() & g["LST_C"].notna()
        g["LST_DIF"] = g["LST_C"] - g.loc[ok, "LST_C"].median()
        g = g[list(CAMPOS) + ["geometry"]]
        for k in ("POBTOT", "LST_CELDAS"):
            g[k] = g[k].astype("int32")
        d = salida / "shapefiles" / s
        d.mkdir()
        # El DBF no guarda vacíos y ArcGIS los lee como 0: los AGEB sin índice van en otra
        # capa, sin esas columnas.
        con, sin = g[ok].copy(), g[~ok].copy()
        con["GM_NUM"] = con["GM_NUM"].astype("int32")
        escribir_shp(con, d / f"AGEB_{s}_2020.shp")
        sin["MOTIVO"] = np.where(sin["LST_C"].isna(), "Sin temperatura",
                                 np.where(sin["POBTOT"] == 0, "Sin población", "Sin índice de CONAPO"))
        escribir_shp(sin[["CVEGEO", "CIUDAD", "CVE_MUN", "NOM_MUN", "POBTOT", "AREA_HA", "MOTIVO", "geometry"]],
                     d / f"AGEB_{s}_sin_dato.shp")
        escribir_shp(gpd.read_file(c / "municipios.gpkg"), d / f"MUN_{s}_2020.shp")
        print(f"{s}: {len(con)} AGEB con los dos datos; {sin['MOTIVO'].value_counts().to_dict()}")
        todas.append(g.drop(columns="geometry"))
        completas.append(con.to_crs(6372))
        correl.append(fila_correlacion(nombre, con))
        for _, t in con.groupby("GM_NUM"):
            grados.append({"ciudad": nombre, "grado": t["GM_2020"].iloc[0], "agebs": len(t),
                           "poblacion": int(t["POBTOT"].sum()), "lst_c_mediana": round(float(t["LST_C"].median()), 2)})
        fechas.append(pd.read_csv(c / "fechas.csv"))
    escribir_shp(gpd.GeoDataFrame(pd.concat(completas, ignore_index=True), crs=6372),
                 salida / "shapefiles" / "AGEB_3_ciudades_2020.shp")
    t, p = salida / "tablas", salida / "procedencia"
    tabla = pd.concat(todas, ignore_index=True)
    for k, n in DECIMALES.items():
        tabla[k] = tabla[k].round(n)
    tabla["GM_NUM"] = tabla["GM_NUM"].astype("Int64")
    m = pd.read_csv(MUNICIPIOS, dtype=str)
    siglas = {v[0]: s for s, v in CIUDADES.items()}
    m = m[m["clave_metropoli"].isin(siglas)]
    for ruta, df in (
        (t / "agebs_2020.csv", tabla),
        (t / "correlacion_por_ciudad.csv", pd.DataFrame(correl)),
        (t / "temperatura_por_grado.csv", pd.DataFrame(grados)),
        (t / "diccionario_campos.csv", pd.DataFrame([(k, *v) for k, v in CAMPOS.items()], columns=["campo", "descripcion", "fuente"])),
        (p / "fuentes.csv", pd.DataFrame(FUENTES, columns=["dato", "productor", "liga", "nota"])),
        (t / "correlacion_por_fecha.csv", pd.concat(fechas).drop(columns="escenas")),
        (p / "escenas_landsat.csv", pd.concat(fechas)[["ciudad", "fecha", "usada_en_LST_C", "urbano_despejado_pct", "escenas"]]),
        (p / "municipios_por_ciudad.csv", m.assign(ciudad=m["clave_metropoli"].map(siglas))),
    ):
        df.to_csv(ruta, index=False, encoding="utf-8-sig")  # con BOM: Excel respeta los acentos
    shutil.copy(AQUI / "LEEME_ciudades_2020.txt", salida / "LEEME.txt")
    print(pd.DataFrame(correl).T.to_string())
    print(pd.DataFrame(grados).to_string())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paso", choices=["base", "lst", "entrega"])
    ap.add_argument("--crudos", type=Path)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--salida", type=Path)
    a = ap.parse_args()
    if a.paso == "base":
        paso_base(a.crudos, a.base)
    elif a.paso == "lst":
        paso_lst(a.base)
    elif not a.salida:
        ap.error("--salida es obligatorio para el paso entrega")
    else:
        paso_entrega(a.base, a.salida)


if __name__ == "__main__":
    main()
