# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "xlrd", "geopandas>=1.0", "pyogrio"]
# ///
"""Cruce de los AGEB urbanos del Marco Geoestadístico 2020 (INEGI) con el Índice de
marginación urbana 2020 (CONAPO), estado completo, solo con los zips del productor.
Ver docs/producto/comparacion-ciudades.md, sección "Cruce AGEB e IMU".

    uv run --script scripts/ambiental/cruce_imu_ageb.py --crudos DIR --salida DIR [--anterior ZIP]

`--crudos` trae, tal como se bajan: 19_nuevoleon.zip y 22_queretaro.zip (INEGI) e
IMU_2020.zip (CONAPO); se cruza cada estado cuyo zip esté. `--anterior` es
marginacion_temperatura_2020_GDL_MTY_QRO.zip, para comparar valor por valor.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

AQUI = Path(__file__).parent
ESTADOS = {"14": ("JAL", "14_jalisco.zip"), "19": ("NL", "19_nuevoleon.zip"), "22": ("QRO", "22_queretaro.zip")}
METROPOLI = {"14": "Guadalajara", "19": "Monterrey", "22": "Querétaro"}
INDICADORES = ["P6A14NAE", "SBASC", "PSDSS", "OVSDE", "OVSEE", "OVSAE", "OVPT", "OVSREF", "OVSINT", "OVSCEL", "OVHAC"]
IMU = ["NOM_MUN", "NOM_LOC", "POB_TOTAL"] + INDICADORES + ["IM_2020", "GM_2020", "IMN_2020"]
GRADOS = {"Muy bajo": 1, "Bajo": 2, "Medio": 3, "Alto": 4, "Muy alto": 5}


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def metropolis(ent: str) -> set[str]:
    m = pd.read_csv(AQUI / "metropolis_2020_municipios.csv", dtype=str)
    return set(m.loc[m["clave_metropoli"] == f"{ent}.1.01", "cvegeo"])


def leer_imu(crudos: Path) -> pd.DataFrame:
    with zipfile.ZipFile(crudos / "IMU_2020.zip") as z:
        d = pd.read_excel(z.open("IMU_2020.xls"), sheet_name="IMU_2020", dtype={"CVE_AGEB": str})
    assert d["CVE_AGEB"].is_unique and (d["CVE_AGEB"].str.len() == 13).all()
    return d


def cruzar(crudos: Path, ent: str, imu: pd.DataFrame) -> tuple[gpd.GeoDataFrame, dict]:
    sigla, archivo = ESTADOS[ent]
    g = gpd.read_file(f"zip://{(crudos / archivo).as_posix()}!conjunto_de_datos/{ent}a.shp")
    assert g["CVEGEO"].is_unique
    # En el marco CVE_AGEB son 4 caracteres; en el IMU es la clave completa (= CVEGEO).
    i = imu[imu["CVE_AGEB"].str[:2] == ent]
    g = g.merge(i[["CVE_AGEB"] + IMU].rename(columns={"CVE_AGEB": "CVEGEO"}), on="CVEGEO", how="left")
    g = g.rename(columns={"CVE_AGEB": "AGEB"})
    g["GM_NUM"] = g["GM_2020"].map(GRADOS).astype("Int64")
    g["METROPOLI"] = np.where((g["CVE_ENT"] + g["CVE_MUN"]).isin(metropolis(ent)), METROPOLI[ent], "Ninguna")
    huerfanos = sorted(set(i["CVE_AGEB"]) - set(g["CVEGEO"]))
    conteo = {
        "estado": sigla,
        "agebs_urbanos_marco": len(g),
        "agebs_en_imu": len(i),
        "cruzados": int(g["IM_2020"].notna().sum()),
        "marco_sin_indice": int(g["IM_2020"].isna().sum()),
        "imu_sin_poligono": len(huerfanos),
        "cruzados_en_metropoli": int((g["IM_2020"].notna() & (g["METROPOLI"] != "Ninguna")).sum()),
    }
    assert not huerfanos, f"{sigla}: claves del IMU sin polígono: {huerfanos[:5]}"
    return g, conteo


def comparar(anterior: Path, g: pd.DataFrame) -> pd.DataFrame:
    with zipfile.ZipFile(anterior) as z:
        nombre = next(n for n in z.namelist() if n.endswith("tablas/agebs_2020.csv"))
        a = pd.read_csv(z.open(nombre), dtype={"CVEGEO": str})
    a = a[a["IM_2020"].notna()]
    m = a.merge(g, on="CVEGEO", suffixes=("_ant", ""))
    filas = []
    for ciudad, t in m.groupby("CIUDAD"):
        fila = {"ciudad": ciudad, "agebs_entrega_anterior": int((a["CIUDAD"] == ciudad).sum()), "encontrados": len(t)}
        for k in INDICADORES + ["IM_2020", "IMN_2020"]:
            fila[f"max_dif_{k}"] = float((t[f"{k}_ant"] - t[k]).abs().max())
        fila["GM_2020_distintos"] = int((t["GM_2020_ant"] != t["GM_2020"]).sum())
        filas.append(fila)
    return pd.DataFrame(filas)


def escribir_shp(g: gpd.GeoDataFrame, ruta: Path) -> None:
    g.to_file(ruta, driver="ESRI Shapefile", encoding="utf-8", promote_to_multi=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crudos", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--anterior", type=Path)
    a = ap.parse_args()
    if a.salida.exists():
        sys.exit(f"{a.salida} ya existe: borrarla o dar otra --salida")
    estados = [e for e, (_, z) in ESTADOS.items() if (a.crudos / z).exists()]
    if not estados:
        sys.exit("no hay zips del marco en --crudos")
    for sub in ("shapefiles", "tablas", "procedencia"):
        (a.salida / sub).mkdir(parents=True)
    imu = leer_imu(a.crudos)
    conteos, tablas = [], []
    for ent in estados:
        sigla = ESTADOS[ent][0]
        g, c = cruzar(a.crudos, ent, imu)
        conteos.append(c)
        con = g[g["IM_2020"].notna()].copy()
        con["POB_TOTAL"] = con["POB_TOTAL"].astype("int32")
        con["GM_NUM"] = con["GM_NUM"].astype("int32")
        escribir_shp(con, a.salida / "shapefiles" / f"AGEB_{sigla}_IMU_2020.shp")
        # El DBF no guarda vacíos y ArcGIS los lee como 0: los AGEB sin índice van aparte.
        escribir_shp(g.loc[g["IM_2020"].isna(), ["CVEGEO", "CVE_ENT", "CVE_MUN", "CVE_LOC", "AGEB", "METROPOLI", "geometry"]],
                     a.salida / "shapefiles" / f"AGEB_{sigla}_sin_indice.shp")
        tablas.append(g.drop(columns="geometry"))
        print(c)
    t, p = a.salida / "tablas", a.salida / "procedencia"
    tabla = pd.concat(tablas, ignore_index=True)
    tabla.to_csv(t / "agebs_imu_2020.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(conteos).to_csv(t / "conteos.csv", index=False, encoding="utf-8-sig")
    archivos = ["IMU_2020.zip"] + [ESTADOS[e][1] for e in estados]
    pd.DataFrame({"archivo": archivos, "sha256": [sha256(a.crudos / f) for f in archivos]}).to_csv(
        p / "archivos_de_entrada.csv", index=False, encoding="utf-8-sig")
    if a.anterior:
        comp = comparar(a.anterior, tabla)
        comp.to_csv(t / "comparacion_entrega_anterior.csv", index=False, encoding="utf-8-sig")
        print(comp.T.to_string())
    shutil.copy(AQUI / "LEEME_cruce_imu_ageb.txt", a.salida / "LEEME.txt")


if __name__ == "__main__":
    main()
