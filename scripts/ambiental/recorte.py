# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyogrio", "pandas", "openpyxl", "xlrd", "rasterio", "shapely>=2", "pyproj"]
# ///
"""Recorta las fuentes ambientales en crudo a una zona y deja un paquete listo
para SIG: un GeoPackage, tablas CSV, el relieve en GeoTIFF y un diccionario.

Sirve para cualquier zona del país: la caja delimita lo que tiene coordenadas y
la lista de municipios lo que solo viene por municipio. Ver
`docs/fuentes/ambientales.md`, sección "Recorte por zona".

    uv run --script scripts/ambiental/recorte.py \
        --crudos ~/srv/mapo-crudos/ambiental --salida ~/srv/mapo-paquetes/autlan \
        --caja -104.65,19.55,-103.95,20.05 --municipios 14015,14037
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import time
import urllib.request
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, box

CRS = "EPSG:4326"

# Una entrada por capa del paquete: de dónde sale y qué tan fina es. La fecha es
# la del dato, no la de la descarga (esa va en el MANIFIESTO de los crudos).
FUENTES = {
    "agua_superficial": ("Conagua, RENAMECA", "Resumen 2012 a 2025 por sitio (no es serie de tiempo)", "punto", "https://www.gob.mx/conagua/articulos/calidad-del-agua"),
    "agua_subterranea": ("Conagua, RENAMECA", "Resumen 2012 a 2025 por sitio", "punto", "https://www.gob.mx/conagua/articulos/calidad-del-agua"),
    "cuerpos_de_agua": ("Conagua", "Etapas I a VI, 2016 en adelante", "polígono", "https://sigagis.conagua.gob.mx"),
    "acuiferos": ("Conagua", "Disponibilidad publicada en el DOF el 2023-11-09", "polígono", "https://sigagis.conagua.gob.mx/gas1/sections/Disponibilidad.html"),
    "acuiferos_vedas": ("Conagua", "Vedas al 2021-11-25", "polígono", "https://sigagis.conagua.gob.mx"),
    "acuiferos_suspension": ("Conagua", "Suspensión de libre alumbramiento al 2021-11-25", "polígono", "https://sigagis.conagua.gob.mx"),
    "acuiferos_reglamentos": ("Conagua", "Reglamentos, reservas y zonas reglamentadas", "polígono", "https://sigagis.conagua.gob.mx"),
    "piezometria": ("Conagua", "Profundidad al nivel estático (PNE) por año, 1996 a 2023", "punto", "https://sigagis.conagua.gob.mx"),
    "repda_descargas": ("Conagua, REPDA", "Títulos vigentes a la fecha de descarga", "punto", "https://app.conagua.gob.mx/consultarepda.aspx"),
    "repda_subterraneos": ("Conagua, REPDA", "Aprovechamientos subterráneos (pozos)", "punto", "https://app.conagua.gob.mx/consultarepda.aspx"),
    "repda_superficiales": ("Conagua, REPDA", "Aprovechamientos superficiales", "punto", "https://app.conagua.gob.mx/consultarepda.aspx"),
    "repda_zonas_federales": ("Conagua, REPDA", "Zonas federales concesionadas", "punto", "https://app.conagua.gob.mx/consultarepda.aspx"),
    "repda_materiales": ("Conagua, REPDA", "Extracción de materiales", "punto", "https://app.conagua.gob.mx/consultarepda.aspx"),
    "retc": ("SEMARNAT, RETC", "Establecimientos que reportaron, 2004 a 2022 (columna anio)", "punto", "https://www.gob.mx/semarnat/acciones-y-programas/registro-de-emisiones-y-transferencia-de-contaminantes-retc"),
    "firms_viirs": ("NASA FIRMS, VIIRS S-NPP 375 m", "Focos de calor 2012 a 2025", "punto", "https://firms.modaps.eosdis.nasa.gov"),
    "firms_modis": ("NASA FIRMS, MODIS 1 km", "Focos de calor 2000 a 2025", "punto", "https://firms.modaps.eosdis.nasa.gov"),
    "uso_suelo_s7": ("INEGI vía CONABIO", "Uso de suelo y vegetación 1:250 000, serie VII (2018)", "polígono", "https://www.inegi.org.mx/temas/usosuelo/"),
    "uso_suelo_s6": ("INEGI vía CONABIO", "Uso de suelo y vegetación 1:250 000, serie VI (2014)", "polígono", "https://www.inegi.org.mx/temas/usosuelo/"),
    "edafologia": ("INEGI vía CONABIO", "Edafología 1:1 000 000", "polígono", "http://geoportal.conabio.gob.mx"),
    "frontera_agricola": ("SIAP, frontera agrícola serie II (copia del Internet Archive)", "2011", "polígono", "http://infosiap.siap.gob.mx/gobmx/datosAbiertos/frontera-agricola/"),
    "anp": ("CONANP vía CONABIO", "Áreas naturales protegidas federales 2020", "polígono", "http://geoportal.conabio.gob.mx"),
    "regiones_hidrologicas": ("INEGI vía CONABIO", "Regiones hidrológicas 1:250 000", "polígono", "http://geoportal.conabio.gob.mx"),
    "localidades": ("INEGI, ITER 2020", "Censo 2020 por localidad, también rurales", "punto", "https://www.inegi.org.mx/programas/ccpv/2020/"),
    "agebs_rurales": ("INEGI, marco geoestadístico (API wscatgeo) + ITER 2020", "Marco de diciembre de 2025; población sumada del ITER 2020", "AGEB rural", "https://gaia.inegi.org.mx/wscatgeo/v2/geo/agebr/"),
    "localidades_poligonos": ("INEGI, marco geoestadístico (API wscatgeo) + ITER 2020", "Marco de diciembre de 2025; población del ITER 2020", "localidad amanzanada", "https://gaia.inegi.org.mx/wscatgeo/v2/geo/localidades/pol/"),
    "manzanas": ("INEGI, marco geoestadístico (API wscatgeo) + censo 2020 por manzana", "Marco de diciembre de 2025; censo 2020", "manzana", "https://www.inegi.org.mx/programas/ccpv/2020/#datos_abiertos"),
    "viento_horario": ("ECMWF ERA5 vía Open-Meteo (CC BY 4.0)", "Reanálisis horario, 10 m, celda de 0.25°", "celda ERA5", "https://open-meteo.com/en/docs/historical-weather-api"),
    "viento_climatologia": ("ECMWF ERA5 vía Open-Meteo (CC BY 4.0)", "Resumen por mes y hora de la serie horaria", "celda ERA5", "https://open-meteo.com/en/docs/historical-weather-api"),
    "agebs": ("INEGI, marco geoestadístico y censo 2020 (vía Mapo)", "2020; censo solo en AGEB urbanas", "AGEB", "https://www.inegi.org.mx/temas/mg/"),
    "denue": ("INEGI, DENUE (vía Mapo)", "Edición cargada en Mapo, ver docs/fuentes/denue.md", "punto", "https://www.inegi.org.mx/app/mapa/denue/"),
    "siap_municipal": ("SIAP", "Cierre agrícola municipal 2003 a 2025", "municipio", "https://nube.siap.gob.mx/cierreagricola/"),
    "colonias_marginacion": ("CONAPO, índice de marginación urbana por colonia", "2020", "colonia", "https://www.gob.mx/conapo/documentos/indices-de-marginacion-2020-284372"),
    "agebs_marginacion": ("CONAPO, índice de marginación urbana por AGEB", "2020", "AGEB", "https://www.gob.mx/conapo/documentos/indices-de-marginacion-2020-284372"),
    "sequia_municipal": ("Conagua, SMN, Monitor de Sequía", "Categoría D0 a D4 por fecha de corte", "municipio", "https://smn.conagua.gob.mx/es/climatologia/monitor-de-sequia/monitor-de-sequia-en-mexico"),
    "defunciones": ("INEGI, defunciones registradas", "2020 a 2023, conteos por municipio de residencia", "municipio", "https://www.inegi.org.mx/programas/edr/"),
    "plantas_tratamiento": ("Conagua", "Inventario de PTAR 2023, sin coordenadas", "localidad (por nombre)", "https://www.gob.mx/conagua"),
    "relieve": ("Copernicus DEM GLO-30", "Modelo digital de superficie, 30 m", "ráster", "https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model"),
}


# Fecha del dato como fecha (AAAA, AAAA-MM o AAAA-MM-DD), para que Mapo la reconozca y
# se pueda filtrar por rango. Si la capa cubre un periodo, el final. Vacía si no se
# sabe: mejor nada que una fecha inventada (el REPDA es "vigente a la descarga", y esa
# fecha va en fecha_consulta). El texto de FUENTES se queda como `fecha_texto`.
FECHAS = {
    "agua_superficial": "2025", "agua_subterranea": "2025",
    "acuiferos": "2023-11-09", "acuiferos_vedas": "2021-11-25", "acuiferos_suspension": "2021-11-25",
    "piezometria": "2023", "retc": "2022", "firms_viirs": "2025", "firms_modis": "2025",
    "uso_suelo_s7": "2018", "uso_suelo_s6": "2014", "frontera_agricola": "2011", "anp": "2020-08",
    "localidades": "2020", "agebs_rurales": "2020", "localidades_poligonos": "2020", "manzanas": "2020",
    "viento_horario": "2024", "viento_climatologia": "2024", "agebs": "2020",
    "siap_municipal": "2025", "colonias_marginacion": "2020", "agebs_marginacion": "2020",
    "defunciones": "2023", "plantas_tratamiento": "2023", "relieve": "2015",
}


def a_grados(valor) -> float | None:
    """Acepta 20.69, '20.69' o grados, minutos y segundos como 20°41'27" o 104°21'48.1" W."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    numeros = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", texto)]
    if not numeros:
        return None
    g = numeros[0] + (numeros[1] / 60 if len(numeros) > 1 else 0) + (numeros[2] / 3600 if len(numeros) > 2 else 0)
    return -g if texto.endswith(("W", "O", "S")) or texto.startswith("-") else g


