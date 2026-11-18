"""Localidades del Censo 2020 (ITER, "Integración Territorial") para todo el país.

Una fila por localidad, urbana o rural, con su punto, población y los ~280
indicadores de INEGI. Es lo único que ubica a la población rural: el censo por
AGEB solo cubre lo urbano. Ver docs/fuentes/localidades.md.

El archivo nacional (37 MB) trae además renglones de totales (estado y municipio,
`LOC` 0000) y dos de resumen por municipio (`LOC` 9998, localidades de una
vivienda; 9999, de dos). Esas localidades ya vienen una por una con su clave, así
que los resúmenes no se guardan ni se suman: la suma de las localidades es, sola,
el total de cada estado.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile

import httpx

from mapo_core.db import get_pool

URL = "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_00_cpv2020_csv.zip"
CSV = "iter_00_cpv2020/conjunto_de_datos/conjunto_de_datos_iter_00CSV20.csv"
# Fecha de referencia del censo, para la procedencia de cada localidad.
FECHA_CENSO = "2020-03-15"
# INEGI llama urbana a la localidad de 2,500 habitantes o más.
UMBRAL_URBANO = 2_500

_DMS = re.compile(r"""(\d+)\D+(\d+)'([\d.]+)"\s*([NSEW])""")


class ArchivoInvalido(Exception):
    pass


def a_grados(texto: str) -> float | None:
    """`102°17'45.768" W` a -102.29604. `None` si no tiene esa forma."""
    m = _DMS.search(texto or "")
    if not m:
        return None
    grados = int(m[1]) + int(m[2]) / 60 + float(m[3]) / 3600
    return -grados if m[4] in "SW" else grados


def _entero(valor: str) -> int | None:
    valor = (valor or "").strip()
    return int(valor) if valor.isdigit() else None


def leer(zip_bytes: bytes) -> tuple[list[dict], dict[str, tuple[int, int]]]:
    """Las localidades y, por estado, la suma de su población contra el total
    que publica el mismo archivo: `{cve_ent: (suma, total)}`. Tienen que ser
    iguales."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        if CSV not in z.namelist():
            raise ArchivoInvalido(f"El ZIP no trae {CSV}.")
        texto = z.read(CSV).decode("utf-8-sig")

    localidades, totales, suma = [], {}, {}
    for fila in csv.DictReader(io.StringIO(texto)):
        ent, mun, loc = fila["ENTIDAD"], fila["MUN"], fila["LOC"]
        if ent == "00":
            continue
        if mun == "000" and loc == "0000":
            totales[ent] = _entero(fila["POBTOT"]) or 0
            continue
        if loc in ("0000", "9998", "9999"):
            continue
        lon, lat = a_grados(fila["LONGITUD"]), a_grados(fila["LATITUD"])
        if lon is None or lat is None:
            raise ArchivoInvalido(f"La localidad {ent}{mun}{loc} no trae coordenadas legibles.")
        pob = _entero(fila["POBTOT"])
        localidades.append(
            {
                "cvegeo": f"{ent}{mun}{loc}",
                "cve_ent": ent,
                "cve_mun": mun,
                "cve_loc": loc,
                "nombre": fila["NOM_LOC"],
                "nom_mun": fila["NOM_MUN"],
                "tamloc": _entero(fila["TAMLOC"]),
                "ambito": None if pob is None else ("urbana" if pob >= UMBRAL_URBANO else "rural"),
                "altitud": _entero(fila["ALTITUD"]),
                "pobtot": pob,
                "lon": lon,
                "lat": lat,
                "datos": fila,
            }
        )
        suma[ent] = suma.get(ent, 0) + (pob or 0)
    return localidades, {e: (suma.get(e, 0), t) for e, t in totales.items()}


async def descargar(archivo: bytes | None = None) -> tuple[int, dict[str, tuple[int, int]]]:
    """Baja el ITER nacional y reemplaza la tabla `localidades` completa en una
    transacción. No guarda nada si un estado no cuadra con su total."""
    if archivo is None:
        async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as cliente:
            respuesta = await cliente.get(URL)
            respuesta.raise_for_status()
            archivo = respuesta.content

    localidades, cuadres = leer(archivo)
    malos = {e: c for e, c in cuadres.items() if c[0] != c[1]}
    if malos:
        raise ArchivoInvalido(f"La población no cuadra con el total publicado en {sorted(malos)}.")

    pool = await get_pool()
    async with pool.connection() as conn, conn.transaction():
        await conn.execute(
            """CREATE TEMP TABLE carga_localidades (
                   cvegeo TEXT, cve_ent TEXT, cve_mun TEXT, cve_loc TEXT, nombre TEXT, nom_mun TEXT,
                   tamloc SMALLINT, ambito TEXT, altitud INTEGER, pobtot INTEGER,
                   lon DOUBLE PRECISION, lat DOUBLE PRECISION, datos JSONB) ON COMMIT DROP"""
        )
        columnas = ["cvegeo", "cve_ent", "cve_mun", "cve_loc", "nombre", "nom_mun", "tamloc",
                    "ambito", "altitud", "pobtot", "lon", "lat"]
        async with conn.cursor().copy(
            f"COPY carga_localidades ({', '.join(columnas)}, datos) FROM STDIN"
        ) as copia:
            for l in localidades:
                await copia.write_row([l[c] for c in columnas] + [json.dumps(l["datos"], ensure_ascii=False)])
        await conn.execute("DELETE FROM localidades")
        await conn.execute(
            f"""INSERT INTO localidades ({', '.join(columnas[:10])}, datos, geom)
                SELECT {', '.join(columnas[:10])}, datos, ST_SetSRID(ST_MakePoint(lon, lat), 4326)
                FROM carga_localidades"""
        )
    return len(localidades), cuadres
