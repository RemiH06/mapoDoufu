# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Estaciones de transporte masivo de una zona desde OSM, para la columna
`transporte_km` del dataset de vivienda (docs/producto/dataset-vivienda.md).

    uv run --script scripts/vivienda/transporte_masivo.py --caja=20.30,-103.70,20.90,-103.00 \
        --redes "Mi Tren,Línea 4,Mi Macro Periférico,Mi Macro Aeropuerto,Mi Macro Calzada" \
        --rutas "Mi Macro Calzada Parador" --salida mapo_core/data/osm/transporte_masivo_zmg.csv

La caja va en el orden de Overpass: sur, oeste, norte, este.

En OSM las estaciones no están etiquetadas igual en cada red (revisado en la ZMG
el 2026-11-16): el tren (Mi Tren, Línea 4) y Mi Macro Periférico tienen nodos
`railway=station|halt` o `public_transport=station` con su `network`; Mi Macro
Calzada solo tiene 4 estaciones así, y las 27 completas están como andenes
(`public_transport=platform`) de la relación de ruta. La etiqueta `network=Mi
Macro` sola no sirve: la llevan más de mil paradas comunes. Por eso hay dos
entradas: `--redes` (nodos de estación filtrados por red) y `--rutas`
(andenes de las relaciones de ruta cuyo nombre contiene el texto).
"""
from __future__ import annotations

import argparse
import csv
import time

import requests

OVERPASS = "https://overpass-api.de/api/interpreter"


def overpass(consulta: str) -> list[dict]:
    for espera in (0, 15, 30, 60, 120):
        time.sleep(espera)
        r = requests.post(OVERPASS, data={"data": consulta}, headers={"User-Agent": "mapo-datos/0.1"}, timeout=300)
        if r.ok and r.text.lstrip().startswith("{"):
            return r.json()["elements"]
    raise RuntimeError("Overpass no respondió con JSON tras cinco intentos")


def centro(el: dict) -> tuple[float, float]:
    c = el.get("center") or el
    return c["lon"], c["lat"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--caja", required=True, help="sur,oeste,norte,este (orden de Overpass)")
    ap.add_argument("--redes", required=True, help="textos de `network` que cuentan como transporte masivo")
    ap.add_argument("--rutas", default="", help="textos de nombre de relaciones de ruta cuyos andenes cuentan")
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    caja = a.caja
    redes = [r.strip() for r in a.redes.split(",") if r.strip()]

    filas = []
    estaciones = overpass(
        f'[out:json][timeout:240];(node["railway"~"^(station|halt|tram_stop)$"]({caja});'
        f'node["public_transport"="station"]({caja});way["public_transport"="station"]({caja}););out center tags;')
    for el in estaciones:
        red = el.get("tags", {}).get("network", "")
        coincide = next((r for r in redes if r.lower() in red.lower()), None)
        if coincide:
            lon, lat = centro(el)
            filas.append({"red": coincide, "nombre": el["tags"].get("name", ""), "lon": lon, "lat": lat, "origen": "estacion"})

    for ruta in [r.strip() for r in a.rutas.split(",") if r.strip()]:
        andenes = overpass(
            f'[out:json][timeout:240];relation["type"="route"]["name"~"{ruta}",i]({caja})->.r;'
            f'(node(r.r)["public_transport"="platform"];way(r.r)["public_transport"="platform"];);out center tags;')
        for el in andenes:
            lon, lat = centro(el)
            filas.append({"red": ruta, "nombre": el.get("tags", {}).get("name", ""), "lon": lon, "lat": lat, "origen": "anden"})

    with open(a.salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["red", "nombre", "lon", "lat", "origen"])
        w.writeheader()
        w.writerows(filas)
    por_red: dict[str, int] = {}
    for x in filas:
        por_red[x["red"]] = por_red.get(x["red"], 0) + 1
    print(f"{len(filas)} puntos en {a.salida}: {por_red}")


if __name__ == "__main__":
    main()
