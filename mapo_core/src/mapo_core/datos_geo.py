"""Archivos con geometría: GeoJSON, shapefile en ZIP, GeoPackage y GeoTIFF.

Vectorial y ráster del usuario, encima de lo tabular de `datos_propios`. Igual
que ese módulo, solo interpreta: no guarda ni sabe de equipos.

Lo vectorial se lee con lectores simples y no con GDAL a propósito: GDAL elige
el formato por contenido, así que un archivo disfrazado de VRT podría leer
archivos del servidor o pedir URLs. Aquí cada formato tiene su lector y nada más.
`rasterio` (que trae GDAL) solo reproyecta coordenadas y abre GeoTIFF con el
driver fijo. Ver docs/producto/datos-propios.md.
"""

from __future__ import annotations

import base64
import io
import json
import re
import sqlite3
import time
import zipfile

import numpy as np
import shapely
from shapely.geometry import mapping, shape

from mapo_core import datos_propios as dp
from mapo_core.datos_propios import ArchivoInvalido, Tabla

VECTORIALES = ("geojson", "json", "zip", "gpkg")
RASTER = ("tif", "tiff")

MAX_VERTICES = 2_000_000
# Lado mayor de la imagen que se guarda: más que eso no se ve en una pantalla.
MAX_LADO_IMAGEN = 2048
MAX_PIXELES = 200_000_000
MAX_BANDAS = 50
_SEGUNDOS_GPKG = 30
# Misma opacidad por quintil que TINTA_QUINTIL en mapa_tecnico.js.
_TINTA_QUINTIL = (0.12, 0.26, 0.42, 0.6, 0.8)


def leer(contenido: bytes, formato: str) -> Tabla:
    """Punto de entrada: cualquier formato de tabla o vectorial a `Tabla`."""
    if formato not in VECTORIALES:
        return dp.leer(contenido, formato)
    if len(contenido) > dp.MAX_BYTES:
        raise ArchivoInvalido("El archivo pasa de 50 MB.")
    if not contenido:
        raise ArchivoInvalido("El archivo está vacío.")

    if formato == "zip":
        crudos, crs, avisos = _shapefile(contenido)
    elif formato == "gpkg":
        crudos, crs, avisos = _geopackage(contenido)
    else:
        crudos, crs, avisos = _geojson(contenido)
    return _tabla_vectorial(crudos, crs, avisos)


