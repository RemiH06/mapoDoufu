# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy", "pyproj"]
# ///
"""Etapa 4 del pipeline de valor catastral para `pdf_mapa`: georreferencia cada
hoja emparejando sus etiquetas de calle con las calles homónimas de OSM, y
ubica las etiquetas de valor. Ver `docs/producto/dataset-vivienda.md`, MEDV.

    uv run --script scripts/catastro/ubicar_pdf_mapa.py ETIQUETAS.csv OSM.json SALIDA_DIR --epsg 32613

Supone lo que cumplen los atlas catastrales: todas las hojas a la misma escala
y orientación. Por eso hay dos pasos:

1. **Global** (escala, giro, espejo): se prueba una rejilla de candidatos en las
   hojas con más calles y gana el que deja más etiquetas sobre su calle.
2. **Por hoja** (desplazamiento): votación de Hough. Cada etiqueta vota por
   cada punto de cada calle de OSM con su nombre; el desplazamiento correcto
   junta los votos de todas las calles en una celda, y uno falso no. Luego se
   afina con ICP (punto más cercano de la misma calle, similitud por mínimos
   cuadrados) y se mide el error en metros.

Salidas en SALIDA_DIR:
    hojas.csv    calidad por hoja (inliers, error mediano, transformación, si se acepta)
    valores.csv  una fila por etiqueta de valor de una hoja aceptada, con lon, lat y
                 `clase`: `zona` (valor base de la colonia) o `calle` (tramo), según el
                 tamaño de letra (--zona-desde-tamano, propio de cada atlas)
    control.csv  claves de manzana repetidas en dos hojas: distancia entre sus dos ubicaciones
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree

PASO_M = 15  # densificación de las calles de OSM
CELDA_HOUGH_M = 40
RADIO_INLIER_M = 40
MIN_INLIERS = 8
MAX_ERROR_M = 20

TIPOS_DE_VIA = {"AV", "AVENIDA", "CALLE", "C", "CALZ", "CALZADA", "BLVD", "BOULEVARD", "BULEVAR", "PRIV",
                "PRIVADA", "AND", "ANDADOR", "CERRADA", "CDA", "PROL", "PROLONGACION", "CIRCUITO", "CTO",
                "PASAJE", "RETORNO", "RT", "CARR", "CARRETERA", "GLORIETA", "PERIFERICO"}
ABREVIATURAS = {"GRAL": "GENERAL", "DR": "DOCTOR", "PDTE": "PRESIDENTE", "STA": "SANTA", "STO": "SANTO",
                "FCO": "FRANCISCO", "LIC": "LICENCIADO", "ING": "INGENIERO", "PROF": "PROFESOR",
                "GPE": "GUADALUPE", "MA": "MARIA", "JN": "JUAN", "SN": "SAN", "NTE": "NORTE", "OTE": "ORIENTE",
                "PTE": "PONIENTE", "CORONEL": "CORONEL", "CNEL": "CORONEL", "ARQ": "ARQUITECTO", "MTRO": "MAESTRO"}
PALABRAS_VACIAS = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y"}


def normalizar(nombre: str) -> str:
    """Nombre de calle comparable entre el PDF y OSM: sin acentos, sin tipo de vía,
    abreviaturas expandidas y sin artículos."""
    t = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().upper()
    palabras = re.sub(r"[^A-Z0-9 ]", " ", t).split()
    palabras = [ABREVIATURAS.get(p, p) for p in palabras]
    while palabras and palabras[0] in TIPOS_DE_VIA:
        palabras = palabras[1:]
    return " ".join(p for p in palabras if p not in PALABRAS_VACIAS)


def compacto(nombre: str) -> str:
    """Llave sin espacios ni artículos quitados, para texto de OCR, que pega las
    palabras ("RIOLERMA"). Se quitan solo signos y acentos."""
    t = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", t)


def llaves_ocr(nombre: str) -> list[str]:
    """Llaves compactas de un nombre: completo y sin el tipo de vía inicial."""
    t = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().upper()
    palabras = re.sub(r"[^A-Z0-9 ]", " ", t).split()
    llaves = {"".join(palabras)}
    while palabras and palabras[0] in TIPOS_DE_VIA:
        palabras = palabras[1:]
        llaves.add("".join(palabras))
    return [k for k in llaves if len(k) >= 5]


def calles_osm(ruta: Path, epsg: int, ocr: bool = False) -> dict[str, np.ndarray]:
    a_utm = Transformer.from_crs(4326, epsg, always_xy=True)
    puntos: dict[str, list] = defaultdict(list)
    for el in json.loads(ruta.read_text(encoding="utf-8"))["elements"]:
        if el.get("type") != "way" or "geometry" not in el:
            continue
        crudo = el["tags"].get("name", "")
        nombres = llaves_ocr(crudo) if ocr else [normalizar(crudo)]
        nombres = [n for n in nombres if len(n) >= 3]
        if not nombres:
            continue
        x, y = a_utm.transform([g["lon"] for g in el["geometry"]], [g["lat"] for g in el["geometry"]])
        for (x0, y0), (x1, y1) in zip(zip(x, y), zip(x[1:], y[1:])):
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) // PASO_M))
            for k in range(n):
                for nombre in nombres:
                    puntos[nombre].append((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
    return {k: np.array(v) for k, v in puntos.items()}


def matriz(escala: float, giro_deg: float, espejo: bool) -> np.ndarray:
    c, s = math.cos(math.radians(giro_deg)), math.sin(math.radians(giro_deg))
    m = np.array([[c, -s], [s, c]]) * escala
    # La hoja tiene la y hacia abajo; el mapa, hacia arriba. El espejo lo decide el ajuste.
    return m @ np.diag([1, -1]) if espejo else m


def hough(etiquetas: list[tuple[str, np.ndarray]], calles: dict[str, np.ndarray], m: np.ndarray):
    """Desplazamiento con más votos y cuántas etiquetas distintas lo apoyan."""
    votos = []
    for i, (nombre, p) in enumerate(etiquetas):
        destino = calles[nombre]
        t = destino - m @ p
        celdas = np.floor(t / CELDA_HOUGH_M).astype(np.int64)
        celdas = np.unique(celdas, axis=0)  # una etiqueta vota una vez por celda
        votos.append(np.column_stack([celdas, np.full(len(celdas), i)]))
    if not votos:
        return None, 0
    v = np.concatenate(votos)
    claves, cuenta = np.unique(v[:, :2], axis=0, return_counts=True)
    mejor = np.argmax(cuenta)
    return (claves[mejor] + 0.5) * CELDA_HOUGH_M, int(cuenta[mejor])


def similitud(origen: np.ndarray, destino: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Umeyama: escala, giro (con espejo permitido) y traslación por mínimos cuadrados."""
    mo, md = origen.mean(0), destino.mean(0)
    o, d = origen - mo, destino - md
    u, s, vt = np.linalg.svd(d.T @ o / len(o))
    r = u @ vt
    escala = s.sum() / (o ** 2).sum(1).mean()
    m = escala * r
    return m, md - m @ mo


