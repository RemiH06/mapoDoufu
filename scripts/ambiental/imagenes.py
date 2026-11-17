# /// script
# requires-python = ">=3.11"
# dependencies = ["pystac-client", "planetary-computer", "odc-stac", "rioxarray", "xarray", "dask", "numpy", "rasterio"]
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

**Por bloques.** odc-stac firma las URL al armar el cálculo, no al leer, y la
firma de Planetary Computer caduca en cerca de una hora. Un producto grande
leído de una vez perdía en silencio lo que se leía al final (el 22 % sur del
primer compuesto de Autlán). Por eso cada producto se arma en bloques de
`--bloque` grados: cada bloque busca, firma, calcula y se guarda en minutos, y
al final se unen. Un bloque que falla se reintenta tres veces; si sigue
fallando, el producto no se escribe (falla en voz alta) y relanzar retoma
desde los bloques que faltan.

Ver `docs/fuentes/imagenes.md`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import time
from pathlib import Path
from typing import Callable

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
# Más que esto sin dato en el producto final es un hueco que hay que explicar.
MAX_SIN_DATO = 0.02

# Reintentos de GDAL ante cortes de red al leer los COG remotos.
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "6")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "3")


def catalogo() -> pystac_client.Client:
    return pystac_client.Client.open(STAC)


def cargar(items, **kw):
    """Firma al armar el cálculo (lo que hace odc-stac con `patch_url`); por eso
    cada bloque se calcula justo después. Una lectura que falla levanta error:
    saltarla dejaba huecos sin aviso."""
    return load(items, patch_url=planetary_computer.sign, fail_on_error=True, **kw)


def buscar(coleccion: str, caja, fechas: str, nubes: int | None = None, extra: dict | None = None,
           maximo: int | None = None, decir: bool = True):
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
    if decir:
        print(f"    {coleccion} {fechas}: {len(items)} de {total} escenas", flush=True)
    return items


def bloques(caja, paso: float) -> list[list[float]]:
    o, s, e, n = caja
    xs = list(np.arange(o, e, paso)) + [e]
    ys = list(np.arange(s, n, paso)) + [n]
    return [[x0, y0, x1, y1] for y0, y1 in zip(ys, ys[1:]) for x0, x1 in zip(xs, xs[1:]) if x1 - x0 > 1e-9 and y1 - y0 > 1e-9]


def producir(ruta: Path, nodata, construir: Callable[[list[float]], xr.DataArray | None], args, caja,
             descripciones: list[str]) -> None:
    """Arma `ruta` bloque por bloque, une los bloques y revisa que no queden huecos."""
    if ruta.exists():
        return
    import rasterio
    from rasterio.merge import merge

    carpeta = ruta.parent / f".bloques_{ruta.stem}"
    carpeta.mkdir(exist_ok=True)
    partes = bloques(caja, args.bloque)
    print(f"  {ruta.name}: {len(partes)} bloques", flush=True)
    for i, sub in enumerate(partes):
        destino = carpeta / f"{i:03d}.tif"
        if destino.exists():
            continue
        for intento in range(1, 4):
            try:
                arr = construir(sub)
                if arr is None:  # sin escenas en ese bloque y periodo
                    break
                arr = arr.compute()
                tmp = destino.with_suffix(".tmp.tif")
                arr.rio.to_raster(tmp, nodata=nodata, compress="deflate", tiled=True)
                tmp.rename(destino)
                break
            except Exception as error:
                print(f"    bloque {i}: {type(error).__name__}: {str(error)[:200]} (intento {intento})", flush=True)
                time.sleep(20 * intento)
        else:
            raise RuntimeError(f"{ruta.name}: el bloque {i} falló tres veces; relanzar retoma desde ahí")
    hechos = sorted(carpeta.glob("[0-9][0-9][0-9].tif"))
    if not hechos:
        print(f"  {ruta.name}: sin escenas, no se escribe", flush=True)
        return
    fuentes = [rasterio.open(p) for p in hechos]
    try:
        datos, transformada = merge(fuentes, nodata=nodata)
        perfil = fuentes[0].profile | {"height": datos.shape[1], "width": datos.shape[2], "transform": transformada,
                                       "nodata": nodata, "compress": "deflate", "tiled": True,
                                       "blockxsize": 512, "blockysize": 512, "count": datos.shape[0]}
    finally:
        for f in fuentes:
            f.close()
    sin_dato = float(np.mean(np.all(datos == nodata, axis=0)))
    tmp = ruta.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **perfil) as dst:
        dst.write(datos)
        for b, d in enumerate(descripciones, 1):
            dst.set_band_description(b, d)
    tmp.rename(ruta)
    shutil.rmtree(carpeta)
    aviso = f"  ¡HUECO! {sin_dato:.1%} sin dato" if sin_dato > MAX_SIN_DATO else f"{sin_dato:.1%} sin dato"
    print(f"  listo {ruta.name}: {aviso}", flush=True)


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
    def construir(sub):
        items = buscar("sentinel-2-l2a", sub, args.bandas, nubes=20, maximo=16, decir=False)
        if not items:
            return None
        refl = s2_reflectancia(items, sub, args.epsg, 10, BANDAS_S2).median("time")
        # En agua la reflectancia puede quedar negativa al restar el desplazamiento de
        # la línea base; convertida a uint16 daba la vuelta (manchas en las presas).
        # Se recorta a 1: el 0 queda reservado para "sin dato".
        refl = (refl.to_array("banda") * 10000).round().clip(1, 65535)
        return refl.fillna(0).astype("uint16").rio.write_crs(args.epsg)

    producir(args.salida / f"s2_bandas_{args.bandas.replace('/', '_')}.tif", 0, construir, args, caja, BANDAS_S2)


