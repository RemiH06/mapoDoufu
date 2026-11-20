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


def distribucion(v: pd.DataFrame) -> go.Figure:
    fig = px.box(v, x="municipio", y="medv", points="outliers", log_y=True,
                 title="Valor catastral de suelo por AGEB (escala logarítmica)")
    fig.update_layout(xaxis_title="", yaxis_title="$/m², pesos del año de la tabla")
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
