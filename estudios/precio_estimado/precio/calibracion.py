"""Calibrar contra un promedio oficial (benchmarking de áreas pequeñas).

Escenario: un municipio sin precio por AGEB, pero con una cifra municipal (la
mediana de anuncios del IIEG). Se deja fuera el municipio entero, se predicen
sus AGEB con un modelo ajustado en los demás y se mide:

1. Sin calibrar: qué tan lejos queda la mediana predicha del municipio de la
   cifra oficial, y el error por AGEB contra el precio observado.
2. Calibrado: se mueve el nivel (el intercepto del municipio, en log) para que
   la mediana predicha iguale la oficial, y se vuelve a medir por AGEB.

La forma (el orden entre AGEB) no cambia al calibrar: solo el nivel.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import modelos


def mediana_ponderada(valores: np.ndarray, pesos: np.ndarray) -> float:
    orden = np.argsort(valores)
    v, w = np.asarray(valores)[orden], np.asarray(pesos)[orden]
    acumulado = np.cumsum(w)
    return float(v[np.searchsorted(acumulado, acumulado[-1] / 2)])


def municipio_fuera(modelo, base: pd.DataFrame, todas: pd.DataFrame, rasgos: list[str],
                    oficial: pd.Series, ponderar: str = "viv_hab") -> pd.DataFrame:
    """Una fila por municipio dejado fuera.

    `oficial`: mediana municipal oficial en pesos, indexada por nombre de
    municipio. La mediana predicha del municipio sale de todas sus AGEB de
    `todas` (también las que no tienen anuncios), pesadas por `ponderar`:
    `viv_hab` es lo único que habría en un municipio sin datos; `medv_n` imita a
    la cifra oficial, que es una mediana de anuncios, pero solo existe donde hay
    anuncios (sirve de cota de lo mejor posible).
    """
    filas = []
    for mun in base["municipio"].unique():
        dentro = base["municipio"] == mun
        m = modelos.ajustar(modelo, base.loc[~dentro, rasgos + ["municipio"]], base.loc[~dentro, "y"],
                            base.loc[~dentro, "bloque"])
        obs = base.loc[dentro]
        pred_obs = m.predict(obs[rasgos + ["municipio"]])
        suyas = todas[todas["municipio"] == mun]
        predicha = mediana_ponderada(np.exp(m.predict(suyas[rasgos + ["municipio"]])),
                                     suyas[ponderar].fillna(0).to_numpy())
        cifra = float(oficial[mun])
        corrimiento = np.log(cifra) - np.log(predicha)
        rmse = lambda p: float(np.sqrt(np.mean((obs["y"] - p) ** 2)))  # noqa: E731
        filas.append({
            "municipio": mun, "agebs": int(dentro.sum()),
            "oficial": round(cifra), "predicha_sin_calibrar": round(predicha),
            "error_nivel_pct": 100 * (predicha / cifra - 1),
            "rmse_log_sin_calibrar": rmse(pred_obs),
            "rmse_log_calibrado": rmse(pred_obs + corrimiento),
            "rmse_log_con_su_mediana": rmse(np.full(len(obs), obs["y"].median())),
            "agebs_sin_precio": int(((todas["municipio"] == mun) & todas["y"].isna()).sum()),
        })
    return pd.DataFrame(filas)
