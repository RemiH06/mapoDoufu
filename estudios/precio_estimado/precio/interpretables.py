"""Modelos interpretables para la forma del precio, en el orden de los temas de
Análisis Estadístico Multivariado, más tres de fuera del temario (aditivo con
splines, árbol y modelo mixto), una red chica y dos referencias de caja negra.

Todos reciben un DataFrame con los rasgos y `municipio`, y pasan por la misma
validación por bloques de `modelos.fuera_de_muestra`.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from sklearn.base import BaseEstimator, RegressorMixin, TransformerMixin
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LassoCV, LinearRegression, LogisticRegression, RidgeCV
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, SplineTransformer, StandardScaler
from sklearn.tree import DecisionTreeRegressor
from statsmodels.stats.outliers_influence import variance_inflation_factor

from .modelos import SEMILLA, _columnas, catalogo as catalogo_caja_negra


def _numericas(*pasos) -> list:
    return [SimpleImputer(strategy="median"), StandardScaler(), *pasos]


def _con_municipio(rasgos: list[str], *pasos) -> ColumnTransformer:
    return ColumnTransformer([
        ("num", make_pipeline(*_numericas(*pasos)), rasgos),
        ("mun", OneHotEncoder(handle_unknown="ignore"), ["municipio"]),
    ])


def _por_bloques(modelo, rejilla: dict) -> GridSearchCV:
    return GridSearchCV(modelo, rejilla, cv=GroupKFold(4), scoring="neg_root_mean_squared_error")


class Tipos(BaseEstimator, TransformerMixin):
    """k-medias sobre los rasgos estandarizados; sale el tipo de zona en one-hot."""

    def __init__(self, k: int = 6):
        self.k = k

    def fit(self, Z, y=None):
        self.km_ = KMeans(self.k, n_init=10, random_state=SEMILLA).fit(Z)
        return self

    def transform(self, Z):
        return np.eye(self.k)[self.km_.predict(Z)]


class Pasos(BaseEstimator, RegressorMixin):
    """OLS con selección hacia adelante por BIC. El municipio entra siempre, como
    intercepto propio (ANCOVA de pendientes paralelas)."""

    def __init__(self, rasgos: list[str], maximo: int = 30):
        self.rasgos, self.maximo = rasgos, maximo

    def _matriz(self, X, cols):
        Z = pd.DataFrame(self.prep_.transform(X[self.rasgos]), columns=self.rasgos, index=X.index)
        D = pd.get_dummies(X["municipio"]).reindex(columns=self.muns_, fill_value=0).astype(float)
        return pd.concat([D, Z[cols]], axis=1)

    def fit(self, X, y):
        self.prep_ = make_pipeline(*_numericas()).fit(X[self.rasgos])
        self.muns_ = sorted(X["municipio"].unique())
        y = np.asarray(y)
        elegidos, bic = [], sm.OLS(y, self._matriz(X, [])).fit().bic
        while len(elegidos) < self.maximo:
            prueba = {c: sm.OLS(y, self._matriz(X, elegidos + [c])).fit().bic
                      for c in self.rasgos if c not in elegidos}
            mejor = min(prueba, key=prueba.get)
            if prueba[mejor] >= bic:
                break
            elegidos.append(mejor)
            bic = prueba[mejor]
        self.elegidos_ = elegidos
        self.res_ = sm.OLS(y, self._matriz(X, elegidos)).fit()
        return self

    def predict(self, X):
        return self.res_.predict(self._matriz(X, self.elegidos_)).to_numpy()


class Mixto(BaseEstimator, RegressorMixin):
    """Modelo lineal mixto: pendientes comunes y un intercepto aleatorio por
    municipio. Un municipio que no vio queda con efecto 0 (la media)."""

    def __init__(self, rasgos: list[str]):
        self.rasgos = rasgos

    def _matriz(self, X):
        return sm.add_constant(self.prep_.transform(X[self.rasgos]), has_constant="add")

    def fit(self, X, y):
        self.prep_ = make_pipeline(*_numericas()).fit(X[self.rasgos])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.res_ = sm.MixedLM(np.asarray(y), self._matriz(X),
                                   groups=X["municipio"].to_numpy()).fit(reml=True)
        self.efectos_ = {k: float(v.iloc[0]) for k, v in self.res_.random_effects.items()}
        return self

    def predict(self, X):
        fijo = self._matriz(X) @ np.asarray(self.res_.fe_params)
        return fijo + X["municipio"].map(self.efectos_).fillna(0.0).to_numpy()


def catalogo(rasgos: list[str]) -> dict[str, tuple[str, object]]:
    """Nombre → (familia, modelo). Familia: `clase` (temario de AEM), `extra`
    (interpretable, fuera del temario), `red` o `referencia` (caja negra)."""
    lineal = lambda *p: make_pipeline(_con_municipio(rasgos, *p), LinearRegression())  # noqa: E731
    negra = catalogo_caja_negra(rasgos)
    return {
        "OLS (ANCOVA)": ("clase", lineal()),
        "Pasos BIC": ("clase", Pasos(rasgos)),
        "Lasso": ("clase", make_pipeline(_columnas(rasgos, True), LassoCV(cv=5, random_state=SEMILLA))),
        "PCR": ("clase", _por_bloques(lineal(PCA()), {
            "columntransformer__num__pca__n_components": [3, 5, 8, 12, 20]})),
        "Tipos k-medias": ("clase", _por_bloques(lineal(Tipos()), {
            "columntransformer__num__tipos__k": [4, 6, 8, 12]})),
        "Aditivo (splines)": ("extra", make_pipeline(
            _con_municipio(rasgos, SplineTransformer(n_knots=4, degree=3)),
            RidgeCV(alphas=np.logspace(-1, 3, 20)))),
        "Árbol": ("extra", _por_bloques(
            make_pipeline(_columnas(rasgos, False),
                          DecisionTreeRegressor(min_samples_leaf=20, random_state=SEMILLA)),
            {"decisiontreeregressor__max_depth": [3, 4, 5, 6]})),
        "Mixto": ("extra", Mixto(rasgos)),
        "Red (32-16)": ("red", TransformedTargetRegressor(
            regressor=make_pipeline(_columnas(rasgos, True), MLPRegressor(
                hidden_layer_sizes=(32, 16), alpha=1e-2, early_stopping=True, max_iter=3000,
                random_state=SEMILLA)),
            transformer=StandardScaler())),
        "SVR": ("referencia", negra["SVR"]),
        "Bosque": ("referencia", negra["Bosque"]),
    }


# Tablas para leer los modelos ------------------------------------------------------

def estandarizar(base: pd.DataFrame, rasgos: list[str]) -> pd.DataFrame:
    z = make_pipeline(*_numericas()).fit_transform(base[rasgos])
    return pd.DataFrame(z, columns=rasgos, index=base.index).assign(
        y=base["y"], municipio=base["municipio"], bloque=base["bloque"])


def ols(base: pd.DataFrame, rasgos: list[str]):
    """OLS de log(valor) con rasgos estandarizados y municipio como factor.
    Errores estándar agrupados por bloque de 3 km: las AGEB vecinas no son
    observaciones independientes."""
    z = estandarizar(base, rasgos)
    formula = "y ~ C(municipio) + " + " + ".join(rasgos)
    return smf.ols(formula, z).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(z["bloque"])[0]})


def coeficientes(res, rasgos: list[str]) -> pd.DataFrame:
    """Coeficiente como % de cambio del valor por una desviación estándar."""
    ic = res.conf_int()
    t = pd.DataFrame({"coef": res.params, "bajo": ic[0], "alto": ic[1], "p": res.pvalues}).loc[rasgos]
    t["cambio_pct"] = 100 * (np.exp(t["coef"]) - 1)
    return t.sort_values("coef", key=np.abs, ascending=False)


def vif(base: pd.DataFrame, rasgos: list[str]) -> pd.Series:
    z = sm.add_constant(estandarizar(base, rasgos)[rasgos])
    return pd.Series([variance_inflation_factor(z.values, i + 1) for i in range(len(rasgos))],
                     index=rasgos, name="vif").sort_values(ascending=False)


def anova_municipio(base: pd.DataFrame, rasgos: list[str]) -> dict[str, pd.DataFrame]:
    """ANOVA de una vía (solo municipio), ANCOVA (municipio + covariables) y la
    prueba de pendientes paralelas para la primera covariable."""
    z = estandarizar(base, rasgos)
    cov = " + ".join(rasgos)
    una = smf.ols("y ~ C(municipio)", z).fit()
    ancova = smf.ols(f"y ~ C(municipio) + {cov}", z).fit()
    inter = smf.ols(f"y ~ C(municipio) * {rasgos[0]} + {cov}", z).fit()
    tabla_una = sm.stats.anova_lm(una, typ=2)
    eta2 = tabla_una.loc["C(municipio)", "sum_sq"] / tabla_una["sum_sq"].sum()
    return {
        "una_via": tabla_una.assign(eta2=[eta2, np.nan]),
        "ancova": sm.stats.anova_lm(ancova, typ=2),
        "pendientes": sm.stats.anova_lm(ancova, inter),
    }


def pca(base: pd.DataFrame, rasgos: list[str], n: int = 3) -> tuple[pd.Series, pd.DataFrame]:
    """Varianza explicada acumulada y cargas de los primeros `n` componentes."""
    p = PCA().fit(estandarizar(base, rasgos)[rasgos])
    var = pd.Series(np.cumsum(p.explained_variance_ratio_), index=range(1, len(rasgos) + 1),
                    name="varianza_acumulada")
    cargas = pd.DataFrame(p.components_[:n].T, index=rasgos, columns=[f"CP{i + 1}" for i in range(n)])
    return var, cargas


def tipos(base: pd.DataFrame, rasgos: list[str], k: int) -> tuple[pd.Series, pd.DataFrame]:
    """Tipo de zona por k-medias y su perfil: media estandarizada de cada rasgo y
    valor mediano del catastro."""
    z = estandarizar(base, rasgos)
    etiqueta = pd.Series(KMeans(k, n_init=10, random_state=SEMILLA).fit_predict(z[rasgos]),
                         index=base.index, name="tipo")
    perfil = z[rasgos].groupby(etiqueta).mean().T
    return etiqueta, perfil


def logistica(base: pd.DataFrame, rasgos: list[str]) -> tuple[pd.DataFrame, float]:
    """¿Qué hace que una AGEB esté por arriba de la mediana de su municipio?
    Razones de momios por desviación estándar (statsmodels) y AUC fuera de muestra
    por bloques (scikit-learn, mismos rasgos)."""
    z = estandarizar(base, rasgos)
    z["cara"] = (base["y"] > base.groupby("municipio")["y"].transform("median")).astype(int)
    res = smf.logit("cara ~ " + " + ".join(rasgos), z).fit(
        disp=0, cov_type="cluster", cov_kwds={"groups": pd.factorize(z["bloque"])[0]})
    ic = np.exp(res.conf_int())
    momios = pd.DataFrame({"razon_momios": np.exp(res.params), "bajo": ic[0], "alto": ic[1],
                           "p": res.pvalues}).loc[rasgos].sort_values("razon_momios")
    prob = pd.Series(np.nan, index=z.index)
    for a, b in GroupKFold(5).split(z, z["cara"], z["bloque"]):
        m = LogisticRegression(max_iter=2000).fit(z.iloc[a][rasgos], z.iloc[a]["cara"])
        prob.iloc[b] = m.predict_proba(z.iloc[b][rasgos])[:, 1]
    return momios, float(roc_auc_score(z["cara"], prob))


def coef_lasso(ajustado) -> pd.DataFrame:
    """Coeficientes distintos de cero de una Lasso ya ajustada, como % de cambio
    del valor por una desviación estándar (los municipios aparte)."""
    nombres = [n.split("__", 1)[1] for n in ajustado[0].get_feature_names_out()]
    c = pd.Series(ajustado[-1].coef_, index=nombres)
    c = c[(c != 0) & ~c.index.str.startswith("municipio_")]
    t = pd.DataFrame({"coef": c, "cambio_pct": 100 * (np.exp(c) - 1)})
    return t.sort_values("coef", key=np.abs, ascending=False)


def reglas_arbol(ajustado, rasgos: list[str]) -> str:
    """Reglas del mejor árbol de la búsqueda, en texto (valores en log)."""
    from sklearn.tree import export_text
    pipe = ajustado.best_estimator_
    nombres = [n.split("__", 1)[1] for n in pipe[0].get_feature_names_out()]
    return export_text(pipe[-1], feature_names=nombres, decimals=2)
