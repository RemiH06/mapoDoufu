# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "numpy", "xlrd"]
# ///
"""Marginación urbana 2010 de CONAPO por AGEB para las siete metrópolis de la comparación
de ciudades, y su comparación con 2020. Solo tablas, con los AGEB de cada censo.
Ver docs/producto/comparacion-ciudades.md, sección "Marginación 2010".

    uv run --script scripts/ambiental/marginacion_2010.py \
        --base10 Base_marginacion_AGEB_00-10.csv --imu20 IMU_2020.zip --salida marginacion_2010

Salidas en --salida:
    marginacion_ageb_2010.csv         contexto: un renglón por AGEB urbano de 2010
    comparacion_ageb_2010_2020.csv    un renglón por clave de AGEB, de 2010, de 2020 o de ambos
    resumen_ciudad_2010_2020.csv      un renglón por ciudad
    diccionario_campos.csv, fuentes.csv
"""
from __future__ import annotations

import argparse
import csv
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from ciudades import CIUDADES, MUNICIPIOS

GRADOS = ["Muy bajo", "Bajo", "Medio", "Alto", "Muy alto"]  # 1 = Muy bajo ... 5 = Muy alto
IND_2010 = ["P6A14NAE", "P15YMSSC", "PSDSS", "HFM15A49", "VSADV", "VSDRPFS", "VSECA", "VPTIERRA", "VHACINA", "VSREFRI"]
# Mismo indicador y misma unidad (porcentaje de personas) en los dos años.
COMPARABLES = [("P6A14NAE", "P6A14NAE", "no_asiste_6a14"), ("P15YMSSC", "SBASC", "sin_basica_15mas"),
               ("PSDSS", "PSDSS", "sin_derechohabiencia")]
# Mismo concepto, distinta unidad: 2010 cuenta viviendas y 2020 ocupantes.
ORIENTATIVOS = [("VPTIERRA", "OVPT", "piso_tierra"), ("VSREFRI", "OVSREF", "sin_refrigerador")]

DICCIONARIO = {
    "ciudad": "Metrópoli (delimitación Metrópolis de México 2020)",
    "cvegeo": "Clave de la AGEB urbana (13 caracteres: estado, municipio, localidad, AGEB)",
    "cve_mun": "Clave del municipio (5 caracteres)", "municipio": "Municipio", "localidad": "Localidad",
    "pob_2010": "Población total 2010 (CONAPO, del censo 2010)", "pob_2020": "Población total 2020 (CONAPO, del censo 2020)",
    "P6A14NAE": "% población de 6 a 14 años que no asiste a la escuela (2010)",
    "P15YMSSC": "% población de 15 años o más sin educación básica completa (2010)",
    "PSDSS": "% población sin derechohabiencia a servicios de salud (2010)",
    "HFM15A49": "% hijos fallecidos de las mujeres de 15 a 49 años (2010)",
    "VSADV": "% viviendas particulares habitadas sin agua entubada dentro de la vivienda (2010)",
    "VSDRPFS": "% viviendas particulares habitadas sin drenaje conectado a la red pública o fosa séptica (2010)",
    "VSECA": "% viviendas particulares habitadas sin excusado con conexión de agua (2010)",
    "VPTIERRA": "% viviendas particulares habitadas con piso de tierra (2010)",
    "VHACINA": "% viviendas particulares habitadas con algún nivel de hacinamiento (2010)",
    "VSREFRI": "% viviendas particulares habitadas sin refrigerador (2010)",
    "imu_2010": "Índice de marginación urbana 2010 (CONAPO; más alto = MÁS marginado, al revés que 2020)",
    "gmu_2010": "Grado de marginación urbana 2010 (CONAPO)",
    "im_2020": "Índice de marginación urbana 2020 (CONAPO; más alto = MENOS marginado)",
    "gm_2020": "Grado de marginación urbana 2020 (CONAPO)",
    "presencia": "en_ambos: la misma clave existe en 2010 y 2020; solo_2010 o solo_2020: INEGI la partió, la redibujó o es nueva",
    "grado_2010_num": "Grado 2010 en número: 1 Muy bajo a 5 Muy alto", "grado_2020_num": "Grado 2020 en número: 1 Muy bajo a 5 Muy alto",
    "cambio_grado": "grado_2020_num menos grado_2010_num; positivo = más marginado respecto al país que en 2010",
    "percentil_ciudad_2010": "Lugar del AGEB entre los de su ciudad en 2010, de 0 (menos marginado) a 100 (más marginado)",
    "percentil_ciudad_2020": "Lo mismo en 2020",
    "cambio_percentil": "percentil_ciudad_2020 menos percentil_ciudad_2010; positivo = se volvió relativamente más marginado dentro de su ciudad",
}
for _, _, n in COMPARABLES:
    DICCIONARIO[f"{n}_2010"] = f"{n.replace('_', ' ')}: % de personas, 2010 (comparable con 2020)"
    DICCIONARIO[f"{n}_2020"] = f"{n.replace('_', ' ')}: % de personas, 2020"
    DICCIONARIO[f"{n}_dif"] = f"{n.replace('_', ' ')}: 2020 menos 2010, en puntos porcentuales"
