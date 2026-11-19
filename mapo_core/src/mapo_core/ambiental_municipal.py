"""Lo que solo viene por municipio: cierre agrícola del SIAP, Monitor de Sequía del SMN
y defunciones registradas de INEGI (agregadas, sin microdatos). Ver
docs/fuentes/siap.md, sequia.md y defunciones.md."""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from mapo_core import crudos as c


# --- SIAP -------------------------------------------------------------------
def _abrir_csv(p: Path):
    # Cada año trae su codificación: unos UTF-8 y otros Latin-1.
    crudo = p.read_bytes()
    try:
        texto = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = crudo.decode("latin-1")
    return csv.DictReader(io.StringIO(texto, newline=""))


_SUMAS = ("Sembrada", "Cosechada", "Siniestrada", "Volumenproduccion", "Valorproduccion")


def leer_siap(crudos: Path) -> list[list]:
    archivos = sorted((crudos / "agricultura").glob("siap_municipal_*.csv"))
    if not archivos:
        raise c.CrudoFaltante("No hay agricultura/siap_municipal_*.csv")
    suma: dict[tuple, list] = defaultdict(lambda: [0.0] * len(_SUMAS))
    for p in archivos:
        for r in _abrir_csv(p):
            # Un municipio puede venir partido entre varios CADER: se suma.
            llave = (int(r["Anio"]), r["Idestado"].zfill(2), r["Idmunicipio"].zfill(3), r["Nomcicloproductivo"].strip(),
                     r["Nommodalidad"].strip(), (r.get("Nomcultivo") or r["Nomcultivo Sin Um"]).strip(),
                     r["Nomunidad"].strip())  # de 2015 a 2020 la columna se llama "Nomcultivo Sin Um"
            acumulado = suma[llave]
            for i, col in enumerate(_SUMAS):
                acumulado[i] += c.numero(r.get(col)) or 0.0
    return [[*llave, *valores] for llave, valores in suma.items()]


async def cargar_siap(crudos: Path) -> dict:
    n = await c.reemplazar("fuente_siap_agricola", [
        "anio", "cve_ent", "cve_mun", "ciclo", "modalidad", "cultivo", "unidad", "sembrada", "cosechada",
        "siniestrada", "volumen", "valor"], leer_siap(crudos))
    maiz = await c.consulta(
        "SELECT anio, sum(volumen) FROM fuente_siap_agricola WHERE cultivo = 'Maíz grano' AND unidad = 'Tonelada'"
        " AND anio >= 2020 GROUP BY 1 ORDER BY 1")
    (jal_sembrada,), = await c.consulta(
        "SELECT sum(sembrada) FROM fuente_siap_agricola WHERE cve_ent = '14' AND anio = 2024")
    return {"filas": n, "maiz_grano_millones_t": {a: round(v / 1e6, 2) for a, v in maiz},
            "jalisco_2024_sembrada_ha": round(jal_sembrada or 0)}


# --- Monitor de Sequía ------------------------------------------------------
_CATEGORIA = re.compile(r"^D[0-4]$")


def leer_sequia(crudos: Path):
    filas = c.xlsx_filas(c.ruta(crudos, "riesgo/sequia_municipios.xlsx"), "MUNICIPIOS")
    encabezado = next(filas)
    fechas = [(i, h.date() if isinstance(h, dt.datetime) else h) for i, h in enumerate(encabezado)
              if isinstance(h, (dt.date, dt.datetime))]
    for fila in filas:
        clave = c.texto(fila[0])
        if not clave:
            continue
        clave = clave.zfill(5)
        for i, fecha in fechas:
            valor = (c.texto(fila[i]) or "").upper()
            if valor and not _CATEGORIA.match(valor):
                raise ValueError(f"categoría de sequía desconocida {valor!r} en {clave} {fecha}")
            # Vacío en el Monitor es "sin anomalía", no dato faltante.
            yield [clave[:2], clave[2:], fecha, valor or "sin"]


async def cargar_sequia(crudos: Path) -> dict:
    n = await c.reemplazar("fuente_sequia_municipal", ["cve_ent", "cve_mun", "fecha", "categoria"],
                           leer_sequia(crudos))
    (primera, ultima, cortes, municipios), = await c.consulta(
        "SELECT min(fecha), max(fecha), count(DISTINCT fecha), count(DISTINCT cve_ent || cve_mun)"
        " FROM fuente_sequia_municipal")
    ultimo = await c.consulta(
        "SELECT categoria, count(*) FROM fuente_sequia_municipal WHERE fecha = %s GROUP BY 1 ORDER BY 1", (ultima,))
    return {"filas": n, "desde": str(primera), "hasta": str(ultima), "cortes": cortes, "municipios": municipios,
            "ultimo_corte": dict(ultimo)}


# --- Defunciones ------------------------------------------------------------
def _contar_defunciones(zip_ruta: Path) -> Counter:
    with zipfile.ZipFile(zip_ruta) as z:
        # La ruta del CSV cambia por año (2023 no usa conjunto_de_datos/): el más grande.
        miembro = max(z.infolist(), key=lambda i: i.file_size)
        conteo: Counter = Counter()
        with z.open(miembro) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace", newline="")):
                conteo[(int(r["anio_regis"]), r["ent_resid"].strip('"').zfill(2), r["mun_resid"].strip('"').zfill(3),
                        r["causa_def"].strip('"')[:3], int(r["sexo"] or 9), int(r["edad_agru"] or 30))] += 1
    return conteo


async def cargar_defunciones(crudos: Path) -> dict:
    archivos = sorted((crudos / "salud").glob("defunciones_*.zip"))
    if not archivos:
        raise c.CrudoFaltante("No hay salud/defunciones_*.zip")
    total: Counter = Counter()
    for p in archivos:
        total.update(_contar_defunciones(p))
    n = await c.reemplazar("fuente_defunciones_municipal", [
        "anio_registro", "cve_ent", "cve_mun", "causa", "sexo", "edad_grupo", "defunciones"],
        ([*llave, k] for llave, k in total.items()))
    por_anio = await c.consulta(
        "SELECT anio_registro, sum(defunciones) FROM fuente_defunciones_municipal GROUP BY 1 ORDER BY 1")
    return {"filas": n, "defunciones_por_anio": {a: int(k) for a, k in por_anio}}
