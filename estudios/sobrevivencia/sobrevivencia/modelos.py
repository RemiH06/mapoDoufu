"""Dos preguntas distintas, dos herramientas:

- **¿Les va mejor a los que se juntan?** Probabilidad lineal con efecto fijo por
  giro (se compara cada negocio solo contra los de su mismo giro) y errores
  agrupados por bloque de 2 km. El coeficiente se lee en puntos porcentuales.
- **¿Qué tanto se puede predecir?** Logística y árboles (HistGradientBoosting)
  con validación por bloques: un negocio y su vecino de enfrente nunca quedan
  uno en entrenamiento y otro en prueba. Una tabla chica rara vez la gana una
  red, así que no se probó.

La probabilidad por negocio o por zona sería un puntaje: se queda aquí, no
pasa a Mapo (RNF5).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SEMILLA = 18


def preparar_x(df: pd.DataFrame, numericas: list[str]) -> pd.DataFrame:
    """Numéricas con los huecos llenos con la mediana y una columna que dice
    dónde faltaba: un hueco no es cero."""
    x = pd.DataFrame(index=df.index)
    for c in numericas:
        falta = df[c].isna()
        x[c] = df[c].fillna(df[c].median())
        if falta.any():
            x[f"{c}_falta"] = falta.astype(int)
    return x


def efecto_dentro_del_giro(df: pd.DataFrame, y: str, numericas: list[str], giro: str = "grupo_giro",
                           bloque: str = "bloque") -> pd.DataFrame:
    """Coeficientes de la probabilidad lineal con efecto fijo por giro, en
    puntos porcentuales, con intervalo al 95 % agrupado por bloque."""
    x = preparar_x(df, numericas)
    x = pd.concat([x, pd.get_dummies(df["estrato"], prefix="estrato", drop_first=True, dtype=float)], axis=1)
    datos = pd.concat([df[[y, giro, bloque]], x], axis=1)
    # Transformación "within": restar la media del giro equivale al efecto fijo.
    columnas = [y, *x.columns]
    dentro = datos[columnas] - datos.groupby(giro)[columnas].transform("mean")
    modelo = sm.OLS(dentro[y], dentro[list(x.columns)]).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(datos[bloque])[0]}
    )
    ic = modelo.conf_int()
    return pd.DataFrame({
        "puntos": modelo.params * 100,
        "desde": ic[0] * 100,
        "hasta": ic[1] * 100,
        "p": modelo.pvalues,
    }).round(3)


def validar(df: pd.DataFrame, y: str, numericas: list[str], giro: str = "grupo_giro",
            bloque: str = "bloque", pliegues: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """AUC y Brier por pliegue espacial de la logística y los árboles, y la
    probabilidad predicha fuera de muestra (para la calibración)."""
    x = pd.concat([preparar_x(df, numericas), df[[giro, "estrato"]]], axis=1)
    categorias = [giro, "estrato"]
    logistica = make_pipeline(
        ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20), categorias),
        ], remainder=StandardScaler()),
        LogisticRegression(max_iter=2000),
    )
    arboles = make_pipeline(
        ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20, sparse_output=False), categorias),
        ], remainder="passthrough"),
        HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=SEMILLA),
    )
    filas, fuera = [], pd.DataFrame(index=df.index)
    for nombre, modelo in [("logística", logistica), ("árboles", arboles)]:
        fuera[nombre] = np.nan
        for i, (entrena, prueba) in enumerate(GroupKFold(pliegues).split(x, df[y], df[bloque])):
            modelo.fit(x.iloc[entrena], df[y].iloc[entrena])
            p = modelo.predict_proba(x.iloc[prueba])[:, 1]
            fuera.iloc[prueba, fuera.columns.get_loc(nombre)] = p
            filas.append({"modelo": nombre, "pliegue": i + 1,
                          "auc": roc_auc_score(df[y].iloc[prueba], p),
                          "brier": brier_score_loss(df[y].iloc[prueba], p)})
    # Referencia: predecir la tasa de su giro, sin nada más.
    tasa_giro = df.groupby(giro)[y].transform("mean")
    filas.append({"modelo": "solo el giro (en muestra)", "pliegue": 0,
                  "auc": roc_auc_score(df[y], tasa_giro), "brier": brier_score_loss(df[y], tasa_giro)})
    return pd.DataFrame(filas), fuera


def tasas(df: pd.DataFrame, y: str, por: str) -> pd.DataFrame:
    salida = df.groupby(por, observed=True)[y].agg(negocios="size", sigue="mean").reset_index()
    salida["sigue"] = (salida["sigue"] * 100).round(1)
    return salida
