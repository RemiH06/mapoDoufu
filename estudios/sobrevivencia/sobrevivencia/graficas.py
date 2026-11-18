"""Gráficas del estudio con una sola plantilla, en la paleta de Mapo
(`mapo/assets/css/pieles.css`, tema claro)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

TINTA = "#12284D"
PAPEL = "#EEF1F4"
COMERCIO = "#2A6B3A"
DEMOGRAFIA = "#6B1A2A"
MOVILIDAD = "#C4691A"

pio.templates["mapo"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family="system-ui, sans-serif", color=TINTA, size=13),
        paper_bgcolor=PAPEL,
        plot_bgcolor=PAPEL,
        colorway=[COMERCIO, DEMOGRAFIA, MOVILIDAD, TINTA],
        xaxis=dict(gridcolor="#D5DBE3", zeroline=False),
        yaxis=dict(gridcolor="#D5DBE3", zeroline=False),
        margin=dict(l=60, r=20, t=60, b=50),
    )
)
pio.templates.default = "mapo"
# El JS de Plotly se carga del CDN al abrir el notebook: guardado pesa kilobytes,
# no megas por figura. GitHub no ejecuta ese JS; las cifras están en las tablas.
pio.renderers.default = "notebook_connected"


def barras_tasa(t: pd.DataFrame, x: str, titulo: str, eje_x: str) -> go.Figure:
    fig = px.bar(t, x=x, y="sigue", text="sigue", hover_data=["negocios"], title=titulo)
    fig.update_traces(texttemplate="%{text:.1f} %", textposition="outside", marker_color=COMERCIO)
    fig.update_layout(xaxis_title=eje_x, yaxis_title="Siguen en 2024 (%)", yaxis_range=[0, 100])
    return fig


def coeficientes(c: pd.DataFrame, etiquetas: dict[str, str], titulo: str) -> go.Figure:
    c = c.loc[[k for k in etiquetas if k in c.index]].iloc[::-1]
    fig = go.Figure(go.Scatter(
        x=c["puntos"], y=[etiquetas[k] for k in c.index], mode="markers",
        marker=dict(color=DEMOGRAFIA, size=9),
        error_x=dict(type="data", symmetric=False, array=c["hasta"] - c["puntos"],
                     arrayminus=c["puntos"] - c["desde"], color=DEMOGRAFIA),
    ))
    fig.add_vline(x=0, line_color=TINTA, line_width=1)
    fig.update_layout(title=titulo, xaxis_title="Puntos porcentuales de probabilidad de seguir (IC 95 %)",
                      yaxis_title="", height=120 + 32 * len(c))
    return fig


def calibracion(y: pd.Series, p: pd.Series, titulo: str, grupos: int = 10) -> go.Figure:
    t = pd.DataFrame({"y": y, "p": p}).dropna()
    t["decil"] = pd.qcut(t["p"], grupos, labels=False, duplicates="drop")
    t = t.groupby("decil").agg(predicho=("p", "mean"), observado=("y", "mean")).reset_index()
    fig = go.Figure([
        go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color="#9AA5B4", dash="dot"), name="Perfecta"),
        go.Scatter(x=t["predicho"], y=t["observado"], mode="lines+markers", line=dict(color=COMERCIO), name="Árboles"),
    ])
    fig.update_layout(title=titulo, xaxis_title="Probabilidad predicha (fuera de muestra)",
                      yaxis_title="Parte que siguió", xaxis_range=[0, 1], yaxis_range=[0, 1])
    return fig


def bosque(r: pd.DataFrame, clave: str, titulo: str) -> go.Figure:
    """Estimación e intervalo por estado, ordenados; en tinta los que no cruzan 0."""
    r = r.sort_values(f"{clave}_puntos")
    claro = (r[f"{clave}_desde"] > 0) | (r[f"{clave}_hasta"] < 0)
    fig = go.Figure(go.Scatter(
        x=r[f"{clave}_puntos"], y=r["nombre"], mode="markers",
        marker=dict(color=[DEMOGRAFIA if c else "#9AA5B4" for c in claro], size=8),
        error_x=dict(type="data", symmetric=False, array=r[f"{clave}_hasta"] - r[f"{clave}_puntos"],
                     arrayminus=r[f"{clave}_puntos"] - r[f"{clave}_desde"], color="#9AA5B4"),
    ))
    fig.add_vline(x=0, line_color=TINTA, line_width=1)
    fig.update_layout(title=titulo, xaxis_title="Puntos porcentuales (IC 95 %); en gris, los que cruzan 0",
                      yaxis_title="", height=140 + 22 * len(r))
    return fig
