"""Valor de suelo por AGEB: el catastro donde hay, un rango conformal donde no.

La tabla sale del estudio `estudios/precio_estimado/` (notebook de la sesión 23c)
y se carga tal cual: Mapo no ajusta el modelo, solo guarda y muestra el resultado
con su método, su cobertura medida y su versión. Ver docs/producto/precio-estimado.md.
"""

from __future__ import annotations

import csv
import io

from mapo_core.db import get_pool

FUENTES = {"catastro", "modelo", "sin_base"}
COLUMNAS = ["cvegeo", "cve_ent", "cve_mun", "fuente", "valor", "rango_bajo", "rango_alto",
            "anio_tabla", "cobertura", "n_base", "metodo", "version"]


class ArchivoInvalido(Exception):
    pass


def _numero(texto: str, tipo=float):
    texto = (texto or "").strip()
    return tipo(float(texto)) if texto else None


def leer(texto: str) -> list[dict]:
    filas = list(csv.DictReader(io.StringIO(texto)))
    faltan = {"cvegeo", "fuente", "valor", "rango_bajo", "rango_alto", "anio_tabla", "cobertura",
              "n_base", "metodo", "version"} - set(filas[0] if filas else [])
    if faltan:
        raise ArchivoInvalido(f"Faltan columnas: {sorted(faltan)}.")
    salida = []
    for f in filas:
        cvegeo = f["cvegeo"].strip()
        if len(cvegeo) != 13:
            raise ArchivoInvalido(f"Clave de AGEB inválida: {cvegeo!r}.")
        if f["fuente"] not in FUENTES:
            raise ArchivoInvalido(f"Fuente desconocida en {cvegeo}: {f['fuente']!r}.")
        fila = {
            "cvegeo": cvegeo, "cve_ent": cvegeo[:2], "cve_mun": cvegeo[2:5], "fuente": f["fuente"],
            "valor": _numero(f["valor"]), "rango_bajo": _numero(f["rango_bajo"]),
            "rango_alto": _numero(f["rango_alto"]), "anio_tabla": _numero(f["anio_tabla"], int),
            "cobertura": _numero(f["cobertura"]), "n_base": _numero(f["n_base"], int),
            "metodo": f["metodo"], "version": f["version"],
        }
        # Cada fuente trae justo lo suyo: un valor observado o un rango, nunca los dos.
        if fila["fuente"] == "catastro" and fila["valor"] is None:
            raise ArchivoInvalido(f"{cvegeo}: catastro sin valor.")
        if fila["fuente"] == "modelo" and not (
            fila["rango_bajo"] is not None and fila["rango_alto"] is not None
            and 0 < fila["rango_bajo"] <= fila["rango_alto"] and fila["cobertura"] is not None
        ):
            raise ArchivoInvalido(f"{cvegeo}: rango o cobertura inválidos.")
        salida.append(fila)
    return salida


async def cargar(texto: str) -> int:
    filas = leer(texto)
    pool = await get_pool()
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("DELETE FROM fuente_precio_estimado")
        async with conn.cursor().copy(f"COPY fuente_precio_estimado ({', '.join(COLUMNAS)}) FROM STDIN") as copia:
            for f in filas:
                await copia.write_row([f[c] for c in COLUMNAS])
    return len(filas)