def _geojson(contenido: bytes):
    try:
        datos = json.loads(contenido.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ArchivoInvalido("No es un GeoJSON válido.") from exc
    if not isinstance(datos, dict):
        raise ArchivoInvalido("No es un GeoJSON válido.")

    tipo = datos.get("type")
    if tipo == "FeatureCollection":
        features = datos.get("features")
    elif tipo == "Feature":
        features = [datos]
    elif isinstance(datos.get("coordinates"), list) or tipo == "GeometryCollection":
        features = [{"properties": {}, "geometry": datos}]
    else:
        raise ArchivoInvalido("No es un GeoJSON válido.")
    if not isinstance(features, list):
        raise ArchivoInvalido("No es un GeoJSON válido.")

    crudos = [
        (f.get("properties") or {}, _geometria(f.get("geometry")))
        for f in features
        if isinstance(f, dict)
    ]
    return crudos, _crs_geojson(datos), []


def _crs_geojson(datos: dict) -> str | None:
    """El RFC dice WGS84, pero QGIS viejo exporta en otra proyección y lo
    declara en `crs`, como las capas de INEGI en EPSG:6372."""
    nombre = (((datos.get("crs") or {}).get("properties")) or {}).get("name", "")
    if "CRS84" in nombre:
        return None
    hallazgo = re.search(r"EPSG:+(\d+)", str(nombre))
    return f"EPSG:{hallazgo.group(1)}" if hallazgo else None


def _geometria(crudo):
    if not crudo:
        return None
    try:
        return shape(crudo)
    except Exception:  # shapely lanza de todo con coordenadas mal formadas
        return None


def _shapefile(contenido: bytes):
    import shapefile

    dp.revisar_zip(contenido, "ZIP")
    with zipfile.ZipFile(io.BytesIO(contenido)) as paquete:
        nombres = {n.lower(): n for n in paquete.namelist() if not n.startswith("__MACOSX")}
        capas = sorted(n[:-4] for n in nombres if n.endswith(".shp"))
        if not capas:
            raise ArchivoInvalido("El ZIP no trae ningún .shp.")
        base = capas[0]
        faltan = [e for e in (".dbf", ".shx") if base + e not in nombres]
        if faltan:
            raise ArchivoInvalido(f"Al shapefile le falta {' y '.join(faltan)}.")

        def pieza(extension):
            nombre = nombres.get(base + extension)
            return paquete.read(nombre) if nombre else None

        shp, shx, dbf, prj, cpg = (pieza(e) for e in (".shp", ".shx", ".dbf", ".prj", ".cpg"))

    avisos = []
    if len(capas) > 1:
        avisos.append(f"El ZIP trae {len(capas)} shapefiles: solo se leyó {capas[0]}.")
    crs = prj.decode("utf-8", "replace") if prj else None
    if crs is None:
        avisos.append("El shapefile no trae .prj: se tomó como grados (WGS84).")

    try:
        lector = shapefile.Reader(
            shp=io.BytesIO(shp),
            shx=io.BytesIO(shx),
            dbf=io.BytesIO(dbf),
            encoding=_codificacion(cpg, dbf),
            encodingErrors="replace",
        )
        campos = [c[0] for c in lector.fields[1:]]
        crudos = []
        for registro in lector.iterShapeRecords():
            if len(crudos) == dp.MAX_FILAS:
                raise ArchivoInvalido(f"El archivo pasa de {dp.MAX_FILAS:,} renglones.")
            forma = registro.shape
            geometria = None if forma.shapeType == 0 else _geometria(forma.__geo_interface__)
            crudos.append((dict(zip(campos, list(registro.record))), geometria))
    except ArchivoInvalido:
        raise
    except Exception as exc:  # pyshp también lanza de todo con archivos rotos
        raise ArchivoInvalido("El shapefile está dañado.") from exc
    return crudos, crs, avisos


def _codificacion(cpg: bytes | None, dbf: bytes) -> str:
    if cpg:
        nombre = cpg.decode("ascii", "ignore").strip()
        if nombre:
            return nombre
    try:
        dbf.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _geopackage(contenido: bytes):
    # `deserialize` deja la base en memoria: nada del usuario toca el disco.
    conexion = sqlite3.connect(":memory:")
    try:
        conexion.deserialize(contenido)
        conexion.execute("PRAGMA trusted_schema=OFF")
        conexion.execute("PRAGMA query_only=ON")
        limite = time.monotonic() + _SEGUNDOS_GPKG
        # Una vista hostil puede tardar para siempre.
        conexion.set_progress_handler(lambda: time.monotonic() > limite, 100_000)
        return _leer_gpkg(conexion)
    except sqlite3.Error as exc:
        raise ArchivoInvalido("No es un GeoPackage válido.") from exc
    finally:
        conexion.close()


def _leer_gpkg(conexion: sqlite3.Connection):
    tablas = conexion.execute(
        """SELECT c.table_name, g.column_name, c.srs_id
           FROM gpkg_contents c JOIN gpkg_geometry_columns g ON g.table_name = c.table_name
           JOIN sqlite_master m ON m.name = c.table_name AND m.type = 'table'
           WHERE c.data_type = 'features' ORDER BY c.table_name"""
    ).fetchall()
    if not tablas:
        raise ArchivoInvalido("El GeoPackage no trae ninguna capa vectorial.")

    tabla, columna, srs_id = tablas[0]
    avisos = [f"El GeoPackage trae {len(tablas)} capas: solo se leyó {tabla}."] if len(tablas) > 1 else []

    definicion = conexion.execute(
        "SELECT definition FROM gpkg_spatial_ref_sys WHERE srs_id = ?", (srs_id,)
    ).fetchone()
    crs = definicion[0] if definicion and srs_id > 0 else None

    def citar(nombre: str) -> str:
        return '"' + nombre.replace('"', '""') + '"'

    campos = [f[1] for f in conexion.execute(f"PRAGMA table_info({citar(tabla)})")]
    datos = [c for c in campos if c != columna]
    cursor = conexion.execute(
        f"SELECT {citar(columna)}, {', '.join(citar(c) for c in datos)} "
        f"FROM {citar(tabla)} LIMIT {dp.MAX_FILAS + 1}"
    )
    crudos = [
        (dict(zip(datos, ["" if isinstance(v, bytes) else v for v in fila[1:]])), _geometria_gpkg(fila[0]))
        for fila in cursor
    ]
    if len(crudos) > dp.MAX_FILAS:
        raise ArchivoInvalido(f"El archivo pasa de {dp.MAX_FILAS:,} renglones.")
    return crudos, crs, avisos


def _geometria_gpkg(blob):
    """WKB con el encabezado de GeoPackage: `GP`, versión, banderas, srs y un
    sobre de tamaño variable que dicen las banderas."""
    if not blob or blob[:2] != b"GP":
        return None
    banderas = blob[3]
    if banderas & 0b10000:
        return None
    sobre = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get((banderas >> 1) & 0b111)
    if sobre is None:
        return None
    try:
        return shapely.from_wkb(bytes(blob[8 + sobre :]))
    except Exception:
        return None


def _tabla_vectorial(crudos: list, crs: str | None, avisos: list[str]) -> Tabla:
    if not crudos:
        raise ArchivoInvalido("El archivo no trae ninguna geometría.")
    if len(crudos) > dp.MAX_FILAS:
        raise ArchivoInvalido(f"El archivo pasa de {dp.MAX_FILAS:,} renglones.")

    columnas: list[str] = []
    for propiedades, _ in crudos:
        for nombre in propiedades:
            if nombre not in columnas:
                columnas.append(nombre)
    if len(columnas) > dp.MAX_COLUMNAS:
        raise ArchivoInvalido(f"El archivo tiene {len(columnas)} columnas; el tope es {dp.MAX_COLUMNAS}.")

    # El nombre de columna ya viene único: solo se normaliza como en una tabla.
    nombres = dp.nombres_columnas(columnas)
    recortadas = 0
    filas = []
    for propiedades, _ in crudos:
        fila = [_texto(propiedades.get(c)) for c in columnas]
        recortadas += sum(len(c) > dp.MAX_CELDA for c in fila)
        filas.append([c.replace("\x00", "")[: dp.MAX_CELDA] for c in fila])
    if recortadas:
        avisos = [*avisos, f"{recortadas:,} celdas pasaban de {dp.MAX_CELDA} caracteres y se recortaron."]

    return Tabla(nombres, filas, avisos, geometrias=_a_grados([g for _, g in crudos], crs))


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False)
    return dp.celda(valor)


