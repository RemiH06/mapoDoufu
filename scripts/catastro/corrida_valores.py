# /// script
# requires-python = ">=3.11"
# ///
"""Extrae la "corrida de valores" (Formato 06 de los expedientes de tablas de
valores de Jalisco) a una muestra de validación: un renglón por predio con su
fraccionamiento, su valor unitario de terreno y el año (vigente o propuesto).

La corrida no cubre el municipio: son unas decenas de predios de ejemplo. Sirve
para medir el error de predicción de `suelo_m2` (el `medv` hasta la v7) donde no hay tabla ubicada
(docs/producto/dataset-vivienda.md, "Para modelar").

    uv run --script scripts/catastro/corrida_valores.py ETIQUETAS_OCR.csv SALIDA.csv --paginas 82-86

Entrada: las etiquetas de `extraer_pdf_raster.py --valor-con-signo` sobre las
páginas de la corrida. Las columnas se encuentran por su encabezado ("Valor
unitario", "Observaciones"); la tabla de cada año, por el número de año que va
sobre ella. Cada valor se empareja con el texto de la columna de observaciones
más cercano en altura.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("etiquetas")
    ap.add_argument("salida")
    ap.add_argument("--paginas", required=True, help="rango, p. ej. 82-86")
    ap.add_argument("--tolerancia", type=float, default=40, help="px de diferencia en altura para emparejar")
    a = ap.parse_args()
    desde, hasta = (int(v) for v in a.paginas.split("-"))

    with open(a.etiquetas, encoding="utf-8") as f:
        todas = [r for r in csv.DictReader(f) if r["pagina"] and desde <= int(r["pagina"]) <= hasta]
    salida = []
    for pagina in sorted({int(r["pagina"]) for r in todas}):
        filas = [r for r in todas if int(r["pagina"]) == pagina]
        col_valor = [float(r["x"]) for r in filas if re.search(r"(?i)valor\s*unitario", r["texto"])]
        col_obs = [float(r["x"]) for r in filas if re.search(r"(?i)observaciones", r["texto"])]
        if not col_valor or not col_obs:
            continue
        xv, xo = sum(col_valor) / len(col_valor), sum(col_obs) / len(col_obs)
        anios = sorted((float(r["y"]), int(r["texto"])) for r in filas if re.fullmatch(r"20\d\d", r["texto"].strip()))
        nombres = [r for r in filas if abs(float(r["x"]) - xo) < 250 and not re.search(r"(?i)observaciones", r["texto"])]
        for r in filas:
            if r["tipo"] != "valor" or abs(float(r["x"]) - xv) > 80:
                continue
            y = float(r["y"])
            cerca = min(nombres, key=lambda n: abs(float(n["y"]) - y), default=None)
            if cerca is None or abs(float(cerca["y"]) - y) > a.tolerancia:
                continue
            anio = next((an for ya, an in reversed(anios) if ya < y), None)
            salida.append({"municipio": r["municipio"], "pagina": pagina, "anio": anio,
                           "fraccionamiento": cerca["texto"].strip(), "valor_m2": r["valor_m2"]})
    with open(a.salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["municipio", "pagina", "anio", "fraccionamiento", "valor_m2"])
        w.writeheader()
        w.writerows(salida)
    print(f"{len(salida)} predios en {a.salida}")


if __name__ == "__main__" and (len(sys.argv) < 2 or sys.argv[1] != "ubicar"):
    main()


# --- Ubicación aproximada de la muestra -------------------------------------------
# `uv run --script scripts/catastro/corrida_valores.py ubicar CORRIDA.csv OSM_NOMBRES.json SALIDA.csv --anio 2026`
# OSM_NOMBRES.json: Overpass `nwr["name"~"<nombres>",i](caja); out center tags;`.
# Regla fija por fraccionamiento: primero un lugar, zona residencial, comunidad o
# club con su nombre; si no hay, la mediana de las calles con su nombre. Es una
# ubicación aproximada (cientos de metros): sirve para saber en qué AGEB cae, no
# para medir distancias. Los parques industriales se omiten (no son vivienda).
import json
import statistics
import sys
import unicodedata


def _llave(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().upper()
    t = re.sub(r"\b(FRACCIONAMIENTO|FRACC|COTO|CASA CLUB|AVENIDA|AV|BOULEVARD|BLVD|CALLE|PRIVADA|GLORIETA)\b", " ", t)
    return re.sub(r"[^A-Z0-9]", "", t)


def ubicar(corrida: str, osm: str, salida: str, anio: int) -> None:
    elementos = json.load(open(osm, encoding="utf-8"))["elements"]
    filas = [r for r in csv.DictReader(open(corrida, encoding="utf-8")) if r["anio"] == str(anio)]
    ubicadas = []
    for r in filas:
        clave = _llave(r["fraccionamiento"])
        if "INDUS" in clave or len(clave) < 5:
            continue
        candidatos = [e for e in elementos if _llave(e.get("tags", {}).get("name", "")) == clave]
        lugares = [e for e in candidatos if "highway" not in e.get("tags", {})]
        usados = lugares[:1] or [e for e in candidatos if "highway" in e.get("tags", {})]
        if not usados:
            continue
        pts = [(e.get("center") or e)["lon"] for e in usados], [(e.get("center") or e)["lat"] for e in usados]
        ubicadas.append({**r, "lon": round(statistics.median(pts[0]), 6), "lat": round(statistics.median(pts[1]), 6),
                         "ubicacion": ("lugar " if lugares else "calles ") + usados[0].get("tags", {}).get("name", "")})
    with open(salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]) + ["lon", "lat", "ubicacion"])
        w.writeheader()
        w.writerows(ubicadas)
    print(f"{len(ubicadas)} de {len(filas)} predios de {anio} ubicados (aproximados) en {salida}")


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "ubicar":
    ap = argparse.ArgumentParser()
    ap.add_argument("ubicar"); ap.add_argument("corrida"); ap.add_argument("osm"); ap.add_argument("salida")
    ap.add_argument("--anio", type=int, required=True)
    x = ap.parse_args()
    ubicar(x.corrida, x.osm, x.salida, x.anio)
