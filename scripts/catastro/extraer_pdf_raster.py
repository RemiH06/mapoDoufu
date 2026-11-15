# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["pymupdf", "rapidocr-onnxruntime", "opencv-python-headless", "numpy", "pillow"]
# [tool.uv]
# override-dependencies = ["opencv-python ; sys_platform == 'never'"]
# ///
"""Etapa 3 del pipeline de valor catastral, adaptador `pdf_raster`: OCR de un
atlas escaneado (una imagen por hoja, como Zapopan 2026). Entrega las mismas
`etiquetas` que `extraer_pdf_mapa.py`, con posición en píxeles de la imagen.
Ver `docs/producto/dataset-vivienda.md`, sección MEDV.

    uv run --script scripts/catastro/extraer_pdf_raster.py PDF SALIDA.csv --municipio 14120 --anio 2026 \
        --valor-desde-alto 80 --ancho-mapa 0.80

- OCR con RapidOCR (modelos ONNX de PaddleOCR, en CPU). `opencv-python` se
  sustituye por la versión sin interfaz: la otra pide libGL, que un servidor no tiene.
- Un número es **valor** si su letra mide al menos `--valor-desde-alto` píxeles
  (en Zapopan 2026: valores de 85 a 100 px, números de manzana de 40 a 75).
  Lo demás numérico es **clave** (manzana) y lo alfabético, **texto** (calles,
  colonias). El umbral es propio de cada atlas: revisar el histograma de alturas.
- Limpieza de valores: el OCR confunde `5` con `$` o `S`, `0` con `O`, y pega
  ruido (`9/2100`). Se corrigen esas letras y se toma la corrida de dígitos más
  larga; un valor que no queda en 3 a 6 cifras se descarta.
- `--ancho-mapa`: fracción izquierda de la hoja que es mapa; a la derecha va la
  leyenda de colonias, que no debe confundirse con calles.
- Reanudable: escribe cada página al terminarla y salta las que ya están.

Columnas: municipio, anio, pagina, hoja, tipo, texto, valor_m2, x, y, angulo, tamano.
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import re
import time
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

CAMPOS = ["municipio", "anio", "pagina", "hoja", "tipo", "texto", "valor_m2", "x", "y", "angulo", "tamano"]
CONFUSIONES = str.maketrans({"$": "5", "S": "5", "s": "5", "O": "0", "o": "0", "l": "1", "I": "1"})


def limpiar_valor(texto: str) -> int | None:
    corridas = re.findall(r"\d+", texto.translate(CONFUSIONES))
    if not corridas:
        return None
    mejor = max(corridas, key=len)
    return int(mejor) if 3 <= len(mejor) <= 6 else None


def geometria(caja) -> tuple[float, float, float, float]:
    """Centro, ángulo de la línea base y altura de letra de una caja de 4 esquinas."""
    p = np.array(caja, dtype=float)
    cx, cy = p.mean(0)
    base = p[1] - p[0]
    alto = np.linalg.norm(p[3] - p[0])
    angulo = math.degrees(math.atan2(-base[1], base[0]))
    return cx, cy, angulo, alto


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--municipio", required=True)
    ap.add_argument("--anio", type=int, required=True)
    ap.add_argument("--valor-desde-alto", type=float, required=True, help="altura de letra en px desde la cual un número es valor")
    ap.add_argument("--ancho-mapa", type=float, default=1.0, help="fracción izquierda de la hoja que es mapa")
    ap.add_argument("--paginas", default=None, help="rango a procesar, p. ej. 6-544 (por omisión, todas)")
    a = ap.parse_args()

    hechas = set()
    if a.salida.exists():
        with open(a.salida, encoding="utf-8") as f:
            hechas = {int(r["pagina"]) for r in csv.DictReader(f)}
    nuevo = not a.salida.exists()

    doc = pymupdf.open(a.pdf)
    desde, hasta = (1, len(doc)) if not a.paginas else map(int, a.paginas.split("-"))
    ocr = RapidOCR()
    with open(a.salida, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        if nuevo:
            w.writeheader()
        for n in range(desde, hasta + 1):
            if n in hechas:
                continue
            t0 = time.time()
            imagenes = doc[n - 1].get_images()
            if not imagenes:
                continue
            img = Image.open(io.BytesIO(doc.extract_image(imagenes[0][0])["image"])).convert("RGB")
            ancho, alto = img.size
            mapa = np.array(img.crop((0, 0, int(ancho * a.ancho_mapa), alto)))
            resultado, _ = ocr(mapa)
            filas = []
            for caja, texto, conf in resultado or []:
                texto = " ".join(texto.split())
                cx, cy, angulo, alto_letra = geometria(caja)
                tipo, valor = "texto", None
                if re.search(r"\d", texto) and not re.search(r"[A-RT-Za-rt-z]{2,}", texto):
                    valor = limpiar_valor(texto) if alto_letra >= a.valor_desde_alto else None
                    tipo = "valor" if valor else "clave"
                filas.append({"municipio": a.municipio, "anio": a.anio, "pagina": n, "hoja": f"p{n}",
                              "tipo": tipo, "texto": texto, "valor_m2": valor, "x": round(cx, 1),
                              "y": round(cy, 1), "angulo": round(angulo, 1), "tamano": round(alto_letra, 1)})
            # Una página sin nada (portada) se marca con una fila vacía para no repetirla.
            w.writerows(filas or [{"municipio": a.municipio, "anio": a.anio, "pagina": n, "hoja": "", "tipo": "vacia"}])
            f.flush()
            valores = sum(1 for r in filas if r["tipo"] == "valor")
            print(f"p{n}: {len(filas)} textos, {valores} valores, {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