def _a_grados(geometrias: list, crs: str | None) -> list:
    """Todo a WGS84 y 2D. Cada renglón conserva su lugar: `None` si no trae
    geometría."""
    arreglo = np.array(geometrias, dtype=object)
    vivas = np.array([g is not None and not g.is_empty for g in geometrias])
    if not vivas.any():
        raise ArchivoInvalido("El archivo no trae ninguna geometría.")

    actuales = shapely.force_2d(arreglo[vivas].astype(object))
    if shapely.get_num_coordinates(actuales).sum() > MAX_VERTICES:
        raise ArchivoInvalido(f"El archivo pasa de {MAX_VERTICES:,} vértices. Simplifícalo antes de subirlo.")

    if crs is not None:
        actuales = _reproyectar(actuales, crs)

    invalidas = ~shapely.is_valid(actuales)
    actuales[invalidas] = shapely.make_valid(actuales[invalidas])
    salida: list = [None] * len(geometrias)
    for i, geometria in zip(np.flatnonzero(vivas), actuales):
        salida[i] = geometria
    return salida


def _reproyectar(geometrias: np.ndarray, crs: str) -> np.ndarray:
    from rasterio.crs import CRS
    from rasterio.errors import CRSError
    from rasterio.warp import transform

    try:
        origen = CRS.from_user_input(crs)
    except CRSError as exc:
        raise ArchivoInvalido("No se reconoce la proyección del archivo.") from exc
    if origen.to_epsg() == 4326:
        return geometrias

    def a_grados(coordenadas: np.ndarray) -> np.ndarray:
        x, y = transform(origen, "EPSG:4326", coordenadas[:, 0].tolist(), coordenadas[:, 1].tolist())
        return np.column_stack([x, y])

    return shapely.transform(geometrias, a_grados)


