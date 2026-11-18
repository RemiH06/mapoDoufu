"""Taxonomía de rubros: qué rubros tienen un patrón parecido en una zona.

Aquí sí cabe k-means (docs/producto/buscador.md): se agrupan rubros, no
negocios, y cada rubro es un punto con tres rasgos de su patrón (patrones.py):

- **agrupacion:** log de la distancia media al vecino del rubro entre la de
  los sorteos. Negativo, se agrupa; positivo, se reparte.
- **plazas:** log de la parte del rubro en plaza o mercado entre la de todos.
- **junto_a:** log del mayor cociente de colocación con otro rubro (0 si no
  busca a ninguno más de lo esperado).

Los rasgos se estandarizan, k va de 2 a 6 y se queda el de mejor silueta. La
semilla es fija. El grupo describe; no recomienda nada (RNF5).

Se calcula con la CLI (`cli taxonomia`) y se guarda en `rubros/taxonomia.csv`:
es dato revisable y versionado, como la tabla de rubros, no algo en vivo.

Resultado en la zona metropolitana de Guadalajara: la silueta no pasa de 0.34
con ningún k de 2 a 8. Los rubros forman un continuo, no tipos, así que la
tabla sirve para análisis (el estudio de sobrevivencia la usa) y no se muestra
en el buscador (docs/producto/buscador.md, "Taxonomía de rubros").
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
from psycopg_pool import AsyncConnectionPool
from scipy.cluster.vq import kmeans2

from mapo_core import patrones, rubros

ARCHIVO = Path(__file__).parent / "rubros" / "taxonomia.csv"
RASGOS = ("agrupacion", "plazas", "junto_a")

# Con menos negocios en la zona, la distancia media depende de unos cuantos.
MIN_NEGOCIOS = 30
K_POSIBLES = range(2, 7)
INTENTOS = 20
SEMILLA = 18

COLUMNAS = [
    "cve_ent", "zona", "rubro", "negocios", "distancia_m", "al_azar_m", "parte_plazas",
    "parte_plazas_todos", "junto_a_rubro", "junto_a_cociente", *RASGOS, "grupo", "descripcion",
]


def rasgos(resultado: dict) -> dict[str, float]:
    a, pl = resultado["agrupacion"], resultado["plazas"]
    cociente = resultado["junto_a"][0]["cociente"] if resultado["junto_a"] else 1.0
    return {
        # +1 m y +1 punto porcentual: un rubro con todos en la misma coordenada
        # o sin ninguno en plaza no da log de cero.
        "agrupacion": math.log((a["distancia_m"] + 1) / (a["al_azar_m"] + 1)),
        "plazas": math.log((pl["rubro"] + 0.01) / (pl["todos"] + 0.01)) if pl else 0.0,
        "junto_a": math.log(cociente),
    }


def _silueta(x: np.ndarray, etiquetas: np.ndarray) -> float:
    d = np.sqrt(((x[:, None, :] - x[None, :, :]) ** 2).sum(-1))
    valores = []
    for i, e in enumerate(etiquetas):
        mismo = etiquetas == e
        if mismo.sum() < 2:
            valores.append(0.0)
            continue
        a = d[i, mismo].sum() / (mismo.sum() - 1)
        b = min(d[i, etiquetas == o].mean() for o in set(etiquetas.tolist()) if o != e)
        valores.append((b - a) / max(a, b))
    return float(np.mean(valores))


def agrupar(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """(etiquetas, centros en las unidades de `x`, silueta) del mejor k."""
    media, escala = x.mean(0), x.std(0)
    escala[escala == 0] = 1
    z = (x - media) / escala
    mejor = None
    for k in K_POSIBLES:
        if k >= len(x):
            break
        # kmeans2 corre una vez por llamada: se repite con semillas distintas y
        # se queda la de menor inercia, como el n_init de scikit-learn.
        corridas = []
        for s in range(INTENTOS):
            centros, etiquetas = kmeans2(z, k, minit="++", seed=SEMILLA + s)
            if len(set(etiquetas.tolist())) == k:
                corridas.append((((z - centros[etiquetas]) ** 2).sum(), centros, etiquetas))
        if not corridas:
            continue
        _, centros, etiquetas = min(corridas, key=lambda c: c[0])
        silueta = _silueta(z, etiquetas)
        if mejor is None or silueta > mejor[2]:
            mejor = (etiquetas, centros * escala + media, silueta)
    return mejor


def describir(centro: np.ndarray) -> str:
    """Nombre del grupo a partir de su centro, en palabras de la pantalla."""
    agrupacion, plazas, junto_a = (float(v) for v in centro)
    partes = [
        "se agrupa" if agrupacion < math.log(0.8) else "se reparte" if agrupacion > math.log(1.1) else "ni se agrupa ni se reparte"
    ]
    if plazas > math.log(1.5):
        partes.append("más en plazas y mercados")
    elif plazas < math.log(1 / 1.5):
        partes.append("poco en plazas y mercados")
    if junto_a > math.log(2):
        partes.append("junto a otros rubros")
    return ", ".join(partes).capitalize()


async def calcular(pool: AsyncConnectionPool, cve_ent: str, cve_muns: list[str], zona: str) -> tuple[list[dict], float]:
    """Una fila por rubro con al menos MIN_NEGOCIOS en la zona, y la silueta."""
    negocios = await patrones.negocios_del_recorte(pool, cve_ent, cve_muns)
    recorte = patrones.preparar(negocios)
    por_clase: dict[str, int] = {}
    for n in negocios:
        por_clase[n[2]] = por_clase.get(n[2], 0) + 1

    filas = []
    for clave in rubros.rubros():
        clases = rubros.clases_de(rubro=clave)
        if sum(por_clase.get(c, 0) for c in clases) < MIN_NEGOCIOS:
            continue
        r = patrones.analizar(negocios, clases, recorte)
        filas.append({
            "cve_ent": cve_ent,
            "zona": zona,
            "rubro": clave,
            "negocios": r["negocios"],
            "distancia_m": r["agrupacion"]["distancia_m"],
            "al_azar_m": r["agrupacion"]["al_azar_m"],
            "parte_plazas": r["plazas"]["rubro"] if r["plazas"] else "",
            "parte_plazas_todos": r["plazas"]["todos"] if r["plazas"] else "",
            "junto_a_rubro": r["junto_a"][0]["rubro"] if r["junto_a"] else "",
            "junto_a_cociente": r["junto_a"][0]["cociente"] if r["junto_a"] else "",
            **{k: round(v, 4) for k, v in rasgos(r).items()},
        })

    etiquetas, centros, silueta = agrupar(np.array([[f[k] for k in RASGOS] for f in filas]))
    # Grupos numerados del más agrupado al más repartido, para que el número
    # signifique algo al leer la tabla.
    orden = {g: i + 1 for i, g in enumerate(np.argsort(centros[:, 0]))}
    for f, e in zip(filas, etiquetas):
        f["grupo"] = orden[int(e)]
        f["descripcion"] = describir(centros[e])
    filas.sort(key=lambda f: (f["grupo"], f["agrupacion"]))
    return filas, silueta


def escribir(filas: list[dict], ruta: Path = ARCHIVO) -> None:
    """Reemplaza las filas del estado de `filas` y deja las de otros estados:
    una zona por estado."""
    estados = {f["cve_ent"] for f in filas}
    otras = []
    if ruta.exists():
        with open(ruta, encoding="utf-8", newline="") as f:
            otras = [fila for fila in csv.DictReader(f) if fila["cve_ent"] not in estados]
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(otras + filas)
