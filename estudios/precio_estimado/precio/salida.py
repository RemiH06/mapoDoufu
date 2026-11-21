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


def tabla_oferta(v: pd.DataFrame, fabrica, rasgos: list[str], alfa: float,
                 cobertura_mun: pd.Series, version: str, parte_cal: float = 0.3,
                 min_agebs: int = 20, max_fuera: int = 3) -> pd.DataFrame:
    """Lo mismo con el precio de oferta del IIEG (dataset v8):

    - `anuncios`: la AGEB tiene al menos 3 anuncios efectivos; se muestra su mediana.
    - `modelo`: su municipio está en los anuncios del IIEG pero la AGEB no; rango.
    - `sin_base`: el IIEG no cubre su municipio, o su municipio tiene menos de
      `min_agebs` AGEB con anuncios (con 5, la cobertura "medida" no mide nada).
      No se le pasa el nivel de otro municipio ni de la mediana municipal
      (modelos.ipynb, sección 11). También queda `sin_base` la AGEB con
      `max_fuera` rasgos o más fuera del rango de las AGEB con anuncios, o donde
      el modelo extrapola (`Normalizado.fuera_de_ajuste`): la cobertura se midió
      en AGEB como las de anuncios, no en ella. Las demás se predicen con los
      rasgos recortados a ese rango.
    """
    base = v.dropna(subset=["y"])
    X, y, g = base[rasgos + ["municipio"]], base["y"], base["bloque"]
    aj, cal = next(GroupShuffleSplit(1, test_size=parte_cal, random_state=modelos.SEMILLA)
                   .split(X, y, g))
    m = fabrica().ajustar(X.iloc[aj], y.iloc[aj], g.iloc[aj])
    q = conformal.cuantil_conformal(m.puntaje(X.iloc[cal], y.iloc[cal].to_numpy()), alfa)

    t = v[["cvegeo", "cve_mun", "municipio", "medv", "medv_n", "medv_periodo"]].copy()
    cubierto = t["medv_periodo"].notna()
    suficientes = base["municipio"].value_counts()
    suficientes = set(suficientes[suficientes >= min_agebs].index)
    mn, mx = base[rasgos].min(), base[rasgos].max()
    fuera = ((v[rasgos] < mn) | (v[rasgos] > mx)).sum(axis=1).to_numpy()
    dominio = fuera < max_fuera
    t["fuente"] = np.where(t["medv"].notna(), "anuncios",
                           np.where(cubierto & t["municipio"].isin(suficientes) & dominio,
                                    "modelo", "sin_base"))
    t["valor"] = t["medv"].round(-3)
    t["anio_tabla"] = pd.to_numeric(t["medv_periodo"].str[:4], errors="coerce").astype("Int64")

    Xr = v[rasgos + ["municipio"]].copy()
    Xr[rasgos] = Xr[rasgos].clip(mn, mx, axis=1)
    candidatas = t["fuente"] == "modelo"
    extrapola = pd.Series(False, index=t.index)
    extrapola[candidatas] = m.fuera_de_ajuste(Xr[candidatas])
    t.loc[extrapola, "fuente"] = "sin_base"
    pred = t["fuente"] == "modelo"
    _, lo, hi = m.rango(Xr[pred], q)
    t.loc[pred, "rango_bajo"] = np.round(np.exp(lo), -4)
    t.loc[pred, "rango_alto"] = np.round(np.exp(hi), -4)
    t.loc[pred, "cobertura"] = t.loc[pred, "municipio"].map(cobertura_mun).round(3)
    t["n_base"] = np.where(t["fuente"] == "anuncios", t["medv_n"].round(),
                           np.where(pred, len(aj), np.nan))
    t["n_base"] = t["n_base"].astype("Int64")
    periodo = t["medv_periodo"].dropna().iloc[0]
    pocos = (t["fuente"] == "sin_base") & cubierto & ~t["municipio"].isin(suficientes)
    raras = (t["fuente"] == "sin_base") & cubierto & t["municipio"].isin(suficientes)
    t["metodo"] = t["fuente"].map({
        "anuncios": (f"mediana del precio pedido en los anuncios de venta del IIEG ({periodo}) "
                     "de las colonias que tocan la AGEB, pesada por área"),
        "modelo": (f"conformal partido normalizado ({1 - alfa:.0%}), Lasso con efecto fijo por "
                   "municipio y ancho por ridge, calibrado por bloques de 3 km; cobertura medida "
                   "en AGEB no vistas de su municipio"),
        "sin_base": "el IIEG no publica anuncios de este municipio",
    })
    t.loc[pocos, "metodo"] = (f"menos de {min_agebs} AGEB con anuncios en el municipio: "
                              "no alcanza para medir la cobertura de un rango")
    t.loc[raras, "metodo"] = ("se parece poco a las AGEB con anuncios (rasgos fuera de su rango o un "
                              "modelo que extrapola): ahí la cobertura del rango no está medida")
    t["version"] = version
    return t[COLUMNAS]
