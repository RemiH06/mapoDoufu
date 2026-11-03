"""Tabla curada de rubros para el modo buscador (docs/producto/buscador.md).

Cada clase de actividad de DENUE cae en un sector y, si el sector es de
cara al público, en un rubro (como le dice la gente al negocio). Es dato
revisado a mano, no se genera en vivo: el buscador no inventa
clasificaciones (RF6, RNF6). DENUE no trae el código SCIAN en
`BuscarEntidad`, así que la llave es el nombre exacto de la clase.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Clase:
    sector: str
    rubro: str | None
    sector_publico: bool


@dataclass(frozen=True)
class Rubro:
    sector: str
    nombre: str
    sinonimos: tuple[str, ...]


def _leer(nombre: str) -> list[dict[str, str]]:
    with open(_DIR / nombre, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@cache
def sectores() -> dict[str, dict[str, str]]:
    return {f["sector"]: f for f in _leer("sectores.csv")}


@cache
def rubros() -> dict[str, Rubro]:
    return {
        f["rubro"]: Rubro(f["sector"], f["nombre"], tuple(s for s in f["sinonimos"].split("|") if s))
        for f in _leer("rubros.csv")
    }


@cache
def clases() -> dict[str, Clase]:
    return {
        f["clase_actividad"]: Clase(f["sector"], f["rubro"] or None, f["sector_publico"] == "si")
        for f in _leer("clases.csv")
    }


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y sin signos: "¿Florerías?" -> "florerias"."""
    sin_acentos = unicodedata.normalize("NFD", texto.lower())
    sin_marcas = "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sin_marcas).split())


@cache
def terminos() -> dict[str, tuple[str, str]]:
    """Término normalizado -> ("rubro" | "sector", clave). Rubros por nombre
    y sinónimos; sectores solo por sus sinónimos (el nombre de algunos, como
    "Otros comercios", es también nombre de rubro). Los choques los atrapa
    `tests/test_rubros.py`."""
    salida: dict[str, tuple[str, str]] = {}
    for clave, rubro in rubros().items():
        for t in (rubro.nombre, *rubro.sinonimos):
            salida[normalizar(t)] = ("rubro", clave)
    for clave, fila in sectores().items():
        if fila["buscable"] == "si":
            for t in filter(None, fila["sinonimos"].split("|")):
                salida[normalizar(t)] = ("sector", clave)
    return salida


def es_publica(clase: Clase) -> bool:
    """Para `solo_publicos`: lo que DENUE marca "del sector público" y todo
    lo de gobierno (docs/producto/buscador.md)."""
    return clase.sector_publico or clase.sector == "gobierno_y_seguridad"


def clases_de(*, rubro: str | None = None, sector: str | None = None, solo_publicos: bool = False) -> list[str]:
    """Nombres exactos de las clases de DENUE de un rubro o de un sector entero."""
    return sorted(
        nombre
        for nombre, c in clases().items()
        if (c.rubro == rubro if rubro else c.sector == sector) and (not solo_publicos or es_publica(c))
    )


@cache
def alias_municipios() -> dict[str, list[tuple[str, str]]]:
    """cve_ent -> [(alias normalizado, cve_mun)]: cómo le dice la gente a
    municipios de nombre largo ("Tlaquepaque", "Ciudad Guzmán")."""
    salida: dict[str, list[tuple[str, str]]] = {}
    for f in _leer("municipios_alias.csv"):
        salida.setdefault(f["cve_ent"], []).append((normalizar(f["alias"]), f["cve_mun"]))
    return salida


def sin_clasificar(nombres: set[str]) -> list[str]:
    """Clases de DENUE que no están en la tabla (por ejemplo, al cargar otro
    estado con giros que Jalisco no tiene). Hay que agregarlas a mano."""
    return sorted(nombres - clases().keys())
