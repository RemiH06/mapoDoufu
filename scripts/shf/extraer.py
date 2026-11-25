# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl"]
# ///
"""Los dos anexos con que la SHF respondió por transparencia (docs/fuentes/shf.md)
a las tablas que lee `mapo_core`.

    uv run scripts/shf/extraer.py <zip de la respuesta>
"""

import csv
import io
import sys
import zipfile
from pathlib import Path

import openpyxl

SALIDA = Path(__file__).parents[2] / "mapo_core/src/mapo_core"
# Clave en el SUN 2018 -> nombre con que la API del SNIIV da la serie.
ZONAS = {
    "M02.03": "ZM Tijuana", "M09.01": "ZM Valle México", "M11.03": "ZM León", "M14.01": "ZM Guadalajara",
    "M15.02": "ZM Toluca", "M19.01": "ZM Monterrey", "M21.01": "ZM PueblaTlax", "M22.01": "ZM Querétaro",
}


def abrir(z: zipfile.ZipFile, extension: str) -> bytes:
    (nombre,) = [n for n in z.namelist() if n.lower().endswith(extension)]
    return z.read(nombre)


def escribir(nombre: str, encabezado: list[str], filas: list[list]) -> None:
    with open(SALIDA / nombre, "w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f, lineterminator="\n")
        escritor.writerow(encabezado)
        escritor.writerows(filas)
    print(f"{nombre}: {len(filas)} filas")


def main() -> None:
    with zipfile.ZipFile(sys.argv[1]) as z:
        hoja = openpyxl.load_workbook(io.BytesIO(abrir(z, ".xlsx"))).worksheets[0]
        # Sin el nombre del municipio: el archivo trae "-lvaro Obregón" y la base ya los tiene.
        zonas = [[fila[4], ZONAS[fila[4]], fila[5], fila[2]]
                 for fila in hoja.iter_rows(values_only=True) if fila[4] in ZONAS]
        avaluos = []
        for fila in csv.DictReader(io.StringIO(abrir(z, ".csv").decode("utf-8"))):
            zona, municipio = fila["CLAVE_ZONA_METROPOLITANA"], fila["CLAVE_MUNICIPIO"]
            if (zona == "NA") == (municipio == "NA"):
                raise SystemExit(f"Se esperaba zona o municipio, no los dos: {fila}")
            avaluos.append([int(fila["anio"]), municipio if zona == "NA" else ZONAS[zona],
                            int(fila["Observaciones"])])
    if len({z for _, z, _, _ in zonas}) != 8 or len({c for _, c, _ in avaluos}) != 82:
        raise SystemExit("Se esperaban 8 zonas y 82 series de avalúos.")
    escribir("shf_zonas.csv", ["clave_sun", "clave", "nombre", "cvegeo"], zonas)
    escribir("shf_avaluos.csv", ["anio", "clave", "avaluos"], avaluos)


main()
