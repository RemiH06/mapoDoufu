"""Rangos con predicción conformal partida, calibrada por bloques espaciales.

Dos formas de dar ancho local (docs/producto/precio-estimado.md):

- `normalizado`: |y - ŷ| / σ̂, donde σ̂ es un bosque que predice el tamaño del
  error fuera de muestra. El rango es ŷ ± q·σ̂.
- `cqr`: regresión cuantílica conformalizada. Dos boosting de cuantiles dan el
  borde bajo y alto; la calibración los abre o cierra en q.

En los dos, q es el cuantil ⌈(n+1)(1-α)⌉/n de los puntajes de calibración.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, KFold, ShuffleSplit
from sklearn.pipeline import make_pipeline

from . import modelos


def cuantil_conformal(puntajes: np.ndarray, alfa: float) -> float:
    n = len(puntajes)
    nivel = min(1.0, np.ceil((n + 1) * (1 - alfa)) / n)
    return float(np.quantile(puntajes, nivel, method="higher"))


class Normalizado:
    """ŷ del modelo dado; σ̂ ajustado a |residuo| fuera de muestra. Con
    `escala="bosque"`, un bosque; con `"lineal"`, una ridge sobre log|residuo|
    (interpretable: cada coeficiente dice qué rasgo abre o cierra el rango)."""

    def __init__(self, modelo, rasgos: list[str], escala: str = "bosque"):
        self.modelo, self.rasgos, self.escala = modelo, rasgos, escala

    def ajustar(self, X, y, grupos):
        self.m = modelos.ajustar(self.modelo, X, y, grupos)
        res = (y - modelos.fuera_de_muestra(self.modelo, X, y, grupos, 4)).abs()
        if self.escala == "lineal":
            self.s = make_pipeline(modelos._columnas(self.rasgos, True),
                                   RidgeCV(alphas=np.logspace(-1, 3, 20)))
            self.s.fit(X, np.log(res + 1e-3))
        else:
            self.s = make_pipeline(modelos._columnas(self.rasgos, False), RandomForestRegressor(
                n_estimators=300, min_samples_leaf=10, random_state=modelos.SEMILLA, n_jobs=-1))
            self.s.fit(X, res)
        return self

    def centro_y_escala(self, X):
        s = self.s.predict(X)
        s = np.exp(s) if self.escala == "lineal" else s
        return self.m.predict(X), np.maximum(s, 1e-3)

    def puntaje(self, X, y):
        c, s = self.centro_y_escala(X)
        return np.abs(y - c) / s

    def rango(self, X, q):
        c, s = self.centro_y_escala(X)
        return c, c - q * s, c + q * s


class CQR:
    """Bordes de boosting de cuantiles en α/2 y 1 - α/2."""

    def __init__(self, rasgos: list[str], alfa: float):
        base = make_pipeline(modelos._columnas(rasgos, False), HistGradientBoostingRegressor(
            loss="quantile", max_iter=300, learning_rate=0.04, min_samples_leaf=20,
            random_state=modelos.SEMILLA))
        self.bajo = clone(base).set_params(histgradientboostingregressor__quantile=alfa / 2)
        self.alto = clone(base).set_params(histgradientboostingregressor__quantile=1 - alfa / 2)
        self.medio = clone(base).set_params(histgradientboostingregressor__quantile=0.5)

    def ajustar(self, X, y, grupos):
        for m in (self.bajo, self.alto, self.medio):
            m.fit(X, y)
        return self

    def puntaje(self, X, y):
        return np.maximum(self.bajo.predict(X) - y, y - self.alto.predict(X))

    def rango(self, X, q):
        return self.medio.predict(X), self.bajo.predict(X) - q, self.alto.predict(X) + q


def evaluar(fabrica, v: pd.DataFrame, rasgos: list[str], alfa: float,
            espacial: bool = True, particiones: int = 5, parte_cal: float = 0.3) -> pd.DataFrame:
    """Cobertura y ancho medidos en AGEB que ni el ajuste ni la calibración vieron.

    Afuera: particiones por bloques (o al azar si `espacial` es False, para ver
    cuánto promete de más). Adentro: lo que queda se parte otra vez, por bloques o
    al azar, en ajuste y calibración.
    """
    X, y, g = v[rasgos + ["municipio"]], v["y"], v["bloque"]
    if espacial:
        afuera = GroupKFold(particiones).split(X, y, g)
        adentro = GroupShuffleSplit(1, test_size=parte_cal, random_state=modelos.SEMILLA)
    else:
        afuera = KFold(particiones, shuffle=True, random_state=modelos.SEMILLA).split(X)
        adentro = ShuffleSplit(1, test_size=parte_cal, random_state=modelos.SEMILLA)
    salida = []
    for entreno, prueba in afuera:
        Xe, ye, ge = X.iloc[entreno], y.iloc[entreno], g.iloc[entreno]
        aj, cal = next(adentro.split(Xe, ye, ge))
        m = fabrica().ajustar(Xe.iloc[aj], ye.iloc[aj], ge.iloc[aj])
        q = cuantil_conformal(m.puntaje(Xe.iloc[cal], ye.iloc[cal].to_numpy()), alfa)
        c, lo, hi = m.rango(X.iloc[prueba], q)
        salida.append(pd.DataFrame({"centro": c, "bajo": lo, "alto": hi}, index=X.index[prueba]))
    r = pd.concat(salida).loc[v.index]
    r["y"], r["municipio"] = y, v["municipio"]
    r["dentro"] = (r["y"] >= r["bajo"]) & (r["y"] <= r["alto"])
    r["razon_ancho"] = np.exp(r["alto"] - r["bajo"])  # alto / bajo en pesos
    return r


def resumen(r: pd.DataFrame) -> pd.DataFrame:
    def fila(t, nombre):
        return {"municipio": nombre, "agebs": len(t), "cobertura": t["dentro"].mean(),
                "alto_entre_bajo_mediana": t["razon_ancho"].median()}
    filas = [fila(r, "Todos")] + [fila(t, m) for m, t in r.groupby("municipio")]
    return pd.DataFrame(filas)
