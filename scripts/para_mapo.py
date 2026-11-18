# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyogrio", "pandas", "rasterio", "numpy"]
# ///
"""Prepara un paquete (de `scripts/ambiental/recorte.py`, `imagenes.py` o el
dataset de vivienda) para subirlo a Mapo como datos propios de un equipo, dentro
de los límites de `docs/producto/datos-propios.md`:

- 50 MB por archivo, 100 columnas, 50,000 renglones, 10,000 geometrías que no
  sean punto y 2,000,000 de vértices por capa.
- Un ráster se ve solo en su primera banda, como imagen de hasta 2,048 px.

    uv run --script scripts/para_mapo.py PAQUETE SALIDA [--columnas-agebs POBTOT,VIVTOT,...]

Qué hace:
- Cada capa de `zona.gpkg` (o cada `.geojson`) va a su propio `.gpkg`. Con más de
  100 columnas se queda con las que no empiezan con `c_` y con las del censo de
  `--columnas-agebs`; con más de 2 millones de vértices se simplifica (~5 m).
  Con más de 50,000 renglones o 10,000 polígonos no se recorta: se avisa.
- Si el paquete trae `diccionario_capas.csv` y `procedencia.csv` (los de
  `recorte.py`), cada renglón lleva su procedencia en las columnas que Mapo
  reserva: `fuente`, `url`, `fecha_dato`, `fecha_consulta` y `nivel` (aquí
  siempre "registro oficial"). `verificado` se queda fuera: dice que una persona
  confirmó el renglón, y eso no pasó.
- `.csv` con columnas `lon` y `lat`: se copia (Mapo los lee como tabla con
  coordenadas).
- Rásters: el compuesto de 10 bandas de Sentinel-2 se vuelve NDVI; los índices
  mensuales, su banda de NDVI; los demás, su primera banda. Si pasan de 50 MB se
  reducen a la mitad de resolución hasta caber.
- Escribe `para_mapo.csv`: archivo, qué es, renglones, tamaño y si cabe.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyogrio
import rasterio
from rasterio.enums import Resampling

LIMITE_MB = 50
MAX_COLUMNAS = 100
MAX_RENGLONES = 50_000
MAX_POLIGONOS = 10_000
MAX_VERTICES = 2_000_000
CENSO_POR_OMISION = ["POBTOT", "POBFEM", "POBMAS", "P_0A2", "P_60YMAS", "GRAPROES", "PSINDER", "PCON_DISC",
                     "VIVTOT", "TVIVHAB", "VIVPAR_DES", "VPH_PISOTI", "VPH_AGUAFV", "VPH_NODREN", "VPH_C_ELEC",
                     "VPH_AUTOM", "VPH_INTER", "PEA", "POCUPADA", "P15YM_SE"]


def vertices(gdf: gpd.GeoDataFrame) -> int:
    import shapely
    return int(shapely.get_num_coordinates(gdf.geometry.values).sum())


def procedencias(paquete: Path) -> dict[str, dict[str, str]]:
    """Capa -> columnas de procedencia, de los CSV que deja `recorte.py`."""
    dic, pro = paquete / "diccionario_capas.csv", paquete / "procedencia.csv"
    if not dic.exists():
        return {}
    descargas = {}
    if pro.exists():
        with open(pro, encoding="utf-8") as f:
            descargas = {r["capa"]: r for r in csv.DictReader(f)}
    salida = {}
    with open(dic, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = descargas.get(r["capa"], {})
            salida[r["capa"]] = {
                "fuente": r["fuente"],
                "url": d.get("url") or r["url"],
                "fecha_dato": r["fecha_dato"],
                "fecha_consulta": (d.get("fecha_descarga") or "")[:10],
                "nivel": "registro oficial",
            }
    return salida


def vectorial(gdf: gpd.GeoDataFrame, destino: Path, censo: list[str],
              procedencia: dict[str, str] | None = None) -> tuple[str, bool]:
    notas, cabe = [], True
    procedencia = {k: v for k, v in (procedencia or {}).items() if v}
    choque = [k for k in procedencia if k in gdf.columns]
    if choque:
        notas.append(f"ya traía {', '.join(choque)}: no se le puso procedencia")
        procedencia = {}
    columnas = [c for c in gdf.columns if c != "geometry"]
    tope = MAX_COLUMNAS - len(procedencia)
    if len(columnas) >= tope:
        quedan = [c for c in columnas if not c.startswith("c_")] + [f"c_{c}" for c in censo if f"c_{c}" in gdf.columns]
        gdf = gdf[quedan[: tope - 1] + ["geometry"]]
        notas.append(f"{len(columnas)} columnas -> {len(quedan[:tope - 1])}")
    if procedencia:
        gdf = gdf.assign(**procedencia)
    if vertices(gdf) > MAX_VERTICES:
        gdf = gdf.assign(geometry=gdf.geometry.simplify(0.00005, preserve_topology=True))
        notas.append(f"simplificada a {vertices(gdf):,} vértices")
    no_puntos = int((~gdf.geom_type.isin(["Point", "MultiPoint"])).sum())
    if len(gdf) > MAX_RENGLONES or no_puntos > MAX_POLIGONOS:
        cabe = False
        notas.append(f"NO CABE: {len(gdf):,} renglones, {no_puntos:,} polígonos")
    gdf.to_file(destino, driver="GPKG")
    return "; ".join(notas), cabe


def raster(origen: Path, destino: Path) -> str:
    with rasterio.open(origen) as r:
        perfil = r.profile.copy()
        nombres = [d or "" for d in r.descriptions]
        if r.count >= 10 and "B08" in nombres and "B04" in nombres:  # compuesto de Sentinel-2 -> NDVI
            b8 = r.read(nombres.index("B08") + 1).astype("float32")
            b4 = r.read(nombres.index("B04") + 1).astype("float32")
            valido = (b8 > 0) & (b4 > 0)
            datos = np.where(valido, np.round((b8 - b4) / np.maximum(b8 + b4, 1) * 10000), -32768).astype("int16")
            perfil.update(dtype="int16", nodata=-32768)
            que = "NDVI × 10000 del compuesto"
        elif "NDVI" in nombres:
            datos, que = r.read(nombres.index("NDVI") + 1), "NDVI × 10000 del mes"
        else:
            datos, que = r.read(1), f"banda 1 ({nombres[0] or 'sin nombre'})"
    perfil.update(count=1, compress="deflate", tiled=True, blockxsize=512, blockysize=512, predictor=2)
    factor = 1
    while True:
        a = datos[::factor, ::factor] if factor > 1 else datos
        p = perfil | {"height": a.shape[0], "width": a.shape[1],
                      "transform": perfil["transform"] * perfil["transform"].scale(factor, factor)}
        with rasterio.open(destino, "w", **p) as dst:
            dst.write(a, 1)
            # Mapo muestra esta descripción junto al valor: la escala viaja con el
            # archivo y no solo en para_mapo.csv.
            dst.set_band_description(1, que)
        if destino.stat().st_size <= LIMITE_MB * 1024 * 1024:
            break
        factor *= 2
    return que + (f", reducido {factor}x" if factor > 1 else "")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paquete", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--columnas-agebs", default=",".join(CENSO_POR_OMISION),
                    help="variables del censo (nombres de INEGI) que se conservan si una capa pasa de 100 columnas")
    a = ap.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)
    censo = [c.strip() for c in a.columnas_agebs.split(",") if c.strip()]
    registro = []
    procedencia = procedencias(a.paquete)

    for gpkg in sorted(a.paquete.glob("*.gpkg")):
        for capa in pyogrio.list_layers(gpkg)[:, 0]:
            destino = a.salida / f"{capa}.gpkg"
            nota, cabe = vectorial(gpd.read_file(gpkg, layer=capa), destino, censo, procedencia.get(capa))
            registro.append((destino.name, f"capa {capa} de {gpkg.name}", nota, cabe))
    for gj in sorted(a.paquete.glob("*.geojson")):
        destino = a.salida / f"{gj.stem}.gpkg"
        nota, cabe = vectorial(gpd.read_file(gj), destino, censo)
        registro.append((destino.name, gj.name, nota, cabe))
    for tabla in sorted(a.paquete.glob("*.csv")) + sorted((a.paquete / "tablas").glob("*.csv")):
        with open(tabla, encoding="utf-8") as f:
            encabezado = next(csv.reader(f), [])
        if {"lon", "lat"} <= set(encabezado) or {"longitud", "latitud"} <= set(encabezado):
            shutil.copy(tabla, a.salida / tabla.name)
            registro.append((tabla.name, "tabla con coordenadas", "", True))
    for tif in sorted(a.paquete.rglob("*.tif")):
        if tif.name.endswith(".tmp.tif") or ".bloques_" in str(tif):
            continue
        destino = a.salida / tif.name
        registro.append((destino.name, raster(tif, destino), "", True))

    with open(a.salida / "para_mapo.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["archivo", "que_es", "nota", "mb", "cabe"])
        for nombre, que, nota, cabe in registro:
            mb = round((a.salida / nombre).stat().st_size / 1048576, 1)
            w.writerow([nombre, que, nota, mb, cabe and mb <= LIMITE_MB])
    total = sum((a.salida / r[0]).stat().st_size for r in registro) / 1048576
    print(f"{len(registro)} archivos en {a.salida}, {total:.0f} MB en total (cuota del equipo: 500 MB)")
    for nombre, que, nota, cabe in registro:
        if not cabe or nota:
            print(f"  {nombre}: {nota or que}")


if __name__ == "__main__":
    main()
