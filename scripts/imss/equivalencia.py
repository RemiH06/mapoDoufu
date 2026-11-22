"""Equivalencia de las claves de municipio del IMSS (A01, Y45...) con las de INEGI.

El archivo de asegurados trae `cve_municipio` del catálogo propio del IMSS, y el
catálogo (hoja "entidad-municipio" del diccionario de datos) solo da estado y
nombre: no trae la clave de INEGI. Se empareja por nombre dentro del estado contra
el catálogo de INEGI (wscatgeo v2), con correcciones a mano para lo que no empata.
Un municipio puede tener varias claves del IMSS (una por subdelegación).

    python scripts/imss/equivalencia.py <diccionario_de_datos.xlsx>

Escribe `mapo_core/src/mapo_core/imss_municipios.csv` e `imss_grupos.csv`.
Ver docs/fuentes/imss.md.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

import openpyxl

DESTINO = Path(__file__).resolve().parents[2] / "mapo_core" / "src" / "mapo_core"
INEGI = "https://gaia.inegi.org.mx/wscatgeo/v2/mgem/{:02d}"

# (cve_ent, nombre en el IMSS) -> (cve_mun de INEGI, por qué).
CORRECCIONES = {
    ("07", "Cintalapa"): ("017", "nombre oficial: Cintalapa de Figueroa"),
    ("08", "Rosario"): ("056", "hoy se llama Valle del Rosario"),
    ("08", "Batopilas"): ("008", "nombre oficial: Batopilas de Manuel Gómez Morín"),
    ("11", "Dolores Hidalgo Cuna de la Independencia"): ("014", "nombre oficial: ... Independencia Nacional"),
    ("11", "San José Iturbide"): ("032", "nombre oficial: San José de Iturbide"),
    ("12", "Apaxtla"): ("006", "nombre oficial: Apaxtla de Castrejón"),
    ("17", "Jonacatepec"): ("013", "nombre oficial: Jonacatepec de Leandro Valle"),
    ("20", "Magdalena Apasco"): ("045", "nombre oficial: Magdalena Apazco"),
    ("20", "Miahuatlán de Porfirio Díaz"): ("059", "nombre oficial: Heroica Ciudad de Miahuatlán..."),
    ("20", "San Martín de los Cansecos"): ("238", "nombre oficial: Heroico San Martín de los Cansecos"),
    ("20", "Santiago Chazumba"): ("459", "nombre oficial: Villa de Santiago Chazumba"),
    ("20", "Heroica Villa Tezoatlán de Segura y Luna"): ("549", "nombre oficial más largo"),
    ("20", "Villa de Tututepec de Melchor Ocampo"): ("334", "nombre oficial: Villa de Tututepec"),
    ("20", "San Blas Atempa"): ("124", "nombre oficial: Heroica Villa de San Blas Atempa"),
    ("20", "Villa Hidalgo"): ("038", "nombre oficial: Villa Hidalgo Yalálag"),
    ("23", "Solidaridad"): ("008", "hoy se llama Playa del Carmen"),
    ("24", "Ahualulco"): ("001", "nombre oficial: Ahualulco del Sonido 13"),
    ("31", "Tixpéhual"): ("095", "INEGI lo escribe Tixpéual"),
    ("02", "Isla de Cedros"): ("001", "localidad de Ensenada"),
    ("11", "Santa Ana Pacueco"): ("023", "localidad de Pénjamo"),
}

# Claves que no están en el catálogo de 2019 y aparecen en los archivos de 2024.
# Solo las que se comprobaron: con ellas, Zapopan y Guadalajara de diciembre de 2024
# dan al puesto lo que publica el IIEG (481,851 y 694,493).
CLAVES_NUEVAS = {
    "Z60": ("14", "120", "Zapopan", "cifra del IIEG, diciembre de 2024"),
    "Z62": ("14", "039", "Guadalajara", "cifra del IIEG, diciembre de 2024"),
}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.strip().lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def municipios_inegi() -> dict[str, dict[str, str]]:
    salida = {}
    for ent in range(1, 33):
        with urllib.request.urlopen(INEGI.format(ent), timeout=60) as r:
            datos = json.load(r)["datos"]
        salida[f"{ent:02d}"] = {normalizar(d["nomgeo"]): d["cve_mun"] for d in datos}
    return salida


def main(diccionario: str) -> None:
    libro = openpyxl.load_workbook(diccionario, read_only=True)
    inegi = municipios_inegi()

    filas, sin_pareja = [], []
    for fila in list(libro["entidad-municipio"].iter_rows(values_only=True))[2:]:
        clave, _deleg, ent, _estado, nombre = fila[:5]
        if not clave:
            continue
        ent, nombre = str(ent).zfill(2), nombre.strip()
        if nombre == "NA":  # la Ciudad de México no se reparte por alcaldía
            continue
        if (ent, nombre) in CORRECCIONES:
            cve_mun, metodo = CORRECCIONES[(ent, nombre)]
        elif cve_mun := inegi[ent].get(normalizar(nombre)):
            metodo = "nombre"
        else:
            sin_pareja.append((clave, ent, nombre))
            continue
        filas.append({"clave_imss": clave, "cve_ent": ent, "cve_mun": cve_mun, "nombre_imss": nombre, "metodo": metodo})
    for clave, (ent, cve_mun, nombre, metodo) in CLAVES_NUEVAS.items():
        filas.append({"clave_imss": clave, "cve_ent": ent, "cve_mun": cve_mun, "nombre_imss": nombre, "metodo": metodo})

    if sin_pareja:
        raise SystemExit(f"Sin pareja en INEGI (agregar a CORRECCIONES): {sin_pareja}")

    with open(DESTINO / "imss_municipios.csv", "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, ["clave_imss", "cve_ent", "cve_mun", "nombre_imss", "metodo"])
        escritor.writeheader()
        escritor.writerows(sorted(filas, key=lambda f: (f["cve_ent"], f["cve_mun"], f["clave_imss"])))

    grupos = []
    for fila in list(libro["sector 2"].iter_rows(values_only=True))[2:]:
        division, _grupo, grupo, nombre = fila[:4]
        if division is None:
            continue
        # El diccionario pone los grupos 20 a 29 en la división 2, pero los archivos
        # los traen en la 3 (Industrias de transformación): manda lo que traen.
        division = 3 if division == 2 else division
        grupos.append({"grupo": str(grupo), "division": str(division), "nombre": " ".join(str(nombre).split())})
    with open(DESTINO / "imss_grupos.csv", "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, ["grupo", "division", "nombre"])
        escritor.writeheader()
        escritor.writerows(grupos)
    print(f"{len(filas)} claves de municipio y {len(grupos)} grupos escritos en {DESTINO}")


if __name__ == "__main__":
    main(sys.argv[1])
