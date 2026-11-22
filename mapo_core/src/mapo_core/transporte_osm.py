"""Rutas de transporte público de OpenStreetMap para todo el país (sesión 27): el
respaldo donde no hay GTFS. Sin horarios ni frecuencias: solo dicen por dónde pasa
una ruta según quien la mapeó. Ver docs/fuentes/gtfs.md.

Entra un archivo OPL (texto de osmium) con las relaciones `type=route` de transporte
y sus vías con coordenadas, que arma `scripts/transporte/rutas_osm.sh` desde el pbf
de México de Geofabrik. Se guarda como el feed `osm` en las tablas de transporte.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

from mapo_core import transporte

# route=* de OSM a un modo de Mapo.
MODOS_OSM = {"bus": "autobus", "share_taxi": "colectivo", "trolleybus": "trolebus", "tram": "tren_ligero",
             "light_rail": "tren_ligero", "subway": "metro", "train": "tren", "monorail": "monorriel",
             "aerialway": "cable", "ferry": "ferri", "funicular": "funicular"}
_FECHA = re.compile(r"(\d{6})")
_ESCAPE = re.compile(r"%([0-9a-fA-F]+)%")


class ArchivoInvalido(Exception):
    pass


def _texto(valor: str) -> str:
    """OPL escapa como %hex% los caracteres especiales (espacio, coma, igual, %, @)."""
    return _ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), valor)


def _campos(linea: str) -> tuple[str, dict[str, str]]:
    partes = linea.rstrip("\n").split(" ")
    return partes[0], {p[0]: p[1:] for p in partes[1:] if p}


def _etiquetas(valor: str) -> dict[str, str]:
    if not valor:
        return {}
    salida = {}
    for par in valor.split(","):
        k, _, v = par.partition("=")
        salida[_texto(k)] = _texto(v)
    return salida


def _coordenada(texto: str) -> tuple[float, float] | None:
    """'n123x-103.35y20.67' -> (lat, lon); None si el nodo no trae coordenada."""
    _, _, resto = texto.partition("x")
    x, _, y = resto.partition("y")
    try:
        lon, lat = float(x), float(y)
    except ValueError:
        return None
    return (lat, lon) if 14 <= lat <= 33.5 and -119 <= lon <= -85 else None


@dataclass
class RutaOSM:
    osm_id: str
    modo: str
    ref: str
    nombre: str
    red: str
    operador: str
    vias: list[str] = field(default_factory=list)
    paradas: list[str] = field(default_factory=list)


def leer(ruta: Path) -> tuple[list[dict], list[dict], list[str]]:
    """(rutas, paradas, avisos). Una ruta sin ninguna vía con coordenadas no se guarda."""
    nodos: dict[str, tuple[str, tuple[float, float]]] = {}
    vias: dict[str, list[tuple[float, float]]] = {}
    relaciones: list[RutaOSM] = []
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            if not linea.strip():
                continue
            ident, c = _campos(linea)
            tipo = ident[0]
            if tipo == "n":
                et = _etiquetas(c.get("T", ""))
                coord = _coordenada("x" + c.get("x", "") + "y" + c.get("y", ""))
                # Solo los nodos con etiqueta pueden ser paradas; los demás ya vienen en sus vías.
                if coord and et:
                    nodos[ident] = (et.get("name", ""), coord)
            elif tipo == "w":
                puntos = [p for p in (_coordenada(n) for n in c.get("N", "").split(",") if n) if p]
                if len(puntos) >= 2:
                    vias[ident] = puntos
            elif tipo == "r":
                et = _etiquetas(c.get("T", ""))
                m = MODOS_OSM.get(et.get("route", ""))
                if et.get("type") != "route" or m is None:
                    continue
                r = RutaOSM(ident, m, et.get("ref", ""), et.get("name", ""), et.get("network", ""),
                            et.get("operator", ""))
                for miembro in c.get("M", "").split(","):
                    if not miembro:
                        continue
                    ref, _, rol = miembro.partition("@")
                    rol = _texto(rol)
                    if ref.startswith("w") and not rol.startswith("platform"):
                        r.vias.append(ref)
                    elif ref.startswith("n") and (rol.startswith("stop") or rol.startswith("platform")):
                        r.paradas.append(ref)
                relaciones.append(r)
    rutas, avisos = [], []
    tocan: dict[str, set[str]] = {}
    sin_vias = 0
    for r in relaciones:
        lineas = [vias[v] for v in r.vias if v in vias]
        if not lineas:
            sin_vias += 1
            continue
        rutas.append({"route_id": r.osm_id, "agencia": r.operador or r.red, "nombre_corto": r.ref,
                      "nombre_largo": r.nombre, "modo": r.modo, "color": "", "viajes_dia": None,
                      "salidas_pico": None, "frecuencia_estimada": False, "geom": transporte._ewkt(lineas)})
        for n in r.paradas:
            if n in nodos:
                tocan.setdefault(n, set()).add(r.osm_id)
    if sin_vias:
        avisos.append(f"{sin_vias} relaciones sin vías con coordenadas (incompletas en el extracto): no se guardan")
    paradas = [{"stop_id": n, "nombre": nodos[n][0], "lat": nodos[n][1][0], "lon": nodos[n][1][1],
                "pasadas_ruta_max": None, "pasadas": None, "rutas": len(rs)} for n, rs in tocan.items()]
    return rutas, paradas, avisos


def fecha_extracto(nombre: str) -> str | None:
    """'rutas-261120.opl' -> '2026-11-20' (la fecha del pbf de Geofabrik)."""
    m = _FECHA.search(nombre)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%y%m%d").date().isoformat()
    except ValueError:
        return None


async def cargar(pool: AsyncConnectionPool, ruta: Path) -> dict:
    fecha = fecha_extracto(ruta.name)
    if fecha is None:
        raise ArchivoInvalido(f"{ruta.name}: se espera la fecha del pbf (AAMMDD) en el nombre")
    rutas, paradas, avisos = leer(ruta)
    if len(rutas) < 100:
        raise ArchivoInvalido(f"solo {len(rutas)} rutas: el país tiene miles en OSM")
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        while bloque := fh.read(1 << 20):
            h.update(bloque)
    fila = {
        "feed": transporte.OSM, "titulo": "OpenStreetMap: rutas de transporte público",
        "productor": "Colaboradores de OpenStreetMap", "licencia": "ODbL-1.0",
        "pagina": "https://www.openstreetmap.org/copyright",
        "url": f"https://download.geofabrik.de/north-america/mexico/mexico-{ruta.stem[-6:]}.osm.pbf",
        "via": "Geofabrik", "sha256": h.hexdigest(), "bytes": ruta.stat().st_size,
        "vigencia_ini": None, "vigencia_fin": None, "fecha_ref": None, "viajes_dia": 0,
        "rutas": len(rutas), "paradas": len(paradas), "avisos": avisos, "frecuencia_util": False,
        "nota": f"Extracto del {fecha}. Sin horarios ni frecuencias: solo el trazo que alguien mapeó.",
    }
    await transporte.guardar(pool, fila, rutas, paradas)
    return {"extracto": fecha, "rutas": len(rutas), "paradas": len(paradas),
            "modos": dict(Counter(r["modo"] for r in rutas)), "avisos": avisos}
