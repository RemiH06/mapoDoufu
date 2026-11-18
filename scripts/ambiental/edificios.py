# /// script
# requires-python = ">=3.11"
# dependencies = ["duckdb>=1.1", "geopandas>=1.0", "pyogrio", "shapely>=2"]
# ///
"""Huellas de edificios de Overture Maps (tema buildings) recortadas a una caja.

    uv run --script scripts/ambiental/edificios.py --salida SALIDA --caja=O,S,E,N [--version 2026-11-18.0]

Overture junta OpenStreetMap, Microsoft (ML Buildings), Google (Open Buildings) y
otras fuentes en una sola capa sin duplicados, y dice de cuál viene cada edificio.
Se lee directo de los GeoParquet públicos en S3 con DuckDB: solo baja los grupos de
renglones cuya caja toca la pedida. Licencia ODbL (por OSM); ver docs/fuentes/edificios.md.

Deja en SALIDA:
- `edificios.gpkg`, capa `edificios`, EPSG:4326: `id` de Overture, `fuente`
  (OpenStreetMap, Microsoft ML Buildings, Google Open Buildings...), `id_fuente`,
  `altura_m` y `pisos` cuando la fuente los trae (casi nunca fuera de OSM), `clase`,
  `area_m2` (calculada en EPSG:6372) y la versión de Overture.
- `procedencia_edificios.csv`: versión, caja, consulta y cuántos edificios por fuente.

Un edificio entra si su caja toca la caja pedida: los de la orilla salen completos.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

import duckdb
import geopandas as gpd
import shapely

VERSION = "2026-11-18.0"
RUTA = "s3://overturemaps-us-west-2/release/{version}/theme=buildings/type=building/*"


def leer(caja: tuple[float, float, float, float], version: str) -> tuple[gpd.GeoDataFrame, str]:
    o, s, e, n = caja
    con = duckdb.connect()
    for sql in ("INSTALL spatial", "LOAD spatial", "INSTALL httpfs", "LOAD httpfs", "SET s3_region='us-west-2'"):
        con.execute(sql)
    consulta = f"""
        SELECT id,
               sources[1].dataset AS fuente,
               sources[1].record_id AS id_fuente,
               height AS altura_m,
               num_floors AS pisos,
               class AS clase,
               ST_AsWKB(geometry) AS wkb
        FROM read_parquet('{RUTA.format(version=version)}', hive_partitioning = 1)
        WHERE bbox.xmin <= {e} AND bbox.xmax >= {o} AND bbox.ymin <= {n} AND bbox.ymax >= {s}
    """
    df = con.execute(consulta).fetch_df()
    geom = shapely.from_wkb(df.pop("wkb").map(bytes))
    gdf = gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")
    gdf["area_m2"] = gdf.to_crs(6372).area.round(1)
    gdf["version_overture"] = version
    return gdf, " ".join(consulta.split())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--caja", required=True, help="oeste,sur,este,norte en grados")
    ap.add_argument("--version", default=VERSION, help="versión de Overture (release/AAAA-MM-DD.N)")
    a = ap.parse_args()
    caja = tuple(float(v) for v in a.caja.split(","))
    if len(caja) != 4 or caja[0] >= caja[2] or caja[1] >= caja[3]:
        sys.exit("--caja debe ser oeste,sur,este,norte")
    salida = a.salida.expanduser()
    salida.mkdir(parents=True, exist_ok=True)

    gdf, consulta = leer(caja, a.version)
    gdf.to_file(salida / "edificios.gpkg", layer="edificios", driver="GPKG")

    por_fuente = gdf["fuente"].fillna("(sin fuente)").value_counts()
    with open(salida / "procedencia_edificios.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["version_overture", "caja", "fecha_consulta", "fuente", "edificios", "consulta"])
        hoy = dt.date.today().isoformat()
        for fuente, cuantos in por_fuente.items():
            w.writerow([a.version, a.caja, hoy, fuente, cuantos, consulta])

    print(f"{len(gdf):,} edificios en {salida / 'edificios.gpkg'}")
    for fuente, cuantos in por_fuente.items():
        print(f"  {fuente}: {cuantos:,}")
    con_altura = gdf["altura_m"].notna().sum()
    print(f"  con altura: {con_altura:,}; área total {gdf['area_m2'].sum() / 1e4:,.0f} ha")


if __name__ == "__main__":
    main()