def _en_mexico(oeste: float, sur: float, este: float, norte: float) -> bool:
    return (
        este >= dp.LON_MEXICO[0]
        and oeste <= dp.LON_MEXICO[1]
        and norte >= dp.LAT_MEXICO[0]
        and sur <= dp.LAT_MEXICO[1]
    )


def ubicar_vector(tabla: Tabla) -> dict:
    numericas = dp.columnas_numericas(tabla)
    descartes = {"sin_dato": 0, "fuera_de_mexico": 0}
    filas = []

    for geometria, datos in zip(tabla.geometrias, dp.datos_de(tabla, numericas)):
        if geometria is None:
            descartes["sin_dato"] += 1
        elif not all(map(np.isfinite, geometria.bounds)) or not _en_mexico(*geometria.bounds):
            descartes["fuera_de_mexico"] += 1
        else:
            filas.append((geometria, datos))

    # Solo puntos: es la misma capa que un CSV con coordenadas.
    puntos = bool(filas) and all(g.geom_type == "Point" for g, _ in filas)
    if not puntos and sum(g.geom_type != "Point" for g, _ in filas) > dp.MAX_POLIGONOS:
        raise ArchivoInvalido(f"El archivo tiene más de {dp.MAX_POLIGONOS:,} polígonos o líneas.")

    return {
        "filas": [
            {"lat": g.y, "lon": g.x, "clave": None, "datos": d}
            if puntos
            else {"geometria": mapping(g), "clave": None, "datos": d}
            for g, d in filas
        ],
        "tipo": "puntos" if puntos else "vector",
        "descartes": descartes,
        "numericas": numericas,
        "repetidas": 0,
    }


def leer_raster(contenido: bytes) -> dict:
    """Mira el GeoTIFF sin decodificar sus píxeles."""
    with _abrir_tiff(contenido) as (_, fuente):
        return {
            "columnas": [],
            "muestra": [],
            "num_filas": 0,
            "avisos": _avisos_raster(fuente),
            "sugerencia": {"tipo": "raster"},
            "raster": {"ancho": fuente.width, "alto": fuente.height, "bandas": fuente.count},
        }


