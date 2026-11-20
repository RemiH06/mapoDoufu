"""Gráficas del estudio con una sola plantilla, en la paleta de Mapo
(`mapo/assets/css/pieles.css`, tema claro; la misma que el estudio de sobrevivencia)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

TINTA = "#12284D"
PAPEL = "#EEF1F4"
VERDE = "#2A6B3A"
VINO = "#6B1A2A"
NARANJA = "#C4691A"

pio.templates["mapo"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family="system-ui, sans-serif", color=TINTA, size=13),
        paper_bgcolor=PAPEL,
        plot_bgcolor=PAPEL,
        colorway=[VERDE, VINO, NARANJA, TINTA],
        xaxis=dict(gridcolor="#D5DBE3", zeroline=False),
        yaxis=dict(gridcolor="#D5DBE3", zeroline=False),
        margin=dict(l=60, r=20, t=60, b=50),
    )
)
pio.templates.default = "mapo"
# El JS de Plotly se carga del CDN al abrir el notebook. GitHub no lo ejecuta; las
# cifras quedan también en las tablas.
pio.renderers.default = "notebook_connected"


def distribucion(v: pd.DataFrame, titulo: str = "Valor catastral de suelo por AGEB (escala logarítmica)",
                 unidad: str = "$/m², pesos del año de la tabla") -> go.Figure:
    fig = px.box(v, x="municipio", y="medv", points="outliers", log_y=True, title=titulo)
    fig.update_layout(xaxis_title="", yaxis_title=unidad)
    return fig


def comparacion(t: pd.DataFrame) -> go.Figure:
    fig = px.bar(t, x="municipio", y="rmse_log", color="modelo", barmode="group",
                 title="Error fuera de muestra por bloques (RMSE de log(valor))")
    fig.update_layout(xaxis_title="", yaxis_title="RMSE en log (0.2 ≈ 20 % de error típico)")
    return fig


def observado_contra_predicho(y: pd.Series, p: pd.Series, municipio: pd.Series, titulo: str) -> go.Figure:
    t = pd.DataFrame({"catastro": np.exp(y), "predicho": np.exp(p), "municipio": municipio})
    fig = px.scatter(t, x="catastro", y="predicho", color="municipio", log_x=True, log_y=True,
                     opacity=0.6, title=titulo)
    lim = [t[["catastro", "predicho"]].min().min(), t[["catastro", "predicho"]].max().max()]
    fig.add_trace(go.Scatter(x=lim, y=lim, mode="lines", line=dict(color="#9AA5B4", dash="dot"),
                             name="Igual", showlegend=False))
    fig.update_layout(xaxis_title="Catastro ($/m²)", yaxis_title="Predicho fuera de muestra ($/m²)")
    return fig


def cobertura(t: pd.DataFrame, nominal: float) -> go.Figure:
    fig = px.bar(t, x="municipio", y="cobertura", color="metodo", barmode="group",
                 title=f"Cobertura medida en AGEB no vistas (nominal {nominal:.0%})")
    fig.add_hline(y=nominal, line_color=TINTA, line_dash="dot")
    fig.update_layout(xaxis_title="", yaxis_title="Parte del catastro dentro del rango",
                      yaxis_tickformat=".0%", yaxis_range=[0, 1])
    return fig


def mapa_ancho(r: pd.DataFrame, v: pd.DataFrame) -> go.Figure:
    t = r.join(v[["lon", "lat"]])
    fig = px.scatter(t, x="lon", y="lat", color=np.log2(t["razon_ancho"]),
                     color_continuous_scale="Cividis", opacity=0.8,
                     title="Ancho del rango por AGEB (log₂ de alto entre bajo)")
    fig.update_yaxes(scaleanchor="x", scaleratio=1 / np.cos(np.deg2rad(20.67)))
    fig.update_layout(xaxis_title="Longitud", yaxis_title="Latitud",
                      coloraxis_colorbar_title="log₂(alto/bajo)", height=600)
    return fig


# Modelos interpretables (modelos.ipynb) ---------------------------------------------

FAMILIAS = {"clase": VERDE, "extra": NARANJA, "red": VINO, "referencia": "#9AA5B4"}


def correlaciones(base: pd.DataFrame, rasgos: list[str], n: int = 20) -> go.Figure:
    t = base[rasgos].corrwith(base["y"], method="spearman").dropna()
    t = t.reindex(t.abs().sort_values().index)[-n:]
    fig = px.bar(x=t.values, y=t.index, orientation="h",
                 color=np.where(t.values > 0, "Sube el valor", "Baja el valor"),
                 color_discrete_map={"Sube el valor": VERDE, "Baja el valor": VINO},
                 title=f"Correlación de Spearman con log(valor), los {n} rasgos más fuertes")
    fig.update_layout(xaxis_title="ρ de Spearman", yaxis_title="", legend_title="", height=600)
    return fig


def qq(residuos: pd.Series, titulo: str) -> go.Figure:
    from scipy import stats
    r = np.sort((residuos - residuos.mean()) / residuos.std())
    teo = stats.norm.ppf((np.arange(1, len(r) + 1) - 0.5) / len(r))
    fig = go.Figure([go.Scatter(x=teo, y=r, mode="markers", marker=dict(color=VERDE, size=4),
                                name="Residuos"),
                     go.Scatter(x=[-3.5, 3.5], y=[-3.5, 3.5], mode="lines",
                                line=dict(color=TINTA, dash="dot"), name="Normal")])
    fig.update_layout(title=titulo, xaxis_title="Cuantil normal teórico",
                      yaxis_title="Residuo estandarizado", showlegend=False)
    return fig


def coeficientes(t: pd.DataFrame, titulo: str) -> go.Figure:
    t = t.iloc[::-1]
    a = lambda c: 100 * (np.exp(t[c]) - 1)  # noqa: E731
    fig = go.Figure(go.Scatter(
        x=t["cambio_pct"], y=t.index, mode="markers", marker=dict(color=VERDE, size=8),
        error_x=dict(type="data", symmetric=False, array=a("alto") - t["cambio_pct"],
                     arrayminus=t["cambio_pct"] - a("bajo"), color=TINTA)))
    fig.add_vline(x=0, line_color="#9AA5B4")
    fig.update_layout(title=titulo, height=max(400, 22 * len(t)), yaxis_title="",
                      xaxis_title="% de cambio del valor por una desviación estándar (IC 95 %)")
    return fig


def varianza(var: pd.Series) -> go.Figure:
    fig = px.line(x=var.index, y=var.values, markers=True,
                  title="Varianza explicada acumulada por los componentes principales")
    fig.add_hline(y=0.8, line_color=TINTA, line_dash="dot")
    fig.update_layout(xaxis_title="Componentes", yaxis_title="Varianza acumulada",
                      yaxis_tickformat=".0%")
    return fig


def mapa_calor(t: pd.DataFrame, titulo: str, etiqueta: str) -> go.Figure:
    fig = px.imshow(t, color_continuous_scale="RdBu_r", color_continuous_midpoint=0,
                    aspect="auto", title=titulo)
    fig.update_layout(height=max(450, 18 * len(t)), coloraxis_colorbar_title=etiqueta)
    return fig


def modelos_juntos(t: pd.DataFrame, familias: dict[str, str]) -> go.Figure:
    t = t.assign(familia=t["modelo"].map(familias))
    fig = px.scatter(t, x="rmse_log", y="spearman", color="familia", text="modelo",
                     color_discrete_map=FAMILIAS,
                     title="Todos los modelos fuera de muestra: error contra orden")
    fig.update_traces(textposition="top center", marker_size=10)
    fig.update_layout(xaxis_title="RMSE en log (menos es mejor)",
                      yaxis_title="Spearman (más es mejor)", height=550)
    return fig
