"""Versión para ArcGIS Pro de un paquete de `recorte.py` (zona.gpkg, imagenes/, tablas/).

Lo que cambia contra el paquete original, que está pensado para QGIS:

- Una File Geodatabase con las capas agrupadas por tema (conjuntos de entidades:
  Población, Agua, Emisiones y fuego, Territorio, Ciudad, Especies). Arrastrar un
  conjunto al mapa lo agrega como grupo de capas.
- Todo en UTM 13N (EPSG:32613), el mismo sistema de las imágenes: buffers, áreas y
  distancias salen en metros sin proyectar nada.
- Nombres de capa y de campo que ArcGIS acepta, con alias legibles: el nombre
  original (con espacios y acentos) o la descripción de INEGI para las variables del
  censo. Un diccionario de campos va como tabla.
- Los conteos del censo y del ITER vienen como texto por el '*' (dato reservado) y
  el 'N/D' (no disponible) de INEGI. Aquí son números y esos quedan vacíos (nulos),
  así se pueden simbolizar.
- Las tablas (viento, SIAP, sequía, marginación...) entran a la geodatabase con sus
  claves como texto: abrirlas en Excel les quitaba los ceros a la izquierda.
- Las imágenes van en unidades reales (NDVI de -1 a 1, °C, metros) y WorldCover con
  el nombre de cada clase y sus colores.
- Del RETC se quitan nombre y establecimiento: hay talleres a nombre de personas.
- Defunciones: solo conteos por municipio, año, causa, sexo y grupo de edad. Si el
  paquete trae los microdatos (un renglón por certificado, versiones de antes del
  2026-11-19), se agregan aquí y no viajan.
- Las tablas también se ven en el mapa: la marginación por AGEB va sobre sus
  polígonos; sequía, siembra, plantas de tratamiento y defunciones, resumidas en una
  capa de municipios (`--municipios`); el estatus de cada especie, en cada registro de
  GBIF; el viento, en un punto en el centro de su celda de ERA5.

Se corre con el Python de QGIS (trae GDAL con OpenFileGDB), no con uv:

    "C:\\Program Files\\QGIS 4.2.3\\bin\\python-qgis.bat" scripts/ambiental/para_arcgis.py \\
        --paquete arbolado_cp45615 --salida arbolado_cp45615_arcgis --nombre Arbolado_CP45615 \\
        --diccionario-censo diccionario_datos_ageb_urbana_14_cpv2020.csv

Ver docs/guias/replicar.md, sección "Para ArcGIS".
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()

EPSG = 32613

# (archivo, capa de origen, conjunto, nombre en la gdb, alias de la capa)
CAPAS = [
    ("zona.gpkg", "manzanas", "Poblacion", "Manzanas_censo_2020", "Manzanas con censo 2020 (INEGI)"),
    ("zona.gpkg", "agebs", "Poblacion", "AGEB_urbanos_censo_2020", "AGEB urbanos con censo 2020 (INEGI)"),
    ("zona.gpkg", "agebs_rurales", "Poblacion", "AGEB_rurales", "AGEB rurales con población del ITER 2020"),
    ("zona.gpkg", "localidades", "Poblacion", "Localidades_ITER_2020", "Localidades (punto) con ITER 2020"),
    ("zona.gpkg", "localidades_poligonos", "Poblacion", "Localidades_amanzanadas", "Localidades amanzanadas (polígono)"),
    ("zona.gpkg", "colonias_marginacion", "Poblacion", "Colonias_marginacion_CONAPO", "Colonias con marginación 2020 (CONAPO)"),
    ("zona.gpkg", "agua_superficial", "Agua", "Calidad_agua_superficial", "Calidad del agua superficial (Conagua, RENAMECA)"),
    ("zona.gpkg", "agua_subterranea", "Agua", "Calidad_agua_subterranea", "Calidad del agua subterránea (Conagua, RENAMECA)"),
    ("zona.gpkg", "cuerpos_de_agua", "Agua", "Cuerpos_de_agua", "Cuerpos de agua (Conagua)"),
    ("zona.gpkg", "acuiferos", "Agua", "Acuiferos_disponibilidad_2023", "Acuíferos y disponibilidad, DOF 2023-11-09"),
    ("zona.gpkg", "acuiferos_vedas", "Agua", "Acuiferos_vedas", "Vedas de agua subterránea"),
    ("zona.gpkg", "piezometria", "Agua", "Pozos_piezometricos", "Pozos de la red piezométrica (profundidad al agua)"),
    ("zona.gpkg", "regiones_hidrologicas", "Agua", "Regiones_hidrologicas", "Regiones hidrológicas"),
    ("zona.gpkg", "repda_descargas", "Agua", "Descargas_aguas_residuales", "Descargas de aguas residuales con permiso (REPDA)"),
    ("zona.gpkg", "repda_subterraneos", "Agua", "Pozos_concesionados", "Pozos con concesión (REPDA)"),
    ("zona.gpkg", "repda_superficiales", "Agua", "Tomas_superficiales", "Tomas de agua superficial con concesión (REPDA)"),
    ("zona.gpkg", "repda_zonas_federales", "Agua", "Zonas_federales", "Zonas federales concesionadas (REPDA)"),
    ("zona.gpkg", "retc", "Emisiones_y_fuego", "Establecimientos_RETC", "Establecimientos que reportan emisiones (RETC)"),
    ("zona.gpkg", "firms_viirs", "Emisiones_y_fuego", "Focos_calor_VIIRS", "Focos de calor VIIRS 375 m (NASA FIRMS)"),
    ("zona.gpkg", "firms_modis", "Emisiones_y_fuego", "Focos_calor_MODIS", "Focos de calor MODIS 1 km (NASA FIRMS)"),
    ("zona.gpkg", "uso_suelo_s7", "Territorio", "Uso_suelo_serie_VII_2018", "Uso de suelo y vegetación, serie VII (2018)"),
    ("zona.gpkg", "uso_suelo_s6", "Territorio", "Uso_suelo_serie_VI_2014", "Uso de suelo y vegetación, serie VI (2014)"),
    ("zona.gpkg", "frontera_agricola", "Territorio", "Frontera_agricola_2011", "Frontera agrícola 1:10 000 (SIAP, 2011)"),
    ("zona.gpkg", "edafologia", "Territorio", "Edafologia", "Edafología 1:1 000 000"),
    ("edificios.gpkg", None, "Ciudad", "Edificios_Overture", "Huellas de edificios (Overture Maps)"),
    ("zona.gpkg", "denue", "Ciudad", "Negocios_DENUE", "Negocios, escuelas y clínicas (DENUE)"),
    ("especies/registros_especies.gpkg", None, "Especies", "Registros_plantas_GBIF", "Registros de plantas (GBIF)"),
]

TABLAS = [
    ("tablas/viento_climatologia.csv", "Viento_por_mes_y_hora"),
    ("tablas/viento_horario.csv", "Viento_horario_2015_2024"),
    ("tablas/siap_municipal.csv", "Siembra_SIAP_municipal"),
    ("tablas/sequia_municipal.csv", "Sequia_por_municipio"),
    ("tablas/agebs_marginacion.csv", "Marginacion_por_AGEB"),
    ("tablas/plantas_tratamiento.csv", "Plantas_de_tratamiento"),
    ("especies/arboles_nativos.csv", "Arboles_nativos"),
    ("especies/especies.csv", "Especies_registradas"),
    ("diccionario_capas.csv", "Diccionario_capas"),
    ("procedencia.csv", "Procedencia"),
]

# Campos que no viajan: identifican a una persona y no hacen falta para estudiar la zona.
QUITAR = {"retc": {"NOMBRE", "ESTABLECIMIENTO"}}

# Claves y códigos: texto aunque parezcan números (los ceros a la izquierda importan).
CLAVE = re.compile(r"(?i)^((c_)?(cve|clv|clave|cvegeo|id|nra|scian|titulo|ent|entidad|mun|loc|ageb|mza|cp|codigo|"
                   r"numero|num|tipo|anexo|causa|lista_mex|ocupacion|edad|sexo|hora_local|acq_time|version|gbif_id|"
                   r"idestado|idmunicipio|idddr|idcader|idciclo|idmodalidad|idcultivo|idunidadmedida)([ _].*)?|"
                   r"c\.p\.|.*_(regis|resid|ocurr|nac))$")
SIN_CONVERTIR = {"tablas/defunciones.csv", "procedencia.csv", "diccionario_capas.csv", "tablas/sequia_municipal.csv"}

ALIAS = {
    "pob_total": "Población total (marco de INEGI)", "pob_masculina": "Población masculina",
    "pob_femenina": "Población femenina", "total_viviendas_habitadas": "Viviendas habitadas",
    "pobtot_iter": "Población (suma de localidades del ITER)", "vivhab_iter": "Viviendas habitadas (ITER)",
    "localidades_iter": "Localidades del ITER dentro", "acq_date": "Fecha", "acq_time": "Hora (UTC, HHMM)",
    "confidence": "Confianza (VIIRS l, n, h; MODIS 0 a 100)", "frp": "Potencia radiativa (MW)",
    "daynight": "Día o noche", "type": "Tipo (0 vegetación, 2 fuente fija)", "area_m2": "Área de techo (m²)",
    "altura_m": "Altura (m)", "fuente": "Fuente del polígono", "DESCRIPCIO": "Descripción",
    "SUP_HA_7mo": "Hectáreas del polígono completo", "MOD_USO": "Uso (A agricultura, P pastos)",
    "MOD_AGR": "Modalidad (R riego, T temporal)", "DMA_POSITI": "Disponibilidad (hm³/año, si es positiva)",
    "DMA_NEGATI": "Déficit (hm³/año, si es negativa)", "RECARGA_TO": "Recarga total (hm³/año)",
    "DESCARGA_N": "Descarga natural comprometida (hm³/año)", "VEAS": "Extracción total (hm³/año)",
    "IM_2020": "Índice de marginación (CONAPO)", "GM_2020": "Grado de marginación (CONAPO)",
    "P6A14NAE": "% de 6 a 14 años que no va a la escuela", "SBASC": "% de 15 años o más sin educación básica",
    "PSDSS": "% sin servicios de salud", "OVSDE": "% de viviendas sin drenaje ni excusado",
    "OVSEE": "% de viviendas sin electricidad", "OVSAE": "% de viviendas sin agua entubada",
    "OVPT": "% de viviendas con piso de tierra", "OVHAC": "% de viviendas con hacinamiento",
    "OVSREF": "% de viviendas sin refrigerador", "OVSINT": "% de viviendas sin internet",
    "OVSCEL": "% de viviendas sin celular", "clase_actividad": "Actividad (SCIAN)",
    "estrato": "Personal ocupado", "uso": "Uso que ampara el título", "nombre_comun": "Nombre común (Enciclovida)",
    "distribucion_mx": "Distribución en México (nativa, endémica, exótica)", "es_arbol": "¿Árbol? (si/no)",
    "griis_mexico": "En el registro de invasoras GRIIS",
}


def nombre_campo(texto: str, usados: set[str]) -> str:
    """Letras, dígitos y guion bajo, empieza con letra, hasta 64, sin repetir."""
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_") or "campo"
    if not base[0].isalpha():
        base = "c_" + base
    base = base[:60]
    nombre, k = base, 1
    while nombre.lower() in usados:
        k += 1
        nombre = f"{base[:57]}_{k}"
    usados.add(nombre.lower())
    return nombre


# Lo que INEGI pone en lugar de un número: '*' reservado por confidencialidad, 'N/D' no disponible.
VACIOS = {None, "", "*", "N/D", "ND", "N.D."}


def tipo_de(valores: list, nombre: str, convertir: bool) -> int:
    """Entero o Real si todos los valores no vacíos son números ('*' cuenta como
    vacío); si no, texto. Claves y códigos siempre texto."""
    if not convertir or CLAVE.match(nombre):
        return ogr.OFTString
    entero = True
    hay = False
    for v in valores:
        if v in VACIOS:
            continue
        try:
            f = float(str(v).replace(",", ""))
        except ValueError:
            return ogr.OFTString
        if f != f:
            continue
        hay = True
        if not f.is_integer() or "." in str(v) or abs(f) >= 2**31:
            entero = False
    if not hay:
        return ogr.OFTString
    # Entero de 32 bits: la geodatabase clásica no tiene de 64 y GDAL los volvería decimales.
    return ogr.OFTInteger if entero else ogr.OFTReal


def valor(v, tipo):
    if isinstance(v, bool):
        return int(v) if tipo in (ogr.OFTInteger, ogr.OFTReal) else str(v)
    if v in VACIOS:
        return None
    if isinstance(v, (int, float)) and tipo in (ogr.OFTInteger, ogr.OFTReal):
        return int(v) if tipo == ogr.OFTInteger else float(v)
    if tipo == ogr.OFTInteger:
        return int(float(str(v).replace(",", "")))
    if tipo == ogr.OFTReal:
        f = float(str(v).replace(",", ""))
        return None if f != f else f
    return str(v)


class Armador:
    def __init__(self, paquete: Path, salida: Path, nombre: str, censo: dict[str, tuple[str, str]]):
        self.paquete, self.salida, self.censo = paquete, salida, censo
        self.gdb = salida / f"{nombre}.gdb"
        if salida.exists():
            shutil.rmtree(salida)
        salida.mkdir(parents=True)
        self.ds = ogr.GetDriverByName("OpenFileGDB").CreateDataSource(str(self.gdb))
        self.srs = osr.SpatialReference()
        self.srs.ImportFromEPSG(EPSG)
        self.srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        self.diccionario: list[dict] = []
        self.conteos: list[tuple[str, int, int]] = []

    def alias_de(self, capa: str, original: str) -> tuple[str, str]:
        clave = original[2:] if original.startswith("c_") else original
        if clave.upper() in self.censo and (original.startswith("c_") or capa in ("localidades",)):
            indicador, descripcion = self.censo[clave.upper()]
            return indicador, descripcion
        return ALIAS.get(original, original), ""

    def capa(self, archivo: str, origen: str | None, conjunto: str, destino: str, alias: str) -> None:
        src = ogr.Open(str(self.paquete / archivo))
        lyr = src.GetLayerByName(origen) if origen else src.GetLayer(0)
        if lyr is None:
            print(f"  (sin {origen} en {archivo})")
            return
        clave_capa = origen or Path(archivo).stem
        defn = lyr.GetLayerDefn()
        quitar = QUITAR.get(clave_capa, set())
        # Por índice: GetField por nombre busca el campo cada vez (lento con 239 campos).
        indices = [i for i in range(defn.GetFieldCount()) if defn.GetFieldDefn(i).GetName() not in quitar]
        campos = [defn.GetFieldDefn(i) for i in indices]
        filas = [(f.GetGeometryRef().Clone() if f.GetGeometryRef() else None,
                  [f.GetField(i) for i in indices]) for f in lyr]
        if clave_capa == "registros_especies":
            # El estatus de cada especie (Enciclovida) en cada registro, para filtrar en el mapa.
            info = {r["especie"]: r for r in self.csv_filas("especies/especies.csv")}
            extra = ["nombre_comun", "distribucion_mx", "es_arbol", "griis_mexico"]
            i_esp = [c.GetName() for c in campos].index("especie")
            for nombre in extra:
                campos.append(ogr.FieldDefn(nombre, ogr.OFTString))
            filas = [(g, vals + [info.get(vals[i_esp], {}).get(n) or None for n in extra]) for g, vals in filas]
        tipos = []
        for i, c in enumerate(campos):
            if c.GetType() == ogr.OFTString:
                tipos.append(tipo_de([r[1][i] for r in filas], c.GetName(), True))
            else:
                tipos.append(c.GetType())

        gtipo = ogr.GT_Flatten(lyr.GetGeomType())
        if gtipo in (ogr.wkbPolygon, ogr.wkbMultiPolygon):
            gtipo = ogr.wkbMultiPolygon
        src_srs = lyr.GetSpatialRef()
        src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        transf = osr.CoordinateTransformation(src_srs, self.srs)
        out = self.ds.CreateLayer(destino, self.srs, gtipo,
                                  options=[f"FEATURE_DATASET={conjunto}", f"LAYER_ALIAS={alias}"])
        usados: set[str] = set()
        nombres = []
        for c, t in zip(campos, tipos):
            n = nombre_campo(c.GetName(), usados)
            fd = ogr.FieldDefn(n, t)
            if t == ogr.OFTString:
                fd.SetWidth(0)
            al, desc = self.alias_de(clave_capa, c.GetName())
            fd.SetAlternativeName(al[:255])
            out.CreateField(fd)
            nombres.append(n)
            self.diccionario.append({"capa": destino, "campo": n, "alias": al, "nombre_original": c.GetName(),
                                     "tipo": ogr.GetFieldTypeName(t), "descripcion": desc})
        out_defn = out.GetLayerDefn()
        n_ok = 0
        for geom, vals in filas:
            f = ogr.Feature(out_defn)
            for k, (t, v) in enumerate(zip(tipos, vals)):
                v = valor(v, t)
                if v is not None:
                    f.SetField(k, v)
            if geom is not None:
                geom.Transform(transf)
                if gtipo == ogr.wkbMultiPolygon:
                    geom = ogr.ForceToMultiPolygon(geom.MakeValid() if not geom.IsValid() else geom)
                f.SetGeometry(geom)
            out.CreateFeature(f)
            n_ok += 1
        self.conteos.append((destino, len(filas), n_ok))
        print(f"  {conjunto}/{destino}: {n_ok:,}")

    def tabla(self, archivo: str, destino: str) -> None:
        p = self.paquete / archivo
        if not p.exists():
            return
        with open(p, encoding="utf-8-sig", newline="") as fh:
            lector = csv.reader(fh)
            encabezado = next(lector)
            filas = list(lector)
        convertir = archivo not in SIN_CONVERTIR
        tipos = [tipo_de([r[i] if i < len(r) else None for r in filas], h, convertir) for i, h in enumerate(encabezado)]
        out = self.ds.CreateLayer(destino, None, ogr.wkbNone)
        usados: set[str] = set()
        nombres = []
        for h, t in zip(encabezado, tipos):
            n = nombre_campo(h, usados)
            fd = ogr.FieldDefn(n, t)
            al, desc = ALIAS.get(h, h), ""
            fd.SetAlternativeName(al[:255])
            out.CreateField(fd)
            nombres.append(n)
            self.diccionario.append({"capa": destino, "campo": n, "alias": al, "nombre_original": h,
                                     "tipo": ogr.GetFieldTypeName(t), "descripcion": desc})
        d = out.GetLayerDefn()
        for r in filas:
            f = ogr.Feature(d)
            for k, (t, v) in enumerate(zip(tipos, r)):
                v = valor(v, t)
                if v is not None:
                    f.SetField(k, v)
            out.CreateFeature(f)
        self.conteos.append((destino, len(filas), out.GetFeatureCount()))
        print(f"  tabla {destino}: {len(filas):,}")

    # --- tablas sobre el mapa -------------------------------------------------
    def capa_nueva(self, conjunto: str, destino: str, alias: str, gtipo, campos: list[tuple[str, int, str]],
                   filas: list[tuple[object, list]]) -> None:
        """Capa armada aquí: campos (nombre, tipo, alias) y filas (geometría en EPSG:4326, valores)."""
        out = self.ds.CreateLayer(destino, self.srs, gtipo,
                                  options=[f"FEATURE_DATASET={conjunto}", f"LAYER_ALIAS={alias}"])
        for n, t, al in campos:
            fd = ogr.FieldDefn(n, t)
            fd.SetAlternativeName(al)
            out.CreateField(fd)
            self.diccionario.append({"capa": destino, "campo": n, "alias": al, "nombre_original": "",
                                     "tipo": ogr.GetFieldTypeName(t), "descripcion": ""})
        wgs = osr.SpatialReference()
        wgs.ImportFromEPSG(4326)
        wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        transf = osr.CoordinateTransformation(wgs, self.srs)
        for geom, vals in filas:
            f = ogr.Feature(out.GetLayerDefn())
            for k, ((_, t, _), v) in enumerate(zip(campos, vals)):
                v = valor(v, t)
                if v is not None:
                    f.SetField(k, v)
            g = geom.Clone()
            g.Transform(transf)
            if gtipo == ogr.wkbMultiPolygon:
                g = ogr.ForceToMultiPolygon(g)
            f.SetGeometry(g)
            out.CreateFeature(f)
        print(f"  {conjunto}/{destino}: {len(filas):,} (armada)")

    def csv_filas(self, archivo: str) -> list[dict]:
        p = self.paquete / archivo
        if not p.exists():
            return []
        with open(p, encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))

    def defunciones(self) -> list[list]:
        """Conteos por año de registro, municipio de residencia, causa (CIE-10 a tres
        caracteres), sexo y grupo de edad de INEGI. Sin localidad ni microdatos."""
        filas = self.csv_filas("tablas/defunciones.csv")
        if filas and "causa_def" in filas[0]:
            conteo: dict[tuple, int] = {}
            for r in filas:
                llave = (r["anio_registro"], r["ent_resid"].zfill(2), r["mun_resid"].zfill(3), r["causa_def"][:3],
                         r["sexo"], r["edad_agru"] or "30")
                conteo[llave] = conteo.get(llave, 0) + 1
            return [[*k, v] for k, v in sorted(conteo.items())]
        return [[r["anio_registro"], r["cve_ent"], r["cve_mun"], r["causa"], r["sexo"], r["edad_grupo"],
                 r["defunciones"]] for r in filas]

    def tabla_defunciones(self, filas: list[list]) -> None:
        if not filas:
            return
        out = self.ds.CreateLayer("Defunciones_por_municipio", None, ogr.wkbNone)
        campos = [("anio_registro", ogr.OFTInteger, "Año de registro"),
                  ("cve_ent", ogr.OFTString, "Entidad de residencia"),
                  ("cve_mun", ogr.OFTString, "Municipio de residencia"),
                  ("causa_cie10", ogr.OFTString, "Causa (CIE-10, 3 caracteres)"),
                  ("sexo", ogr.OFTString, "Sexo (1 hombre, 2 mujer, 9 no especificado)"),
                  ("edad_grupo", ogr.OFTString, "Grupo de edad de INEGI (1 menor de un año ... 30 no especificada)"),
                  ("defunciones", ogr.OFTInteger, "Defunciones")]
        for n, t, al in campos:
            fd = ogr.FieldDefn(n, t)
            fd.SetAlternativeName(al)
            out.CreateField(fd)
            self.diccionario.append({"capa": "Defunciones_por_municipio", "campo": n, "alias": al,
                                     "nombre_original": "", "tipo": ogr.GetFieldTypeName(t), "descripcion": ""})
        for r in filas:
            f = ogr.Feature(out.GetLayerDefn())
            for k, ((_, t, _), v) in enumerate(zip(campos, r)):
                v = valor(v, t)
                if v is not None:
                    f.SetField(k, v)
            out.CreateFeature(f)
        self.conteos.append(("Defunciones_por_municipio", len(filas), out.GetFeatureCount()))
        print(f"  tabla Defunciones_por_municipio: {len(filas):,} (agregada)")

    def marginacion_agebs(self) -> None:
        tabla = {r["cvegeo"]: r for r in self.csv_filas("tablas/agebs_marginacion.csv")}
        src = ogr.Open(str(self.paquete / "zona.gpkg"))
        lyr = src.GetLayerByName("agebs")
        if not tabla or lyr is None:
            return
        cols = [("POB_TOTAL", ogr.OFTInteger, "Población total")] + [
            (c, ogr.OFTReal, ALIAS[c]) for c in ("P6A14NAE", "SBASC", "PSDSS", "OVSDE", "OVSEE", "OVSAE", "OVPT",
                                                "OVHAC", "OVSREF", "OVSINT", "OVSCEL", "IM_2020")
        ] + [("GM_2020", ogr.OFTString, ALIAS["GM_2020"])]
        filas = []
        for f in lyr:
            r = tabla.get(f.GetField("cvegeo"))
            if r:
                filas.append((f.GetGeometryRef().Clone(), [f.GetField("cvegeo")] + [r.get(c) for c, _, _ in cols]))
        self.capa_nueva("Poblacion", "Marginacion_AGEB_CONAPO", "Marginación urbana por AGEB 2020 (CONAPO)",
                        ogr.wkbMultiPolygon, [("cvegeo", ogr.OFTString, "Clave del AGEB")] + cols, filas)

    def municipios(self, geojson: Path | None, defunciones: list[list]) -> None:
        if not geojson:
            return
        src = ogr.Open(str(geojson))
        lyr = src.GetLayer(0)
        sequia = {r["CVE_CONCATENADA"].zfill(5): r for r in self.csv_filas("tablas/sequia_municipal.csv")}
        siap = self.csv_filas("tablas/siap_municipal.csv")
        ptar = self.csv_filas("tablas/plantas_tratamiento.csv")
        campos = [("cvegeo", ogr.OFTString, "Clave del municipio"), ("nombre", ogr.OFTString, "Municipio"),
                  ("sequia_fecha", ogr.OFTString, "Último corte del Monitor de Sequía"),
                  ("sequia_categoria", ogr.OFTString, "Categoría de sequía en el último corte (D0 a D4; vacío sin anomalía)"),
                  ("sequia_severa_5a", ogr.OFTInteger, "Cortes en sequía severa o peor (D2 a D4), últimos 5 años"),
                  ("sequia_cortes_5a", ogr.OFTInteger, "Cortes del Monitor en los últimos 5 años"),
                  ("siap_anio", ogr.OFTInteger, "Año del cierre agrícola"),
                  ("sembrada_ha", ogr.OFTReal, "Hectáreas sembradas (todas)"),
                  ("riego_ha", ogr.OFTReal, "Hectáreas sembradas de riego"),
                  ("temporal_ha", ogr.OFTReal, "Hectáreas sembradas de temporal"),
                  ("cultivo_mayor", ogr.OFTString, "Cultivo con más hectáreas"),
                  ("ptar_activas", ogr.OFTInteger, "Plantas de tratamiento activas (por nombre de municipio)"),
                  ("defun_2020_2023", ogr.OFTInteger, "Defunciones de residentes, 2020 a 2023"),
                  ("defun_tumores", ogr.OFTInteger, "De ellas, tumores (C00 a D48)"),
                  ("defun_renales", ogr.OFTInteger, "De ellas, renales (N00 a N29)"),
                  ("defun_respiratorias", ogr.OFTInteger, "De ellas, respiratorias (J00 a J99)")]

        def sin_acentos(t: str) -> str:
            return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper().strip()

        filas = []
        for f in lyr:
            cve = f.GetField("cvegeo")
            fila = [cve, f.GetField("nombre")]
            s = sequia.get(cve)
            if s:
                fechas = sorted(k for k in s if k[:4].isdigit())
                ultima = fechas[-1]
                desde = f"{int(ultima[:4]) - 5}{ultima[4:10]}"
                recientes = [k for k in fechas if k[:10] > desde]
                fila += [ultima[:10], s[ultima] or None, sum(s[k] in ("D2", "D3", "D4") for k in recientes),
                         len(recientes)]
            else:
                fila += [None, None, None, None]
            mun = [r for r in siap if r["Idestado"].zfill(2) + r["Idmunicipio"].zfill(3) == cve]
            if mun:
                anio = max(int(float(r["Anio"])) for r in mun)
                ult = [r for r in mun if int(float(r["Anio"])) == anio]

                def ha(rs):
                    return sum(float(r["Sembrada"] or 0) for r in rs)

                por_cultivo: dict[str, float] = {}
                for r in ult:
                    nombre = r.get("Nomcultivo") or r.get("Nomcultivo Sin Um") or ""
                    por_cultivo[nombre] = por_cultivo.get(nombre, 0) + float(r["Sembrada"] or 0)
                fila += [anio, ha(ult), ha([r for r in ult if r["Nommodalidad"] == "Riego"]),
                         ha([r for r in ult if r["Nommodalidad"] == "Temporal"]),
                         max(por_cultivo, key=por_cultivo.get)]
            else:
                fila += [None] * 5
            fila.append(sum(1 for r in ptar if sin_acentos(r["Municipio"]) == sin_acentos(fila[1])
                            and (r.get("Estado de operación 2023") or "").startswith("Activ")))
            d = [r for r in defunciones if r[1] + r[2] == cve]

            def k(cond):
                return sum(int(r[6]) for r in d if cond(r[3]))

            fila += [k(lambda c: True), k(lambda c: "C00" <= c <= "D48"), k(lambda c: "N00" <= c <= "N29"),
                     k(lambda c: c.startswith("J"))]
            filas.append((f.GetGeometryRef().Clone(), fila))
        self.capa_nueva("Municipios", "Municipios_resumen", "Municipios: sequía, siembra, tratamiento y defunciones",
                        ogr.wkbMultiPolygon, campos, filas)

    def viento(self) -> None:
        filas = self.csv_filas("tablas/viento_climatologia.csv")
        nota = next((r["nota"] for r in self.csv_filas("diccionario_capas.csv") if r["capa"] == "viento_climatologia"), "")
        m = re.search(r"celda ERA5 (-?[\d.]+), (-?[\d.]+)", nota)
        if not filas or not m:
            return
        lat, lon = float(m.group(1)), float(m.group(2))
        rumbos = [k for k in filas[0] if k.startswith("frec_")]

        def resumen(meses):
            rs = [r for r in filas if int(r["mes"]) in meses]
            horas = sum(float(r["horas"]) for r in rs)

            def prom(c):
                return sum(float(r[c]) * float(r["horas"]) for r in rs) / horas

            dominante = max(rumbos, key=prom)
            return [round(prom("velocidad_media"), 2), round(100 * prom("calma"), 1), dominante[5:],
                    round(100 * prom(dominante), 1)]

        campos = [("celda", ogr.OFTString, "Celda ERA5 (centro)")]
        for etiqueta, clave in (("febrero a mayo (secas)", "secas"), ("junio a enero", "resto")):
            campos += [(f"vel_media_{clave}", ogr.OFTReal, f"Velocidad media (m/s), {etiqueta}"),
                       (f"calma_pct_{clave}", ogr.OFTReal, f"% de horas en calma (menos de 1 m/s), {etiqueta}"),
                       (f"viene_de_{clave}", ogr.OFTString, f"Rumbo más frecuente (de donde viene), {etiqueta}"),
                       (f"viene_de_pct_{clave}", ogr.OFTReal, f"% de horas con ese rumbo, {etiqueta}")]
        punto = ogr.Geometry(ogr.wkbPoint)
        punto.AddPoint_2D(lon, lat)
        self.capa_nueva("Clima", "Viento_celda_ERA5", "Viento 2015 a 2024, celda ERA5 de ~28 km (centro)",
                        ogr.wkbPoint, campos,
                        [(punto, [f"{lat}, {lon}"] + resumen({2, 3, 4, 5}) + resumen({6, 7, 8, 9, 10, 11, 12, 1}))])

    def tabla_diccionario(self) -> None:
        out = self.ds.CreateLayer("Diccionario_campos", None, ogr.wkbNone)
        for k in ("capa", "campo", "alias", "nombre_original", "tipo", "descripcion"):
            out.CreateField(ogr.FieldDefn(k, ogr.OFTString))
        for r in self.diccionario:
            f = ogr.Feature(out.GetLayerDefn())
            for k, v in r.items():
                f.SetField(k, v)
            out.CreateFeature(f)

    # --- imágenes -----------------------------------------------------------
    def imagenes(self) -> None:
        im = self.paquete / "imagenes"
        dst = self.salida / "imagenes"
        dst.mkdir()
        for p in sorted(im.glob("s2_indices_*.tif")):
            mes = p.stem.split("_")[-1].replace("-", "_")
            for banda, nombre in ((1, "NDVI"), (2, "NDWI"), (3, "NBR")):
                self.escalar(p, banda, dst / nombre / f"{nombre}_{mes}.tif", 1 / 10000, nombre)
        for p in sorted(im.glob("lst_secas_*.tif")):
            anio = p.stem.split("_")[-1]
            self.escalar(p, 1, dst / "Temperatura_superficie" / f"Temperatura_superficie_secas_{anio}_C.tif", 1 / 100,
                         "Temperatura de superficie (°C), mediana de marzo a mayo")
        copias = {"dosel_1m.tif": "Altura_dosel_1m_m.tif", "dosel_fecha.tif": "Fecha_imagen_dosel.tif",
                  "s2_bandas_2025-02-01_2025-05-31.tif": "Sentinel2_bandas_secas_2025_x10000.tif"}
        for a, b in copias.items():
            if (im / a).exists():
                gdal.Translate(str(dst / b), str(im / a), creationOptions=["COMPRESS=DEFLATE", "TILED=YES"])
        if (im / "worldcover_2021.tif").exists():
            self.worldcover(im / "worldcover_2021.tif", dst / "Cobertura_WorldCover_2021.tif")
        if (self.paquete / "relieve.tif").exists():
            gdal.Warp(str(dst / "Relieve_m.tif"), str(self.paquete / "relieve.tif"), dstSRS=f"EPSG:{EPSG}",
                      resampleAlg="bilinear", xRes=30, yRes=30, dstNodata=-9999,
                      creationOptions=["COMPRESS=DEFLATE", "TILED=YES"])

    def escalar(self, p: Path, banda: int, destino: Path, factor: float, descripcion: str) -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        src = gdal.Open(str(p))
        b = src.GetRasterBand(banda)
        datos = b.ReadAsArray().astype("float32")
        sin = b.GetNoDataValue()
        salida = np.where(datos == sin, -9999, datos * factor).astype("float32")
        out = gdal.GetDriverByName("GTiff").Create(str(destino), src.RasterXSize, src.RasterYSize, 1, gdal.GDT_Float32,
                                                   options=["COMPRESS=DEFLATE", "TILED=YES", "PREDICTOR=3"])
        out.SetGeoTransform(src.GetGeoTransform())
        out.SetProjection(src.GetProjection())
        ob = out.GetRasterBand(1)
        ob.SetNoDataValue(-9999)
        ob.SetDescription(descripcion)
        ob.WriteArray(salida)
        ob.ComputeStatistics(False)
        out = None

    def worldcover(self, p: Path, destino: Path) -> None:
        clases = {10: ("Árboles", "#006400"), 20: ("Matorral", "#ffbb22"), 30: ("Pastizal", "#ffff4c"),
                  40: ("Cultivo", "#f096ff"), 50: ("Construido", "#fa0000"), 60: ("Suelo desnudo o escasa vegetación", "#b4b4b4"),
                  70: ("Nieve y hielo", "#f0f0f0"), 80: ("Agua permanente", "#0064c8"), 90: ("Humedal herbáceo", "#0096a0"),
                  95: ("Manglar", "#00cf75"), 100: ("Musgo y liquen", "#fae6a0")}
        gdal.Translate(str(destino), str(p), creationOptions=["COMPRESS=DEFLATE", "TILED=YES"])
        ds = gdal.Open(str(destino), gdal.GA_Update)
        b = ds.GetRasterBand(1)
        tabla = gdal.ColorTable()
        rat = gdal.RasterAttributeTable()
        rat.CreateColumn("Value", gdal.GFT_Integer, gdal.GFU_MinMax)
        rat.CreateColumn("Clase", gdal.GFT_String, gdal.GFU_Name)
        for i, (v, (nombre, color)) in enumerate(sorted(clases.items())):
            tabla.SetColorEntry(v, tuple(int(color[k:k + 2], 16) for k in (1, 3, 5)) + (255,))
            rat.SetValueAsInt(i, 0, v)
            rat.SetValueAsString(i, 1, nombre)
        b.SetRasterColorTable(tabla)
        b.SetDefaultRAT(rat)
        ds = None


def leer_censo(p: Path | None) -> dict[str, tuple[str, str]]:
    """Mnemónico → (indicador, descripción) del diccionario de datos del censo 2020."""
    if not p:
        return {}
    with open(p, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.reader(fh))
    i = next(k for k, r in enumerate(filas) if any("Mnem" in c for c in r))
    enc = filas[i]
    m, ind, desc = enc.index(next(c for c in enc if "Mnem" in c)), enc.index("Indicador"), enc.index(next(c for c in enc if "Descrip" in c))
    return {r[m].strip().upper(): (r[ind].strip(), r[desc].strip()) for r in filas[i + 1:] if len(r) > m and r[m].strip()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paquete", type=Path, required=True, help="carpeta del paquete de recorte.py (descomprimida)")
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--nombre", default="Zona", help="nombre de la geodatabase")
    ap.add_argument("--municipios", type=Path, default=None,
                    help="GeoJSON con los polígonos de los municipios del paquete (cvegeo, nombre), en EPSG:4326")
    ap.add_argument("--diccionario-censo", type=Path, default=None,
                    help="diccionario_datos_ageb_urbana_EE_cpv2020.csv de INEGI, para los alias del censo")
    a = ap.parse_args()
    arm = Armador(a.paquete, a.salida, a.nombre, leer_censo(a.diccionario_censo))
    for capa in CAPAS:
        if (a.paquete / capa[0]).exists():
            arm.capa(*capa)
    arm.marginacion_agebs()
    defunciones = arm.defunciones()
    arm.municipios(a.municipios, defunciones)
    arm.viento()
    for archivo, destino in TABLAS:
        arm.tabla(archivo, destino)
    arm.tabla_defunciones(defunciones)
    arm.tabla_diccionario()
    arm.ds = None
    arm.imagenes()
    for extra in ("LEEME.txt", "zona.txt", "procedencia_edificios.csv", "especies/procedencia_especies.csv",
                  "imagenes/procedencia_imagenes.csv", "imagenes/procedencia_dosel.csv"):
        if (a.paquete / extra).exists():
            shutil.copy(a.paquete / extra, a.salida / ("LEEME_original.txt" if extra == "LEEME.txt" else Path(extra).name))
    shutil.copy(Path(__file__).with_name("LEEME_ArcGIS.txt"), a.salida / "LEEME_ArcGIS.txt")
    malos = [c for c in arm.conteos if c[1] != c[2]]
    if malos:
        sys.exit(f"Filas que no cuadran: {malos}")
    print(f"Listo: {a.salida}")


if __name__ == "__main__":
    main()
