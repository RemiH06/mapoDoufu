# /// script
# requires-python = ">=3.11"
# dependencies = ["pymupdf"]
# ///
"""Etapa 3 del pipeline de valor catastral, adaptador `pdf_mapa`: saca de un
PDF de tablas de valores dibujado como mapa cada texto útil con su posición en
la hoja. Ver `docs/producto/dataset-vivienda.md`, sección MEDV.

    uv run --script scripts/catastro/extraer_pdf_mapa.py PDF SALIDA.csv --municipio 14039 --anio 2020

Salida `etiquetas`, una fila por texto:
    municipio, anio, pagina, hoja, tipo, texto, valor_m2, x, y, angulo, tamano
`tipo` es `valor` ($ 2,300), `hoja` (clave de hoja como B5-2), `clave`
(clave catastral de manzana) o `texto` (lo demás: calles, colonias, títulos).
`x`, `y` son el centro de la caja en puntos de la hoja tal como se ve.
`hoja` es la clave de la hoja de mapa a la que pertenece la página (la etiqueta
más grande con forma de clave de hoja), vacía en las páginas que no son mapa.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path

import pymupdf

VALOR = re.compile(r"^\$\s*([\d,]+(?:\.\d+)?)$")
CLAVE_HOJA = re.compile(r"^[A-Z]\d{1,2}-\d$")
CLAVE_MANZANA = re.compile(r"^[A-Z]\d{2}[A-Z]\d{4}")


def etiquetas(pagina: pymupdf.Page) -> list[dict]:
    filas = []
    for bloque in pagina.get_text("dict")["blocks"]:
        if bloque["type"] != 0:
            continue
        for linea in bloque["lines"]:
            angulo = round(math.degrees(math.atan2(-linea["dir"][1], linea["dir"][0])), 1)
            for span in linea["spans"]:
                texto = " ".join(span["text"].split())
                if not texto:
                    continue
                x0, y0, x1, y1 = span["bbox"]
                filas.append({"texto": texto, "x": round((x0 + x1) / 2, 2), "y": round((y0 + y1) / 2, 2),
                              "angulo": angulo, "tamano": round(span["size"], 1)})
    # Un valor y su calle a veces vienen en el mismo span ("$ 2530 PASEO DE LOS LEONES").
    separadas = []
    for f in filas:
        m = re.match(r"^(\$\s*[\d,]+(?:\.\d+)?)\s+(.+)$", f["texto"])
        if m:
            separadas += [{**f, "texto": m.group(1)}, {**f, "texto": m.group(2)}]
        else:
            separadas.append(f)
    return separadas


def clasificar(texto: str) -> tuple[str, float | None]:
    if m := VALOR.match(texto):
        return "valor", float(m.group(1).replace(",", ""))
    if CLAVE_HOJA.match(texto):
        return "hoja", None
    if CLAVE_MANZANA.match(texto):
        return "clave", None
    return "texto", None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--municipio", required=True, help="clave de 5 dígitos")
    ap.add_argument("--anio", required=True, type=int, help="año fiscal de la tabla")
    a = ap.parse_args()

    doc = pymupdf.open(a.pdf)
    campos = ["municipio", "anio", "pagina", "hoja", "tipo", "texto", "valor_m2", "x", "y", "angulo", "tamano"]
    total = 0
    with open(a.salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for n, pagina in enumerate(doc, 1):
            filas = etiquetas(pagina)
            for fila in filas:
                fila["tipo"], fila["valor_m2"] = clasificar(fila["texto"])
            claves = [x for x in filas if x["tipo"] == "hoja"]
            # La clave de la propia hoja es la más grande; las vecinas van chicas en el borde.
            # En un índice todas miden igual: ahí no hay hoja propia.
            tamanos = sorted({x["tamano"] for x in claves})
            hoja = max(claves, key=lambda x: x["tamano"])["texto"] if len(tamanos) > 1 else ""
            for fila in filas:
                w.writerow({"municipio": a.municipio, "anio": a.anio, "pagina": n, "hoja": hoja, **fila})
            total += len(filas)
    print(f"{total} etiquetas de {len(doc)} páginas en {a.salida}")


if __name__ == "__main__":
    main()