def ubicar_raster(contenido: bytes) -> dict:
    """Primera banda reproyectada a Web Mercator (lo que dibuja Leaflet) y
    pintada por quintiles en una imagen negra con transparencia: el navegador
    le pone la tinta, para que siga al tema."""
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import calculate_default_transform, transform_bounds

    with _abrir_tiff(contenido) as (_, fuente):
        destino, ancho, alto = calculate_default_transform(
            fuente.crs, "EPSG:3857", fuente.width, fuente.height, *fuente.bounds
        )
        escala = min(1.0, MAX_LADO_IMAGEN / max(ancho, alto))
        ancho, alto = max(1, int(ancho * escala)), max(1, int(alto * escala))
        destino = destino @ destino.scale(1 / escala)

        with WarpedVRT(
            fuente, crs="EPSG:3857", transform=destino, width=ancho, height=alto, resampling=Resampling.nearest
        ) as vrt:
            banda = np.ma.masked_invalid(vrt.read(1, masked=True).astype("float64"))
            limites = vrt.bounds
        oeste, sur, este, norte = transform_bounds("EPSG:3857", "EPSG:4326", *limites)
        avisos = _avisos_raster(fuente)

    if not _en_mexico(oeste, sur, este, norte):
        raise ArchivoInvalido("El ráster cae fuera de México.")
    validos = np.sort(banda.compressed())
    if validos.size == 0:
        raise ArchivoInvalido("El ráster no trae ningún valor.")

    n = validos.size
    cortes = [float(validos[int(q * (n - 1))]) for q in (0.2, 0.4, 0.6, 0.8)]
    clases = np.searchsorted(cortes, banda.filled(np.inf), side="left")
    alfa = (np.array(_TINTA_QUINTIL) * 255).astype("uint8")[np.minimum(clases, 4)]
    alfa[np.ma.getmaskarray(banda)] = 0

    return {
        "raster": {
            "png": base64.b64encode(_png(alfa)).decode("ascii"),
            "oeste": oeste,
            "sur": sur,
            "este": este,
            "norte": norte,
            "limites": [float(validos[0]), *cortes, float(validos[-1])],
        },
        "filas": [],
        "tipo": "raster",
        "descartes": {},
        "numericas": [],
        "repetidas": 0,
        "avisos": avisos,
        "columnas": [],
        "num_filas": 0,
    }


def _avisos_raster(fuente) -> list[str]:
    return [f"El ráster trae {fuente.count} bandas: solo se leyó la primera."] if fuente.count > 1 else []


class _abrir_tiff:
    """Abre el GeoTIFF en memoria y con el driver fijo: no se autodetecta nada."""

    def __init__(self, contenido: bytes):
        if len(contenido) > dp.MAX_BYTES:
            raise ArchivoInvalido("El archivo pasa de 50 MB.")
        if not contenido:
            raise ArchivoInvalido("El archivo está vacío.")
        self.contenido = contenido

    def __enter__(self):
        from rasterio import Env
        from rasterio.errors import RasterioError
        from rasterio.io import MemoryFile

        self.env = Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR")
        self.env.__enter__()
        self.memoria = MemoryFile(self.contenido)
        try:
            self.fuente = self.memoria.open(driver="GTiff")
        except RasterioError as exc:
            self.__exit__(None, None, None)
            raise ArchivoInvalido("No es un GeoTIFF válido.") from exc

        problema = _problema_raster(self.fuente)
        if problema:
            self.__exit__(None, None, None)
            raise ArchivoInvalido(problema)
        return self.memoria, self.fuente

    def __exit__(self, *_):
        if getattr(self, "fuente", None) is not None:
            self.fuente.close()
        self.memoria.close()
        self.env.__exit__(None, None, None)


def _problema_raster(fuente) -> str | None:
    if fuente.crs is None:
        return "El GeoTIFF no dice su proyección: no se puede ubicar."
    if fuente.count > MAX_BANDAS:
        return f"El GeoTIFF tiene {fuente.count} bandas; el tope es {MAX_BANDAS}."
    # Lo que frena a un TIFF chico que se infla a varios GB al decodificarse.
    if fuente.width * fuente.height > MAX_PIXELES:
        return f"El GeoTIFF pasa de {MAX_PIXELES:,} píxeles."
    return None


def _png(alfa: np.ndarray) -> bytes:
    from rasterio.io import MemoryFile

    alto, ancho = alfa.shape
    negro = np.zeros_like(alfa)
    with MemoryFile() as memoria:
        with memoria.open(driver="PNG", width=ancho, height=alto, count=4, dtype="uint8") as imagen:
            imagen.write(np.stack([negro, negro, negro, alfa]))
        return memoria.read()