def afinar(etiquetas, calles, m, t, iteraciones: int = 6):
    arboles = {n: cKDTree(calles[n]) for n, _ in etiquetas}
    for _ in range(iteraciones):
        pares_o, pares_d, errores = [], [], []
        for nombre, p in etiquetas:
            q = m @ p + t
            dist, idx = arboles[nombre].query(q)
            errores.append(dist)
            if dist <= RADIO_INLIER_M:
                pares_o.append(p)
                pares_d.append(calles[nombre][idx])
        if len(pares_o) < MIN_INLIERS:
            return m, t, np.array(errores), len(pares_o)
        m, t = similitud(np.array(pares_o), np.array(pares_d))
    errores = np.array([arboles[n].query(m @ p + t)[0] for n, p in etiquetas])
    return m, t, errores, int((errores <= RADIO_INLIER_M).sum())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("etiquetas", type=Path)
    ap.add_argument("osm", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--epsg", type=int, required=True)
    ap.add_argument("--ocr", action="store_true",
                    help="etiquetas de extraer_pdf_raster.py: emparejar nombres sin espacios")
    ap.add_argument("--escala-por-hoja", action="store_true",
                    help="estimar la escala de cada hoja (atlas por zona, no por rejilla)")
    ap.add_argument("--escalas", default="0.2,6", help="rango de escalas a probar, m por unidad de la hoja")
    ap.add_argument("--zona-desde-tamano", type=float, default=None,
                    help="tamaño de letra desde el cual un valor es de zona y no de calle (GDL 2020: 10)")
    a = ap.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)

    calles = calles_osm(a.osm, a.epsg, ocr=a.ocr)
    esc_min, esc_max = (float(v) for v in a.escalas.split(","))
    print(f"{len(calles)} nombres de calle en OSM", flush=True)

    por_hoja: dict[str, list[dict]] = defaultdict(list)
    with open(a.etiquetas, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            if fila["hoja"]:
                por_hoja[fila["hoja"]].append(fila)

    def de_calle(filas):
        salida = []
        for f in filas:
            if f["tipo"] != "texto":
                continue
            p = np.array([float(f["x"]), float(f["y"])])
            if a.ocr:
                n = next((k for k in llaves_ocr(f["texto"]) if k in calles), None)
                if n:
                    salida.append((n, p))
            else:
                n = normalizar(f["texto"])
                if len(n) >= 4 and n in calles:
                    salida.append((n, p))
        return salida

    calles_por_hoja = {h: de_calle(fs) for h, fs in por_hoja.items()}

    # 1. Global: escala, giro y espejo con las hojas con más calles.
    muestra = sorted(calles_por_hoja, key=lambda h: -len(calles_por_hoja[h]))[:6]
    mejor = None
    for espejo in (True, False):
        for giro in range(0, 360, 90):
            for escala in np.geomspace(esc_min, esc_max, 40):
                m = matriz(escala, giro, espejo)
                total = sum(hough(calles_por_hoja[h], calles, m)[1] for h in muestra)
                if mejor is None or total > mejor[0]:
                    mejor = (total, escala, giro, espejo)
    _, escala, giro, espejo = mejor
    m0 = matriz(escala, giro, espejo)
    print(f"global: {escala:.3f} m por punto, giro {giro}°, espejo {espejo} ({mejor[0]} votos en {len(muestra)} hojas)", flush=True)

    # 2. Por hoja.
    a_geo = Transformer.from_crs(a.epsg, 4326, always_xy=True)
    resultados = {}
    with open(a.salida / "hojas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hoja", "pagina", "etiquetas_calle", "votos", "inliers", "error_mediano_m", "escala", "aceptada",
                    "m11", "m12", "m21", "m22", "tx", "ty"])
        for hoja, etiq in sorted(calles_por_hoja.items()):
            pagina = por_hoja[hoja][0]["pagina"]
            m_hoja = m0
            if a.escala_por_hoja and etiq:
                # Misma orientación que la global, escala propia de la hoja.
                candidatas = [(hough(etiq, calles, matriz(e, giro, espejo)), e) for e in np.geomspace(esc_min, esc_max, 60)]
                (_, _), e_hoja = max(candidatas, key=lambda c: c[0][1])
                m_hoja = matriz(e_hoja, giro, espejo)
            t, votos = hough(etiq, calles, m_hoja) if etiq else (None, 0)
            if t is None:
                w.writerow([hoja, pagina, len(etiq), votos, 0, "", "", False] + [""] * 6)
                continue
            m, t, errores, inliers = afinar(etiq, calles, m_hoja, t)
            error = float(np.median(errores[errores <= RADIO_INLIER_M])) if inliers else float("inf")
            esc = math.sqrt(abs(np.linalg.det(m)))
            # Una hoja vale si muchas calles caen sobre su homónima y la escala no se desbocó.
            referencia = math.sqrt(abs(np.linalg.det(m_hoja)))
            aceptada = inliers >= MIN_INLIERS and error <= MAX_ERROR_M and abs(esc / referencia - 1) < 0.1
            resultados[hoja] = (m, t, aceptada)
            w.writerow([hoja, pagina, len(etiq), votos, inliers, round(error, 1), round(esc, 4), aceptada,
                        *np.round(m.ravel(), 6), round(t[0], 2), round(t[1], 2)])

    aceptadas = [h for h, (_, _, ok) in resultados.items() if ok]
    print(f"{len(aceptadas)} de {len(por_hoja)} hojas aceptadas", flush=True)

    # 3. Valores y control.
    n_valores = 0
    claves = defaultdict(list)
    with open(a.salida / "valores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["municipio", "anio", "pagina", "hoja", "valor_m2", "tamano", "clase", "lon", "lat"])
        for hoja in aceptadas:
            m, t, _ = resultados[hoja]
            for fila in por_hoja[hoja]:
                if fila["tipo"] not in ("valor", "clave"):
                    continue
                x, y = m @ np.array([float(fila["x"]), float(fila["y"])]) + t
                if fila["tipo"] == "clave":
                    claves[fila["texto"][:8]].append((hoja, x, y))
                    continue
                lon, lat = a_geo.transform(x, y)
                tamano = float(fila["tamano"])
                clase = "" if a.zona_desde_tamano is None else ("zona" if tamano >= a.zona_desde_tamano else "calle")
                w.writerow([fila["municipio"], fila["anio"], fila["pagina"], hoja, fila["valor_m2"], fila["tamano"],
                            clase, round(lon, 6), round(lat, 6)])
                n_valores += 1
    # Una misma clave puede rotularse dos veces en una hoja (manzana grande): entre dos
    # hojas se compara la ocurrencia más cercana. Cada hoja rotula la parte de la
    # manzana que le toca, así que decenas de metros son normales.
    cercanas: dict[tuple[str, str, str], float] = {}
    for clave, sitios in claves.items():
        for i in range(len(sitios)):
            for j in range(i + 1, len(sitios)):
                ha, hb = sorted((sitios[i][0], sitios[j][0]))
                if ha != hb:
                    d = math.hypot(sitios[i][1] - sitios[j][1], sitios[i][2] - sitios[j][2])
                    cercanas[(clave, ha, hb)] = min(d, cercanas.get((clave, ha, hb), d))
    with open(a.salida / "control.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clave", "hoja_a", "hoja_b", "distancia_m"])
        for (clave, ha, hb), d in sorted(cercanas.items()):
            w.writerow([clave, ha, hb, round(d, 1)])
    if cercanas:
        d = np.array(list(cercanas.values()))
        print(f"control: {len(d)} claves en dos hojas, distancia mediana {np.median(d):.1f} m, "
              f"p90 {np.percentile(d, 90):.1f} m", flush=True)
    print(f"{n_valores} valores ubicados en {a.salida / 'valores.csv'}")


if __name__ == "__main__":
    main()
