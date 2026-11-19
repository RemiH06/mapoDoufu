"""Emisiones y fuego: RETC de SEMARNAT (establecimientos y lo que reportan) y focos
de calor de NASA FIRMS. Ver docs/fuentes/retc.md y firms.md."""

from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile
from pathlib import Path

from mapo_core import crudos as c

# --- RETC -------------------------------------------------------------------
_VACIOS_SEGUIDOS = 500  # algunos Excel declaran un millón de renglones vacíos


def _columna(encabezado: list[str], *opciones: str, excluir: str = "") -> int | None:
    for o in opciones:
        if o in encabezado:
            return encabezado.index(o)
    for o in opciones:
        for i, h in enumerate(encabezado):
            if o in h and not (excluir and excluir in h):
                return i
    return None


def _tabla(filas, marca: str):
    """Renglones a partir del encabezado: el que tiene una celda con `marca`. Encima
    hay títulos de la dirección general, la fecha de modificación y, en algunos
    años, un renglón de grupos ("Sustancias", "Emisiones") que no es el encabezado."""
    encabezado = None
    vacios = 0
    for fila in filas:
        if encabezado is None:
            normal = [c.normalizar(v) if v is not None else "" for v in fila]
            if marca in normal or (marca == "LATITUD" and any("LATITUD" in h for h in normal)):
                encabezado = normal
            continue
        if not fila or fila[0] in (None, ""):
            vacios += 1
            if vacios > _VACIOS_SEGUIDOS:
                return
            continue
        vacios = 0
        yield encabezado, fila
    if encabezado is None:
        raise ValueError(f"no se encontró el encabezado con {marca}")


def _hojas(crudos: Path):
    import openpyxl

    with zipfile.ZipFile(c.ruta(crudos, "emisiones/retc_2004-2022.zip")) as z:
        for nombre in sorted(z.namelist()):
            anio = int("".join(ch for ch in nombre if ch.isdigit())[:4])
            libro = openpyxl.load_workbook(io.BytesIO(z.read(nombre)), read_only=True, data_only=True)
            try:
                yield anio, libro.worksheets[0], libro.worksheets[1]
            finally:
                libro.close()


def establecimientos(anio: int, hoja):
    vistos = set()
    for enc, fila in _tabla(hoja.iter_rows(values_only=True), "LATITUD"):
        i = {k: _columna(enc, *v, excluir=x) for k, v, x in (
            ("nra", ("NRA",), ""), ("scian", ("SCIAN",), "DESCRIPCION"),
            ("actividad", ("DESCRIPCION SCIAN", "ACTIVIDAD PRINCIPAL", "PRINCIPAL ACTIVIDAD PRODUCTIVA"), "SEMARNAT"),
            ("sector", ("SECTOR",), "SUB"), ("estado", ("ESTADO", "ENTIDAD"), ""),
            ("municipio", ("MUNICIPIO",), ""), ("lat", ("LATITUD",), ""), ("lon", ("LONGITUD",), ""))}

        def v(k):
            return c.texto(fila[i[k]]) if i[k] is not None and i[k] < len(fila) else None

        nra = v("nra")
        if not nra or nra in vistos:
            continue
        vistos.add(nra)
        lat = c.a_grados(fila[i["lat"]])
        lon = c.a_grados(fila[i["lon"]])
        lat = abs(lat) if lat is not None else None
        lon = -abs(lon) if lon is not None else None  # "Longitud Oeste": casi siempre sin signo
        scian = v("scian")
        yield [anio, nra, scian.split(".")[0] if scian else None, v("actividad"), v("sector"), v("estado"),
               v("municipio"), c.punto_ewkb(lon, lat) if c.en_mexico(lon, lat) else None]


_TRANSFERENCIAS = {"REUSO": "reutilizacion", "REUTILIZACION": "reutilizacion", "RECICLADO": "reciclado",
                   "COPROCESAMIENTO": "coprocesamiento", "TRATAMIENTO": "tratamiento",
                   "DISPOSICION FINAL": "disposicion_final", "ALCANTARILLADO": "alcantarillado",
                   "INCINERACION": "incineracion", "OTRO": "otros", "OTROS": "otros"}


