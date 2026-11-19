"""Agua: acuíferos de Conagua (disponibilidad, vedas, piezometría), calidad del
agua de la RENAMECA y descargas residuales del REPDA. Ver docs/fuentes/acuiferos.md,
renameca.md y repda.md."""

from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile
from pathlib import Path

from mapo_core import crudos as c

FECHA_DISPONIBILIDAD = dt.date(2023, 11, 9)


# --- Acuíferos --------------------------------------------------------------
def leer_acuiferos(crudos: Path):
    for a, g in c.shapefile_en_zip(c.ruta(crudos, "acuiferos/disponibilidad_2023-11-09.zip")):
        v = {k: c.numero(a.get(k)) for k in ("AREA_KM2", "RECARGA_TO", "DESCARGA_N", "VCAS", "VEALA",
                                              "VAPTYR", "VAPRH", "VEAS", "DMA_POSITI", "DMA_NEGATI")}
        # Conagua parte la DMA en dos columnas: una positiva y otra negativa (déficit).
        dma = (v["DMA_POSITI"] or 0) + (v["DMA_NEGATI"] or 0)
        yield [str(a["CLV_ACUI"]).zfill(4), c.texto(a["NOM_ACUI"]), str(a["CLV_EDO"]).zfill(2),
               c.texto(a["NOM_REGION"]), v["AREA_KM2"], v["RECARGA_TO"], v["DESCARGA_N"], v["VCAS"], v["VEALA"],
               v["VAPTYR"], v["VAPRH"], v["VEAS"], dma, FECHA_DISPONIBILIDAD, c.ewkb(c.multipoligono(g))]


ORDENAMIENTOS = (("veda", "Vedas"), ("suspension", "Suspension"), ("reglamento", "Reglamentos"))


def _fecha(valor) -> dt.date | None:
    if isinstance(valor, dt.date):
        return valor
    try:
        return dt.date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def leer_ordenamientos(crudos: Path):
    zip_ruta = c.ruta(crudos, "acuiferos/vedas_y_ordenamientos.zip")
    for tipo, contiene in ORDENAMIENTOS:
        for a, g in c.shapefile_en_zip(zip_ruta, contiene):
            clave = c.texto(a.get("CLV_ACUI"))
            yield [tipo, c.texto(a.get("NOM_CORTO")) or "", c.texto(a.get("NOM_OFI")), _fecha(a.get("FECHA_DOF")),
                   None if clave in (None, "n/a") else clave.zfill(4), c.texto(a.get("DES_CLASIF")),
                   c.texto(a.get("LINK_DOF")), c.ewkb(c.multipoligono(g))]


def leer_piezometria(crudos: Path):
    vistos = set()
    for a, g in c.shapefile_en_zip(c.ruta(crudos, "acuiferos/red_piezometrica_2023.zip")):
        pozo = str(a["num_pozo"])
        if pozo in vistos:
            raise ValueError(f"pozo repetido en la red piezométrica: {pozo}")
        vistos.add(pozo)
        pne = {k[4:]: c.numero(v) for k, v in a.items() if k.startswith("PNE_") and c.numero(v) is not None}
        if g is None or g.is_empty:
            continue
        yield [pozo, c.texto(a.get("nom_pozo")), str(a.get("CVE_ACUI") or "").zfill(4) or None,
               c.numero(a.get("elev_broc")), c.jsonb(pne), c.ewkb(g)]


async def cargar_acuiferos(crudos: Path) -> dict:
    n = await c.reemplazar("fuente_acuiferos", [
        "clave", "nombre", "cve_ent", "region", "area_km2", "recarga", "descarga_natural", "vcas", "veala",
        "vaptyr", "vaprh", "veas", "disponibilidad", "fecha_dof", "geom"], leer_acuiferos(crudos))
    o = await c.reemplazar("fuente_acuiferos_ordenamientos", [
        "tipo", "nombre", "nombre_dof", "fecha_dof", "clave_acuifero", "clasificacion", "url_dof", "geom"],
        leer_ordenamientos(crudos))
    p = await c.reemplazar("fuente_piezometria", [
        "pozo", "nombre", "clave_acuifero", "elev_brocal", "pne", "geom"], leer_piezometria(crudos))
    (sin, deficit_formula), = await c.consulta(
        "SELECT count(*) FILTER (WHERE disponibilidad <= 0),"
        " max(abs(recarga - descarga_natural - veas - disponibilidad)) FROM fuente_acuiferos")
    return {"acuiferos": n, "sin_disponibilidad": sin, "error_max_dma_hm3": round(deficit_formula or 0, 6),
            "ordenamientos": o, "pozos_piezometricos": p}


