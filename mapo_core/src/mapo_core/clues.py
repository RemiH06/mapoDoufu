"""Establecimientos de salud del catálogo CLUES de la Secretaría de Salud (DGIS):
cada unidad pública y privada del país con su tipo (consulta externa,
hospitalización, apoyo), institución, estatus de operación y coordenadas.

Se carga del Excel que publica la DGIS cada mes
(`ESTABLECIMIENTO_SALUD_AAAAMM.xlsx`, hoja `CLUES_AAAAMM`, ~68 mil renglones):
openpyxl lo lee en unos minutos. Reemplaza el catálogo completo. Lo usa la
accesibilidad a servicios (accesibilidad.py); ver docs/fuentes/clues.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import openpyxl

from mapo_core.db import get_pool

_NOMBRE = re.compile(r"ESTABLECIMIENTO_SALUD_(\d{4})(\d{2})\.xlsx$", re.IGNORECASE)

# Columna de la base -> encabezado del Excel.
_COLUMNAS = {
    "clues": "CLUES",
    "cve_institucion": "CLAVE DE LA INSTITUCION",
    "institucion": "NOMBRE DE LA INSTITUCION",
    "cve_ent": "CLAVE DE LA ENTIDAD",
    "cve_mun": "CLAVE DEL MUNICIPIO",
    "cve_loc": "CLAVE DE LA LOCALIDAD",
    "tipo": "NOMBRE TIPO ESTABLECIMIENTO",
    "tipologia": "NOMBRE DE TIPOLOGIA",
    "subtipologia": "NOMBRE DE SUBTIPOLOGIA",
    "nombre": "NOMBRE DE LA UNIDAD",
    "estatus": "ESTATUS DE OPERACION",
    "nivel": "NIVEL ATENCION",
    "estrato": "ESTRATO UNIDAD",
    "unidad_movil": "UNIDAD MOVIL TIPO",
    "lat": "LATITUD",
    "lon": "LONGITUD",
}

# Instituciones que no son públicas: servicios médicos privados, Cruz Roja y
# Centros de Integración Juvenil (asociaciones). Lo demás es público, aunque no
# todo atiende a cualquiera (IMSS, ISSSTE, Sedena, Pemex, forenses): quien usa
# el catálogo elige instituciones, no solo `publica`.
PRIVADAS = {"SMP", "CRO", "CIJ"}


class ArchivoInvalido(Exception):
    pass


def corte(ruta: Path) -> str:
    """'2026-10' del nombre del archivo; sin él no se sabe de qué mes es."""
    m = _NOMBRE.search(ruta.name)
    if not m:
        raise ArchivoInvalido(f"{ruta.name}: se espera ESTABLECIMIENTO_SALUD_AAAAMM.xlsx")
    return f"{m.group(1)}-{m.group(2)}"


def _coordenada(valor, minimo: float, maximo: float) -> float | None:
    try:
        x = float(valor)
    except (TypeError, ValueError):
        return None
    return x if minimo <= x <= maximo else None


def _texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


def leer(ruta: Path) -> list[dict]:
    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        hoja = next((libro[n] for n in libro.sheetnames if n.upper().startswith("CLUES_")), None)
        if hoja is None:
            raise ArchivoInvalido(f"no hay hoja CLUES_AAAAMM (hojas: {', '.join(libro.sheetnames)})")
        filas = hoja.iter_rows(values_only=True)
        encabezado = [_texto(c).upper() for c in next(filas)]
        faltan = [e for e in _COLUMNAS.values() if e not in encabezado]
        if faltan:
            raise ArchivoInvalido(f"faltan columnas: {', '.join(faltan)}")
        indice = {col: encabezado.index(e) for col, e in _COLUMNAS.items()}
        salida = []
        for fila in filas:
            r = {col: _texto(fila[i]) for col, i in indice.items()}
            if not r["clues"]:
                continue
            r["cve_ent"] = r["cve_ent"].zfill(2)
            r["cve_mun"] = r["cve_mun"].zfill(3)
            r["cve_loc"] = r["cve_loc"].zfill(4)
            # La caja de México; una coordenada fuera (o en 0) es un error de captura.
            r["lat"] = _coordenada(fila[indice["lat"]], 14.0, 33.0)
            r["lon"] = _coordenada(fila[indice["lon"]], -118.5, -86.5)
            r["publica"] = r["cve_institucion"] not in PRIVADAS
            salida.append(r)
        return salida
    finally:
        libro.close()


async def cargar(ruta: Path) -> dict:
    mes = corte(ruta)
    filas = leer(ruta)
    if len(filas) < 1000:
        raise ArchivoInvalido(f"solo {len(filas)} establecimientos: el catálogo nacional trae decenas de miles")
    columnas = [*_COLUMNAS, "publica"]
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM fuente_clues")
            async with conn.cursor() as cur:
                async with cur.copy(f"COPY fuente_clues ({', '.join(columnas)}, corte) FROM STDIN") as copia:
                    for f in filas:
                        await copia.write_row([*(f[c] for c in columnas), mes])
            await conn.execute(
                "UPDATE fuente_clues SET geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326) WHERE lat IS NOT NULL AND lon IS NOT NULL"
            )
    return {
        "corte": mes,
        "establecimientos": len(filas),
        "sin_coordenadas": sum(f["lat"] is None or f["lon"] is None for f in filas),
        "en_operacion": sum(f["estatus"] == "EN OPERACION" for f in filas),
    }