def a_kg(unidad: str | None) -> float:
    u = c.normalizar(unidad or "").replace(" ", "")
    if u.startswith("TON"):
        return 1000.0
    if u.startswith("KG"):
        return 1.0
    if u in ("G", "G/ANO", "GR", "GRAMOS"):
        return 0.001
    raise ValueError(f"unidad del RETC sin conversión: {unidad!r}")


def emisiones(anio: int, hoja):
    for enc, fila in _tabla(hoja.iter_rows(values_only=True), "NRA"):
        col = {h: n for n, h in enumerate(enc)}
        sustancia = c.texto(fila[col["SUSTANCIA"] if "SUSTANCIA" in col else _columna(enc, "SUSTANCIA", "DESCRIPCION")])
        nra = c.texto(fila[col["NRA"]])
        if not nra or not sustancia:
            continue
        factor = a_kg(fila[col["UNIDAD"]])

        def kg(nombre):
            n = c.numero(fila[col[nombre]]) if nombre in col and col[nombre] < len(fila) else None
            return None if n is None else n * factor

        transferencias = {}
        for h, clave in _TRANSFERENCIAS.items():
            valor = kg(h)
            if valor:
                transferencias[clave] = transferencias.get(clave, 0) + valor
        cas = _columna(enc, "CAS", "NO. CAS")
        yield [anio, nra, sustancia, c.texto(fila[cas]) if cas is not None else None,
               kg("AIRE"), kg("AGUA"), kg("SUELO"), c.jsonb(transferencias)]


async def cargar_retc(crudos: Path) -> dict:
    est, emi = [], []
    for anio, generales, sustancias in _hojas(crudos):
        est.extend(establecimientos(anio, generales))
        emi.extend(emisiones(anio, sustancias))
    n = await c.reemplazar("fuente_retc_establecimientos", [
        "anio", "nra", "scian", "actividad", "sector", "estado", "municipio", "geom"], est)
    m = await c.reemplazar("fuente_retc_emisiones", [
        "anio", "nra", "sustancia", "cas", "aire_kg", "agua_kg", "suelo_kg", "transferencias"], emi)
    por_anio = await c.consulta(
        "SELECT anio, count(*), count(geom) FROM fuente_retc_establecimientos GROUP BY 1 ORDER BY 1")
    return {"establecimientos": n, "emisiones": m,
            "por_anio": {a: f"{k} ({g} con coordenada)" for a, k, g in por_anio}}


# --- FIRMS ------------------------------------------------------------------
# VIIRS (375 m) empieza en 2012 y ve todo lo que ve MODIS (1 km) y más. MODIS solo
# entra en los años en que VIIRS no existía, para no contar dos veces un mismo fuego.
PRIMER_ANIO_VIIRS = 2012


def leer_firms(crudos: Path):
    carpeta = crudos / "incendios"
    archivos = sorted(carpeta.glob("firms_viirs_snpp_*.csv")) + sorted(
        p for p in carpeta.glob("firms_modis_*.csv") if int(p.stem[-4:]) < PRIMER_ANIO_VIIRS)
    if not archivos:
        raise c.CrudoFaltante(f"No hay CSV de FIRMS en {carpeta}")
    for p in archivos:
        sensor = "VIIRS_SNPP" if "viirs" in p.name else "MODIS"
        with open(p, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                lon, lat = c.numero(r["longitude"]), c.numero(r["latitude"])
                if not c.en_mexico(lon, lat):
                    continue
                tipo = c.numero(r.get("type"))
                yield [sensor, dt.date.fromisoformat(r["acq_date"]), r["acq_time"].zfill(4), r["confidence"],
                       c.numero(r.get("frp")), r.get("daynight"), None if tipo is None else int(tipo),
                       c.punto_ewkb(lon, lat)]


async def cargar_firms(crudos: Path) -> dict:
    n = await c.reemplazar("fuente_firms_focos", [
        "sensor", "fecha", "hora", "confianza", "frp", "dia_noche", "tipo", "geom"], leer_firms(crudos))
    por_anio = await c.consulta(
        "SELECT sensor, extract(year FROM fecha)::int, count(*) FROM fuente_firms_focos GROUP BY 1, 2 ORDER BY 2")
    return {"focos": n, "por_anio": {f"{a} {s}": k for s, a, k in por_anio}}