# --- RENAMECA ---------------------------------------------------------------
RENAMECA = (("superficial", "agua/calidad_superficial_2012-2025.xlsx"),
            ("subterranea", "agua/calidad_subterranea_2012-2025.xlsx"))
_DESCRIPTIVAS = {"CLAVE SITIO", "NOMBRE DEL SITIO", "SITIO", "ORGANISMO_DE_CUENCA", "ESTADO", "MUNICIPIO",
                 "CUENCA", "ACUIFERO", "CUERPO DE AGUA", "TIPO", "SUBTIPO", "LATITUD", "LONGITUD", "ANO",
                 "PERIODO", "SEMAFORO"}


def parametros(encabezado: list[str], fila: tuple) -> dict:
    """Cada medición con su calificación, tal como la publica Conagua: '<2' (bajo el
    límite de detección) se queda como texto. Una medición puede tener dos
    calificaciones (sólidos disueltos para riego y por salinidad)."""
    salida: dict = {}
    actual = None
    for nombre, valor in zip(encabezado, fila):
        clave = c.normalizar(nombre)
        if clave in _DESCRIPTIVAS:
            actual = None
            continue
        if clave.startswith("CALIDAD"):
            if actual is not None and valor not in (None, ""):
                salida[actual].setdefault("calidades", []).append(str(valor).strip())
            continue
        actual = nombre
        salida[nombre] = {"valor": valor if isinstance(valor, (int, float)) else c.texto(valor)}
    limpio = {}
    for nombre, d in salida.items():
        if d["valor"] is None and not d.get("calidades"):
            continue
        calidades = d.pop("calidades", [])
        if calidades:
            d["calidad"] = calidades[0]
            if len(calidades) > 1:
                d["calidad_2"] = calidades[1]
        limpio[nombre] = d
    return limpio


def leer_renameca(crudos: Path):
    for tipo, archivo in RENAMECA:
        filas = c.xlsx_filas(c.ruta(crudos, archivo), 0)
        encabezado = [str(h or "") for h in next(filas)]
        col = {c.normalizar(h): i for i, h in enumerate(encabezado)}

        def v(fila, *nombres):
            for n in nombres:
                if n in col and col[n] < len(fila):
                    return c.texto(fila[col[n]])
            return None

        for fila in filas:
            clave = v(fila, "CLAVE SITIO")
            if not clave:
                continue
            lon, lat = c.numero(fila[col["LONGITUD"]]), c.numero(fila[col["LATITUD"]])
            geom = c.punto_ewkb(lon, lat) if c.en_mexico(lon, lat) else None
            yield [clave, tipo, v(fila, "NOMBRE DEL SITIO", "SITIO"), v(fila, "ORGANISMO_DE_CUENCA"), v(fila, "ESTADO"),
                   v(fila, "MUNICIPIO"), v(fila, "CUENCA", "ACUIFERO"), v(fila, "CUERPO DE AGUA"), v(fila, "SUBTIPO"),
                   v(fila, "ANO", "PERIODO") or "", v(fila, "SEMAFORO"), c.jsonb(parametros(encabezado, fila)), geom]


async def cargar_renameca(crudos: Path) -> dict:
    n = await c.reemplazar("fuente_renameca_sitios", [
        "clave", "tipo", "nombre", "organismo", "estado", "municipio", "cuenca", "cuerpo", "subtipo", "periodo",
        "semaforo", "parametros", "geom"], _sin_repetir(leer_renameca(crudos), (0, 1)))
    filas = await c.consulta(
        "SELECT tipo, coalesce(semaforo, '(sin)'), count(*), count(geom) FROM fuente_renameca_sitios"
        " GROUP BY 1, 2 ORDER BY 1, 2")
    return {"sitios": n, "por_semaforo": {f"{t} {s}": k for t, s, k, _ in filas},
            "sin_coordenada_valida": sum(k - g for _, _, k, g in filas)}


def _sin_repetir(filas, indices):
    vistos = set()
    for f in filas:
        llave = tuple(f[i] for i in indices)
        if llave in vistos:
            continue
        vistos.add(llave)
        yield f


