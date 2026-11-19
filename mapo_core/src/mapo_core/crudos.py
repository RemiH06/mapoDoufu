"""Lectura de las fuentes ambientales en crudo (sesión 22).

Los archivos ya están bajados con `scripts/crudos-ambientales.sh` (ver
docs/fuentes/ambientales.md); los cargadores (`ambiental_*.py`) los leen de una
carpeta que se monta en el contenedor y los dejan en tablas `fuente_*`. Aquí va
lo que comparten: shapefiles dentro de un ZIP, grados en texto, números con
"<" de límite de detección, y el reemplazo de una tabla en una transacción.
"""

from __future__ import annotations

import json
import re
import tempfile
import unicodedata
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, shape

from mapo_core.datos_geo import _codificacion, _reproyectar
from mapo_core.db import get_pool

LOTE = 5_000


class CrudoFaltante(Exception):
    """El archivo crudo no está en la carpeta: hay que bajarlo antes."""


def ruta(crudos: Path, relativa: str) -> Path:
    p = crudos / relativa
    if not p.exists():
        raise CrudoFaltante(f"No está {relativa} en {crudos}: correr scripts/crudos-ambientales.sh")
    return p


def normalizar(texto) -> str:
    sin_acentos = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.upper().split())


def numero(valor) -> float | None:
    """Número o nada. '<2' (bajo el límite de detección) no es un número: es nada aquí,
    y el texto original se guarda aparte."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return None if valor != valor or valor in (float("inf"), float("-inf")) else float(valor)
    texto = str(valor).strip().replace(",", "")
    try:
        n = float(texto)
    except ValueError:
        return None
    return None if n != n or n in (float("inf"), float("-inf")) else n


def texto(valor) -> str | None:
    if valor is None:
        return None
    t = str(valor).strip()
    return t or None


def a_grados(valor) -> float | None:
    """20.69, '20.69' o grados, minutos y segundos (20°41'27", 104°21'48.1" W)."""
    n = numero(valor)
    if n is not None:
        return n
    if valor is None:
        return None
    t = str(valor).strip()
    partes = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t)]
    if not partes:
        return None
    g = partes[0] + (partes[1] / 60 if len(partes) > 1 else 0) + (partes[2] / 3600 if len(partes) > 2 else 0)
    return -g if t.upper().endswith(("W", "O", "S")) or t.startswith("-") else g


def en_mexico(lon: float | None, lat: float | None) -> bool:
    """Caja amplia de México con su mar territorial. Fuera de ella es error de captura."""
    return lon is not None and lat is not None and -119 <= lon <= -85 and 14 <= lat <= 33.5


def punto_ewkb(lon: float, lat: float) -> str:
    return shapely.to_wkb(shapely.set_srid(shapely.points(lon, lat), 4326), hex=True, include_srid=True)


def multipoligono(g) -> MultiPolygon | None:
    """Solo la parte de área, válida y como MultiPolygon (lo que pide la columna)."""
    if g is None or g.is_empty:
        return None
    if not g.is_valid:
        g = shapely.make_valid(g)
    partes = [p for p in getattr(g, "geoms", [g]) if p.geom_type in ("Polygon", "MultiPolygon")]
    poligonos = [q for p in partes for q in getattr(p, "geoms", [p])]
    return MultiPolygon(poligonos) if poligonos else None


def ewkb(g) -> str | None:
    if g is None:
        return None
    return shapely.to_wkb(shapely.set_srid(g, 4326), hex=True, include_srid=True)


