"""Tabla curada de rubros para el modo buscador (docs/producto/buscador.md).

Cada clase de actividad de DENUE cae en un sector y, si el sector es de
cara al público, en un rubro (como le dice la gente al negocio). Es dato
revisado a mano, no se genera en vivo: el buscador no inventa
clasificaciones (RF6, RNF6). DENUE no trae el código SCIAN en
`BuscarEntidad`, así que la llave es el nombre exacto de la clase.
"""

from __future__ import annotations

import csv
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


def sin_clasificar(nombres: set[str]) -> list[str]:
    """Clases de DENUE que no están en la tabla (por ejemplo, al cargar otro
    estado con giros que Jalisco no tiene). Hay que agregarlas a mano."""
    return sorted(nombres - clases().keys())
