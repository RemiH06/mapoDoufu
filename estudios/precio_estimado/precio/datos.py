"""Carga del dataset de vivienda por AGEB y bloques espaciales.

El objetivo es `log(medv)`. Su significado cambió con el dataset:

- v7 (`precio_estimado.ipynb`, lo que está en producción): mediana del valor
  catastral de suelo de zona, $/m² en pesos del año de la tabla de su municipio
  (Guadalajara 2020; Zapopan, Tonalá e Ixtlahuacán 2026).
- v8 (`modelos.ipynb`): mediana del precio de oferta por vivienda del IIEG, en
  pesos de julio de 2024, en seis municipios. El suelo pasó a `suelo_m2`.

Los años distintos los absorbe el efecto fijo por municipio. Las columnas de
nivel municipal (crim, tax, ptratio) quedan fuera: con el efecto fijo no aportan
nada.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ARCHIVO = "vivienda_gdl/vivienda_ageb.csv"

# Rasgos de nivel AGEB o de radio de 1 km (diccionario.csv del dataset).
RASGOS = [
    "area_ha", "pobtot", "viv_hab", "viv_ha", "indus", "chas", "nox", "rm",
    "pro_ocup_c", "pct_viv_3ymas_cuartos", "pct_viv_2ymas_dorm", "age", "age_1975",
    "dis_km", "rad_km", "pct_sin_secundaria", "pct_sin_servicios_salud",
    "pct_piso_tierra", "graproes", "pct_viv_deshabitadas", "pct_viv_auto",
    "pct_viv_internet", "pct_60ymas", "razon_dependencia", "pct_jefatura_femenina",
    "pct_nacidos_otra_entidad", "pct_con_discapacidad", "pct_viv_uso_temporal",
    "pct_viv_agua_fuera", "pct_viv_sin_drenaje", "negocios_1km", "escuelas_1km",
    "salud_1km", "supermercados_1km", "restaurantes_cafes_1km",
    "diversidad_giros_1km", "transporte_km", "parques_ha_1km", "reserva_km",
    "altitud_m", "pendiente_grados", "altura_edificios_m", "ndvi", "lst_c",
]
# Conteos y áreas muy sesgados: se pasan a log1p para los modelos lineales y la SVR.
SESGADOS = [
    "area_ha", "pobtot", "viv_hab", "viv_ha", "negocios_1km", "escuelas_1km",
    "salud_1km", "supermercados_1km", "restaurantes_cafes_1km", "parques_ha_1km",
    "dis_km", "rad_km", "transporte_km", "reserva_km",
]


def cargar(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        v = pd.read_csv(z.open(ARCHIVO), dtype={"cvegeo": str, "cve_mun": str})
    v[SESGADOS] = np.log1p(v[SESGADOS])
    v["y"] = np.log(v["medv"])
    return v


def bloques(v: pd.DataFrame, km: float = 3.0) -> pd.Series:
    """Celda de una rejilla de `km` por lado que contiene el punto de cada AGEB.

    AGEB de la misma celda van juntas al partir: así la calibración no se mide
    con vecinas de las AGEB con que se ajustó el modelo.
    """
    lat0 = np.deg2rad(v["lat"].mean())
    x = v["lon"] * 111.32 * np.cos(lat0)
    y = v["lat"] * 110.57
    return (np.floor(x / km).astype(int).astype(str) + "_" + np.floor(y / km).astype(int).astype(str))


def municipal(zip_path: Path) -> pd.DataFrame:
    """`mercado_municipal.csv` del dataset (v8 en adelante): media, mediana y
    cuartiles de todos los anuncios del IIEG por municipio."""
    with zipfile.ZipFile(zip_path) as z:
        return pd.read_csv(z.open("vivienda_gdl/mercado_municipal.csv"), dtype={"cve_mun": str})
