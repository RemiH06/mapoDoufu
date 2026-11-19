"""Arma la entrega de la comparación de ciudades (salida de `ciudades.sh`) para ArcGIS Pro.

- `Comparacion_ciudades.gdb`: un conjunto de entidades por ciudad, cada uno en su UTM,
  con sus AGEB (y en Guadalajara, las colonias de CONAPO y la colonia López Cotilla);
  las tablas `Comparacion_por_ciudad`, `Procedencia` y `Diccionario_campos`. Cada campo
  con alias en español.
- `rasters/<ciudad>/`: temperatura de superficie (°C), NDVI y dosel (% y altura), los
  mismos de los que salen los promedios por AGEB.
- `csv/`: todo lo anterior en CSV (UTF-8), para Excel o R sin ArcGIS.
- `agebs_todas_las_ciudades.gpkg`: las 7 ciudades juntas en EPSG:6372 (QGIS).
- `procedencia/`: escenas de satélite y mosaicos de dosel de cada ciudad.

Se corre con el Python de QGIS (GDAL con OpenFileGDB):

    "C:\\Program Files\\QGIS 4.2.3\\bin\\python-qgis.bat" scripts/ambiental/empaquetar_ciudades.py \\
        --entrada salida_de_ciudades --salida comparacion_ciudades --leeme LEEME.txt
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()

ORDEN = ["zmg", "mty", "pue", "leo", "mer", "hmo", "cdmx"]
NOMBRE_GDB = {"zmg": "Guadalajara", "mty": "Monterrey", "pue": "Puebla_Tlaxcala", "leo": "Leon", "mer": "Merida",
              "hmo": "Hermosillo", "cdmx": "Ciudad_de_Mexico"}

ALIAS = {
    "ciudad": "Metrópoli", "cvegeo": "Clave del AGEB (INEGI)", "cve_ent": "Entidad", "cve_mun": "Municipio",
    "cve_loc": "Localidad", "pobtot": "Población total (censo 2020)", "pob0_14": "Población de 0 a 14 años",
    "p_0a2": "Población de 0 a 2 años", "p_3a5": "Población de 3 a 5 años", "p_60ymas": "Población de 60 años y más",
    "pob65_mas": "Población de 65 años y más", "pcon_disc": "Población con discapacidad",
    "psinder": "Población sin afiliación a servicios de salud", "graproes": "Grado promedio de escolaridad (años)",
    "tvivparhab": "Viviendas particulares habitadas", "prom_ocup": "Promedio de ocupantes por vivienda",
    "vph_aguafv": "Viviendas sin agua entubada en la vivienda o el terreno", "vph_nodren": "Viviendas sin drenaje",
    "vph_refri": "Viviendas con refrigerador", "vph_inter": "Viviendas con internet",
    "censo_reservados": "Variables del censo reservadas por INEGI en este AGEB",
    "p6a14nae": "% de 6 a 14 años que no asiste a la escuela (CONAPO)",
    "sbasc": "% de 15 años o más sin educación básica (CONAPO)", "psdss": "% sin servicios de salud (CONAPO)",
    "ovsde": "% de viviendas sin drenaje ni excusado (CONAPO)", "ovsee": "% de viviendas sin electricidad (CONAPO)",
    "ovsae": "% de viviendas sin agua entubada (CONAPO)", "ovpt": "% de viviendas con piso de tierra (CONAPO)",
    "ovhac": "% de viviendas con hacinamiento (CONAPO)", "ovsref": "% de viviendas sin refrigerador (CONAPO)",
    "ovsint": "% de viviendas sin internet (CONAPO)", "ovscel": "% de viviendas sin celular (CONAPO)",
    "im_2020": "Índice de marginación urbana 2020 (CONAPO; más alto = MENOS marginado)",
    "gm_2020": "Grado de marginación urbana 2020 (CONAPO)",
    "imn_2020": "Índice de marginación normalizado (CONAPO)", "area_ha": "Área (ha)",
    "densidad_hab_ha": "Densidad (habitantes por hectárea)",
    "lst_c": "Temperatura de superficie promedio (°C), secas 2025", "lst_c_celdas": "Celdas de 30 m usadas (temperatura)",
    "ndvi": "NDVI promedio, secas 2025", "ndvi_celdas": "Celdas de 10 m usadas (NDVI)",
    "dosel_pct": "Dosel: % del área con árboles de 3 m o más", "dosel_pct_celdas": "Celdas de 10 m usadas (dosel)",
    "dosel_altura_m": "Altura media de los árboles (m)", "dosel_altura_m_celdas": "Celdas de 10 m usadas (altura)",
    "lst_vs_mediana_ciudad_c": "Temperatura menos la mediana de los AGEB de su ciudad (°C)",
    "COLONIA": "Colonia", "CVE_COL": "Clave de colonia (CONAPO)", "POBTOT": "Población estimada (CONAPO)",
    "IM_2020": "Índice de marginación 2020 (CONAPO; más alto = MENOS marginado)", "GM_2020": "Grado de marginación 2020 (CONAPO)",
}

# (dato, productor oficial, liga del productor, cómo se obtuvo, liga por donde se bajó, fecha de consulta, nota)
PROCEDENCIA = [
    ("Delimitación de metrópolis", "SEDATU, CONAPO e INEGI (Grupo Interinstitucional), Metrópolis de México 2020, edición 2024",
     "https://www.gob.mx/cms/uploads/sedatu/MM2020_06022024.pdf", "Directo del productor (PDF); municipios tomados de los cuadros A",
     "https://www.gob.mx/cms/uploads/sedatu/MM2020_06022024.pdf", "2026-11-19",
     "sha256 1d8e7b90dbbbfcb609914ec89d53580c54cdf9e27f16de3d8adfb00c16e6ee84; tabla en metropolis_2020_municipios.csv"),
    ("Polígonos de AGEB urbanos", "INEGI, Marco Geoestadístico", "https://www.inegi.org.mx/temas/mg/",
     "Directo del productor: API del Catálogo Único de Claves Geoestadísticas de INEGI (wscatgeo v2), por municipio",
     "https://gaia.inegi.org.mx/wscatgeo/v2/", "2026-11", "Términos de libre uso de INEGI"),
    ("Censo 2020 por AGEB", "INEGI, Censo de Población y Vivienda 2020", "https://www.inegi.org.mx/programas/ccpv/2020/",
     "Directo del productor: datos abiertos por AGEB y manzana urbana (renglones de total de AGEB)",
     "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/ageb_manzana/ageb_mza_urbana_EE_cpv2020_csv.zip",
     "2026-11", "EE es la clave del estado; '*' es dato reservado por INEGI y queda vacío"),
    ("Marginación por AGEB", "CONAPO, Índice de marginación urbana 2020",
     "https://www.gob.mx/conapo/documentos/indices-de-marginacion-2020-284372", "Directo del productor: datos abiertos de CONAPO",
     "https://conapo.segob.gob.mx/work/models/CONAPO/Datos_Abiertos/Marginacion/IMU_2020.zip", "2026-11-18",
     "sha256 17fdd6a31a57d4deb5519fe1e7bd58e7e52d115cf0474d6b59fbf9a52cde26b9. Más alto = menos marginado"),
    ("Marginación por colonia", "CONAPO, Índice de marginación urbana 2020 por colonia",
     "https://www.gob.mx/conapo/documentos/indices-de-marginacion-2020-284372", "Directo del productor: datos abiertos de CONAPO",
     "https://conapo.segob.gob.mx/work/models/CONAPO/Datos_Abiertos/Colonia/imc2020_shp.zip", "2026-11-18",
     "sha256 69d73b5bb0127df6c81701684eb28cd6bd666d9319a1ffb45da76446ae278426"),
    ("Temperatura de superficie", "USGS (Servicio Geológico de Estados Unidos), Landsat 8 y 9 Collection 2 Level-2, banda térmica",
     "https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products (descarga oficial: https://earthexplorer.usgs.gov)",
     "Copia del producto del USGS en Microsoft Planetary Computer, que guarda los mismos archivos en formato para leer por partes",
     "https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2", "2026-11-19",
     "K = DN × 0.00341802 + 149.0, sin nubes ni sombras (qa_pixel), mediana de marzo a mayo de 2025, 30 m. Escenas en "
     "procedencia/<ciudad>_procedencia_imagenes.csv con el mismo identificador que en EarthExplorer. Dominio público"),
    ("NDVI", "ESA, programa Copernicus de la Unión Europea, Sentinel-2 Level-2A",
     "https://sentinels.copernicus.eu/web/sentinel/sentinel-data-access (descarga oficial: https://browser.dataspace.copernicus.eu)",
     "Copia del producto de la ESA en Microsoft Planetary Computer",
     "https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a", "2026-11-19",
     "(B08 − B04) / (B08 + B04), compuestos mensuales sin nubes (SCL) de marzo a mayo de 2025 y su mediana, 10 m. Escenas en "
     "procedencia/<ciudad>_procedencia_imagenes.csv con el mismo identificador que en Copernicus. Contiene datos modificados de Copernicus Sentinel 2025"),
    ("Altura de dosel", "Meta y World Resources Institute, High Resolution Canopy Height Maps (Tolan et al. 2024, Remote Sensing of Environment 300, doi:10.1016/j.rse.2023.113888)",
     "https://registry.opendata.aws/dataforgood-fb-forests/",
     "Directo del productor: su distribución oficial en AWS (programa Data for Good de Meta), mosaicos de ~1 m",
     "https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float/chm/", "2026-11-19",
     "CC BY 4.0. Modelo entrenado con lidar aéreo sobre imágenes de Maxar de 2017 a 2020: estimación, no medición. "
     "Aquí, % del área con 3 m o más y altura media en celdas de 10 m. Mosaicos en procedencia/<ciudad>_procedencia_dosel.csv"),
]


def campos_de(lyr) -> list:
    d = lyr.GetLayerDefn()
    return [d.GetFieldDefn(i) for i in range(d.GetFieldCount())]


def copiar_capa(ds, src_path: Path, conjunto: str, destino: str, alias_capa: str, epsg: int, filtro: str | None = None,
                diccionario: list | None = None) -> int:
    src = ogr.Open(str(src_path))
    lyr = src.GetLayer(0)
    if filtro:
        lyr.SetAttributeFilter(filtro)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    s_srs = lyr.GetSpatialRef()
    s_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr = osr.CoordinateTransformation(s_srs, srs)
    out = ds.CreateLayer(destino, srs, ogr.wkbMultiPolygon,
                         options=[f"FEATURE_DATASET={conjunto}", f"LAYER_ALIAS={alias_capa}"])
    fuente = campos_de(lyr)
    for f in fuente:
        nuevo = ogr.FieldDefn(f.GetName()[:64], f.GetType() if f.GetType() != ogr.OFTInteger64 else ogr.OFTInteger)
        nuevo.SetAlternativeName(ALIAS.get(f.GetName(), f.GetName()))
        out.CreateField(nuevo)
        if diccionario is not None:
            diccionario.append((destino, f.GetName(), ALIAS.get(f.GetName(), f.GetName())))
    n = 0
    for feat in lyr:
        o = ogr.Feature(out.GetLayerDefn())
        for i in range(len(fuente)):
            v = feat.GetField(i)
            if v is not None:
                o.SetField(i, v)
        g = feat.GetGeometryRef()
        if g is not None:
            g = g.Clone()
            g.Transform(tr)
            o.SetGeometry(ogr.ForceToMultiPolygon(g))
        out.CreateFeature(o)
        n += 1
    return n


def tabla_csv(ds, ruta: Path, destino: str, diccionario: list | None = None) -> None:
    with open(ruta, encoding="utf-8", newline="") as f:
        filas = list(csv.reader(f))
    enc, datos = filas[0], filas[1:]
    tipos = []
    for i, _ in enumerate(enc):
        vals = [r[i] for r in datos if i < len(r) and r[i] != ""]
        try:
            [float(v) for v in vals]
            tipos.append(ogr.OFTReal if vals else ogr.OFTString)
        except ValueError:
            tipos.append(ogr.OFTString)
    out = ds.CreateLayer(destino, None, ogr.wkbNone)
    for h, t in zip(enc, tipos):
        fd = ogr.FieldDefn(h[:64], t)
        fd.SetAlternativeName(ALIAS.get(h, h.replace("_", " ")))
        out.CreateField(fd)
        if diccionario is not None:
            diccionario.append((destino, h, ALIAS.get(h, h.replace("_", " "))))
    for r in datos:
        o = ogr.Feature(out.GetLayerDefn())
        for i, (v, t) in enumerate(zip(r, tipos)):
            if v != "":
                o.SetField(i, float(v) if t == ogr.OFTReal else v)
        out.CreateFeature(o)


MAX_MAPO = 50 * 1024 * 1024
DOC = "https://github.com/RemiH06/mapoDoufu/blob/master/docs/producto/comparacion-ciudades.md"
FUENTE_AGEB = ("INEGI censo 2020 y marco geoestadístico; CONAPO marginación urbana 2020; USGS Landsat 8 y 9; "
               "ESA Sentinel-2; Meta y WRI altura de dosel (Tolan et al. 2024). Detalle en procedencia/fuentes.csv")


def para_mapo(entrada: Path, salida: Path) -> list[list]:
    """Lo mismo, dentro de los límites de los datos propios de Mapo (50 MB, 100 columnas,
    10,000 polígonos): un GeoPackage en grados por ciudad con las columnas de
    procedencia que Mapo reserva, y los rásteres reducidos hasta caber."""
    dest = salida / "para_mapo"
    dest.mkdir()
    registro = []
    for c in ORDEN:
        d = entrada / c
        for archivo, capa in ((d / f"agebs_{c}.gpkg", f"agebs_{NOMBRE_GDB[c]}"), (d / f"colonias_{c}.gpkg", f"colonias_{NOMBRE_GDB[c]}")):
            if not archivo.exists():
                continue
            ruta = dest / f"{capa}.gpkg"
            origen = gdal.OpenEx(str(archivo))  # la capa muere con su dataset: guardar la referencia
            nombre = origen.GetLayer(0).GetName()
            origen = None
            sql = (f"SELECT *, '{FUENTE_AGEB}' AS fuente, '{DOC}' AS url, '2025-05' AS fecha_dato, "
                   f"'2026-11-19' AS fecha_consulta, 'registro oficial' AS nivel FROM \"{nombre}\"")
            gdal.VectorTranslate(str(ruta), str(archivo), format="GPKG", dstSRS="EPSG:4326", SQLStatement=sql,
                                 SQLDialect="SQLITE", layerName=capa, geometryType="MULTIPOLYGON")
            hecho = gdal.OpenEx(str(ruta))
            n = hecho.GetLayer(0).GetFeatureCount()
            hecho = None
            registro.append([ruta.name, "vector", n, round(ruta.stat().st_size / 1e6, 1), "sí" if n <= 10_000 and ruta.stat().st_size <= MAX_MAPO else "NO"])
        for archivo in ("temperatura_superficie_secas_2025_C.tif", "ndvi_secas_2025.tif", "dosel_cobertura_10m.tif"):
            src = d / archivo
            if not src.exists():
                continue
            ruta = dest / f"{NOMBRE_GDB[c]}_{archivo}"
            factor = 1
            while True:
                info = gdal.Open(str(src))
                gdal.Translate(str(ruta), str(src), width=info.RasterXSize // factor, height=info.RasterYSize // factor,
                               resampleAlg="average", creationOptions=["COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES"])
                if ruta.stat().st_size <= MAX_MAPO or factor >= 16:
                    break
                factor *= 2
            res = round(gdal.Open(str(ruta)).GetGeoTransform()[1])
            registro.append([ruta.name, f"ráster a {res} m", "", round(ruta.stat().st_size / 1e6, 1),
                             "sí" if ruta.stat().st_size <= MAX_MAPO else "NO"])
    with open(dest / "para_mapo.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["archivo", "tipo", "renglones", "MB", "cabe_en_mapo"])
        w.writerows(registro)
    return registro


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--leeme", type=Path, required=True)
    ap.add_argument("--guia", type=Path, default=None)
    a = ap.parse_args()
    if a.salida.exists():
        shutil.rmtree(a.salida)
    for sub in ("rasters", "csv", "procedencia"):
        (a.salida / sub).mkdir(parents=True)
    ds = ogr.GetDriverByName("OpenFileGDB").CreateDataSource(str(a.salida / "Comparacion_ciudades.gdb"))
    diccionario: list = []
    gpkg_todas = None
    for c in ORDEN:
        d = a.entrada / c
        if not (d / f"agebs_{c}.gpkg").exists():
            print(f"  (falta {c})")
            continue
        info = json.loads((d / "ciudad.json").read_text(encoding="utf-8"))
        conjunto = NOMBRE_GDB[c]
        n = copiar_capa(ds, d / f"agebs_{c}.gpkg", conjunto, f"AGEB_{conjunto}",
                        f"AGEB urbanos de {info['nombre']}: calor, dosel, NDVI, censo y marginación", info["epsg"],
                        diccionario=diccionario if c == "zmg" else None)
        print(f"  {conjunto}: {n} AGEB")
        if (d / f"colonias_{c}.gpkg").exists():
            copiar_capa(ds, d / f"colonias_{c}.gpkg", conjunto, f"Colonias_{conjunto}",
                        f"Colonias de CONAPO de {info['nombre']}: calor, dosel y NDVI", info["epsg"])
            copiar_capa(ds, d / f"colonias_{c}.gpkg", conjunto, "Colonia_Lopez_Cotilla",
                        "Colonia López Cotilla (CONAPO 14098_0135), objetivo del proyecto", info["epsg"],
                        filtro="CVE_COL = '14098_0135'")
            shutil.copy(d / f"colonias_{c}.csv", a.salida / "csv" / f"colonias_{conjunto}.csv")
        rd = a.salida / "rasters" / conjunto
        rd.mkdir()
        for archivo in ("temperatura_superficie_secas_2025_C.tif", "ndvi_secas_2025.tif", "dosel_cobertura_10m.tif",
                        "dosel_altura_media_10m.tif"):
            if (d / archivo).exists():
                gdal.Translate(str(rd / archivo), str(d / archivo), creationOptions=["COMPRESS=DEFLATE", "TILED=YES", "PREDICTOR=3"])
                r = gdal.Open(str(rd / archivo))  # guardar la referencia: la banda muere con el dataset
                r.GetRasterBand(1).ComputeStatistics(False)
                r = None
        shutil.copy(d / f"agebs_{c}.csv", a.salida / "csv" / f"agebs_{conjunto}.csv")
        for p, nombre in ((d / "imagenes" / "procedencia_imagenes.csv", "procedencia_imagenes"),
                          (d / "procedencia_dosel.csv", "procedencia_dosel")):
            if p.exists():
                shutil.copy(p, a.salida / "procedencia" / f"{conjunto}_{nombre}.csv")
        opciones = dict(format="GPKG", dstSRS="EPSG:6372", layerName="agebs", geometryType="MULTIPOLYGON")
        if gpkg_todas is None:
            gpkg_todas = a.salida / "agebs_todas_las_ciudades.gpkg"
            gdal.VectorTranslate(str(gpkg_todas), str(d / f"agebs_{c}.gpkg"), **opciones)
        else:
            gdal.VectorTranslate(str(gpkg_todas), str(d / f"agebs_{c}.gpkg"), accessMode="append", **opciones)
    if (a.entrada / "comparacion_ciudades.csv").exists():
        shutil.copy(a.entrada / "comparacion_ciudades.csv", a.salida / "csv" / "comparacion_ciudades.csv")
        tabla_csv(ds, a.entrada / "comparacion_ciudades.csv", "Comparacion_por_ciudad", diccionario)
    with open(a.salida / "procedencia" / "fuentes.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["dato", "productor_oficial", "liga_productor", "como_se_obtuvo", "liga_de_acceso", "fecha_consulta", "nota"])
        w.writerows(PROCEDENCIA)
    tabla_csv(ds, a.salida / "procedencia" / "fuentes.csv", "Procedencia")
    out = ds.CreateLayer("Diccionario_campos", None, ogr.wkbNone)
    for k in ("capa", "campo", "descripcion"):
        out.CreateField(ogr.FieldDefn(k, ogr.OFTString))
    with open(a.salida / "csv" / "diccionario_campos.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["capa", "campo", "descripcion"])
        for fila in diccionario:
            w.writerow(fila)
            o = ogr.Feature(out.GetLayerDefn())
            for i, v in enumerate(fila):
                o.SetField(i, v)
            out.CreateFeature(o)
    ds = None
    for fila in para_mapo(a.entrada, a.salida):
        print("  para_mapo:", fila)
    shutil.copy(a.leeme, a.salida / "LEEME.txt")
    if a.guia:
        shutil.copy(a.guia, a.salida / a.guia.name)
    shutil.copy(Path(__file__).with_name("metropolis_2020_municipios.csv"), a.salida / "procedencia" / "metropolis_2020_municipios.csv")
    print(f"Listo: {a.salida}")


if __name__ == "__main__":
    main()
