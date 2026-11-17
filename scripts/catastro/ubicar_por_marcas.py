# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pyproj"]
# ///
"""Etapa 4 del pipeline de valor catastral para planos con cuadrícula de
coordenadas: georreferencia cada hoja con las marcas UTM de sus bordes
("674500" arriba y abajo, "2295000" a los lados), sin emparejar calles. Sirve
para cualquier plano con cuadrícula UTM (Guadalajara 2026, Ixtlahuacán 2026).
Ver `docs/producto/dataset-vivienda.md`, MEDV.

    uv run --script scripts/catastro/ubicar_por_marcas.py ETIQUETAS.csv SALIDA_DIR --epsg 32613 \
        --este '6\\d{5}' --norte '2\\d{6}' --valores-validos 100,60000,10

Cada marca da una ecuación lineal. Con la hoja en (x, y) y la y hacia abajo,
una similitud (escala, giro, traslación) es

    E = a·x + b·y + tE        N = b·x − a·y + tN

así que las marcas de este y de norte juntas se resuelven por mínimos
cuadrados. Una marca mal leída por el OCR deja un residuo grande: se quita la
peor y se ajusta de nuevo mientras su residuo pase de `--tolerancia` metros.
Se acepta la hoja con al menos dos marcas de cada eje y error RMS bajo la
tolerancia. Mismas salidas que `ubicar_pdf_mapa.py` (hojas.csv y valores.csv).
"""
from __future__ import annotations

import argparse
import csv
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from pyproj import Transformer


def ajustar(marcas: list[tuple[str, float, float, float]], tolerancia: float):
    """marcas: (eje 'E' o 'N', x, y, valor). Devuelve (a, b, tE, tN, rms, usadas) o None."""
    marcas = list(marcas)
    while True:
        if sum(1 for m in marcas if m[0] == "E") < 2 or sum(1 for m in marcas if m[0] == "N") < 2:
            return None
        filas, obj = [], []
        for eje, x, y, v in marcas:
            filas.append([x, y, 1, 0] if eje == "E" else [-y, x, 0, 1])
            obj.append(v)
        sol, *_ = np.linalg.lstsq(np.array(filas, float), np.array(obj, float), rcond=None)
        residuos = np.abs(np.array(filas) @ sol - np.array(obj))
        peor = int(np.argmax(residuos))
        if residuos[peor] > tolerancia:
            marcas.pop(peor)  # una marca mal leída: fuera, y otra vuelta
            continue
        a, b, te, tn = sol
        return a, b, te, tn, float(np.sqrt(np.mean(residuos ** 2))), len(marcas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("etiquetas", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--epsg", type=int, required=True, help="UTM de la cuadrícula del plano")
    ap.add_argument("--este", required=True, help="expresión regular de una marca de este (zona 13 en Jalisco: 6\\d{5})")
    ap.add_argument("--norte", required=True, help="expresión regular de una marca de norte (2\\d{6})")
    ap.add_argument("--tolerancia", type=float, default=15, help="metros de residuo para descartar una marca")
    ap.add_argument("--valores-validos", default=None, help="mínimo,máximo,múltiplo de un valor plausible")
    ap.add_argument("--zona-desde-tamano", type=float, default=0)
    a = ap.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)

    por_hoja: dict[str, list[dict]] = defaultdict(list)
    with open(a.etiquetas, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            if fila["hoja"]:
                por_hoja[fila["hoja"]].append(fila)
    if a.valores_validos:
        vmin, vmax, mult = (float(v) for v in a.valores_validos.split(","))
        plausible = lambda v: vmin <= v <= vmax and v % mult == 0
    else:
        plausible = lambda v: True

    a_geo = Transformer.from_crs(a.epsg, 4326, always_xy=True)
    aceptadas = n_valores = descartados = 0
    with open(a.salida / "hojas.csv", "w", newline="", encoding="utf-8") as fh, \
         open(a.salida / "valores.csv", "w", newline="", encoding="utf-8") as fv:
        wh, wv = csv.writer(fh), csv.writer(fv)
        wh.writerow(["hoja", "pagina", "marcas_este", "marcas_norte", "marcas_usadas", "error_rms_m", "escala", "aceptada"])
        wv.writerow(["municipio", "anio", "pagina", "hoja", "valor_m2", "tamano", "clase", "lon", "lat"])
        for hoja, filas in sorted(por_hoja.items(), key=lambda kv: int(kv[1][0]["pagina"])):
            marcas = []
            for f in filas:
                t = f["texto"].strip().replace(" ", "")
                eje = "E" if re.fullmatch(a.este, t) else "N" if re.fullmatch(a.norte, t) else None
                if eje:
                    marcas.append((eje, float(f["x"]), float(f["y"]), float(t)))
            ne, nn = sum(1 for m in marcas if m[0] == "E"), sum(1 for m in marcas if m[0] == "N")
            ajuste = ajustar(marcas, a.tolerancia)
            if ajuste is None:
                wh.writerow([hoja, filas[0]["pagina"], ne, nn, 0, "", "", False])
                continue
            ca, cb, te, tn, rms, usadas = ajuste
            escala = math.hypot(ca, cb)
            wh.writerow([hoja, filas[0]["pagina"], ne, nn, usadas, round(rms, 2), round(escala, 4), True])
            aceptadas += 1
            for f in filas:
                if f["tipo"] != "valor":
                    continue
                v = float(f["valor_m2"])
                if not plausible(v):
                    descartados += 1
                    continue
                x, y = float(f["x"]), float(f["y"])
                lon, lat = a_geo.transform(ca * x + cb * y + te, cb * x - ca * y + tn)
                clase = "zona" if float(f["tamano"] or 0) >= a.zona_desde_tamano else "calle"
                wv.writerow([f["municipio"], f["anio"], f["pagina"], hoja, v, f["tamano"], clase, round(lon, 6), round(lat, 6)])
                n_valores += 1
    print(f"{aceptadas} de {len(por_hoja)} hojas con marcas suficientes; {n_valores} valores ubicados"
          + (f", {descartados} descartados por implausibles" if descartados else ""))


if __name__ == "__main__":
    main()
