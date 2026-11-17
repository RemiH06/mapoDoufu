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
    # Un signo de pesos al inicio ("$ 3300", "$3300") se quita antes de corregir
    # confusiones: si no, "$3300" se leería 53300 (Tlajomulco 2026).
    t = re.sub(r"^\s*[$sS]\s*(?=[\dlIO])", "", texto).translate(CONFUSIONES)
    # Separador de miles: "38,400" y "18.900" son un solo número. Partirlos en la
    # coma dejaba 400 y 900 (encontrado con Zapopan 2026).
    t = re.sub(r"(?<=\d)[,.](?=\d{3}(?:\D|$))", "", t)
    corridas = re.findall(r"\d+", t)
    if not corridas:
        return None
    mejor = max(corridas, key=len)
    return int(mejor) if 3 <= len(mejor) <= 6 else None


def clasificar(texto: str, alto_letra: float, valor_desde_alto: float, con_signo: bool = False) -> tuple[str, int | None]:
    """(tipo, valor). Un número con cero a la izquierda ("080", "011903") es clave de
    manzana: los valores nunca se escriben así. Con `con_signo` (atlas que escriben
    "$ 3300", como Tlajomulco), el signo decide y la altura de letra no importa."""
    # "Tiene letras" sin contar las que el OCR confunde con cifras (I, l, O, o, S, s).
    if not re.search(r"\d", texto) or re.search(r"[A-HJ-NP-RT-Za-km-np-rt-z]{2,}", texto):
        return "texto", None
    if con_signo:
        if not re.match(r"^\s*\$", texto):
            return "clave", None
        valor = limpiar_valor(texto)
        return ("valor", valor) if valor else ("clave", None)
    if texto.strip().startswith("0") or alto_letra < valor_desde_alto:
        return "clave", None
    valor = limpiar_valor(texto)
    return ("valor", valor) if valor else ("clave", None)


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
    ap.add_argument("--valor-desde-alto", type=float, default=0, help="altura de letra en px desde la cual un número es valor")
    ap.add_argument("--valor-con-signo", action="store_true",
                    help="un número es valor si empieza con $ (atlas como Tlajomulco 2026); ignora la altura")
    ap.add_argument("--renderizar", type=int, default=0,
                    help="dpi para renderizar la página completa en vez de tomar su primera imagen "
                         "(para escaneos partidos en varias imágenes por página)")
    ap.add_argument("--ancho-mapa", type=float, default=1.0, help="fracción izquierda de la hoja que es mapa")
    ap.add_argument("--paginas", default=None, help="rango a procesar, p. ej. 6-544 (por omisión, todas)")
    ap.add_argument("--reclasificar", action="store_true",
                    help="no hace OCR: vuelve a clasificar el CSV de salida con las reglas actuales")
    a = ap.parse_args()

    if a.reclasificar:
        # El OCR tarda una hora; clasificar, segundos. Afinar reglas no debe pedir otro OCR.
        with open(a.salida, encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        for fila in filas:
            if fila["tipo"] != "vacia":
                fila["tipo"], fila["valor_m2"] = clasificar(fila["texto"], float(fila["tamano"]), a.valor_desde_alto,
                                                            a.valor_con_signo)
        with open(a.salida, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS)
            w.writeheader()
            w.writerows(filas)
        print(f"{sum(1 for x in filas if x['tipo'] == 'valor')} valores tras reclasificar {len(filas)} textos")
        return

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
            if a.renderizar:
                pix = doc[n - 1].get_pixmap(dpi=a.renderizar)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            else:
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
                tipo, valor = clasificar(texto, alto_letra, a.valor_desde_alto, a.valor_con_signo)
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
