# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "beautifulsoup4", "truststore"]
# ///
"""Alumnos, docentes y escuelas por municipio y nivel desde "Principales cifras"
de la DGPPyEE de la SEP (planeacion.sep.gob.mx/principalescifras), para PTRATIO
del dataset de vivienda (docs/producto/dataset-vivienda.md).

No hay descarga abierta por escuela; esta consulta da los totales por municipio.
Es un formulario ASP.NET: cada lista desplegable hace un postback, así que se
reenvía el estado (__VIEWSTATE) en cada paso, como lo haría el navegador.

    uv run --script scripts/vivienda/sep_cifras.py --ciclo 2019-2020 --estado 14 \
        --municipios 002,039,044 --salida sep_2019-2020.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time

import requests
import truststore
from bs4 import BeautifulSoup

# El servidor de la SEP no manda su certificado intermedio. El almacén del
# sistema (Windows, macOS) lo completa; certifi no. Se valida igual, sin apagar
# la verificación.
truststore.inject_into_ssl()

URL = "https://www.planeacion.sep.gob.mx/principalescifras/"


def campos(sopa: BeautifulSoup) -> dict[str, str]:
    """Estado del formulario tal como lo mandaría el navegador."""
    datos = {i["name"]: i.get("value", "") for i in sopa.select("input[type=hidden]") if i.get("name")}
    for sel in sopa.select("select"):
        elegido = sel.select_one("option[selected]") or sel.select_one("option")
        datos[sel["name"]] = elegido["value"] if elegido else ""
    return datos


def opciones(sopa: BeautifulSoup, nombre: str) -> dict[str, str]:
    return {o.get_text(strip=True): o["value"] for o in sopa.select(f"select[name={nombre}] option")}


class Consulta:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "Mozilla/5.0 (mapo-datos)"
        self.sopa = BeautifulSoup(self.s.get(URL, timeout=60).text, "html.parser")

    def elegir(self, nombre: str, valor: str) -> None:
        datos = campos(self.sopa) | {nombre: valor, "__EVENTTARGET": nombre, "__EVENTARGUMENT": ""}
        self.sopa = BeautifulSoup(self.s.post(URL, data=datos, timeout=120).text, "html.parser")
        time.sleep(0.5)  # el servidor es de la SEP: sin prisa

    def consultar(self) -> BeautifulSoup:
        datos = campos(self.sopa) | {"Button1": "Consulta", "__EVENTTARGET": "", "__EVENTARGUMENT": ""}
        self.sopa = BeautifulSoup(self.s.post(URL, data=datos, timeout=120).text, "html.parser")
        return self.sopa


def tabla(sopa: BeautifulSoup) -> list[list[str]]:
    """La tabla de resultados más grande de la página."""
    tablas = sopa.select("table")
    if not tablas:
        return []
    t = max(tablas, key=lambda x: len(x.select("tr")))
    return [[c.get_text(" ", strip=True) for c in tr.select("th,td")] for tr in t.select("tr")]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ciclo", required=True, help="como lo escribe la SEP, p. ej. 2019-2020")
    ap.add_argument("--estado", required=True, help="clave de entidad de 2 dígitos")
    ap.add_argument("--municipios", required=True, help="claves de 3 dígitos separadas por coma")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--ver", action="store_true", help="imprime la tabla cruda del primer municipio y sale")
    a = ap.parse_args()

    numero = lambda x: int(x.replace(",", "")) if x.replace(",", "").isdigit() else 0
    filas_salida = []
    for mun in a.municipios.split(","):
        for control, etiqueta in (("0", "todos"), ("1", "publico")):
            c = Consulta()
            ciclos = opciones(c.sopa, "DDLciclos")
            if a.ciclo not in ciclos:
                sys.exit(f"ciclo {a.ciclo} no está; hay: {list(ciclos)}")
            # Orden obligado: cada lista reinicia a las de abajo. Elegir un ciclo que no
            # sea el vigente deja vacía la lista de estados: el sitio solo abre por
            # municipio el ciclo vigente (probado el 2026-11-15).
            if ciclos[a.ciclo] != campos(c.sopa)["DDLciclos"]:
                c.elegir("DDLciclos", ciclos[a.ciclo])
            c.elegir("DDLEscolarizadas", "1")  # escolarizada
            c.elegir("DDLNivel", "1")  # educación básica: preescolar, primaria y secundaria
            if control != "0":
                c.elegir("DDLControl", control)
            if len(opciones(c.sopa, "DDLEntidad")) < 2:
                sys.exit(f"el sitio no abre estados para el ciclo {a.ciclo}; usa el vigente")
            c.elegir("DDLEntidad", a.estado)
            municipios = {v[-3:]: v for v in opciones(c.sopa, "DDLMunicipio").values() if v != "0"}
            if mun not in municipios:
                sys.exit(f"municipio {mun} no aparece")
            c.elegir("DDLMunicipio", municipios[mun])
            t = tabla(c.consultar())
            if a.ver:
                for r in t:
                    print(r)
                return
            # Renglones por localidad bajo el encabezado "Localidad".
            k = next(n for n, r in enumerate(t) if r and r[0] == "Localidad")
            enc = t[k]
            locs = [dict(zip(enc, r)) for r in t[k + 1:] if len(r) == len(enc) and r[0].upper() != "TOTAL"]
            docentes = next(h for h in enc if h.startswith("Docentes") and "Mujeres" not in h and "Hombres" not in h)
            fila = {"municipio": a.estado + mun, "ciclo": a.ciclo, "nivel": "basica", "control": etiqueta,
                    "localidades": len(locs),
                    "escuelas": sum(numero(l["Escuelas"]) for l in locs),
                    "alumnos": sum(numero(l["Alumnos"]) for l in locs),
                    "docentes": sum(numero(l[docentes]) for l in locs)}
            filas_salida.append(fila)
            print(fila, flush=True)

    with open(a.salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas_salida[0]))
        w.writeheader()
        w.writerows(filas_salida)


if __name__ == "__main__":
    main()