def shapefile_en_zip(zip_ruta: Path, contiene: str = "") -> Iterator[tuple[dict, object]]:
    """Registros (atributos, geometría en grados WGS84) del primer .shp del ZIP cuyo
    nombre contenga `contiene`. Se extrae a una carpeta temporal: los de uso de suelo
    pesan cientos de MB y pyshp lee mejor de disco que de un ZIP."""
    import shapefile

    with zipfile.ZipFile(zip_ruta) as z, tempfile.TemporaryDirectory() as tmp:
        nombres = {n.lower(): n for n in z.namelist() if not n.startswith("__MACOSX")}
        capas = sorted(n[:-4] for n in nombres if n.endswith(".shp") and contiene.lower() in n.lower())
        if not capas:
            raise CrudoFaltante(f"{zip_ruta.name} no trae un .shp con '{contiene}'")
        base = capas[0]
        locales = {}
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            if base + ext in nombres:
                locales[ext] = Path(z.extract(nombres[base + ext], tmp))
        prj = locales[".prj"].read_text("utf-8", "replace") if ".prj" in locales else None
        cpg = locales[".cpg"].read_bytes() if ".cpg" in locales else None
        lector = shapefile.Reader(
            shp=open(locales[".shp"], "rb"), shx=open(locales[".shx"], "rb"), dbf=open(locales[".dbf"], "rb"),
            encoding=_codificacion_dbf(cpg, locales[".dbf"]), encodingErrors="replace",
        )
        campos = [c[0] for c in lector.fields[1:]]
        try:
            lote: list[tuple[dict, object]] = []
            for registro in lector.iterShapeRecords():
                forma = registro.shape
                g = None if forma.shapeType == 0 else shape(forma.__geo_interface__)
                lote.append((dict(zip(campos, list(registro.record))), g))
                if len(lote) == LOTE:
                    yield from _a_grados(lote, prj)
                    lote = []
            yield from _a_grados(lote, prj)
        finally:
            lector.close()


def _codificacion_dbf(cpg: bytes | None, dbf: Path) -> str:
    """El .cpg si lo hay; si no, UTF-8 cuando los registros lo son. Los de CONABIO
    vienen en UTF-8 sin .cpg. Se revisan los primeros MB (el archivo completo pesa
    cientos): un carácter cortado justo al final de la muestra no cuenta."""
    if cpg and cpg.decode("ascii", "ignore").strip():
        return _codificacion(cpg, b"")
    with open(dbf, "rb") as f:
        muestra = f.read(8_000_000)
    inicio = int.from_bytes(muestra[8:10], "little") if len(muestra) >= 10 else 0
    try:
        muestra[inicio:].decode("utf-8")
    except UnicodeDecodeError as error:
        if error.start < len(muestra) - inicio - 3:
            return "latin-1"
    return "utf-8"


def _a_grados(lote: list[tuple[dict, object]], prj: str | None) -> Iterator[tuple[dict, object]]:
    if not lote:
        return
    geoms = np.array([g if g is not None else shapely.Point() for _, g in lote], dtype=object)
    geoms = shapely.force_2d(geoms)
    if prj:
        geoms = _reproyectar(geoms, prj)
    for (atributos, original), g in zip(lote, geoms):
        yield atributos, (None if original is None or g.is_empty else g)


def xlsx_filas(p: Path, hoja: str | int = 0) -> Iterator[tuple]:
    import openpyxl

    libro = openpyxl.load_workbook(p, read_only=True, data_only=True)
    try:
        ws = libro.worksheets[hoja] if isinstance(hoja, int) else libro[hoja]
        yield from ws.iter_rows(values_only=True)
    finally:
        libro.close()


def jsonb(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)


async def reemplazar(tabla: str, columnas: list[str], filas: Iterable[list],
                     donde: str = "", parametros: tuple = ()) -> int:
    """Borra lo de antes (todo o lo de `donde`) y copia las filas nuevas en la misma
    transacción: si algo falla a la mitad, la tabla queda como estaba."""
    pool = await get_pool()
    n = 0
    async with pool.connection() as conn, conn.transaction():
        await conn.execute(f"DELETE FROM {tabla}" + (f" WHERE {donde}" if donde else ""), parametros)
        async with conn.cursor().copy(f"COPY {tabla} ({', '.join(columnas)}) FROM STDIN") as copia:
            for fila in filas:
                await copia.write_row(fila)
                n += 1
    return n


async def consulta(sql: str, parametros: tuple | dict = ()) -> list[tuple]:
    pool = await get_pool()
    async with pool.connection() as conn:
        cursor = await conn.execute(sql, parametros)
        return await cursor.fetchall()
