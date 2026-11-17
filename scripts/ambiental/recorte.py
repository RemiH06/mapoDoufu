# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyogrio", "pandas", "openpyxl", "rasterio", "shapely>=2", "pyproj"]
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
import pandas as pd
import pyogrio
from pyproj import Transformer
from shapely.geometry import box

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
    "anp": ("CONANP vía CONABIO", "Áreas naturales protegidas federales 2020", "polígono", "http://geoportal.conabio.gob.mx"),
    "regiones_hidrologicas": ("INEGI vía CONABIO", "Regiones hidrológicas 1:250 000", "polígono", "http://geoportal.conabio.gob.mx"),
    "localidades": ("INEGI, ITER 2020", "Censo 2020 por localidad, también rurales", "punto", "https://www.inegi.org.mx/programas/ccpv/2020/"),
    "agebs_rurales": ("INEGI, marco geoestadístico (API wscatgeo) + ITER 2020", "Marco de diciembre de 2025; población sumada del ITER 2020", "AGEB rural", "https://gaia.inegi.org.mx/wscatgeo/v2/geo/agebr/"),
    "localidades_poligonos": ("INEGI, marco geoestadístico (API wscatgeo) + ITER 2020", "Marco de diciembre de 2025; población del ITER 2020", "localidad amanzanada", "https://gaia.inegi.org.mx/wscatgeo/v2/geo/localidades/pol/"),
    "agebs": ("INEGI, marco geoestadístico y censo 2020 (vía Mapo)", "2020; censo solo en AGEB urbanas", "AGEB", "https://www.inegi.org.mx/temas/mg/"),
    "denue": ("INEGI, DENUE (vía Mapo)", "Edición cargada en Mapo, ver docs/fuentes/denue.md", "punto", "https://www.inegi.org.mx/app/mapa/denue/"),
    "siap_municipal": ("SIAP", "Cierre agrícola municipal 2003 a 2025", "municipio", "https://nube.siap.gob.mx/cierreagricola/"),
    "sequia_municipal": ("Conagua, SMN, Monitor de Sequía", "Categoría D0 a D4 por fecha de corte", "municipio", "https://smn.conagua.gob.mx/es/climatologia/monitor-de-sequia/monitor-de-sequia-en-mexico"),
    "defunciones": ("INEGI, defunciones registradas", "2020 a 2023, por municipio y localidad de residencia", "localidad", "https://www.inegi.org.mx/programas/edr/"),
    "plantas_tratamiento": ("Conagua", "Inventario de PTAR 2023, sin coordenadas", "localidad (por nombre)", "https://www.gob.mx/conagua"),
    "relieve": ("Copernicus DEM GLO-30", "Modelo digital de superficie, 30 m", "ráster", "https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model"),
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


def normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.upper().split())


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
                              "fecha_dato": fecha, "nivel": nivel, "url": url, "nota": nota})
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
        gdf = pyogrio.read_dataframe(ruta_vsi, bbox=caja)
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
        self.guardar("retc", gdf, "(columnas cambian por año: se unieron por nombre)")

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
            df.insert(0, "anio_registro", p.stem.split("_")[-1])
            partes.append(df)
        self.guardar_tabla("defunciones", pd.concat(partes, ignore_index=True),
                           "(por residencia; causa_def en CIE-10, catálogos en el zip original)")

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
        mosaicos = []
        for lat in range(math.floor(s), math.floor(n) + 1):
            for lon in range(math.floor(o), math.floor(e) + 1):
                p = self.crudos / "relieve" / f"Copernicus_DSM_COG_10_N{lat:02d}_00_W{abs(lon):03d}_00_DEM.tif"
                if p.exists():
                    mosaicos.append(rasterio.open(p))
        if not mosaicos:
            self.anotar("relieve", 0, "relieve.tif", "sin mosaicos para la caja")
            return
        arr, transformada = merge(mosaicos, bounds=self.caja)
        perfil = mosaicos[0].profile | {"height": arr.shape[1], "width": arr.shape[2], "transform": transformada,
                                        "driver": "GTiff", "compress": "deflate", "tiled": True}
        with rasterio.open(self.salida / "relieve.tif", "w", **perfil) as dst:
            dst.write(arr)
        self.anotar("relieve", arr.shape[1] * arr.shape[2], "relieve.tif", f"(píxeles; {len(mosaicos)} mosaicos)")

    # --- orquestación ----------------------------------------------------
    def intentar(self, capa: str, fn) -> None:
        try:
            fn()
        except Exception as error:  # una fuente rota no tumba el paquete; queda anotada
            self.anotar(capa, None, "-", f"FALLÓ: {type(error).__name__}: {error}")

    def todo(self) -> None:
        pasos = [("agua_superficial", self.renameca), ("cuerpos_de_agua", self.vectoriales),
                 ("repda_descargas", self.repda), ("retc", self.retc), ("firms_viirs", self.firms),
                 ("localidades", self.localidades), ("agebs_rurales", self.rural), ("agebs", self.desde_mapo), ("siap_municipal", self.siap),
                 ("sequia_municipal", self.sequia), ("defunciones", self.defunciones),
                 ("plantas_tratamiento", self.ptar), ("relieve", self.relieve)]
        for capa, fn in pasos:
            print(f"- {fn.__name__}", flush=True)
            self.intentar(capa, fn)
        with open(self.salida / "diccionario_capas.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(self.registro[0]))
            w.writeheader()
            w.writerows(self.registro)
        (self.salida / "zona.txt").write_text(
            f"caja (oeste,sur,este,norte): {','.join(map(str, self.caja))}\n"
            f"municipios: {','.join(self.municipios)}\nCRS: {CRS}\n"
            f"generado: {dt.datetime.now().isoformat(timespec='seconds')}\n", encoding="utf-8")


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
