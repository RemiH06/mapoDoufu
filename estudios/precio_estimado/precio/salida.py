"""Tabla por AGEB para Mapo (`mapo_core.cli precio`).

Una fila por AGEB urbana del dataset:

- `catastro`: la AGEB tiene valor catastral; se muestra ese valor, sin modelo.
- `modelo`: su municipio tiene tabla de valores pero la AGEB no; rango conformal.
- `sin_base`: su municipio no tiene tabla de valores ubicada. No se rellena con
  vecinas ni con otros municipios (los años y niveles de cada tabla son distintos).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from . import conformal, modelos

COLUMNAS = ["cvegeo", "cve_mun", "municipio", "fuente", "valor", "rango_bajo", "rango_alto",
            "anio_tabla", "cobertura", "n_base", "metodo", "version"]


def tabla(v: pd.DataFrame, fabrica, rasgos: list[str], alfa: float,
          cobertura_mun: pd.Series, version: str, parte_cal: float = 0.3) -> pd.DataFrame:
    base = v.dropna(subset=["y"])
    X, y, g = base[rasgos + ["municipio"]], base["y"], base["bloque"]
    aj, cal = next(GroupShuffleSplit(1, test_size=parte_cal, random_state=modelos.SEMILLA)
                   .split(X, y, g))
    m = fabrica().ajustar(X.iloc[aj], y.iloc[aj], g.iloc[aj])
    q = conformal.cuantil_conformal(m.puntaje(X.iloc[cal], y.iloc[cal].to_numpy()), alfa)

    con_tabla = set(base["municipio"])
    anio = base.groupby("municipio")["medv_anio"].first()
    t = v[["cvegeo", "cve_mun", "municipio", "medv", "medv_n", "medv_anio"]].copy()
    t["fuente"] = np.where(t["medv"].notna(), "catastro",
                           np.where(t["municipio"].isin(con_tabla), "modelo", "sin_base"))
    t["valor"] = t["medv"].round(0)
    t["anio_tabla"] = t["municipio"].map(anio).astype("Int64")

    pred = t["fuente"] == "modelo"
    _, lo, hi = m.rango(v.loc[pred, rasgos + ["municipio"]], q)
    t.loc[pred, "rango_bajo"] = np.round(np.exp(lo), -1)
    t.loc[pred, "rango_alto"] = np.round(np.exp(hi), -1)
    t.loc[pred, "cobertura"] = t.loc[pred, "municipio"].map(cobertura_mun).round(3)
    t["n_base"] = np.where(t["fuente"] == "catastro", t["medv_n"],
                           np.where(pred, len(aj), np.nan))
    t["n_base"] = t["n_base"].astype("Int64")
    t["metodo"] = t["fuente"].map({
        "catastro": "mediana de los valores de zona de la tabla catastral dentro de la AGEB",
        "modelo": (f"conformal partido normalizado ({1 - alfa:.0%}), bosque aleatorio con "
                   "efecto fijo por municipio, calibrado por bloques de 3 km; cobertura "
                   "medida en AGEB no vistas de su municipio"),
        "sin_base": "sin tabla de valores ubicada para este municipio",
    })
    t["version"] = version
    return t[COLUMNAS]
