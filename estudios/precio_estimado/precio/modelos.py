"""Modelos de la forma (log del valor catastral) y su validación por bloques."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVR

SEMILLA = 2026


def _columnas(rasgos: list[str], escalar: bool) -> ColumnTransformer:
    num = [SimpleImputer(strategy="median", add_indicator=True)]
    if escalar:
        num.append(StandardScaler())
    return ColumnTransformer([
        ("num", make_pipeline(*num), rasgos),
        # Efecto fijo por municipio; un municipio nuevo queda en ceros.
        ("mun", OneHotEncoder(handle_unknown="ignore"), ["municipio"]),
    ])


def catalogo(rasgos: list[str]) -> dict[str, object]:
    """Los cuatro candidatos. La SVR y la ridge buscan sus hiperparámetros por
    bloques dentro de cada partición (validación anidada)."""
    svr = make_pipeline(_columnas(rasgos, True), SVR(kernel="rbf"))
    return {
        "Ridge": make_pipeline(_columnas(rasgos, True), RidgeCV(alphas=np.logspace(-2, 3, 20))),
        "SVR": GridSearchCV(
            svr,
            {"svr__C": [0.3, 1, 3, 10], "svr__epsilon": [0.05, 0.1, 0.2],
             "svr__gamma": ["scale", 0.01]},
            cv=GroupKFold(4), scoring="neg_root_mean_squared_error",
        ),
        "Bosque": make_pipeline(_columnas(rasgos, False), RandomForestRegressor(
            n_estimators=400, min_samples_leaf=3, max_features=0.4,
            random_state=SEMILLA, n_jobs=-1)),
        "Boosting": make_pipeline(_columnas(rasgos, False), HistGradientBoostingRegressor(
            max_iter=400, learning_rate=0.04, min_samples_leaf=15, l2_regularization=1.0,
            random_state=SEMILLA)),
    }


def ajustar(modelo, X: pd.DataFrame, y: pd.Series, grupos: pd.Series):
    m = clone(modelo)
    if isinstance(m, GridSearchCV):
        m.fit(X, y, groups=grupos)
    else:
        m.fit(X, y)
    return m


def fuera_de_muestra(modelo, X: pd.DataFrame, y: pd.Series, grupos: pd.Series,
                     particiones: int = 5) -> pd.Series:
    """Predicción de cada AGEB con un modelo que no vio su bloque."""
    pred = pd.Series(np.nan, index=X.index)
    for a, b in GroupKFold(particiones).split(X, y, grupos):
        m = ajustar(modelo, X.iloc[a], y.iloc[a], grupos.iloc[a])
        pred.iloc[b] = m.predict(X.iloc[b])
    return pred


def metricas(y: pd.Series, pred: pd.Series, municipio: pd.Series) -> pd.DataFrame:
    """RMSE en log (≈ error relativo) y Spearman dentro de cada municipio: el orden
    es lo que la forma debe dar bien."""
    filas = []
    for nombre, idx in [("Todos", y.index)] + list(municipio.groupby(municipio).groups.items()):
        e = y[idx] - pred[idx]
        filas.append({
            "municipio": nombre, "agebs": len(idx),
            "rmse_log": float(np.sqrt((e ** 2).mean())),
            "spearman": float(spearmanr(y[idx], pred[idx]).statistic) if len(idx) > 2 else np.nan,
        })
    return pd.DataFrame(filas)


def transferencia(modelo, v: pd.DataFrame, rasgos: list[str]) -> pd.DataFrame:
    """Deja fuera un municipio entero, ajusta con los demás y mide si el orden
    predicho dentro del municipio dejado fuera se parece al del catastro. Es lo que
    tendría que valer para dar forma a un municipio sin tabla de valores."""
    filas = []
    for mun in v["municipio"].unique():
        fuera = v["municipio"] == mun
        if fuera.sum() < 20:
            continue
        m = ajustar(modelo, v.loc[~fuera, rasgos + ["municipio"]], v.loc[~fuera, "y"],
                    v.loc[~fuera, "bloque"])
        p = m.predict(v.loc[fuera, rasgos + ["municipio"]])
        filas.append({"municipio": mun, "agebs": int(fuera.sum()),
                      "spearman": float(spearmanr(v.loc[fuera, "y"], p).statistic)})
    return pd.DataFrame(filas)
