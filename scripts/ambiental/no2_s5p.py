# /// script
# requires-python = ">=3.11"
# dependencies = ["pystac-client", "planetary-computer", "fsspec", "aiohttp", "h5py", "numpy",
#                 "shapely>=2", "rasterio", "truststore"]
# ///
"""NO₂ troposférico medio de Sentinel-5P (TROPOMI) en una rejilla fina, para una
caja y un año. Es NOX del dataset de vivienda (docs/producto/dataset-vivienda.md)
y sirve igual como capa ambiental en cualquier zona (docs/fuentes/imagenes.md).

    uv run --script scripts/ambiental/no2_s5p.py --caja=-103.70,20.30,-103.00,20.90 \
        --anio 2020 --salida ~/srv/mapo-paquetes/zmg/no2_2020.tif

Cada órbita es un NetCDF de cientos de MB; se leen por rangos HTTP solo los
renglones que tocan la caja (unos 15 s por órbita). Un píxel de TROPOMI mide
unos 5.5 × 3.5 km: se reparte en la rejilla por su huella (las cuatro esquinas
de SUPPORT_DATA), sumando su valor a cada celda cuyo centro cae dentro, y se
promedia. Solo píxeles con qa_value > 0.75 (recomendación de KNMI: quita nubes
y nieve). El avance se guarda tras cada órbita: relanzar reanuda.

Salida: GeoTIFF de dos bandas, NO₂ medio en µmol/m² y número de observaciones
por celda. La resolución fina no inventa detalle: cada celda promedia píxeles
de 5 km; ayuda a no perder la forma de la huella, nada más.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import fsspec
import h5py
import numpy as np
import planetary_computer
import pystac_client
import truststore
from shapely import contains_xy
from shapely.geometry import Polygon

truststore.inject_into_ssl()
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
QA_MINIMO = 0.75


def orbitas(caja, anio: int) -> list:
    c = pystac_client.Client.open(STAC)
    items = list(c.search(collections=["sentinel-5p-l2-netcdf"], bbox=caja, datetime=f"{anio}-01-01/{anio}-12-31",
                          query={"s5p:product_name": {"eq": "no2"}, "s5p:processing_mode": {"eq": "OFFL"}}).items())
    return sorted(items, key=lambda i: i.id)


def leer_orbita(href: str, caja) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """(valor µmol/m², esquinas lon (n, 4), esquinas lat (n, 4)) de los píxeles válidos en la caja."""
    o, s, e, n = caja
    fs = fsspec.filesystem("https")
    with fs.open(href, block_size=2**20, cache_type="blockcache") as f, h5py.File(f) as h:
        p = h["PRODUCT"]
        lat, lon = p["latitude"][0], p["longitude"][0]
        margen = 0.1  # un píxel que cae justo afuera puede cubrir la orilla de la caja
        m = (lat > s - margen) & (lat < n + margen) & (lon > o - margen) & (lon < e + margen)
        filas = np.where(m.any(1))[0]
        if not len(filas):
            return None
        a, b = filas.min(), filas.max() + 1
        no2 = p["nitrogendioxide_tropospheric_column"][0, a:b]
        qa = p["qa_value"][0, a:b]
        geo = p["SUPPORT_DATA"]["GEOLOCATIONS"]
        lat_b, lon_b = geo["latitude_bounds"][0, a:b], geo["longitude_bounds"][0, a:b]
        relleno = p["nitrogendioxide_tropospheric_column"].attrs.get("_FillValue", 9.96921e36)
        ok = m[a:b] & (qa > QA_MINIMO) & (no2 < relleno / 10)
        return no2[ok] * 1e6, lon_b[ok], lat_b[ok]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--caja", required=True, help="oeste,sur,este,norte en grados")
    ap.add_argument("--anio", type=int, required=True)
    ap.add_argument("--resolucion", type=float, default=0.01, help="grados por celda (0.01 ≈ 1 km)")
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--max-orbitas", type=int, default=None, help="solo para probar")
    a = ap.parse_args()
    a.salida = a.salida.expanduser()
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    caja = [float(v) for v in a.caja.split(",")]
    o, s, e, n = caja
    r = a.resolucion
    ancho, alto = math.ceil((e - o) / r), math.ceil((n - s) / r)
    xs = o + (np.arange(ancho) + 0.5) * r
    ys = n - (np.arange(alto) + 0.5) * r  # de norte a sur, como un ráster

    estado = a.salida.with_suffix(".estado.npz")
    hechas_ruta = a.salida.with_suffix(".hechas.json")
    if estado.exists() and hechas_ruta.exists():
        z = np.load(estado)
        suma, cuenta = z["suma"], z["cuenta"]
        hechas = set(json.loads(hechas_ruta.read_text()))
    else:
        suma, cuenta, hechas = np.zeros((alto, ancho)), np.zeros((alto, ancho)), set()

    items = orbitas(caja, a.anio)[: a.max_orbitas]
    print(f"{len(items)} órbitas de {a.anio}; {len(hechas)} ya hechas", flush=True)
    for k, it in enumerate(items, 1):
        if it.id in hechas:
            continue
        for intento in range(3):
            try:
                href = planetary_computer.sign(it.assets["no2"].href)  # firmar justo antes: el token caduca
                datos = leer_orbita(href, caja)
                break
            except Exception as error:  # red o servidor: reintentar, y si no, saltar la órbita
                print(f"  {it.id}: {type(error).__name__} {error}; intento {intento + 1}", flush=True)
                time.sleep(10 * (intento + 1))
        else:
            continue
        if datos is not None:
            valores, lon_b, lat_b = datos
            for v, plon, plat in zip(valores, lon_b, lat_b):
                huella = Polygon(zip(plon, plat))
                x0, y0, x1, y1 = huella.bounds
                ci = np.where((xs >= x0) & (xs <= x1))[0]
                fi = np.where((ys >= y0) & (ys <= y1))[0]
                if not len(ci) or not len(fi):
                    continue
                gx, gy = np.meshgrid(xs[ci], ys[fi])
                dentro = contains_xy(huella, gx, gy)
                suma[np.ix_(fi, ci)] += np.where(dentro, v, 0)
                cuenta[np.ix_(fi, ci)] += dentro
        hechas.add(it.id)
        if k % 10 == 0 or k == len(items):
            np.savez(estado.with_suffix(".tmp.npz"), suma=suma, cuenta=cuenta)
            estado.with_suffix(".tmp.npz").replace(estado)
            hechas_ruta.write_text(json.dumps(sorted(hechas)))
            print(f"  {k}/{len(items)} órbitas, celdas con dato: {(cuenta > 0).mean():.0%}", flush=True)

    import rasterio
    from rasterio.transform import from_origin

    media = np.where(cuenta > 0, suma / np.maximum(cuenta, 1), np.nan).astype("float32")
    perfil = {"driver": "GTiff", "height": alto, "width": ancho, "count": 2, "dtype": "float32",
              "crs": "EPSG:4326", "transform": from_origin(o, n, r, r), "nodata": np.nan, "compress": "deflate"}
    with rasterio.open(a.salida, "w", **perfil) as dst:
        dst.write(media, 1)
        dst.write(cuenta.astype("float32"), 2)
        dst.set_band_description(1, "NO2 troposferico medio, umol/m2")
        dst.set_band_description(2, "observaciones (pixeles con qa > 0.75)")
    print(f"listo {a.salida}: media {np.nanmean(media):.1f} µmol/m², "
          f"p5 {np.nanpercentile(media, 5):.1f}, p95 {np.nanpercentile(media, 95):.1f}", flush=True)


if __name__ == "__main__":
    main()
