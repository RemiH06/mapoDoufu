"""Precios de oferta de vivienda del IIEG (Jalisco) para el MEDV del dataset.

El IIEG junta cada trimestre los anuncios de venta de casas y departamentos de
los portales inmobiliarios en seis municipios de la zona metropolitana de
Guadalajara y publica dos cosas que se usan aquí:

- `BD_SECTOR_INMOBILIARIO_<mes>_<año>.xlsx`, hoja `Venta`: un renglón por anuncio,
  con municipio, colonia (vacía en ~43 %), precio y metros cuadrados.
- `mapa_venta.shp` (de `conjunto_datos_vectoriales.zip`): los polígonos de las
  colonias con que el IIEG ubicó los anuncios, en WGS84.

Los anuncios no traen coordenadas: se ubican por el nombre de su colonia.
Documentación: docs/fuentes/iieg-oferta.md.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from shapely import STRtree, wkb
from shapely.geometry import shape
from shapely.ops import unary_union

# Nombres del IIEG → clave INEGI del municipio (Jalisco).
MUNICIPIOS = {
    "GUADALAJARA": "039", "ZAPOPAN": "120", "TLAQUEPAQUE": "098",
    "TONALA": "101", "TLAJOMULCO": "097", "EL SALTO": "070",
}
# Anuncios efectivos mínimos para dar medv a una AGEB.
MIN_ANUNCIOS = 3
# Metros construidos plausibles para el precio por m².
M2_MIN, M2_MAX = 20, 3000


class ArchivoInvalido(ValueError):
    pass


def normalizar(texto: str | None) -> str | None:
    """Mayúsculas sin acentos ni signos: el XLSX y el shapefile no codifican la Ñ igual."""
    if texto is None or (isinstance(texto, float) and np.isnan(texto)):
        return None
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Z0-9]+", " ", t.upper()).strip()
    return t or None


def _municipio(nombre) -> str:
    clave = MUNICIPIOS.get(normalizar(nombre) or "")
    if clave is None:
        raise ArchivoInvalido(f"municipio desconocido en el archivo del IIEG: {nombre!r}")
    return clave


@dataclass(frozen=True)
class Anuncio:
    cve_mun: str
    colonia: str | None
    inmueble: str
    precio: float
    m2_construccion: float | None


def leer_anuncios(ruta: Path) -> list[Anuncio]:
    """Anuncios de venta sin duplicados exactos (el IIEG avisa que los portales
    repiten el mismo anuncio; un duplicado exacto es mismo municipio, colonia,
    tipo, precio y metros)."""
    from openpyxl import load_workbook

    libro = load_workbook(ruta, read_only=True, data_only=True)
    if "Venta" not in libro.sheetnames:
        raise ArchivoInvalido(f"{ruta.name} no tiene la hoja Venta")
    filas = libro["Venta"].iter_rows(values_only=True)
    encabezado = [normalizar(c) for c in next(filas)]
    esperado = ["INMUEBLE", "MUNICIPIO", "COLONIA", "PRECIO", "METROS CUADRADOS DE TERRENO",
                "METROS CUADRADOS DE CONSTRUCCION"]
    if encabezado[:6] != esperado:
        raise ArchivoInvalido(f"columnas inesperadas en {ruta.name}: {encabezado}")
    vistos, salida = set(), []
    for fila in filas:
        inmueble, mun, colonia, precio, m2t, m2c = fila[:6]
        if precio is None or mun is None:
            continue
        clave = (inmueble, mun, colonia, precio, m2t, m2c)
        if clave in vistos:
            continue
        vistos.add(clave)
        m2 = float(m2c) if m2c is not None and M2_MIN <= float(m2c) <= M2_MAX else None
        salida.append(Anuncio(_municipio(mun), normalizar(colonia), str(inmueble), float(precio), m2))
    return salida


def leer_colonias(ruta: Path) -> dict[tuple[str, str], object]:
    """(cve_mun, colonia normalizada) → polígono. Las colonias con el mismo nombre
    en el mismo municipio se unen: el anuncio no dice cuál de ellas es."""
    import shapefile

    cpg = ruta.with_suffix(".cpg")
    codificacion = cpg.read_text().strip() if cpg.exists() else "utf-8"
    partes: dict[tuple[str, str], list] = {}
    with shapefile.Reader(str(ruta), encoding=codificacion, encodingErrors="replace") as r:
        for reg in r.iterShapeRecords():
            d = reg.record.as_dict()
            nombre = normalizar(d["COLONIA"])
            if nombre and reg.shape.points:
                partes.setdefault((_municipio(d["NOMBRE_MUN"]), nombre), []).append(
                    shape(reg.shape.__geo_interface__).buffer(0))
    return {k: unary_union(v) for k, v in partes.items()}


def mediana_ponderada(valores: list[float], pesos: list[float]) -> float:
    orden = np.argsort(valores)
    v, w = np.asarray(valores, dtype=float)[orden], np.asarray(pesos, dtype=float)[orden]
    acumulado = np.cumsum(w)
    return float(v[np.searchsorted(acumulado, acumulado[-1] / 2)])


def asignar(filas: list[dict], anuncios: list[Anuncio], colonias: dict, periodo: str) -> None:
    """`medv` y compañía por AGEB.

    Un anuncio de la colonia c cuenta en la AGEB a con peso área(c ∩ a) / área(c):
    si los anuncios se reparten parejo dentro de su colonia, es cuántos caen en a.
    Solo cuentan colonias del mismo municipio que la AGEB. Nunca se rellena con
    vecinas: con menos de MIN_ANUNCIOS efectivos, medv queda vacío y se dice.
    """
    por_colonia: dict[tuple[str, str], list[Anuncio]] = {}
    for a in anuncios:
        if a.colonia and (a.cve_mun, a.colonia) in colonias:
            por_colonia.setdefault((a.cve_mun, a.colonia), []).append(a)
    claves = list(colonias)
    arbol = STRtree([colonias[k] for k in claves])
    con_datos = set(MUNICIPIOS.values())
    for f in filas:
        geom = wkb.loads(f["_geom"])
        precios, m2, pesos, pesos_m2, deptos = [], [], [], [], 0.0
        for i in arbol.query(geom, predicate="intersects"):
            k = claves[int(i)]
            if k[0] != f["cve_mun"] or k not in por_colonia:
                continue
            col = colonias[k]
            peso = col.intersection(geom).area / col.area if col.area else 0.0
            if peso <= 0:
                continue
            for a in por_colonia[k]:
                precios.append(a.precio)
                pesos.append(peso)
                deptos += peso if a.inmueble == "Departamento" else 0.0
                if a.m2_construccion:
                    m2.append(a.precio / a.m2_construccion)
                    pesos_m2.append(peso)
        n = sum(pesos)
        f["medv_n"] = round(n, 2) if f["cve_mun"] in con_datos else None
        f["medv_periodo"] = periodo if f["cve_mun"] in con_datos else None
        if f["cve_mun"] not in con_datos:
            f["medv"] = f["medv_m2"] = f["pct_departamentos"] = None
            f["medv_metodo"] = "el IIEG no publica anuncios de este municipio"
        elif n < MIN_ANUNCIOS:
            f["medv"] = f["medv_m2"] = f["pct_departamentos"] = None
            f["medv_metodo"] = f"menos de {MIN_ANUNCIOS} anuncios efectivos ({n:.1f})"
        else:
            f["medv"] = round(mediana_ponderada(precios, pesos))
            f["medv_m2"] = round(mediana_ponderada(m2, pesos_m2)) if sum(pesos_m2) >= MIN_ANUNCIOS else None
            f["pct_departamentos"] = round(100 * deptos / n, 1)
            f["medv_metodo"] = f"mediana ponderada de {n:.1f} anuncios efectivos de las colonias que tocan la AGEB"


def resumen_municipal(anuncios: list[Anuncio], periodo: str) -> list[dict]:
    """Media, mediana y cuartiles por municipio con todos los anuncios, también
    los que no tienen colonia: es la cifra contra la que se calibra."""
    salida = []
    for nombre, cve in MUNICIPIOS.items():
        p = np.array([a.precio for a in anuncios if a.cve_mun == cve])
        if not len(p):
            continue
        salida.append({
            "cve_mun": cve, "municipio_iieg": nombre, "periodo": periodo, "anuncios": len(p),
            "anuncios_con_colonia": sum(1 for a in anuncios if a.cve_mun == cve and a.colonia),
            "media": round(float(p.mean())), "p25": round(float(np.percentile(p, 25))),
            "mediana": round(float(np.median(p))), "p75": round(float(np.percentile(p, 75))),
        })
    return salida