# --- REPDA: descargas residuales -------------------------------------------
def _csv_en_zip(z: zipfile.ZipFile, termina: str):
    nombre = next(n for n in z.namelist() if n.split("/")[-1].upper() == termina)
    with z.open(nombre) as f:
        lector = csv.reader(io.TextIOWrapper(f, encoding="utf-8", newline=""))
        encabezado = [c.normalizar(h) for h in next(lector)]
        for fila in lector:
            yield dict(zip(encabezado, fila))


def _dms(grados, minutos, segundos) -> float | None:
    g, m, s = (c.numero(x) for x in (grados, minutos, segundos))
    if g is None:
        return None
    return abs(g) + (m or 0) / 60 + (s or 0) / 3600


def leer_repda(crudos: Path):
    with zipfile.ZipFile(c.ruta(crudos, "concesiones/otorgamiento_de_concesiones.zip")) as z:
        # El uso y la fecha vienen del título. TITULAR no se lee: puede ser una persona.
        titulos = {}
        for t in _csv_en_zip(z, "CONCESIONES.CSV"):
            titulos[t["TITULO"]] = (c.texto(t.get("USO QUE AMPARA EL TITULO")), _fecha(t.get("FECHA DE REGISTRO")))
        for d in _csv_en_zip(z, "ANEXOS_RESIDUALES.CSV"):
            lat = _dms(d["GRADOS LATITUD"], d["MINUTOS LATITUD"], d["SEGUNDOS LATITUD"])
            lon = _dms(d["GRADOS LONGITUD"], d["MINUTOS LONGITUD"], d["SEGUNDOS LONGITUD"])
            lon = -lon if lon is not None else None  # vienen sin signo; México es oeste
            uso, fecha = titulos.get(d["TITULO"], (None, None))
            yield [d["TITULO"], c.texto(d.get("NUMERO DE ANEXO")), uso,
                   (c.texto(d.get("CLAVE DE ESTADO")) or "").zfill(2) or None,
                   (c.texto(d.get("CLAVE DE MUNICIPIO")) or "").zfill(3) or None,
                   c.texto(d.get("NOMBRE DE MUNICIPIO")), c.texto(d.get("NOMBRE DE CUENCA HIDROLOGICA")),
                   c.numero(d.get("VOLUMEN ANUAL EN M3")), c.texto(d.get("PROCEDENCIA")),
                   c.texto(d.get("CUERPO RECEPTOR")), c.texto(d.get("TIPO DE DESCARGA")),
                   c.texto(d.get("AFLUENTE AL QUE SE DESCARGA")), c.texto(d.get("FORMA DE DESCARGAR")), fecha,
                   c.punto_ewkb(lon, lat) if c.en_mexico(lon, lat) else None]


async def cargar_repda(crudos: Path) -> dict:
    n = await c.reemplazar("fuente_repda_descargas", [
        "titulo", "anexo", "uso", "cve_ent", "cve_mun", "municipio", "cuenca", "volumen_anual", "procedencia",
        "cuerpo_receptor", "tipo_descarga", "afluente", "forma", "fecha_registro", "geom"], leer_repda(crudos))
    (con_geom, volumen, sin_uso), = await c.consulta(
        "SELECT count(geom), sum(volumen_anual), count(*) FILTER (WHERE uso IS NULL) FROM fuente_repda_descargas")
    return {"descargas": n, "con_coordenada": con_geom, "volumen_anual_hm3": round((volumen or 0) / 1e6, 1),
            "sin_titulo_en_concesiones": sin_uso, **await en_su_municipio("fuente_repda_descargas")}


async def en_su_municipio(tabla: str) -> dict:
    """Qué parte de los puntos cae en el municipio que declara, entre los municipios
    cargados en Mapo. Conagua y SEMARNAT traen errores de captura."""
    (total, dentro), = await c.consulta(f"""
        SELECT count(*), count(*) FILTER (WHERE ST_Covers(m.geom, t.geom))
        FROM {tabla} t JOIN municipios m ON m.cve_ent = t.cve_ent AND m.cve_mun = t.cve_mun
        WHERE t.geom IS NOT NULL""")
    return {"puntos_con_municipio_cargado": total,
            "en_su_municipio_pct": round(100 * dentro / total, 1) if total else None}
