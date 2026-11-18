# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "truststore"]
# ///
"""Mide qué tan estable es la paginación de `BuscarEntidad` de la API de DENUE
(docs/fuentes/denue.md, "Paginación inestable de la API").

Pide cada página dos veces, con una pausa entre las dos vueltas, y cuenta:
negocios que cambian entre las dos respuestas de la misma página, si el orden
cambia, y repetidos entre páginas contiguas de una misma vuelta. Con una
paginación estable, todo sale en cero.

    GAIARDA_DENUE_TOKEN=... uv run --script scripts/denue/paginacion.py \
        --estado 14 --paginas 20 --salida paginacion.csv

El token es el gratuito de INEGI. No imprime el token ni lo guarda.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time

import requests
import truststore

truststore.inject_into_ssl()

URL = "https://www.inegi.org.mx/app/api/denue/v1/consulta/BuscarEntidad/todos/{ent}/{ini}/{fin}/{token}"
TAMANO = 1000


def pedir(sesion: requests.Session, ent: str, ini: int, token: str) -> list[str]:
    for intento in range(3):
        try:
            r = sesion.get(URL.format(ent=ent, ini=ini, fin=ini + TAMANO - 1, token=token), timeout=120)
            r.raise_for_status()
            return [x["Id"] for x in r.json()]
        except (requests.RequestException, ValueError):
            if intento == 2:
                raise
            time.sleep(5 * (intento + 1))
    return []


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--estado", default="14")
    p.add_argument("--total", type=int, default=401_813, help="negocios del estado (para repartir las páginas)")
    p.add_argument("--paginas", type=int, default=20, help="páginas contiguas de a pares, repartidas en el estado")
    p.add_argument("--pausa", type=float, default=60, help="segundos entre la primera y la segunda vuelta")
    p.add_argument("--salida", default=None, help="CSV con el detalle por página")
    a = p.parse_args()

    token = os.environ.get("GAIARDA_DENUE_TOKEN")
    if not token:
        sys.exit("Falta GAIARDA_DENUE_TOKEN.")

    # Pares de páginas contiguas, repartidos de punta a punta del estado.
    pares = a.paginas // 2
    salto = (a.total - 2 * TAMANO) // max(pares - 1, 1)
    inicios = sorted({1 + (i * salto // TAMANO) * TAMANO + d for i in range(pares) for d in (0, TAMANO)})

    sesion = requests.Session()
    vueltas = []
    for vuelta in range(2):
        if vuelta:
            time.sleep(a.pausa)
        vueltas.append({ini: pedir(sesion, a.estado, ini, token) for ini in inicios})

    filas = []
    for ini in inicios:
        uno, dos = vueltas[0][ini], vueltas[1][ini]
        siguiente = vueltas[0].get(ini + TAMANO)
        filas.append({
            "inicio": ini,
            "registros": len(uno),
            "distintos_entre_vueltas": len(set(uno) - set(dos)),
            "mismo_orden": uno == dos,
            "repetidos_con_la_siguiente": len(set(uno) & set(siguiente)) if siguiente is not None else "",
            "repetidos_dentro": len(uno) - len(set(uno)),
        })

    if a.salida:
        with open(a.salida, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)

    distintos = [f["distintos_entre_vueltas"] for f in filas]
    contiguas = [f["repetidos_con_la_siguiente"] for f in filas if f["repetidos_con_la_siguiente"] != ""]
    print(f"Páginas pedidas dos veces: {len(filas)} de {TAMANO} (pausa de {a.pausa:.0f} s)")
    print(f"  con otro orden: {sum(not f['mismo_orden'] for f in filas)}")
    print(f"  con negocios distintos: {sum(d > 0 for d in distintos)} (en total {sum(distintos)}, máximo {max(distintos)} en una página)")
    print(f"Pares de páginas contiguas: {len(contiguas)}, con repetidos entre sí: {sum(c > 0 for c in contiguas)} (en total {sum(contiguas)})")
    print(f"Repetidos dentro de una misma página: {sum(f['repetidos_dentro'] for f in filas)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
