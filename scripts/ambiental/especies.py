# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyogrio", "requests>=2.31", "shapely>=2"]
# ///
"""Plantas vasculares registradas alrededor de una zona, con su estatus en México.

    uv run --script scripts/ambiental/especies.py --salida SALIDA --caja=O,S,E,N [--radio-km 30] [--cache ARCHIVO]

Tres fuentes, cada una en su columna, sin puntaje:
- GBIF: todos los registros de plantas vasculares (Tracheophyta) con coordenadas
  en un círculo de `--radio-km` alrededor del centro de la caja. Ejemplares de
  herbario y observaciones (iNaturalist con grado de investigación, que excluye lo
  cultivado), cada uno con su licencia.
- Enciclovida (CONABIO): tipo de distribución en México (nativa, endémica,
  exótica, exótica invasora), forma de crecimiento (árbol, arbusto...), hábitat,
  categorías de riesgo (NOM-059, UICN, CITES), usos y si es nectarífera.
- GRIIS México (Global Register of Introduced and Invasive Species, en GBIF): si
  la especie está registrada como introducida en el país (2,034 taxones, no
  todos: es un cruce, no la lista completa de exóticas).

Deja en SALIDA:
- `especies.csv`: una fila por especie, con registros en la región, en la caja,
  de herbario y de observación, último año, y las columnas de Enciclovida y GRIIS.
  Si el nombre de GBIF no está en Enciclovida se prueban sus sinónimos de GBIF;
  `metodo_enciclovida` dice con qué nombre se encontró o por qué quedó vacía.
- `arboles_nativos.csv`: las mismas columnas, solo especies con forma árbol y
  distribución nativa o endémica, por familia y nombre (sin orden de prioridad).
- `registros_especies.gpkg`, capa `registros`, EPSG:4326: cada registro de GBIF
  con su especie, año, tipo, incertidumbre, conjunto de datos y licencia.
- `procedencia_especies.csv`: consultas, fechas y conteos.

Los nombres de Enciclovida traen subgénero en algunos géneros
("Quercus (Quercus) rugosa"): se comparan sin él. Las respuestas se guardan en
`--cache` para no repetir consultas.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import requests
import shapely

GBIF = "https://api.gbif.org/v1"
ENCICLOVIDA = "https://enciclovida.mx"
TRACHEOPHYTA = 7707728
GRIIS_MX = "7185a1d5-9dc2-44fc-b3ef-5e4d068f12f1"
# Nivel1 de las características de Enciclovida -> columna. Revisado contra las
# 3,191 especies de la ZMG: 1 es "Descripción del taxón" (no es dato) y se omite.
FORMA = 18
NIVELES = {
    2: "habitat",            # Terrestre, Ripario, Bosque de encino, Ruderal...
    4: "riesgo",             # UICN, NOM-059 y CITES
    11: "usos",              # Ornamental, Maderable, Restauración, Leña...
    23: "estado_silvestre",  # Silvestre, Cultivada, Naturalizada
    24: "polinizadores",     # Plantas nectar-poliníferas
    25: "agrobiodiversidad",  # Parientes silvestres de cultivos
}
CAMPOS = ["key", "speciesKey", "species", "family", "decimalLatitude", "decimalLongitude",
          "coordinateUncertaintyInMeters", "year", "basisOfRecord", "establishmentMeans",
          "datasetKey", "institutionCode", "license"]

sesion = requests.Session()
sesion.headers["User-Agent"] = "mapo-especies/1.0"


def pedir(url: str, params: dict | None = None, intentos: int = 4) -> dict:
    for i in range(intentos):
        try:
            r = sesion.get(url, params=params, timeout=120)
            if r.status_code == 200:
                return r.json()
            if r.status_code not in (429, 500, 502, 503, 504):
                r.raise_for_status()
        except (requests.ConnectionError, requests.Timeout):
            pass
        time.sleep(2 ** i * 2)
    raise RuntimeError(f"sin respuesta tras {intentos} intentos: {url} {params}")


def circulo(lat: float, lon: float, radio_km: float, n: int = 48):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append((lon + radio_km / (111.32 * math.cos(math.radians(lat))) * math.cos(a),
                    lat + radio_km / 110.57 * math.sin(a)))
    return shapely.Polygon(pts)


BASE = {"taxonKey": TRACHEOPHYTA, "hasCoordinate": "true", "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT"}
# Con desplazamientos grandes la búsqueda de GBIF tarda minutos por página
# (medido: más de 2 min en el registro 30,000). Se parte la región en cuadros
# hasta que cada uno tenga a lo más esto, y se pagina cada cuadro desde cero.
MAX_POR_CUADRO = 3000


def _wkt(g) -> str:
    """GBIF pide el anillo exterior en sentido antihorario."""
    return shapely.to_wkt(shapely.geometry.polygon.orient(g, 1.0), rounding_precision=4)


def registros_gbif(region) -> tuple[list[dict], int, int]:
    total = pedir(f"{GBIF}/occurrence/search", {**BASE, "geometry": _wkt(region), "limit": 0})["count"]
    pendientes, cuadros = [region], 0
    filas: dict[int, dict] = {}
    while pendientes:
        g = pendientes.pop()
        n = pedir(f"{GBIF}/occurrence/search", {**BASE, "geometry": _wkt(g), "limit": 0})["count"]
        o, s, e, nn = g.bounds
        if n > MAX_POR_CUADRO and (e - o) > 0.002:
            xm, ym = (o + e) / 2, (s + nn) / 2
            for c in (shapely.box(o, s, xm, ym), shapely.box(xm, s, e, ym),
                      shapely.box(o, ym, xm, nn), shapely.box(xm, ym, e, nn)):
                parte = g.intersection(c)
                if not parte.is_empty and parte.area > 0:
                    pendientes.append(parte if parte.geom_type == "Polygon" else parte.convex_hull)
            continue
        cuadros += 1
        offset = 0
        while offset < n:
            d = pedir(f"{GBIF}/occurrence/search", {**BASE, "geometry": _wkt(g), "limit": 300, "offset": offset})
            for r in d["results"]:
                filas[r["key"]] = {c: r.get(c) for c in CAMPOS}
            offset += len(d["results"])
            if d["endOfRecords"] or not d["results"]:
                break
    if len(filas) != total:
        print(f"aviso: GBIF dijo {total} registros en la región y llegaron {len(filas)}", file=sys.stderr)
    return [f for f in filas.values() if f["speciesKey"]], total, cuadros


def griis() -> dict[int, str]:
    """speciesKey del backbone de GBIF -> 'introducida' si está en GRIIS México.

    La búsqueda de GBIF no trae si es invasora (está en la distribución de cada
    taxón): para eso queda la columna de Enciclovida."""
    out, offset = {}, 0
    while True:
        d = pedir(f"{GBIF}/species/search", {"datasetKey": GRIIS_MX, "limit": 1000, "offset": offset})
        for r in d["results"]:
            if r.get("nubKey"):
                out[r["nubKey"]] = "introducida"
        offset += len(d["results"])
        if d["endOfRecords"] or not d["results"]:
            break
    return out


def sin_subgenero(nombre: str) -> str:
    return re.sub(r"\s+\([^)]*\)", "", nombre).strip()


class Enciclovida:
    def __init__(self, cache: Path):
        self.ruta = cache
        self.datos = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        self.datos.setdefault("genero", {})
        self.datos.setdefault("especie", {})
        self.datos.setdefault("sinonimos", {})

    def guardar(self) -> None:
        self.ruta.write_text(json.dumps(self.datos, ensure_ascii=False), encoding="utf-8")

    def genero(self, g: str) -> dict[str, list]:
        if g not in self.datos["genero"]:
            d = pedir(f"{ENCICLOVIDA}/busquedas/resultados.json",
                      {"busqueda": "basica", "nombre": g, "solo_categoria": 19, "por_pagina": 2000})
            self.datos["genero"][g] = [[t["IdNombre"], t["NombreCompleto"], t.get("Estatus")]
                                       for t in d.get("taxa", [])
                                       if sin_subgenero(t["NombreCompleto"]).split(" ")[0] == g]
        return {sin_subgenero(n): [i, e] for i, n, e in self.datos["genero"][g]}

    def sinonimos(self, clave_gbif: int) -> list[str]:
        """Sinónimos binomiales de una especie según el backbone de GBIF."""
        k = str(clave_gbif)
        if k not in self.datos["sinonimos"]:
            d = pedir(f"{GBIF}/species/{clave_gbif}/synonyms", {"limit": 200})
            self.datos["sinonimos"][k] = sorted({r["canonicalName"] for r in d["results"]
                                                 if len((r.get("canonicalName") or "").split()) == 2})
        return self.datos["sinonimos"][k]

    def especie(self, id_nombre: int) -> dict:
        k = str(id_nombre)
        if k not in self.datos["especie"]:
            d = pedir(f"{ENCICLOVIDA}/especies/{id_nombre}.json")
            self.datos["especie"][k] = {
                "nombre": d.get("NombreCompleto"),
                "estatus": d.get("Estatus"),
                "comun": d.get("e_nombre_comun_principal"),
                "dist": [x["Descripcion"] for x in d.get("e_tipo_distribucion") or []],
                "carac": [[x.get("Nivel1"), x["Descripcion"]] for x in d.get("e_caracteristicas") or []],
            }
        return self.datos["especie"][k]


def consultar(enc: Enciclovida, claves: dict[str, int], hilos: int) -> dict[str, dict]:
    """Nombre de GBIF -> columnas de Enciclovida. Primero el nombre tal cual; si no
    está, los sinónimos de GBIF (la taxonomía de CONABIO no siempre es la de GBIF:
    Vachellia farnesiana es Acacia farnesiana allá). Entre sinónimos se prefiere el
    que conserva el epíteto, y el método dice cuál se usó."""
    nombres = list(claves)
    with ThreadPoolExecutor(hilos) as ex:
        list(ex.map(enc.genero, sorted({n.split(" ")[0] for n in nombres})))
        faltan = [n for n in nombres if enc.genero(n.split(" ")[0]).get(n) is None]
        sinon = dict(zip(faltan, ex.map(enc.sinonimos, [claves[n] for n in faltan])))
        list(ex.map(enc.genero, sorted({s.split(" ")[0] for ss in sinon.values() for s in ss})))
    enc.guardar()
    ids, por_sinonimo, out = {}, {}, {}
    for n in nombres:
        cand = enc.genero(n.split(" ")[0]).get(n)
        if cand is not None:
            ids[n] = cand[0]
            continue
        hallados = [s for s in sinon[n] if enc.genero(s.split(" ")[0]).get(s) is not None]
        if not hallados:
            out[n] = {"metodo_enciclovida": "sin coincidencia del nombre ni de sus sinónimos en GBIF"}
            continue
        mismo = [s for s in hallados if s.split(" ")[1] == n.split(" ")[1]]
        elegido = (mismo or hallados)[0]
        ids[n] = enc.genero(elegido.split(" ")[0])[elegido][0]
        nota = f"por sinónimo de GBIF: {elegido}"
        if not mismo:
            nota += " (otro epíteto: revisar)"
        if len(hallados) > 1:
            nota += f"; otros sinónimos en Enciclovida: {', '.join(s for s in hallados if s != elegido)}"
        por_sinonimo[n] = nota
    with ThreadPoolExecutor(hilos) as ex:
        fichas = dict(zip(ids, ex.map(enc.especie, ids.values())))
    enc.guardar()
    for n, f in fichas.items():
        formas = [d for nivel, d in f["carac"] if nivel == FORMA]
        otras = {col: "; ".join(d for nivel, d in f["carac"] if nivel == n) for n, col in NIVELES.items()}
        out[n] = {
            "id_enciclovida": ids[n],
            "nombre_enciclovida": f["nombre"],
            "nombre_comun": f["comun"] or "",
            "distribucion_mx": "; ".join(f["dist"]),
            "formas_crecimiento": "; ".join(formas),
            "es_arbol": "si" if "Árbol" in formas else ("no" if formas else ""),
            **otras,
            "metodo_enciclovida": (por_sinonimo.get(n, "mismo nombre")
                                   + ("" if f["estatus"] == 2 else "; nombre no válido en Enciclovida")
                                   + ("" if f["dist"] else "; sin tipo de distribución")),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--caja", required=True, help="oeste,sur,este,norte en grados")
    ap.add_argument("--radio-km", type=float, default=30.0, help="radio de la región alrededor del centro de la caja")
    ap.add_argument("--cache", type=Path, help="JSON con las respuestas de Enciclovida (por omisión, en SALIDA)")
    ap.add_argument("--hilos", type=int, default=4, help="consultas simultáneas a Enciclovida")
    a = ap.parse_args()
    caja = tuple(float(v) for v in a.caja.split(","))
    if len(caja) != 4 or caja[0] >= caja[2] or caja[1] >= caja[3]:
        sys.exit("--caja debe ser oeste,sur,este,norte")
    salida = a.salida.expanduser()
    salida.mkdir(parents=True, exist_ok=True)
    o, s, e, n = caja
    lat, lon = (s + n) / 2, (o + e) / 2
    region = circulo(lat, lon, a.radio_km)
    consulta = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    filas, total_gbif, cuadros = registros_gbif(region)
    gdf = gpd.GeoDataFrame(filas, geometry=shapely.points(
        [f["decimalLongitude"] for f in filas], [f["decimalLatitude"] for f in filas]), crs="EPSG:4326")
    gdf = gdf.drop(columns=["decimalLatitude", "decimalLongitude"]).rename(columns={
        "key": "gbif_id", "speciesKey": "gbif_especie", "species": "especie", "family": "familia",
        "coordinateUncertaintyInMeters": "incertidumbre_m", "year": "anio", "basisOfRecord": "tipo",
        "establishmentMeans": "establecimiento", "datasetKey": "conjunto_gbif",
        "institutionCode": "institucion", "license": "licencia"})
    gdf["en_caja"] = gdf.geometry.within(shapely.box(o, s, e, n))

    especies = sorted(gdf["especie"].dropna().unique())
    enc = Enciclovida(a.cache or salida / "enciclovida_cache.json")
    info = consultar(enc, dict(zip(especies, gdf.groupby("especie")["gbif_especie"].first().loc[especies].astype(int))), a.hilos)
    introducidas = griis()

    por = defaultdict(Counter)
    anio = {}
    clave = {}
    familia = {}
    for r in gdf.itertuples():
        c = por[r.especie]
        c["region"] += 1
        c["caja"] += bool(r.en_caja)
        c["herbario"] += r.tipo == "PRESERVED_SPECIMEN"
        c["observacion"] += r.tipo == "HUMAN_OBSERVATION"
        if r.anio == r.anio and r.anio:
            anio[r.especie] = max(anio.get(r.especie, 0), int(r.anio))
        clave[r.especie] = int(r.gbif_especie)
        familia[r.especie] = r.familia

    cols_enc = ["id_enciclovida", "nombre_enciclovida", "nombre_comun", "distribucion_mx",
                "formas_crecimiento", "es_arbol", *NIVELES.values(), "metodo_enciclovida"]
    encabezado = ["especie", "familia", "gbif_especie", "registros_region", "registros_caja",
                  "registros_herbario", "registros_observacion", "ultimo_anio", *cols_enc, "griis_mexico"]
    renglones = []
    for sp in especies:
        c, i = por[sp], info.get(sp, {})
        renglones.append([sp, familia[sp], clave[sp], c["region"], c["caja"], c["herbario"], c["observacion"],
                          anio.get(sp, ""), *[i.get(k, "") for k in cols_enc], introducidas.get(clave[sp], "")])
    with open(salida / "especies.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([encabezado, *renglones])
    # Atajo para quien busca qué plantar: forma árbol y nativa o endémica según
    # Enciclovida. Orden por familia y nombre, nunca por un puntaje.
    nativos = sorted(
        (r for r, sp in zip(renglones, especies)
         if info.get(sp, {}).get("es_arbol") == "si"
         and re.search(r"Nativa|Endémica", info[sp].get("distribucion_mx", ""))),
        key=lambda r: (r[1] or "", r[0]))
    with open(salida / "arboles_nativos.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([encabezado, *nativos])

    gdf["en_caja"] = gdf["en_caja"].map({True: "si", False: "no"})
    gdf["fecha_consulta"] = consulta
    gdf.to_file(salida / "registros_especies.gpkg", layer="registros", driver="GPKG")

    dist = Counter(info.get(sp, {}).get("distribucion_mx", "") or "(sin dato)" for sp in especies)
    arboles = [sp for sp in especies if info.get(sp, {}).get("es_arbol") == "si"]
    with open(salida / "procedencia_especies.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clave", "valor"])
        w.writerow(["fecha_consulta", consulta])
        w.writerow(["centro", f"{lat:.5f},{lon:.5f}"])
        w.writerow(["radio_km", a.radio_km])
        w.writerow(["caja", a.caja])
        w.writerow(["gbif_consulta", f"{GBIF}/occurrence/search?taxonKey={TRACHEOPHYTA}&hasCoordinate=true"
                                     "&hasGeospatialIssue=false&occurrenceStatus=PRESENT&geometry=(círculo)"])
        w.writerow(["gbif_registros_reportados", total_gbif])
        w.writerow(["gbif_registros", len(gdf)])
        w.writerow(["gbif_cuadros_consultados", cuadros])
        w.writerow(["gbif_especies", len(especies)])
        for k, v in Counter(gdf["tipo"]).most_common():
            w.writerow([f"registros_{k}", v])
        for k, v in Counter(gdf["licencia"]).most_common():
            w.writerow([f"licencia_{k}", v])
        w.writerow(["enciclovida", f"{ENCICLOVIDA}/especies/ID.json"])
        for k, v in dist.most_common():
            w.writerow([f"especies_distribucion_{k}", v])
        w.writerow(["especies_arbol", len(arboles)])
        w.writerow(["arboles_nativos", len(nativos)])
        w.writerow(["griis_mexico", f"https://www.gbif.org/dataset/{GRIIS_MX}"])
        w.writerow(["griis_especies_en_region", sum(1 for sp in especies if clave[sp] in introducidas)])
    print(f"{len(gdf)} registros, {len(especies)} especies, {len(arboles)} con forma árbol; {dict(dist)}")


if __name__ == "__main__":
    main()
