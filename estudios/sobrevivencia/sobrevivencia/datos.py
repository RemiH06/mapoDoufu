"""Ediciones de DENUE: descarga, lectura y la tabla base con la etiqueta.

Hallazgos que fijan el diseño (docs/producto/sobrevivencia.md):

- Entre ediciones normales sigue el 99 % de los negocios: INEGI actualiza sobre
  todo a los grandes. Las bajas de los chicos aparecen de golpe cuando entra un
  Censo Económico: 2018_11 -> 2019_11 (sigue el 61.6 %) y 2023_11 -> 2024_11
  (71.3 %). La ventana con sentido es de un corte censal al siguiente.
- La llave es `id`. `clee` no existe antes de 2022_11 y cambia aunque el
  negocio siga (74 mil de 2024_11 a 2026_05 conservan `id` y no `clee`).
- La codificación cambia por edición: 2017_11 viene en UTF-8 con BOM; las
  demás, en Latin-1.
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.spatial import cKDTree

URL = "https://www.inegi.org.mx/contenidos/masiva/denue/{aaaa}_{mm}/denue_{ent}_{mm}{aa}_csv.zip"
COLUMNAS = {
    "id": "id",
    "nom_estab": "nombre",
    "codigo_act": "scian",
    "nombre_act": "clase",
    "per_ocu": "estrato",
    "tipoCenCom": "tipo_plaza",
    "cve_ent": "cve_ent",
    "cve_mun": "cve_mun",
    "cve_loc": "cve_loc",
    "ageb": "ageb",
    "tipoUniEco": "tipo",
    "latitud": "lat",
    "longitud": "lon",
    "fecha_alta": "fecha_alta",
}
ESTRATOS = [
    "0 a 5 personas", "6 a 10 personas", "11 a 30 personas", "31 a 50 personas",
    "51 a 100 personas", "101 a 250 personas", "251 y más personas",
]
MESES = {m: i + 1 for i, m in enumerate(
    ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
     "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"])}


def _url(edicion: str, ent: str, parte: str = "") -> str:
    aaaa, mm = edicion.split("_")
    return URL.format(aaaa=aaaa, mm=mm, aa=aaaa[2:], ent=f"{ent}{parte}")


def _guardar(url: str, ruta: Path) -> bool:
    """El servidor de INEGI contesta 200 con una página HTML cuando el archivo
    no existe: solo cuenta si empieza como ZIP."""
    r = requests.get(url, timeout=600)
    r.raise_for_status()
    if not r.content.startswith(b"PK"):
        return False
    ruta.write_bytes(r.content)
    return True


def bajar(edicion: str, destino: Path, ent: str = "14") -> list[Path]:
    """Archivos de una edición (`AAAA_MM`) de un estado, bajados si faltan. Los
    estados grandes vienen en partes (`denue_15_1_...`, `denue_15_2_...`)."""
    destino.mkdir(parents=True, exist_ok=True)
    entero = destino / f"denue_{ent}_{edicion}.zip"
    if entero.exists():
        return [entero]
    partes = sorted(destino.glob(f"denue_{ent}_{edicion}_parte*.zip"))
    if partes:
        return partes
    if _guardar(_url(edicion, ent), entero):
        return [entero]
    for n in range(1, 10):
        ruta = destino / f"denue_{ent}_{edicion}_parte{n}.zip"
        if not _guardar(_url(edicion, ent, f"_{n}"), ruta):
            break
        partes.append(ruta)
    if not partes:
        raise ValueError(f"INEGI no tiene la edición {edicion} del estado {ent}.")
    return partes


def _csv(ruta: Path, **kwargs) -> pd.DataFrame:
    with zipfile.ZipFile(ruta) as z:
        nombre = next(n for n in z.namelist() if "conjunto_de_datos/" in n and n.endswith(".csv"))
        with z.open(nombre) as f:
            codificacion = "utf-8-sig" if f.read(3) == bytes([0xEF, 0xBB, 0xBF]) else "latin-1"
        with z.open(nombre) as f:
            return pd.read_csv(io.TextIOWrapper(f, encoding=codificacion, newline=""), dtype=str,
                               keep_default_na=False, **kwargs)


def leer(rutas: Path | list[Path]) -> pd.DataFrame:
    rutas = [rutas] if isinstance(rutas, Path) else rutas
    df = pd.concat([_csv(r, usecols=list(COLUMNAS)) for r in rutas], ignore_index=True)
    df = df.rename(columns=COLUMNAS)
    for c in df.columns:
        df[c] = df[c].str.strip()
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    return df


def meses_desde_alta(fecha: pd.Series, referencia: str) -> pd.Series:
    """Meses entre la fecha de alta y la edición. Tres formatos: `2010-07`,
    `DICIEMBRE 2014` y `06/10/2023`. 2010-07 es la primera edición de DENUE:
    quiere decir "ya estaba en 2010", no "abrió en 2010"."""
    ref = pd.Timestamp(referencia.replace("_", "-") + "-01")

    def uno(t: str):
        if m := re.fullmatch(r"(\d{4})-(\d{2})", t):
            return pd.Timestamp(int(m[1]), int(m[2]), 1)
        if m := re.fullmatch(r"([A-ZÁÉÍÓÚ]+) (\d{4})", t.upper()):
            return pd.Timestamp(int(m[2]), MESES.get(m[1], 1), 1)
        if m := re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", t):
            return pd.Timestamp(int(m[3]), int(m[2]), 1)
        return pd.NaT

    fechas = fecha.map(uno)
    return ((ref - fechas).dt.days / 30.44).round()


def rubros(ruta_clases: Path, actual: pd.DataFrame) -> pd.DataFrame:
    """codigo SCIAN -> clase, sector y rubro de la tabla de Mapo. Los nombres de
    clase cambian entre ediciones; el código, no (SCIAN 2018 desde 2019)."""
    tabla = pd.read_csv(ruta_clases, dtype=str, keep_default_na=False)
    codigos = actual[["scian", "clase"]].drop_duplicates("scian")
    salida = codigos.merge(tabla, left_on="clase", right_on="clase_actividad", how="left")
    salida["rubro"] = salida["rubro"].replace("", np.nan)
    return salida[["scian", "sector", "rubro"]]


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", str(texto).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def reregistrados(base: pd.DataFrame, fin: pd.DataFrame, metros: float = 30) -> pd.Series:
    """Ids de `base` que no siguen en `fin` pero tienen ahí un negocio nuevo a
    menos de `metros` con la misma rama SCIAN (4 dígitos) y el mismo nombre:
    probablemente el mismo negocio con otro id."""
    idos = base[~base["id"].isin(fin["id"]) & base["lat"].notna()]
    nuevos = fin[~fin["id"].isin(base["id"]) & fin["lat"].notna()].reset_index(drop=True)
    km = lambda d: np.column_stack([d["lat"] * 111.32, d["lon"] * 104.5])
    vecinos = cKDTree(km(nuevos)).query_ball_point(km(idos), r=metros / 1000)
    rama_n, nombre_n = nuevos["scian"].str[:4].to_numpy(), nuevos["nombre"].map(normalizar).to_numpy()
    marcados = []
    for (i, fila), cerca in zip(idos.iterrows(), vecinos):
        nombre = normalizar(fila["nombre"])
        if nombre and nombre != "sin nombre" and any(
            rama_n[j] == fila["scian"][:4] and nombre_n[j] == nombre for j in cerca
        ):
            marcados.append(fila["id"])
    return base["id"].isin(marcados)


def caja_robusta(df: pd.DataFrame, margen: float = 0.5) -> tuple[float, float, float, float]:
    """Caja del 0.1 al 99.9 % de las coordenadas, más `margen` grados: deja
    fuera los negocios con coordenadas de otro estado sin tener que cargar el
    polígono de cada uno."""
    lat, lon = df["lat"].dropna(), df["lon"].dropna()
    return (lat.quantile(0.001) - margen, lat.quantile(0.999) + margen,
            lon.quantile(0.001) - margen, lon.quantile(0.999) + margen)


def tabla_base(base: pd.DataFrame, fin: pd.DataFrame, municipios: list[str] | None, catalogo: pd.DataFrame,
               caja: tuple[float, float, float, float]) -> pd.DataFrame:
    """Una fila por negocio de la edición base en los municipios, con coordenadas
    dentro de `caja` (lat mín, lat máx, lon mín, lon máx) y la etiqueta: `sigue`
    (mismo id en `fin`) y `sigue_o_reregistrado`. En 2019_11, 12 negocios de la
    zona metropolitana traen coordenadas de Ensenada, Monterrey o Tabasco."""
    lat_min, lat_max, lon_min, lon_max = caja
    df = base[
        (base["cve_mun"].isin(municipios) if municipios is not None else True)
        & base["lat"].between(lat_min, lat_max)
        & base["lon"].between(lon_min, lon_max)
    ].copy()
    df["sigue"] = df["id"].isin(set(fin["id"])).astype(int)
    df["sigue_o_reregistrado"] = (df["sigue"].astype(bool) | reregistrados(df, fin)).astype(int)
    df = df.merge(catalogo, on="scian", how="left")
    # Lo que no tiene rubro en la tabla de Mapo (industria, oficinas) se agrupa por sector.
    df["grupo_giro"] = df["rubro"].fillna("sector:" + df["sector"].fillna("sin_clasificar"))
    df["estrato_n"] = df["estrato"].map({e: i for i, e in enumerate(ESTRATOS)})
    df["en_plaza"] = (df["tipo_plaza"] != "").astype(int)
    df["semifijo"] = (df["tipo"].str.lower() != "fijo").astype(int)
    df["cvegeo"] = df["cve_ent"] + df["cve_mun"] + df["cve_loc"] + df["ageb"]
    return df.reset_index(drop=True)


def ids(rutas: list[Path]) -> pd.Series:
    return pd.concat([_csv(r, usecols=["id"])["id"] for r in rutas]).str.strip()


def persistencia(rutas: dict[str, list[Path]]) -> pd.DataFrame:
    """Parte de los negocios de cada edición que sigue en la siguiente. Los
    desplomes marcan los cortes censales."""
    filas, anterior = [], None
    for edicion, ruta in sorted(rutas.items()):
        actual = set(ids(ruta))
        if anterior:
            e0, previos = anterior
            filas.append({"de": e0, "a": edicion, "negocios": len(previos),
                          "siguen": round(100 * len(previos & actual) / len(previos), 1)})
        anterior = (edicion, actual)
    return pd.DataFrame(filas)


ENTIDADES = {
    "01": "Aguascalientes", "02": "Baja California", "03": "Baja California Sur", "04": "Campeche",
    "05": "Coahuila", "06": "Colima", "07": "Chiapas", "08": "Chihuahua", "09": "Ciudad de México",
    "10": "Durango", "11": "Guanajuato", "12": "Guerrero", "13": "Hidalgo", "14": "Jalisco",
    "15": "Estado de México", "16": "Michoacán", "17": "Morelos", "18": "Nayarit", "19": "Nuevo León",
    "20": "Oaxaca", "21": "Puebla", "22": "Querétaro", "23": "Quintana Roo", "24": "San Luis Potosí",
    "25": "Sinaloa", "26": "Sonora", "27": "Tabasco", "28": "Tamaulipas", "29": "Tlaxcala",
    "30": "Veracruz", "31": "Yucatán", "32": "Zacatecas",
}


def resultados(carpeta: Path) -> pd.DataFrame:
    """Una fila por estado con las cifras que dejó `estado.ipynb`."""
    import json

    filas = []
    for ruta in sorted(carpeta.glob("*.json")):
        r = json.loads(ruta.read_text(encoding="utf-8"))
        fila = {"estado": r["estado"], "nombre": ENTIDADES[r["estado"]], "negocios": r["negocios"],
                "sigue": r["sigue"], "corte_2019": r["persistencia"].get("2019_11"),
                "corte_2024": r["persistencia"].get("2024_11"), "entre_cortes": r["persistencia"].get("2023_11"),
                "giros_se_agrupan": r["giros_se_agrupan"], "auc_arboles": r["auc_arboles"], "auc_giro": r["auc_giro"]}
        for clave in ("vecinos_mismo", "vecinos_todos", "en_plaza", "vecinos_mismo_rereg", "interaccion"):
            fila |= {f"{clave}_{k}": v for k, v in r[clave].items()}
        filas.append(fila)
    return pd.DataFrame(filas)
