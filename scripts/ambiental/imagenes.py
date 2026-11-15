# /// script
# requires-python = ">=3.11"
# dependencies = ["pystac-client", "planetary-computer", "odc-stac", "rioxarray", "xarray", "dask", "numpy"]
# ///
"""Compuestos de satélite recortados a una caja, desde el STAC de Planetary
Computer (sin cuenta). Deja GeoTIFF con mosaicos internos, listos para QGIS.

Productos (cada uno se salta si ya existe, así que se puede relanzar):
  s2_bandas_<periodo>.tif   Sentinel-2 L2A, 10 bandas a 10 m, mediana sin nubes
  s2_indices_<AAAA-MM>.tif  NDVI, NDWI y NBR mensuales (×10000, int16)
  lst_secas_<AAAA>.tif      Landsat 8/9, temperatura de superficie en °C, mediana de marzo a mayo
  worldcover_2021.tif       ESA WorldCover 10 m, clases de cobertura

    uv run --script scripts/ambiental/imagenes.py --salida ~/srv/mapo-paquetes/autlan/imagenes \
        --caja=-104.65,19.55,-103.95,20.05 --epsg 32613 \
        --bandas 2025-02-01/2025-05-31 --indices 2024-11/2025-10 --lst 2014/2025

Ver `docs/fuentes/imagenes.md`.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import os

import numpy as np
import planetary_computer
import pystac_client
import xarray as xr
from odc.stac import load

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
BANDAS_S2 = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
# Clases de la SCL que se conservan: vegetación, suelo, agua, sin clasificar.
# Se tiran nubes (8, 9, 10), sombras (3), saturados (1) y sin dato (0).
SCL_BUENOS = [4, 5, 6, 7]


# Reintentos de GDAL ante cortes de red al leer los COG remotos.
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "6")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "3")


def catalogo() -> pystac_client.Client:
    return pystac_client.Client.open(STAC)


def cargar(items, **kw):
    """Las URL firmadas de Planetary Computer caducan en cerca de una hora, y una
    mediana larga lee mucho después de buscar: se firma cada URL al leerla
    (`patch_url`). Una escena que falla se salta en vez de tumbar el producto."""
    return load(items, patch_url=planetary_computer.sign, fail_on_error=False, **kw)


def buscar(coleccion: str, caja, fechas: str, nubes: int | None = None, extra: dict | None = None,
           maximo: int | None = None):
    """Escenas que tocan la caja. Con `maximo`, solo las más despejadas: la mediana
    de una docena de escenas limpias sale igual y se lee una fracción de los datos."""
    consulta = {"eo:cloud_cover": {"lt": nubes}} if nubes is not None else {}
    consulta |= extra or {}
    items = list(catalogo().search(collections=[coleccion], bbox=caja, datetime=fechas, query=consulta).items())
    total = len(items)
    if maximo is not None and total > maximo:
        # Por mosaico (MGRS): si la caja cae en dos, las más despejadas de uno solo
        # dejarían el otro sin datos.
        por_mosaico: dict[str, list] = {}
        for i in items:
            por_mosaico.setdefault(i.properties.get("s2:mgrs_tile", ""), []).append(i)
        cuota = -(-maximo // len(por_mosaico))
        items = [i for grupo in por_mosaico.values()
                 for i in sorted(grupo, key=lambda i: i.properties.get("eo:cloud_cover", 100))[:cuota]]
    print(f"  {coleccion} {fechas}: {len(items)} de {total} escenas", flush=True)
    return items


def guardar(arr: xr.DataArray | xr.Dataset, ruta: Path, nodata) -> None:
    tmp = ruta.with_suffix(".tmp.tif")
    arr.rio.to_raster(tmp, compress="deflate", tiled=True, blockxsize=512, blockysize=512,
                      predictor=2, nodata=nodata, windowed=True, lock=False)
    tmp.rename(ruta)  # escribir aparte y renombrar: un corte no deja un archivo a medias
    print(f"  listo {ruta.name}", flush=True)


def s2_reflectancia(items, caja, epsg: int, resolucion: int, bandas: list[str]) -> xr.Dataset:
    """Reflectancia de superficie (0 a 1) sin nubes. Desde la línea base 04.00
    (enero de 2022) ESA suma 1000 a cada valor: se resta según la escena."""
    ds = cargar(items, bands=bandas + ["SCL"], bbox=caja, crs=f"EPSG:{epsg}", resolution=resolucion,
              chunks={"x": 1024, "y": 1024}, groupby="solar_day", dtype="uint16", nodata=0)
    base = {}
    for it in items:
        dia = np.datetime64(it.datetime.date(), "D")
        base[dia] = it.properties.get("s2:processing_baseline", "00.00") >= "04.00"
    desplazamiento = xr.DataArray([1000 if base.get(np.datetime64(t, "D"), False) else 0 for t in ds.time.values],
                                  dims="time", coords={"time": ds.time})
    limpio = ds["SCL"].isin(SCL_BUENOS)
    refl = {b: ((ds[b].astype("float32") - desplazamiento) / 10000).where(limpio & (ds[b] > 0)) for b in bandas}
    return xr.Dataset(refl)


def bandas_s2(args, caja) -> None:
    ruta = args.salida / f"s2_bandas_{args.bandas.replace('/', '_')}.tif"
    if ruta.exists():
        return
    items = buscar("sentinel-2-l2a", caja, args.bandas, nubes=20, maximo=16)
    refl = s2_reflectancia(items, caja, args.epsg, 10, BANDAS_S2).median("time")
    salida = (refl.to_array("banda") * 10000).round().fillna(0).astype("uint16")
    salida = salida.assign_coords(banda=BANDAS_S2).rio.write_crs(args.epsg)
    salida.attrs["long_name"] = BANDAS_S2
    guardar(salida, ruta, 0)


def indices_s2(args, caja) -> None:
    inicio, fin = (dt.date.fromisoformat(f"{m}-01") for m in args.indices.split("/"))
    mes = inicio
    while mes <= fin:
        siguiente = (mes.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        ruta = args.salida / f"s2_indices_{mes:%Y-%m}.tif"
        if not ruta.exists():
            items = buscar("sentinel-2-l2a", caja, f"{mes}/{siguiente - dt.timedelta(days=1)}", nubes=80, maximo=8)
            if len(items):
                r = s2_reflectancia(items, caja, args.epsg, 10, ["B03", "B04", "B08", "B12"])
                nd = lambda a, b: (a - b) / (a + b)
                idx = xr.concat([nd(r.B08, r.B04), nd(r.B03, r.B08), nd(r.B08, r.B12)], dim="banda").median("time")
                salida = (idx * 10000).round().fillna(-32768).astype("int16")
                salida = salida.assign_coords(banda=["NDVI", "NDWI", "NBR"]).rio.write_crs(args.epsg)
                salida.attrs["long_name"] = ["NDVI", "NDWI", "NBR"]
                guardar(salida, ruta, -32768)
        mes = siguiente


def lst_landsat(args, caja) -> None:
    """Temperatura de superficie de Landsat Collection 2 nivel 2 (banda lwir11).
    Escala de USGS: K = DN × 0.00341802 + 149.0. Se enmascaran nubes y sombras
    con QA_PIXEL (bits 3 y 4) y se toma la mediana de marzo a mayo."""
    a0, a1 = (int(a) for a in args.lst.split("/"))
    for anio in range(a0, a1 + 1):
        ruta = args.salida / f"lst_secas_{anio}.tif"
        if ruta.exists():
            continue
        items = buscar("landsat-c2-l2", caja, f"{anio}-03-01/{anio}-05-31", nubes=50,
                       extra={"platform": {"in": ["landsat-8", "landsat-9"]}})
        if not len(items):
            continue
        ds = cargar(items, bands=["lwir11", "qa_pixel"], bbox=caja, crs=f"EPSG:{args.epsg}", resolution=30,
                  chunks={"x": 1024, "y": 1024}, groupby="solar_day")
        nubes = ((ds.qa_pixel & (1 << 3)) > 0) | ((ds.qa_pixel & (1 << 4)) > 0)
        celsius = (ds.lwir11.astype("float32") * 0.00341802 + 149.0 - 273.15).where(~nubes & (ds.lwir11 > 0))
        salida = (celsius.median("time") * 100).round().fillna(-32768).astype("int16").rio.write_crs(args.epsg)
        salida.attrs["long_name"] = "LST °C × 100"
        guardar(salida, ruta, -32768)


def worldcover(args, caja) -> None:
    ruta = args.salida / "worldcover_2021.tif"
    if ruta.exists():
        return
    items = buscar("esa-worldcover", caja, "2021-01-01/2021-12-31")
    ds = cargar(items, bands=["map"], bbox=caja, crs=f"EPSG:{args.epsg}", resolution=10, chunks={"x": 1024, "y": 1024})
    guardar(ds["map"].isel(time=0).astype("uint8").rio.write_crs(args.epsg), ruta, 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--caja", required=True, help="oeste,sur,este,norte en grados")
    ap.add_argument("--epsg", type=int, required=True, help="UTM de la zona, p. ej. 32613 (zona 13N)")
    ap.add_argument("--bandas", help="periodo del compuesto de 10 bandas, AAAA-MM-DD/AAAA-MM-DD")
    ap.add_argument("--indices", help="meses de NDVI, NDWI y NBR, AAAA-MM/AAAA-MM")
    ap.add_argument("--lst", help="años de temperatura de secas, AAAA/AAAA")
    ap.add_argument("--worldcover", action="store_true")
    ap.add_argument("--hilos", type=int, default=3)
    args = ap.parse_args()
    args.salida = args.salida.expanduser()
    args.salida.mkdir(parents=True, exist_ok=True)
    caja = [float(v) for v in args.caja.split(",")]
    import dask
    import rioxarray  # noqa: F401  (registra .rio)

    # Pocos hilos: la mediana carga todas las fechas de un bloque a la vez, y la
    # máquina comparte RAM con otros servicios.
    dask.config.set(scheduler="threads", num_workers=args.hilos)

    if args.worldcover:
        worldcover(args, caja)
    if args.bandas:
        bandas_s2(args, caja)
    if args.lst:
        lst_landsat(args, caja)
    if args.indices:
        indices_s2(args, caja)


if __name__ == "__main__":
    main()