# De qué archivo crudo (relativo a --crudos) sale cada capa; con su sha256 y su
# fecha del MANIFIESTO.tsv queda la procedencia exacta (procedencia.csv).
CRUDOS = {
    "agua_superficial": ["agua/calidad_superficial_2012-2025.xlsx"],
    "agua_subterranea": ["agua/calidad_subterranea_2012-2025.xlsx"],
    "cuerpos_de_agua": ["agua/cuerpos_de_agua.zip"],
    "acuiferos": ["acuiferos/disponibilidad_2023-11-09.zip"],
    "acuiferos_vedas": ["acuiferos/vedas_y_ordenamientos.zip"],
    "acuiferos_suspension": ["acuiferos/vedas_y_ordenamientos.zip"],
    "acuiferos_reglamentos": ["acuiferos/vedas_y_ordenamientos.zip"],
    "piezometria": ["acuiferos/red_piezometrica_2023.zip"],
    "repda_descargas": ["concesiones/otorgamiento_de_concesiones.zip"],
    "repda_subterraneos": ["concesiones/otorgamiento_de_concesiones.zip"],
    "repda_superficiales": ["concesiones/otorgamiento_de_concesiones.zip"],
    "repda_zonas_federales": ["concesiones/otorgamiento_de_concesiones.zip"],
    "repda_materiales": ["concesiones/otorgamiento_de_concesiones.zip"],
    "retc": ["emisiones/retc_2004-2022.zip"],
    "firms_viirs": ["incendios/firms_viirs_snpp_*.csv"],
    "firms_modis": ["incendios/firms_modis_*.csv"],
    "uso_suelo_s7": ["territorio/usv250_serie7.zip"],
    "frontera_agricola": ["agricultura/frontera_agricola_s2_*.kmz"],
    "colonias_marginacion": ["marginacion/imc_2020_colonias_shp.zip"],
    "agebs_marginacion": ["marginacion/imu_2020_ageb.zip"],
    "uso_suelo_s6": ["territorio/usv250_serie6.zip"],
    "edafologia": ["territorio/edafologia_1m.zip"],
    "anp": ["territorio/anp_2020.zip"],
    "regiones_hidrologicas": ["territorio/regiones_hidrologicas_250k.zip"],
    "localidades": ["poblacion/iter_14_2020.zip"],
    "localidades_poligonos": ["API INEGI wscatgeo v2 geo/localidades/pol", "poblacion/iter_14_2020.zip"],
    "agebs_rurales": ["API INEGI wscatgeo v2 geo/agebr", "poblacion/iter_14_2020.zip"],
    "manzanas": ["API INEGI wscatgeo v2 geo/mza", "poblacion/manzanas_*_2020.zip"],
    "viento_horario": ["API Open-Meteo archive (modelo era5)"],
    "viento_climatologia": ["API Open-Meteo archive (modelo era5)"],
    "agebs": ["base de Mapo (desde_mapo.sh): agebs y fuente_censo_poblacion"],
    "denue": ["base de Mapo (desde_mapo.sh): fuente_denue_negocios"],
    "siap_municipal": ["agricultura/siap_municipal_*.csv"],
    "sequia_municipal": ["riesgo/sequia_municipios.xlsx"],
    "defunciones": ["salud/defunciones_*.zip"],
    "plantas_tratamiento": ["agua/plantas_tratamiento.csv"],
    "relieve": ["relieve/Copernicus_DSM_COG_10_*_DEM.tif"],
}


def normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.upper().split())



def codificacion_dbf(ruta_vsi: str) -> str | None:
    """UTF-8 si los registros del .dbf lo son. Los de CONABIO vienen en UTF-8 sin
    .cpg y GDAL los leería como Latin-1 ("MESÃ“FILO"). Mismo criterio que
    `mapo_core.datos_geo._codificacion`: el encabezado es binario y no cuenta."""
    if not ruta_vsi.startswith("/vsizip/") or not ruta_vsi.lower().endswith(".shp"):
        return None
    zip_ruta, _, interna = ruta_vsi[len("/vsizip/"):].partition(".zip/")
    with zipfile.ZipFile(zip_ruta + ".zip") as z:
        nombres = {n.lower(): n for n in z.namelist()}
        base = interna[:-4].lower()
        if base + ".cpg" in nombres:
            return None
        dbf = z.read(nombres[base + ".dbf"])
    inicio = int.from_bytes(dbf[8:10], "little")
    try:
        dbf[inicio:].decode("utf-8")
        return "UTF-8"
    except UnicodeDecodeError:
        return None

class Paquete:
    def __init__(self, crudos: Path, salida: Path, caja: tuple[float, float, float, float], municipios: list[str]):
        self.crudos, self.salida, self.caja, self.municipios = crudos, salida, caja, municipios
        self.poligono = box(*caja)
        self.gpkg = salida / "zona.gpkg"
        self.tablas = salida / "tablas"
        self.tablas.mkdir(parents=True, exist_ok=True)
        if self.gpkg.exists():
            self.gpkg.unlink()
        self.registro: list[dict] = []

    # --- utilidades -------------------------------------------------------
    def anotar(self, capa: str, filas: int | None, archivo: str, nota: str = "") -> None:
        fuente, fecha, nivel, url = FUENTES[capa]
        self.registro.append({"capa": capa, "archivo": archivo, "filas": filas, "fuente": fuente,
                              "fecha_dato": FECHAS.get(capa, ""), "fecha_texto": fecha,
                              "nivel": nivel, "url": url, "nota": nota})
        print(f"  {capa}: {filas if filas is not None else '-'} filas {nota}", flush=True)

    def guardar(self, capa: str, gdf: gpd.GeoDataFrame, nota: str = "") -> None:
        if gdf.empty:
            self.anotar(capa, 0, "zona.gpkg", "sin datos en la zona " + nota)
            return
        gdf = gdf.to_crs(CRS)
        gdf.columns = [str(c) for c in gdf.columns]
        gdf.to_file(self.gpkg, layer=capa, driver="GPKG")
        self.anotar(capa, len(gdf), f"zona.gpkg:{capa}", nota)

    def guardar_tabla(self, capa: str, df: pd.DataFrame, nota: str = "") -> None:
        df.to_csv(self.tablas / f"{capa}.csv", index=False, encoding="utf-8")
        self.anotar(capa, len(df), f"tablas/{capa}.csv", nota)

    def en_caja(self, df: pd.DataFrame, lon: str, lat: str) -> gpd.GeoDataFrame:
        x = pd.to_numeric(df[lon], errors="coerce")
        y = pd.to_numeric(df[lat], errors="coerce")
        o, s, e, n = self.caja
        dentro = df[(x >= o) & (x <= e) & (y >= s) & (y <= n)].copy()
        return gpd.GeoDataFrame(dentro, geometry=gpd.points_from_xy(x[dentro.index], y[dentro.index]), crs=CRS)

    def vector(self, ruta_vsi: str) -> gpd.GeoDataFrame:
        info = pyogrio.read_info(ruta_vsi)
        caja = self.caja
        if info["crs"] and info["crs"] != CRS:
            t = Transformer.from_crs(CRS, info["crs"], always_xy=True)
            xs, ys = t.transform([caja[0], caja[2], caja[0], caja[2]], [caja[1], caja[1], caja[3], caja[3]])
            caja = (min(xs), min(ys), max(xs), max(ys))
        gdf = pyogrio.read_dataframe(ruta_vsi, bbox=caja, encoding=codificacion_dbf(ruta_vsi))
        if gdf.empty:
            return gdf
        gdf = gdf.to_crs(CRS)
        gdf["geometry"] = gdf.geometry.make_valid()
        return gdf.clip(self.poligono)

    def zip_vsi(self, rel: str, contiene: str = "") -> str:
        p = self.crudos / rel
        with zipfile.ZipFile(p) as z:
            shp = [n for n in z.namelist() if n.lower().endswith(".shp") and contiene.lower() in n.lower()]
        return f"/vsizip/{p}/{shp[0]}"

    def mun_claves(self) -> set[tuple[int, int]]:
        return {(int(m[:2]), int(m[2:])) for m in self.municipios}

    # --- fuentes con coordenadas ----------------------------------------
    def renameca(self) -> None:
        for capa, archivo in (("agua_superficial", "calidad_superficial_2012-2025.xlsx"),
                              ("agua_subterranea", "calidad_subterranea_2012-2025.xlsx")):
            df = pd.read_excel(self.crudos / "agua" / archivo, sheet_name=0)
            self.guardar(capa, self.en_caja(df, "LONGITUD", "LATITUD"), "(no mide plaguicidas)")

    def vectoriales(self) -> None:
        capas = [
            ("cuerpos_de_agua", "agua/cuerpos_de_agua.zip", ""),
            ("acuiferos", "acuiferos/disponibilidad_2023-11-09.zip", ""),
            ("acuiferos_vedas", "acuiferos/vedas_y_ordenamientos.zip", "Vedas"),
            ("acuiferos_suspension", "acuiferos/vedas_y_ordenamientos.zip", "Suspension"),
            ("acuiferos_reglamentos", "acuiferos/vedas_y_ordenamientos.zip", "Reglamentos"),
            ("piezometria", "acuiferos/red_piezometrica_2023.zip", ""),
            ("uso_suelo_s7", "territorio/usv250_serie7.zip", ""),
            ("uso_suelo_s6", "territorio/usv250_serie6.zip", ""),
            ("edafologia", "territorio/edafologia_1m.zip", ""),
            ("anp", "territorio/anp_2020.zip", ""),
            ("regiones_hidrologicas", "territorio/regiones_hidrologicas_250k.zip", ""),
        ]
        for capa, rel, contiene in capas:
            self.intentar(capa, lambda rel=rel, contiene=contiene, capa=capa:
                          self.guardar(capa, self.vector(self.zip_vsi(rel, contiene))))

    def frontera_agricola(self) -> None:
        """Serie II del SIAP: 1:10 000 sobre SPOT 5 de 2010 y 2011. Viene como KMZ de
        ArcGIS con los atributos en una tabla HTML dentro de `description`, que GDAL
        no separa en campos: se leen con expresiones regulares."""
        celda = re.compile(r"<td>([^<]*)</td>\s*<td>([^<]*)</td>")
        poligono = re.compile(r"<Polygon>(.*?)</Polygon>", re.S)
        anillo = re.compile(r"<(outer|inner)BoundaryIs>.*?<coordinates>([^<]*)</coordinates>", re.S)
        o, s_, e, n = self.caja
        filas, geoms = [], []
        for kmz in sorted((self.crudos / "agricultura").glob("frontera_agricola_s2_*.kmz")):
            with zipfile.ZipFile(kmz) as z:
                texto = z.read([m for m in z.namelist() if m.endswith(".kml")][0]).decode("utf-8")
            for bloque in texto.split("<Placemark")[1:]:
                partes = []
                for p in poligono.findall(bloque):
                    exterior, interiores = None, []
                    for tipo, coords in anillo.findall(p):
                        xy = np.array([c.split(",")[:2] for c in coords.split()], dtype=float)
                        if tipo == "outer":
                            exterior = xy
                        else:
                            interiores.append(xy)
                    if exterior is not None and len(exterior) >= 4:
                        x, y = exterior[:, 0], exterior[:, 1]
                        if x.max() >= o and x.min() <= e and y.max() >= s_ and y.min() <= n:
                            partes.append(Polygon(exterior, [i for i in interiores if len(i) >= 4]))
                if partes:
                    atributos = dict(celda.findall(bloque.split("</description>")[0]))
                    atributos.pop("FID", None)
                    filas.append(atributos)
                    geoms.append(MultiPolygon(partes) if len(partes) > 1 else partes[0])
        if not filas:
            self.anotar("frontera_agricola", 0, "zona.gpkg", "sin datos en la zona (¿falta el KMZ de la región?)")
            return
        gdf = gpd.GeoDataFrame(filas, geometry=geoms, crs=CRS)
        gdf["SUP_HA_7mo"] = pd.to_numeric(gdf["SUP_HA_7mo"], errors="coerce")
        gdf["geometry"] = gdf.geometry.make_valid()
        self.guardar("frontera_agricola", gdf.clip(self.poligono),
                     "(1:10 000, SPOT 5 2010-2011; MOD_USO A agricultura o P pastos; MOD_AGR R riego o T temporal; "
                     "SUP_HA_7mo es el polígono completo, no lo recortado)")

    def repda(self) -> None:
        archivos = {
            "repda_descargas": "ANEXOS_RESIDUALES.csv",
            "repda_subterraneos": "ANEXOS_SUBTERR",  # el nombre trae una Á mal codificada
            "repda_superficiales": "ANEXOS_SUPERFICIALES.csv",
            "repda_zonas_federales": "ANEXOS_ZONAS_FEDERALES.csv",
            "repda_materiales": "ANEXOS_DE_EXT_MATERIALES.csv",
        }
        p = self.crudos / "concesiones" / "otorgamiento_de_concesiones.zip"
        with zipfile.ZipFile(p) as z:
            nombres = z.namelist()
            # Uso del título desde CONCESIONES.csv. TITULAR se omite: puede ser una
            # persona y para estudiar la zona basta el uso.
            con = pd.read_csv(io.BytesIO(z.read(next(n for n in nombres if n.endswith("/CONCESIONES.csv")))),
                              dtype=str, encoding="utf-8", usecols=lambda c: "TULO" in c and "TITULAR" not in c)
            con = con.rename(columns={con.columns[0]: "titulo", con.columns[1]: "uso"})[["titulo", "uso"]]
            for capa, prefijo in archivos.items():
                nombre = next(n for n in nombres if n.split("/")[-1].startswith(prefijo) and "DTTOS" not in n)
                df = pd.read_csv(io.BytesIO(z.read(nombre)), dtype=str, encoding="utf-8")
                df.columns = [normalizar(c) for c in df.columns]
                grados = lambda eje: (pd.to_numeric(df[f"GRADOS {eje}"], errors="coerce")
                                      + pd.to_numeric(df[f"MINUTOS {eje}"], errors="coerce") / 60
                                      + pd.to_numeric(df[f"SEGUNDOS {eje}"], errors="coerce") / 3600)
                df["latitud"] = grados("LATITUD")
                df["longitud"] = -grados("LONGITUD").abs()  # México: siempre oeste
                df = df.merge(con, left_on="TITULO", right_on="titulo", how="left").drop(columns="titulo")
                self.guardar(capa, self.en_caja(df, "longitud", "latitud"),
                             "(coordenadas convertidas de grados, minutos y segundos)")

    def retc(self) -> None:
        partes = []
        with zipfile.ZipFile(self.crudos / "emisiones" / "retc_2004-2022.zip") as z:
            for nombre in sorted(z.namelist()):
                anio = int("".join(ch for ch in nombre if ch.isdigit())[:4])
                crudo = pd.read_excel(io.BytesIO(z.read(nombre)), header=None)
                # El encabezado no está en el primer renglón: es el que dice latitud.
                fila = next(i for i, r in crudo.iterrows()
                            if any("LATITUD" in normalizar(v) for v in r.dropna().astype(str)))
                df = crudo.iloc[fila + 1:].copy()
                df.columns = [normalizar(c) if pd.notna(c) else f"col{i}" for i, c in enumerate(crudo.iloc[fila])]
                lat = next(c for c in df.columns if "LATITUD" in c)
                lon = next(c for c in df.columns if "LONGITUD" in c)
                df = df.rename(columns={lat: "latitud", lon: "longitud"})
                df["latitud"] = df["latitud"].map(a_grados)
                df["longitud"] = -df["longitud"].map(a_grados).abs()  # vienen sin signo
                df.insert(0, "anio", anio)
                partes.append(df.loc[:, ~df.columns.duplicated()])
        todo = pd.concat(partes, ignore_index=True).astype({c: str for c in partes[0].columns if c not in ("anio", "latitud", "longitud")}, errors="ignore")
        gdf = self.en_caja(todo, "longitud", "latitud")
        gdf = gdf.astype({c: str for c in gdf.columns if c not in ("anio", "latitud", "longitud", "geometry")})
        # Sin nombre: hay granjas y talleres a nombre de personas (igual que en Mapo).
        gdf = gdf.drop(columns=[c for c in ("NOMBRE", "ESTABLECIMIENTO") if c in gdf.columns])
        self.guardar("retc", gdf, "(columnas cambian por año: se unieron por nombre; sin nombre del establecimiento)")

    def firms(self) -> None:
        for capa, prefijo in (("firms_viirs", "firms_viirs_snpp_"), ("firms_modis", "firms_modis_")):
            partes = []
            for p in sorted((self.crudos / "incendios").glob(f"{prefijo}*.csv")):
                for trozo in pd.read_csv(p, chunksize=500_000, dtype={"acq_time": str}):
                    partes.append(self.en_caja(trozo, "longitude", "latitude"))
            self.guardar(capa, pd.concat(partes, ignore_index=True) if partes else gpd.GeoDataFrame(),
                         "(un foco no es un incendio confirmado; ver confidence)")

    def iter_2020(self) -> pd.DataFrame:
        with zipfile.ZipFile(self.crudos / "poblacion" / "iter_14_2020.zip") as z:
            nombre = next(n for n in z.namelist() if n.lower().endswith(".csv") and "conjunto" in n.lower())
            crudo = z.read(nombre)
        try:
            return pd.read_csv(io.BytesIO(crudo), dtype=str, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(io.BytesIO(crudo), dtype=str, encoding="latin1")

    def localidades(self) -> None:
        df = self.iter_2020()
        df = df[pd.to_numeric(df["LOC"], errors="coerce").between(1, 9997)]  # quita totales
        claves = self.mun_claves()
        # GeoPackage no distingue mayúsculas: LONGITUD (texto en grados) y lon_dec.
        df = df.assign(lon_dec=df["LONGITUD"].map(a_grados), lat_dec=df["LATITUD"].map(a_grados))
        df = df.dropna(subset=["lon_dec", "lat_dec"])
        o, s, e, n = self.caja
        en_caja = df["lon_dec"].between(o, e) & df["lat_dec"].between(s, n)
        pedidos = pd.Series([(int(a), int(m)) in claves for a, m in zip(df["ENTIDAD"], df["MUN"])], index=df.index)
        df = df[en_caja | pedidos].assign(en_municipios_pedidos=pedidos)
        gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon_dec"], df["lat_dec"]), crs=CRS)
        self.guardar("localidades", gdf, "(municipios pedidos más las vecinas dentro de la caja; '*' es dato reservado)")

    def municipios_en_caja(self) -> set[tuple[str, str]]:
        """(entidad, municipio) con localidades del ITER dentro de la caja, más los pedidos."""
        df = self.iter_2020()
        df = df.assign(lon=df["LONGITUD"].map(a_grados), lat=df["LATITUD"].map(a_grados)).dropna(subset=["lon", "lat"])
        o, s, e, n = self.caja
        dentro = df[df["lon"].between(o, e) & df["lat"].between(s, n)]
        claves = {(f"{int(a):02d}", f"{int(m):03d}") for a, m in zip(dentro["ENTIDAD"], dentro["MUN"])}
        return claves | {(m[:2], m[2:]) for m in self.municipios}

    def inegi(self, ruta: str) -> gpd.GeoDataFrame:
        """GeoJSON del API de INEGI (wscatgeo v2), con reintentos."""
        url = f"https://gaia.inegi.org.mx/wscatgeo/v2/{ruta}"
        for espera in (0, 10, 30, 60):
            time.sleep(espera)
            try:
                with urllib.request.urlopen(url, timeout=180) as r:
                    datos = json.load(r)
                if not datos.get("features"):
                    return gpd.GeoDataFrame()
                return gpd.GeoDataFrame.from_features(datos["features"], crs=CRS)
            except Exception as error:  # red o servidor: reintentar
                ultimo = error
        raise RuntimeError(f"INEGI no respondió {url}: {ultimo}")

    def rural(self) -> None:
        """Polígonos de AGEB rurales y de localidades amanzanadas (rurales y urbanas)
        del API de INEGI. Las rancherías sin manzanas no tienen polígono: siguen como
        puntos en `localidades`. El censo por AGEB solo existe para las urbanas, así
        que a cada AGEB rural se le suma la población de las localidades del ITER
        que caen dentro."""
        claves = sorted(self.municipios_en_caja())
        agebs = pd.concat([self.inegi(f"geo/agebr/{e}/{m}") for e, m in claves], ignore_index=True)
        locs = pd.concat([self.inegi(f"geo/localidades/pol/{e}/{m}/{amb}") for e, m in claves for amb in ("R", "U")],
                         ignore_index=True)
        it = self.iter_2020()
        it = it[pd.to_numeric(it["LOC"], errors="coerce").between(1, 9997)].copy()
        it["cvegeo"] = it["ENTIDAD"].str.zfill(2) + it["MUN"].str.zfill(3) + it["LOC"].str.zfill(4)
        it["pobtot"] = pd.to_numeric(it["POBTOT"], errors="coerce")
        it["vivhab"] = pd.to_numeric(it.get("TVIVHAB"), errors="coerce")
        if not locs.empty:
            locs = gpd.GeoDataFrame(locs, crs=CRS).merge(it[["cvegeo", "pobtot", "vivhab"]], on="cvegeo", how="left")
            locs["geometry"] = locs.geometry.make_valid()
            self.guardar("localidades_poligonos", locs.clip(self.poligono), "(con población del ITER 2020)")
        if not agebs.empty:
            agebs = gpd.GeoDataFrame(agebs, crs=CRS)
            agebs["geometry"] = agebs.geometry.make_valid()
            puntos = it.assign(lon=it["LONGITUD"].map(a_grados), lat=it["LATITUD"].map(a_grados)).dropna(subset=["lon", "lat"])
            puntos = gpd.GeoDataFrame(puntos[["pobtot", "vivhab"]], geometry=gpd.points_from_xy(puntos["lon"], puntos["lat"]), crs=CRS)
            suma = gpd.sjoin(puntos, agebs[["cvegeo", "geometry"]], predicate="within").groupby("cvegeo")[["pobtot", "vivhab"]].sum(min_count=1)
            agebs = agebs.merge(suma.add_suffix("_iter").reset_index(), on="cvegeo", how="left")
            agebs["localidades_iter"] = agebs["cvegeo"].map(gpd.sjoin(puntos, agebs[["cvegeo", "geometry"]], predicate="within").groupby("cvegeo").size())
            self.guardar("agebs_rurales", agebs.clip(self.poligono),
                         "(población sumada de las localidades del ITER dentro; '*' reservado cuenta como vacío)")

    def manzanas(self) -> None:
        """Polígonos de manzana del API de INEGI (un GeoJSON por municipio, con
        población y viviendas) más las ~220 variables del censo 2020 por manzana
        (`ageb_mza_urbana_EE_cpv2020_csv.zip`), unidas por la clave de 16 dígitos.
        INEGI reserva los valores de manzanas con pocas viviendas: '*' queda como
        texto, no como cero."""
        claves = sorted(self.municipios_en_caja())
        mza = pd.concat([self.inegi(f"geo/mza/{e}/{m}") for e, m in claves], ignore_index=True)
        if mza.empty:
            self.anotar("manzanas", 0, "zona.gpkg", "el API no devolvió manzanas")
            return
        mza = gpd.GeoDataFrame(mza, crs=CRS)
        mza = mza[mza.intersects(self.poligono)].copy()
        mza["geometry"] = mza.geometry.make_valid()
        nota = "(sin censo por manzana: falta el zip en crudos/poblacion)"
        partes = []
        for ent in sorted({e for e, _ in claves}):
            p = self.crudos / "poblacion" / f"manzanas_{ent}_2020.zip"
            if not p.exists():
                continue
            with zipfile.ZipFile(p) as z:
                nombre = max(z.infolist(), key=lambda i: i.file_size).filename
                df = pd.read_csv(io.BytesIO(z.read(nombre)), dtype=str, encoding="latin1")
            df = df[(df["MZA"] != "000") & (df["AGEB"] != "0000")]  # quita los totales
            df["cvegeo"] = df["ENTIDAD"].str.zfill(2) + df["MUN"].str.zfill(3) + df["LOC"].str.zfill(4) + df["AGEB"] + df["MZA"].str.zfill(3)
            partes.append(df.drop(columns=["ENTIDAD", "NOM_ENT", "MUN", "NOM_MUN", "LOC", "NOM_LOC", "AGEB", "MZA"]).add_prefix("c_").rename(columns={"c_cvegeo": "cvegeo"}))
        if partes:
            censo = pd.concat(partes, ignore_index=True)
            mza = mza.merge(censo, on="cvegeo", how="left")
            nota = f"(censo en columnas c_*: {int(mza['c_POBTOT'].notna().sum()):,} de {len(mza):,} con renglón; '*' es dato reservado)"
        self.guardar("manzanas", mza, nota)

    def viento(self) -> None:
        """Viento horario de ERA5 (10 m) de 2015 a 2024 en el centro de la caja, y su
        resumen por mes y hora: velocidad media, calma (< 1 m/s), dirección
        resultante, constancia (resultante entre media: 1 es siempre del mismo lado)
        y frecuencia por rumbo. ERA5 tiene celdas de ~28 km: da el régimen de la zona,
        no el viento entre edificios."""
        import math
        o, s, e, n = self.caja
        lat, lon = round((s + n) / 2, 4), round((o + e) / 2, 4)
        url = ("https://archive-api.open-meteo.com/v1/archive?"
               f"latitude={lat}&longitude={lon}&start_date=2015-01-01&end_date=2024-12-31"
               "&hourly=wind_speed_10m,wind_direction_10m,wind_gusts_10m&models=era5"
               "&wind_speed_unit=ms&timezone=America%2FMexico_City")
        for espera in (0, 10, 30, 60):
            time.sleep(espera)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "mapo-recorte/1.0"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    datos = json.load(r)
                break
            except Exception as error:
                ultimo = error
        else:
            raise RuntimeError(f"Open-Meteo no respondió: {ultimo}")
        h = pd.DataFrame(datos["hourly"]).rename(columns={"time": "hora_local", "wind_speed_10m": "velocidad_ms",
                                                          "wind_direction_10m": "desde_grados", "wind_gusts_10m": "rafaga_ms"})
        h = h.dropna(subset=["velocidad_ms", "desde_grados"])
        if h.empty:
            raise RuntimeError("Open-Meteo devolvió la serie vacía")
        celda = f"celda ERA5 {datos['latitude']}, {datos['longitude']}"
        self.guardar_tabla("viento_horario", h, f"({celda}; dirección de donde viene)")
        t = pd.to_datetime(h["hora_local"])
        rad = h["desde_grados"].map(math.radians)
        h = h.assign(mes=t.dt.month, hora=t.dt.hour, u=-h["velocidad_ms"] * rad.map(math.sin),
                     v=-h["velocidad_ms"] * rad.map(math.cos), calma=h["velocidad_ms"] < 1,
                     rumbo=((h["desde_grados"] + 22.5) % 360 // 45).astype(int).map(dict(enumerate(["N", "NE", "E", "SE", "S", "SO", "O", "NO"]))))
        g = h.groupby(["mes", "hora"])
        res = g.agg(horas=("velocidad_ms", "size"), velocidad_media=("velocidad_ms", "mean"),
                    velocidad_p90=("velocidad_ms", lambda x: x.quantile(0.9)), rafaga_media=("rafaga_ms", "mean"),
                    calma=("calma", "mean"), u=("u", "mean"), v=("v", "mean"))
        resultante = (res["u"] ** 2 + res["v"] ** 2) ** 0.5
        res["desde_resultante"] = ((pd.Series(map(math.atan2, -res["u"], -res["v"]), index=res.index).map(math.degrees) + 360) % 360)
        res["constancia"] = resultante / res["velocidad_media"]
        frec = pd.crosstab([h["mes"], h["hora"]], h["rumbo"], normalize="index").add_prefix("frec_")
        res = res.drop(columns=["u", "v"]).join(frec).round(3).reset_index()
        self.guardar_tabla("viento_climatologia", res, f"({celda}; 2015 a 2024, una fila por mes y hora local)")

    def desde_mapo(self) -> None:
        """Capas que `desde_mapo.sh` sacó de la base de Mapo a `salida/mapo/`."""
        import json
        from shapely import wkt
        carpeta = self.salida / "mapo"
        if not carpeta.exists():
            self.anotar("agebs", None, "-", "no corrió desde_mapo.sh")
            return
        for capa in ("agebs", "denue"):
            df = pd.read_csv(carpeta / f"{capa}.csv", dtype=str)
            if capa == "agebs":
                # Las ~220 columnas del censo, una por variable, con su nombre de INEGI.
                censo = pd.json_normalize([json.loads(j) if isinstance(j, str) else {} for j in df.pop("censo_json")])
                df = pd.concat([df, censo.add_prefix("c_")], axis=1)
            gdf = gpd.GeoDataFrame(df.drop(columns="wkt"), geometry=df["wkt"].map(wkt.loads), crs=CRS)
            self.guardar(capa, gdf, "(censo en columnas c_*, nombres de INEGI)" if capa == "agebs" else "")

    # --- fuentes por municipio ------------------------------------------
    def marginacion(self) -> None:
        """Índices de marginación urbana 2020 de CONAPO. Son índices compuestos: van
        con sus once componentes (porcentajes del censo) para leerlos por separado,
        y el índice tal como lo publica CONAPO, nunca como puntaje propio. Las
        colonias son la única cartografía pública de colonias con nombre; su
        población es estimada (por eso trae decimales)."""
        nota = ("(componentes en %: P6A14NAE, SBASC, PSDSS, OVSDE, OVSEE, OVSAE, OVPT, OVHAC, OVSREF, "
                "OVSINT, OVSCEL; IM_2020 y GM_2020 son de CONAPO, no un puntaje de Mapo)")
        self.guardar("colonias_marginacion", self.vector(self.zip_vsi("marginacion/imc_2020_colonias_shp.zip")), nota)
        with zipfile.ZipFile(self.crudos / "marginacion" / "imu_2020_ageb.zip") as z:
            df = pd.read_excel(io.BytesIO(z.read("IMU_2020.xls")), sheet_name="IMU_2020", dtype={"CVE_AGEB": str, "ENT": str, "MUN": str, "LOC": str, "AGEB": str})
        df = df[(df["ENT"] + df["MUN"]).isin(self.municipios)]
        self.guardar_tabla("agebs_marginacion", df.rename(columns={"CVE_AGEB": "cvegeo"}), nota + " (se une con agebs por cvegeo)")

    def siap(self) -> None:
        claves, partes = self.mun_claves(), []
        for p in sorted((self.crudos / "agricultura").glob("siap_municipal_*.csv")):
            df = pd.read_csv(p, encoding="latin1", dtype=str)
            if "Anio" not in df.columns:
                df = pd.read_csv(p, encoding="utf-8", dtype=str)
            partes.append(df[[(int(e), int(m)) in claves for e, m in zip(df["Idestado"], df["Idmunicipio"])]])
        self.guardar_tabla("siap_municipal", pd.concat(partes, ignore_index=True))

    def sequia(self) -> None:
        df = pd.read_excel(self.crudos / "riesgo" / "sequia_municipios.xlsx", sheet_name="MUNICIPIOS", dtype=str)
        clave = df["CVE_CONCATENADA"].str.zfill(5)
        self.guardar_tabla("sequia_municipal", df[clave.isin(self.municipios)],
                           "(una columna por fecha de corte; vacío es sin sequía)")

    def defunciones(self) -> None:
        claves, partes = self.mun_claves(), []
        for p in sorted((self.crudos / "salud").glob("defunciones_*.zip")):
            with zipfile.ZipFile(p) as z:
                # La ruta cambia por año (2023 no usa conjunto_de_datos/): el más grande es el de datos.
                nombre = max(z.infolist(), key=lambda i: i.file_size).filename
                df = pd.read_csv(io.BytesIO(z.read(nombre)), dtype=str, encoding="utf-8")
            df = df[[(int(e), int(m)) in claves for e, m in zip(df["ent_resid"], df["mun_resid"])]]
            # Solo conteos: cada renglón del original es un certificado (una persona), y con
            # localidad, edad, causa y fechas se puede reconocer a alguien en un pueblo chico.
            df = df.assign(anio_registro=p.stem.split("_")[-1], cve_ent=df["ent_resid"].str.zfill(2),
                           cve_mun=df["mun_resid"].str.zfill(3), causa=df["causa_def"].str[:3],
                           edad_grupo=df["edad_agru"].fillna("30"))
            partes.append(df.groupby(["anio_registro", "cve_ent", "cve_mun", "causa", "sexo", "edad_grupo"])
                          .size().rename("defunciones").reset_index())
        self.guardar_tabla("defunciones", pd.concat(partes, ignore_index=True),
                           "(conteos por municipio de residencia, año de registro, causa CIE-10 a 3 caracteres, "
                           "sexo y edad_agru de INEGI; sin microdatos)")

    def ptar(self) -> None:
        df = pd.read_csv(self.crudos / "agua" / "plantas_tratamiento.csv", encoding="cp850", dtype=str)
        nombres = self.nombres_municipio()
        mun = df["Municipio"].map(normalizar)
        self.guardar_tabla("plantas_tratamiento", df[mun.isin(nombres)],
                           "(empatado por nombre de municipio; revisar homónimos)")

    def nombres_municipio(self) -> set[str]:
        df = self.iter_2020()[["ENTIDAD", "MUN", "NOM_MUN"]]
        claves = self.mun_claves()
        return {normalizar(n) for e, m, n in df.itertuples(index=False) if (int(e), int(m)) in claves}

    # --- ráster ----------------------------------------------------------
    def relieve(self) -> None:
        import math
        import rasterio
        from rasterio.merge import merge

        o, s, e, n = self.caja
        mosaicos, faltan = [], False
        for lat in range(math.floor(s), math.floor(n) + 1):
            for lon in range(math.floor(o), math.floor(e) + 1):
                p = self.crudos / "relieve" / f"Copernicus_DSM_COG_10_N{lat:02d}_00_W{abs(lon):03d}_00_DEM.tif"
                if p.exists():
                    mosaicos.append(rasterio.open(p))
                else:
                    faltan = True
        origen = f"{len(mosaicos)} mosaicos locales"
        if faltan:
            # Los crudos solo traen Jalisco: el resto del país se lee del STAC de
            # Planetary Computer, la misma colección, leyendo solo la ventana.
            mosaicos = [rasterio.open(u) for u in self.relieve_stac()]
            origen = f"{len(mosaicos)} mosaicos de Planetary Computer (cop-dem-glo-30)"
        if not mosaicos:
            self.anotar("relieve", 0, "relieve.tif", "sin mosaicos para la caja")
            return
        arr, transformada = merge(mosaicos, bounds=self.caja)
        perfil = mosaicos[0].profile | {"height": arr.shape[1], "width": arr.shape[2], "transform": transformada,
                                        "driver": "GTiff", "compress": "deflate", "tiled": True}
        with rasterio.open(self.salida / "relieve.tif", "w", **perfil) as dst:
            dst.write(arr)
        self.anotar("relieve", arr.shape[1] * arr.shape[2], "relieve.tif", f"(píxeles; {origen})")

    def relieve_stac(self) -> list[str]:
        """URL firmadas (/vsicurl/) de los mosaicos GLO-30 que tocan la caja. La firma
        dura cerca de una hora: alcanza para leer una caja de un municipio."""
        api = "https://planetarycomputer.microsoft.com/api"
        cuerpo = json.dumps({"collections": ["cop-dem-glo-30"], "bbox": list(self.caja), "limit": 100}).encode()
        req = urllib.request.Request(f"{api}/stac/v1/search", data=cuerpo,
                                     headers={"Content-Type": "application/json", "User-Agent": "mapo-recorte/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            items = json.load(r)["features"]
        with urllib.request.urlopen(f"{api}/sas/v1/token/cop-dem-glo-30", timeout=60) as r:
            token = json.load(r)["token"]
        return [f"/vsicurl/{i['assets']['data']['href']}?{token}" for i in items]

    # --- orquestación ----------------------------------------------------
    def intentar(self, capa: str, fn) -> None:
        try:
            fn()
        except Exception as error:  # una fuente rota no tumba el paquete; queda anotada
            self.anotar(capa, None, "-", f"FALLÓ: {type(error).__name__}: {error}")

    def todo(self) -> None:
        pasos = [("agua_superficial", self.renameca), ("cuerpos_de_agua", self.vectoriales),
                 ("frontera_agricola", self.frontera_agricola),
                 ("repda_descargas", self.repda), ("retc", self.retc), ("firms_viirs", self.firms),
                 ("localidades", self.localidades), ("agebs_rurales", self.rural), ("manzanas", self.manzanas),
                 ("viento_horario", self.viento), ("agebs", self.desde_mapo), ("siap_municipal", self.siap),
                 ("colonias_marginacion", self.marginacion),
                 ("sequia_municipal", self.sequia), ("defunciones", self.defunciones),
                 ("plantas_tratamiento", self.ptar), ("relieve", self.relieve)]
        for capa, fn in pasos:
            print(f"- {fn.__name__}", flush=True)
            self.intentar(capa, fn)
        with open(self.salida / "diccionario_capas.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(self.registro[0]))
            w.writeheader()
            w.writerows(self.registro)
        self.escribir_procedencia()
        import hashlib
        huella = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (self.salida / "zona.txt").write_text(
            f"caja (oeste,sur,este,norte): {','.join(map(str, self.caja))}\n"
            f"municipios: {','.join(self.municipios)}\nCRS: {CRS}\n"
            f"generado: {dt.datetime.now().isoformat(timespec='seconds')}\n"
            f"comando: {' '.join(sys.argv)}\n"
            f"script recorte.py sha256: {huella}\n", encoding="utf-8")

    def escribir_procedencia(self) -> None:
        """Una fila por capa y archivo crudo, con sha256, fecha y URL del MANIFIESTO."""
        import fnmatch
        manifiesto = {}
        ruta = self.crudos / "MANIFIESTO.tsv"
        if ruta.exists():
            with open(ruta, encoding="utf-8") as f:
                for r in csv.DictReader(f, delimiter="\t"):
                    manifiesto[r["archivo"]] = r
        filas = []
        for capa in [r["capa"] for r in self.registro]:
            for patron in CRUDOS.get(capa, []):
                coincide = sorted(k for k in manifiesto if fnmatch.fnmatch(k, patron))
                if not coincide:
                    filas.append({"capa": capa, "archivo_crudo": patron, "sha256": "", "fecha_descarga": "", "url": ""})
                for k in coincide:
                    m = manifiesto[k]
                    filas.append({"capa": capa, "archivo_crudo": k, "sha256": m.get("sha256", ""),
                                  "fecha_descarga": m.get("fecha", ""), "url": m.get("url", "")})
        with open(self.salida / "procedencia.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["capa", "archivo_crudo", "sha256", "fecha_descarga", "url"])
            w.writeheader()
            w.writerows(filas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crudos", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--caja", required=True, help="oeste,sur,este,norte en grados")
    ap.add_argument("--municipios", required=True, help="claves de 5 dígitos separadas por coma, p. ej. 14015,14037")
    a = ap.parse_args()
    caja = tuple(float(v) for v in a.caja.split(","))
    if len(caja) != 4 or caja[0] >= caja[2] or caja[1] >= caja[3]:
        sys.exit("--caja debe ser oeste,sur,este,norte")
    municipios = [m.strip().zfill(5) for m in a.municipios.split(",")]
    Paquete(a.crudos.expanduser(), a.salida.expanduser(), caja, municipios).todo()


if __name__ == "__main__":
    main()
