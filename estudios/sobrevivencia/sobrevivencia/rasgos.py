"""Rasgos de cada negocio: vecindad y contexto de su AGEB."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

RADIO_M = 200
CONTEXTO = {
    "viv_ha": "Viviendas por hectárea",
    "graproes": "Escolaridad promedio (años)",
    "pct_viv_auto": "Viviendas con auto (%)",
    "dis_km": "Distancia a centros de empleo (km)",
}


def _km(df: pd.DataFrame) -> np.ndarray:
    lat0 = np.radians(df["lat"].mean())
    return np.column_stack([df["lat"] * 111.32, df["lon"] * 111.32 * np.cos(lat0)])


def vecindad(df: pd.DataFrame, radio_m: float = RADIO_M) -> pd.DataFrame:
    """Negocios a menos de `radio_m` (todos y del mismo giro, sin contarse) y
    distancia al más cercano del mismo giro. Con los negocios de la misma
    edición: es la vecindad que tenía el negocio cuando se le midió."""
    xy = _km(df)
    arbol = cKDTree(xy)
    r = radio_m / 1000
    todos = np.array([len(v) - 1 for v in arbol.query_ball_point(xy, r)])
    mismo = np.zeros(len(df), dtype=int)
    distancia = np.full(len(df), np.nan)
    for _, filas in df.groupby("grupo_giro").indices.items():
        if len(filas) < 2:
            continue
        sub = cKDTree(xy[filas])
        mismo[filas] = [len(v) - 1 for v in sub.query_ball_point(xy[filas], r)]
        d, _ = sub.query(xy[filas], k=2)
        distancia[filas] = d[:, 1] * 1000
    return pd.DataFrame({
        "vecinos_todos": todos,
        "vecinos_mismo_giro": mismo,
        "dist_mismo_giro_m": distancia,
    }, index=df.index)


def contexto(df: pd.DataFrame, ruta_vivienda: Path) -> pd.DataFrame:
    """Columnas de `CONTEXTO` de la AGEB del negocio, del dataset de vivienda
    (docs/producto/dataset-vivienda.md). Vacío fuera de las AGEB urbanas."""
    with zipfile.ZipFile(ruta_vivienda) as z:
        nombre = next(n for n in z.namelist() if n.endswith("vivienda_ageb.csv"))
        with z.open(nombre) as f:
            ageb = pd.read_csv(f, dtype={"cvegeo": str}, usecols=["cvegeo", *CONTEXTO])
    return df[["cvegeo"]].merge(ageb, on="cvegeo", how="left").drop(columns="cvegeo").set_index(df.index)


def bloques(df: pd.DataFrame, km: float = 2.0) -> pd.Series:
    """Celda de una rejilla de `km` por lado: los vecinos comparten barrio, así
    que la validación y los errores estándar se hacen por bloque, no por negocio."""
    xy = _km(df)
    celda = np.floor(xy / km).astype(int)
    return pd.Series([f"{a}_{b}" for a, b in celda], index=df.index)


def agrupacion_por_giro(df: pd.DataFrame, sorteos: int = 19, minimo: int = 30, semilla: int = 18) -> pd.Series:
    """Distancia media al vecino del mismo giro entre la misma medida con las
    etiquetas sorteadas, por giro (menos de 1, se agrupa). Es el rasgo
    `agrupacion` de la taxonomía de Mapo (`mapo_core/taxonomia.py`), sin log
    y con menos sorteos: aquí solo separa giros, no prueba nada."""
    xy = _km(df)
    giros = df["grupo_giro"].to_numpy()
    cuenta = pd.Series(giros).value_counts()
    validos = cuenta[cuenta >= minimo].index

    def medias(etiquetas: np.ndarray) -> dict:
        indices = pd.Series(etiquetas).groupby(etiquetas).indices
        salida = {}
        for g in validos:
            puntos = xy[indices[g]]
            d, _ = cKDTree(puntos).query(puntos, k=2)
            salida[g] = d[:, 1].mean()
        return salida

    observada = pd.Series(medias(giros))
    rng = np.random.default_rng(semilla)
    azar = pd.DataFrame([medias(rng.permutation(giros)) for _ in range(sorteos)]).mean()
    return (observada / azar).rename("razon_agrupacion")
