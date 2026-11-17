# /// script
# requires-python = ">=3.11"
# dependencies = ["rasterio", "numpy", "shapely>=2"]
# ///
"""Altura de dosel a ~1 m (Meta y WRI, "High Resolution Canopy Height Maps",
Tolan et al. 2024, CC BY 4.0) recortada a una caja y llevada a la UTM de la zona.

    uv run --script scripts/ambiental/dosel.py --salida SALIDA --caja=O,S,E,N --epsg 32613

Deja en SALIDA:
- `dosel_1m.tif`: altura del dosel en metros (uint8; 0 es sin dosel, 255 sin dato).
- `dosel_fecha.tif`: fecha de la imagen de origen de cada zona (la de Maxar que
  usó el modelo), a la resolución del archivo de fechas.
- `procedencia_dosel.csv`: mosaico, URL y bytes leídos.

Los mosaicos son COG en EPSG:3857 de unos 600 MB, guardados en franjas de una
fila y sin vistas reducidas: leer una ventana baja filas completas (unos 80 MB por
mosaico para una caja de 11 km). Ver `docs/fuentes/imagenes.md`.
"""
from __future__ import annotations

import argparse
import csv
import json
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from shapely.geometry import box, shape

BASE = "https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float"


def mosaicos(caja: tuple[float, float, float, float]) -> list[str]:
    with urllib.request.urlopen(f"{BASE}/tiles.geojson", timeout=300) as r:
        indice = json.load(r)
    b = box(*caja)
    return sorted(f["properties"]["tile"] for f in indice["features"] if shape(f["geometry"]).intersects(b))


def a_utm(origen, transform, crs_origen, destino: Path, epsg: int, caja, nodata, dtype, resolucion=None,
          remuestreo=Resampling.bilinear) -> None:
    o, s, e, n = transform_bounds("EPSG:4326", f"EPSG:{epsg}", *caja)
    res = resolucion or abs(transform.a)
    ancho, alto = int(np.ceil((e - o) / res)), int(np.ceil((n - s) / res))
    t = rasterio.transform.from_origin(o, n, res, res)
    salida = np.full((alto, ancho), nodata, dtype=dtype)
    reproject(origen, salida, src_transform=transform, src_crs=crs_origen, src_nodata=nodata,
              dst_transform=t, dst_crs=f"EPSG:{epsg}", dst_nodata=nodata, resampling=remuestreo)
    perfil = {"driver": "GTiff", "height": alto, "width": ancho, "count": 1, "dtype": dtype, "crs": f"EPSG:{epsg}",
              "transform": t, "nodata": nodata, "compress": "deflate", "tiled": True, "blockxsize": 512, "blockysize": 512}
    with rasterio.open(destino, "w", **perfil) as dst:
        dst.write(salida, 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--caja", required=True, help="oeste,sur,este,norte en grados")
    ap.add_argument("--epsg", type=int, required=True, help="UTM de la zona, p. ej. 32613")
    a = ap.parse_args()
    caja = tuple(float(v) for v in a.caja.split(","))
    a.salida.mkdir(parents=True, exist_ok=True)

    nombres = mosaicos(caja)
    if not nombres:
        raise SystemExit("ningún mosaico de dosel toca la caja")
    print(f"{len(nombres)} mosaicos: {', '.join(nombres)}", flush=True)
    caja_3857 = transform_bounds("EPSG:4326", "EPSG:3857", *caja)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="5"):
        fuentes = [rasterio.open(f"/vsicurl/{BASE}/chm/{t}.tif") for t in nombres]
        # Sin nodata declarado: 0 es "sin dosel", así que lo que no cubre ningún mosaico va a 255.
        arr, t = merge(fuentes, bounds=caja_3857, nodata=255)
        crs = fuentes[0].crs
        a_utm(arr[0], t, crs, a.salida / "dosel_1m.tif", a.epsg, caja, 255, "uint8", resolucion=1.0)

        with rasterio.open(f"/vsicurl/{BASE}/CHM_acquisition_date.tif") as f:
            ventana = rasterio.windows.from_bounds(*transform_bounds("EPSG:4326", f.crs, *caja), f.transform)
            fechas = f.read(1, window=ventana.round_offsets().round_lengths(), boundless=True, fill_value=0)
            tf = f.window_transform(ventana.round_offsets().round_lengths())
            # El archivo de fechas puede venir en grados: la resolución de salida va fija en metros.
            a_utm(fechas, tf, f.crs, a.salida / "dosel_fecha.tif", a.epsg, caja, 0, fechas.dtype.name,
                  resolucion=10.0, remuestreo=Resampling.nearest)
            valores, cuenta = np.unique(fechas[fechas > 0], return_counts=True)
            print("fechas de imagen (valor: píxeles):", dict(zip(valores.tolist()[:10], cuenta.tolist()[:10])), flush=True)

    with rasterio.open(a.salida / "dosel_1m.tif") as r:
        d = r.read(1)
        validos = d[d != 255]
        print(f"dosel_1m.tif: {r.width}x{r.height}, {validos.size / d.size:.1%} con dato, "
              f"{(validos >= 3).mean():.1%} con dosel de 3 m o más", flush=True)
    with open(a.salida / "procedencia_dosel.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mosaico", "url", "licencia"])
        for t in nombres:
            w.writerow([t, f"{BASE}/chm/{t}.tif", "CC BY 4.0, Meta y WRI"])


if __name__ == "__main__":
    main()