for _, _, n in ORIENTATIVOS:
    DICCIONARIO[f"{n}_viv_2010"] = f"{n.replace('_', ' ')}: % de VIVIENDAS, 2010 (orientativo)"
    DICCIONARIO[f"{n}_ocup_2020"] = f"{n.replace('_', ' ')}: % de OCUPANTES, 2020 (orientativo: no se resta con 2010)"

FUENTES = [
    ("Marginación urbana por AGEB 2000, 2005 y 2010", "CONAPO, Índice de marginación urbana",
     "https://www.gob.mx/conapo/documentos/indices-de-marginacion-1990-2010",
     "https://conapo.segob.gob.mx/work/models/CONAPO/Datos_Abiertos/AGEB_Urbana/Base_marginacion_AGEB_00-10.csv",
     "2026-11-19", "sha256 ac31daf76d99c8b139879f8c92416139a449d3d70917e2fc2eb218fb0b41ef8d. Se usan solo los renglones de 2010"),
    ("Metodología 2010", "CONAPO, Índice de marginación urbana 2010 (2012), cuadro 1.1 y anexo C",
     "https://www.gob.mx/conapo/documentos/indices-de-marginacion-1990-2010",
     "https://www.gob.mx/cms/uploads/attachment/file/671852/Indice_de_marginacion_urbana_2010_-_parte_1.pdf",
     "2026-11-19", "Definición de los 10 indicadores; componentes principales y estratificación de Dalenius y Hodges"),
    ("Marginación urbana por AGEB 2020", "CONAPO, Índice de marginación urbana 2020",
     "https://www.gob.mx/conapo/documentos/indices-de-marginacion-2020-284372",
     "https://conapo.segob.gob.mx/work/models/CONAPO/Datos_Abiertos/Marginacion/IMU_2020.zip",
     "2026-11-19", "sha256 17fdd6a31a57d4deb5519fe1e7bd58e7e52d115cf0474d6b59fbf9a52cde26b9 (el mismo de la comparación de ciudades)"),
    ("Municipios de cada metrópoli", "SEDATU, CONAPO e INEGI, Metrópolis de México 2020",
     "https://www.gob.mx/cms/uploads/sedatu/MM2020_06022024.pdf", "", "2026-11",
     "Se usa la delimitación de 2020 también para 2010, para comparar el mismo territorio"),
]


def municipios() -> dict[str, str]:
    """cvegeo del municipio -> clave corta de la ciudad."""
    claves = {v[0]: k for k, v in CIUDADES.items()}
    with open(MUNICIPIOS, encoding="utf-8") as f:
        return {r["cvegeo"]: claves[r["clave_metropoli"]] for r in csv.DictReader(f) if r["clave_metropoli"] in claves}


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.strip().replace("", np.nan), errors="coerce")


def leer_2010(ruta: Path, muns: dict[str, str]) -> pd.DataFrame:
    d = pd.read_csv(ruta, dtype=str, encoding="utf-8-sig")
    d = d[d[d.columns[-1]].str.strip() == "2010"].copy()  # la última columna es el año (AÑO)
    d["cvegeo"] = d["CVE_AGEB"].str.strip().str.zfill(13)
    d["cve_mun"] = d["CVE_MUN"].str.strip().str.zfill(5)
    d = d[d["cve_mun"].isin(muns)]
    assert d["cvegeo"].is_unique, "claves de AGEB repetidas en 2010"
    out = pd.DataFrame({"ciudad": d["cve_mun"].map(muns).map(lambda c: CIUDADES[c][1]), "cvegeo": d["cvegeo"],
                        "cve_mun": d["cve_mun"], "municipio": d["NOM_MUN"], "localidad": d["NOM_LOC"],
                        "pob_2010": num(d["POB_TOT"])})
    for c in IND_2010:
        out[c] = num(d[c])
    out["imu_2010"] = num(d["IMU"])
    out["gmu_2010"] = d["GMU"].str.strip()
    return out.sort_values(["ciudad", "cvegeo"]).reset_index(drop=True)