def indices_s2(args, caja) -> None:
    inicio, fin = (dt.date.fromisoformat(f"{m}-01") for m in args.indices.split("/"))
    mes = inicio
    while mes <= fin:
        siguiente = (mes.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        periodo = f"{mes}/{siguiente - dt.timedelta(days=1)}"

        def construir(sub, periodo=periodo):
            items = buscar("sentinel-2-l2a", sub, periodo, nubes=80, maximo=8, decir=False)
            if not items:
                return None
            r = s2_reflectancia(items, sub, args.epsg, 10, ["B03", "B04", "B08", "B12"])
            nd = lambda a, b: (a - b) / (a + b)
            idx = xr.concat([nd(r.B08, r.B04), nd(r.B03, r.B08), nd(r.B08, r.B12)], dim="banda").median("time")
            return (idx * 10000).round().fillna(-32768).astype("int16").rio.write_crs(args.epsg)

        producir(args.salida / f"s2_indices_{mes:%Y-%m}.tif", -32768, construir, args, caja, ["NDVI", "NDWI", "NBR"])
        mes = siguiente


def lst_landsat(args, caja) -> None:
    """Temperatura de superficie de Landsat Collection 2 nivel 2 (banda lwir11).
    Escala de USGS: K = DN × 0.00341802 + 149.0. Se enmascaran nubes y sombras
    con QA_PIXEL (bits 3 y 4) y se toma la mediana de marzo a mayo."""
    a0, a1 = (int(a) for a in args.lst.split("/"))
    for anio in range(a0, a1 + 1):
        def construir(sub, anio=anio):
            items = buscar("landsat-c2-l2", sub, f"{anio}-03-01/{anio}-05-31", nubes=50,
                           extra={"platform": {"in": ["landsat-8", "landsat-9"]}}, decir=False)
            if not items:
                return None
            ds = cargar(items, bands=["lwir11", "qa_pixel"], bbox=sub, crs=f"EPSG:{args.epsg}", resolution=30,
                        chunks={"x": 1024, "y": 1024}, groupby="solar_day")
            nubes = ((ds.qa_pixel & (1 << 3)) > 0) | ((ds.qa_pixel & (1 << 4)) > 0)
            celsius = (ds.lwir11.astype("float32") * 0.00341802 + 149.0 - 273.15).where(~nubes & (ds.lwir11 > 0))
            return (celsius.median("time") * 100).round().fillna(-32768).astype("int16").rio.write_crs(args.epsg)

        producir(args.salida / f"lst_secas_{anio}.tif", -32768, construir, args, caja, ["LST °C x 100"])


def worldcover(args, caja) -> None:
    def construir(sub):
        items = buscar("esa-worldcover", sub, "2021-01-01/2021-12-31", decir=False)
        if not items:
            return None
        ds = cargar(items, bands=["map"], bbox=sub, crs=f"EPSG:{args.epsg}", resolution=10,
                    chunks={"x": 1024, "y": 1024})
        return ds["map"].isel(time=0).astype("uint8").rio.write_crs(args.epsg)

    producir(args.salida / "worldcover_2021.tif", 0, construir, args, caja, ["clase ESA WorldCover"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--caja", required=True, help="oeste,sur,este,norte en grados")
    ap.add_argument("--epsg", type=int, required=True, help="UTM de la zona, p. ej. 32613 (zona 13N)")
    ap.add_argument("--bandas", help="periodo del compuesto de 10 bandas, AAAA-MM-DD/AAAA-MM-DD")
    ap.add_argument("--indices", help="meses de NDVI, NDWI y NBR, AAAA-MM/AAAA-MM")
    ap.add_argument("--lst", help="años de temperatura de secas, AAAA/AAAA")
    ap.add_argument("--worldcover", action="store_true")
    ap.add_argument("--bloque", type=float, default=0.25, help="lado del bloque en grados (0.25 ≈ 27 km)")
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
