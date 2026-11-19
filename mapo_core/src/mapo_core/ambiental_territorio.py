"""Territorio: uso de suelo y vegetación de INEGI (series VI y VII) y áreas naturales
protegidas federales de CONANP, ambas en la copia del geoportal de CONABIO. Ver
docs/fuentes/uso-suelo.md y anp.md."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from mapo_core import crudos as c

SERIES = {7: "territorio/usv250_serie7.zip", 6: "territorio/usv250_serie6.zip"}


def _codigo(valor) -> str | None:
    n = c.numero(valor)
    if n is not None and n == int(n):
        return str(int(n))
    return c.texto(valor)


def leer_uso_suelo(crudos: Path, serie: int):
    for a, g in c.shapefile_en_zip(c.ruta(crudos, SERIES[serie])):
        mp = c.multipoligono(g)
        if mp is None:
            continue
        descripcion = c.texto(a.get("DESCRIPCIO") or a.get("DESCRIPCION")) or "(sin descripción)"
        yield [serie, descripcion, _codigo(a.get("codigo") or a.get("CODIGO") or a.get("CVE_UNION")), c.ewkb(mp)]


async def cargar_uso_suelo(crudos: Path) -> dict:
    salida = {}
    for serie in SERIES:
        n = await c.reemplazar("fuente_uso_suelo", ["serie", "descripcion", "codigo", "geom"],
                               leer_uso_suelo(crudos, serie), "serie = %s", (serie,))
        filas = await c.consulta(
            "SELECT descripcion, sum(ST_Area(geom::geography)) / 1e4 AS ha FROM fuente_uso_suelo"
            " WHERE serie = %s GROUP BY 1 ORDER BY 2 DESC LIMIT 6", (serie,))
        (total,), = await c.consulta(
            "SELECT sum(ST_Area(geom::geography)) / 1e4 FROM fuente_uso_suelo WHERE serie = %s", (serie,))
        salida[f"serie_{serie}"] = {"poligonos": n, "millones_ha": round(total / 1e6, 2),
                                    "mayores_millones_ha": {d: round(h / 1e6, 2) for d, h in filas}}
    return salida


def _fecha(valor) -> dt.date | None:
    if isinstance(valor, dt.date):
        return valor
    try:
        return dt.date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def leer_anp(crudos: Path):
    for a, g in c.shapefile_en_zip(c.ruta(crudos, "territorio/anp_2020.zip")):
        yield [c.texto(a["ID_ANP"]), c.texto(a["NOMBRE"]), c.texto(a.get("CAT_DECRET")), c.texto(a.get("ESTADOS")),
               c.numero(a.get("SUPERFICIE")), c.numero(a.get("S_TERRES")), c.numero(a.get("S_MARINA")),
               _fecha(a.get("PRIM_DEC")), _fecha(a.get("ULT_DOF")), c.ewkb(c.multipoligono(g))]


async def cargar_anp(crudos: Path) -> dict:
    n = await c.reemplazar("fuente_anp", [
        "id", "nombre", "categoria", "estados", "superficie_ha", "terrestre_ha", "marina_ha", "primer_decreto",
        "ultimo_dof", "geom"], leer_anp(crudos))
    (decreto, calculada), = await c.consulta(
        "SELECT sum(superficie_ha), sum(ST_Area(geom::geography)) / 1e4 FROM fuente_anp")
    por_cat = await c.consulta("SELECT categoria, count(*) FROM fuente_anp GROUP BY 1 ORDER BY 2 DESC")
    return {"anp": n, "superficie_decretada_millones_ha": round(decreto / 1e6, 2),
            "superficie_de_los_poligonos_millones_ha": round(calculada / 1e6, 2),
            "por_categoria": dict(por_cat)}