def leer_2020(ruta: Path, muns: dict[str, str]) -> pd.DataFrame:
    with zipfile.ZipFile(ruta) as z:
        d = pd.read_excel(z.open("IMU_2020.xls"), sheet_name="IMU_2020", dtype={"CVE_AGEB": str})
    d["cve_mun"] = d["CVE_AGEB"].str[:5]
    d = d[d["cve_mun"].isin(muns)].rename(columns={"CVE_AGEB": "cvegeo", "POB_TOTAL": "pob_2020"})
    d["ciudad"] = d["cve_mun"].map(muns).map(lambda c: CIUDADES[c][1])
    d = d.rename(columns={"IM_2020": "im_2020", "GM_2020": "gm_2020", "NOM_MUN": "municipio", "NOM_LOC": "localidad"})
    return d


def percentil(s: pd.Series) -> pd.Series:
    return (s.rank(pct=True, method="average") * 100).round(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base10", type=Path, required=True)
    ap.add_argument("--imu20", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)
    muns = municipios()

    m10 = leer_2010(a.base10, muns)
    m20 = leer_2020(a.imu20, muns)
    # Dirección de cada índice, comprobada con los datos y no solo con la metodología.
    r10 = m10["imu_2010"].rank().corr(m10["P15YMSSC"].rank())  # Spearman sin scipy
    r20 = m20["im_2020"].rank().corr(m20["SBASC"].rank())
    assert r10 > 0.5 and r20 < -0.5, (r10, r20)
    print(f"Spearman índice contra sin educación básica: 2010 {r10:+.2f}, 2020 {r20:+.2f}")
    m10.to_csv(a.salida / "marginacion_ageb_2010.csv", index=False, encoding="utf-8")

    # Comparación: unión por clave. El percentil se calcula dentro de cada ciudad y año
    # con todos los AGEB de ese año, para que no dependa de cuáles cambiaron de clave.
    m10["percentil_ciudad_2010"] = m10.groupby("ciudad")["imu_2010"].transform(percentil)
    m20["percentil_ciudad_2020"] = m20.groupby("ciudad")["im_2020"].transform(lambda s: percentil(-s))
    c10 = m10[["ciudad", "cvegeo", "cve_mun", "municipio", "localidad", "pob_2010", "gmu_2010", "imu_2010",
               "percentil_ciudad_2010"] + [x for x, _, _ in COMPARABLES + ORIENTATIVOS]]
    c20 = m20[["ciudad", "cvegeo", "cve_mun", "municipio", "localidad", "pob_2020", "gm_2020", "im_2020",
               "percentil_ciudad_2020"] + [y for _, y, _ in COMPARABLES + ORIENTATIVOS]]
    c20 = c20.rename(columns={y: f"{y}__20" for _, y, _ in COMPARABLES + ORIENTATIVOS})
    c = c10.merge(c20, on="cvegeo", how="outer", suffixes=("", "_20"), indicator=True)
    for k in ("ciudad", "cve_mun", "municipio", "localidad"):
        c[k] = c[k].fillna(c[f"{k}_20"])
    c["presencia"] = c["_merge"].map({"both": "en_ambos", "left_only": "solo_2010", "right_only": "solo_2020"})
    c["grado_2010_num"] = c["gmu_2010"].map({g: i + 1 for i, g in enumerate(GRADOS)})
    c["grado_2020_num"] = c["gm_2020"].map({g: i + 1 for i, g in enumerate(GRADOS)})
    c["cambio_grado"] = c["grado_2020_num"] - c["grado_2010_num"]
    c["cambio_percentil"] = (c["percentil_ciudad_2020"] - c["percentil_ciudad_2010"]).round(1)
    cols = ["ciudad", "cvegeo", "cve_mun", "municipio", "localidad", "presencia", "pob_2010", "pob_2020",
            "imu_2010", "im_2020", "gmu_2010", "gm_2020", "grado_2010_num", "grado_2020_num", "cambio_grado",
            "percentil_ciudad_2010", "percentil_ciudad_2020", "cambio_percentil"]
    for x, y, n in COMPARABLES:
        c[f"{n}_2010"], c[f"{n}_2020"] = c[x].round(2), c[f"{y}__20"].round(2)
        c[f"{n}_dif"] = (c[f"{n}_2020"] - c[f"{n}_2010"]).round(2)
        cols += [f"{n}_2010", f"{n}_2020", f"{n}_dif"]
    for x, y, n in ORIENTATIVOS:
        c[f"{n}_viv_2010"], c[f"{n}_ocup_2020"] = c[x].round(2), c[f"{y}__20"].round(2)
        cols += [f"{n}_viv_2010", f"{n}_ocup_2020"]
    c = c[cols].sort_values(["ciudad", "presencia", "cvegeo"]).reset_index(drop=True)
    c.to_csv(a.salida / "comparacion_ageb_2010_2020.csv", index=False, encoding="utf-8")

    filas = []
    for k, (_, nombre, _, grupo) in CIUDADES.items():
        g10, g20, g = m10[m10["ciudad"] == nombre], m20[m20["ciudad"] == nombre], c[c["ciudad"] == nombre]
        amb = g[g["presencia"] == "en_ambos"]

        def pct_alto(d: pd.DataFrame, col: str, pob: str) -> float:
            return round(100 * d.loc[d[col].isin(["Alto", "Muy alto"]), pob].sum() / d[pob].sum(), 1)

        f = {"ciudad": nombre, "grupo": grupo, "agebs_2010": len(g10), "agebs_2020": len(g20), "agebs_en_ambos": len(amb),
             "pob_2010": int(g10["pob_2010"].sum()), "pob_2020": int(g20["pob_2020"].sum()),
             "pct_pob_2020_en_agebs_en_ambos": round(100 * amb["pob_2020"].sum() / g20["pob_2020"].sum(), 1),
             "pct_pob_alto_muy_alto_2010": pct_alto(g10, "gmu_2010", "pob_2010"),
             "pct_pob_alto_muy_alto_2020": pct_alto(g20, "gm_2020", "pob_2020")}
        for x, y, n in COMPARABLES:
            f[f"{n}_mediana_2010"] = round(float(g10[x].median()), 2)
            f[f"{n}_mediana_2020"] = round(float(g20[y].median()), 2)
        f["agebs_en_ambos_subieron_de_grado"] = int((amb["cambio_grado"] > 0).sum())
        f["agebs_en_ambos_bajaron_de_grado"] = int((amb["cambio_grado"] < 0).sum())
        filas.append(f)
    r = pd.DataFrame(filas)
    r.to_csv(a.salida / "resumen_ciudad_2010_2020.csv", index=False, encoding="utf-8")
    print(r.to_string())

    resumen = {
        "grupo": "similar o distinta respecto a Guadalajara (objetivo)",
        "agebs_2010": "AGEB urbanos de 2010 con índice de CONAPO", "agebs_2020": "AGEB urbanos de 2020 con índice de CONAPO",
        "agebs_en_ambos": "AGEB cuya clave existe en los dos años",
        "pct_pob_2020_en_agebs_en_ambos": "% de la población 2020 que vive en AGEB con la misma clave que en 2010",
        "pct_pob_alto_muy_alto_2010": "% de la población 2010 en AGEB de grado Alto o Muy alto",
        "pct_pob_alto_muy_alto_2020": "% de la población 2020 en AGEB de grado Alto o Muy alto",
        "agebs_en_ambos_subieron_de_grado": "AGEB en ambos años con grado más alto (más marginado) en 2020",
        "agebs_en_ambos_bajaron_de_grado": "AGEB en ambos años con grado más bajo (menos marginado) en 2020",
    }
    for _, _, n in COMPARABLES:
        resumen[f"{n}_mediana_2010"] = f"{n.replace('_', ' ')}: mediana de los AGEB de la ciudad, 2010"
        resumen[f"{n}_mediana_2020"] = f"{n.replace('_', ' ')}: mediana de los AGEB de la ciudad, 2020"
    with open(a.salida / "diccionario_campos.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["campo", "descripcion"])
        for k, v in {**DICCIONARIO, **resumen}.items():
            w.writerow([k, v])
    with open(a.salida / "fuentes.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["dato", "productor", "pagina", "descarga", "consultado", "nota"])
        w.writerows(FUENTES)
    leeme = Path(__file__).with_name("LEEME_marginacion_2010.txt")
    if leeme.exists():
        shutil.copy(leeme, a.salida / "LEEME.txt")


if __name__ == "__main__":
    main()
