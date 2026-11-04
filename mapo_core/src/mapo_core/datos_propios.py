"""Archivos tabulares que sube un equipo (CSV, XLSX) y cómo se ubican. Lo que
trae geometría propia está en `datos_geo`.

Este módulo no guarda nada ni sabe de equipos: recibe bytes y regresa filas.
La autorización, la cuota y lo guardado viven en `Mapo.Capas` (Phoenix). Los
límites se revisan aquí porque aquí se descomprime y se interpreta el archivo.
Ver docs/producto/datos-propios.md.
"""

from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from typing import Any
from datetime import date, datetime, time

MAX_BYTES = 50 * 1024 * 1024
MAX_FILAS = 50_000
MAX_COLUMNAS = 100
MAX_CELDA = 500
# Un polígono pesa mucho más que un punto en el plano. La coropleta de un estado
# son unos 5 mil y se mueve bien; el doble sigue siendo razonable.
MAX_POLIGONOS = 10_000
# Un XLSX es un ZIP: esto es lo que frena un archivo de pocos KB que se infla
# a varios GB. El tamaño declarado es un tope real: `zipfile` no lee más allá.
MAX_XLSX_DESCOMPRIMIDO = 200 * 1024 * 1024
MAX_XLSX_PIEZAS = 1_000

FORMATOS = ("csv", "xlsx")
NIVELES = ("municipio", "ageb")

# Marco de México con margen, para detectar coordenadas volteadas o sin signo.
LAT_MEXICO = (14.0, 33.5)
LON_MEXICO = (-118.6, -86.0)

_NOMBRES_LAT = {"lat", "latitud", "latitude", "y"}
_NOMBRES_LON = {"lon", "lng", "long", "longitud", "longitude", "x"}
_ANCHOS = {"municipio": (2, 3), "ageb": (2, 3, 4, 4)}
_PISTAS_CLAVE = ("cvegeo", "clave", "cve", "ageb", "municipio", "mun")
_MILES = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")
_COMA_DECIMAL = re.compile(r"^-?\d+,\d+$")


class ArchivoInvalido(ValueError):
    """El archivo no se puede usar; el mensaje es para quien lo subió."""


@dataclass
class Tabla:
    columnas: list[str]
    filas: list[list[str]]
    avisos: list[str] = field(default_factory=list)
    # Solo en archivos vectoriales: una geometría por fila, en WGS84 o `None`.
    geometrias: list[Any] | None = None


def leer(contenido: bytes, formato: str) -> Tabla:
    if formato not in FORMATOS:
        raise ArchivoInvalido("Formato no reconocido. Sube CSV, XLSX, GeoJSON, shapefile en ZIP, GeoPackage o GeoTIFF.")
    if len(contenido) > MAX_BYTES:
        raise ArchivoInvalido("El archivo pasa de 50 MB.")
    if not contenido:
        raise ArchivoInvalido("El archivo está vacío.")

    if formato == "xlsx":
        filas, avisos = _renglones_xlsx(contenido)
    else:
        filas, avisos = _renglones_texto(contenido), []
    return _tabla(filas, avisos)


def _renglones_texto(contenido: bytes):
    texto = _decodificar(contenido)
    primera = texto.split("\n", 1)[0]
    delimitador = max(",;\t|", key=primera.count)
    try:
        yield from csv.reader(io.StringIO(texto, newline=""), delimiter=delimitador)
    except csv.Error as exc:
        raise ArchivoInvalido(f"No se pudo leer como tabla: {exc}.") from exc


def _decodificar(contenido: bytes) -> str:
    # Excel en español guarda CSV en Windows-1252; "Texto Unicode", en UTF-16.
    if contenido[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return contenido.decode("utf-16", errors="replace")
    if b"\x00" in contenido[:8192]:
        raise ArchivoInvalido("El archivo no parece de texto. ¿Es un CSV de verdad?")
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        return contenido.decode("cp1252", errors="replace")


def _renglones_xlsx(contenido: bytes):
    # Se importa aquí: solo este camino lo necesita y tarda en cargar.
    from openpyxl import load_workbook

    revisar_zip(contenido, "XLSX")
    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        hoja = libro.worksheets[0]
    except Exception as exc:  # openpyxl lanza de todo con un XLSX roto o cifrado
        raise ArchivoInvalido("No se pudo abrir el XLSX. ¿Tiene contraseña o está dañado?") from exc

    avisos = []
    if len(libro.worksheets) > 1:
        avisos.append(f'Solo se leyó la primera hoja ("{hoja.title}") de {len(libro.worksheets)}.')

    def renglones():
        try:
            for fila in hoja.iter_rows(values_only=True):
                yield [celda(v) for v in fila]
        except ArchivoInvalido:
            raise
        except Exception as exc:
            raise ArchivoInvalido("El XLSX está dañado.") from exc
        finally:
            libro.close()

    return renglones(), avisos


def revisar_zip(contenido: bytes, nombre: str) -> None:
    """Frena un ZIP inflado antes de abrirlo. Sirve para XLSX y shapefile."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as paquete:
            piezas = paquete.infolist()
    except zipfile.BadZipFile as exc:
        raise ArchivoInvalido(f"No es un {nombre} válido.") from exc
    if len(piezas) > MAX_XLSX_PIEZAS:
        raise ArchivoInvalido(f"El {nombre} trae demasiadas piezas por dentro.")
    if sum(p.file_size for p in piezas) > MAX_XLSX_DESCOMPRIMIDO:
        raise ArchivoInvalido(f"El {nombre} descomprimido pasa de 200 MB.")


def celda(valor) -> str:
    """Un valor tipado (XLSX, atributos de un vectorial) como texto de celda."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    return str(valor)


def _tabla(renglones, avisos: list[str]) -> Tabla:
    columnas = None
    filas: list[list[str]] = []
    recortadas = 0

    for crudo in renglones:
        renglon = [c.replace("\x00", "").strip() for c in crudo]
        while renglon and not renglon[-1]:
            renglon.pop()
        if not renglon:
            continue
        if columnas is None:
            if len(renglon) > MAX_COLUMNAS:
                raise ArchivoInvalido(f"El archivo tiene {len(renglon)} columnas; el tope es {MAX_COLUMNAS}.")
            columnas = nombres_columnas(renglon)
            continue
        if len(filas) == MAX_FILAS:
            raise ArchivoInvalido(f"El archivo pasa de {MAX_FILAS:,} renglones.")
        # Sobra o falta columna: se ajusta al encabezado.
        renglon = (renglon + [""] * len(columnas))[: len(columnas)]
        recortadas += sum(len(c) > MAX_CELDA for c in renglon)
        filas.append([c[:MAX_CELDA] for c in renglon])

    if columnas is None or not filas:
        raise ArchivoInvalido("El archivo necesita un renglón de encabezados y al menos un renglón de datos.")
    if recortadas:
        avisos = [*avisos, f"{recortadas:,} celdas pasaban de {MAX_CELDA} caracteres y se recortaron."]
    return Tabla(columnas, filas, avisos)


def nombres_columnas(encabezados: list[str]) -> list[str]:
    nombres: list[str] = []
    for i, crudo in enumerate(encabezados, start=1):
        base = crudo[:80] or f"columna {i}"
        nombre, n = base, 2
        while nombre in nombres:
            nombre, n = f"{base} ({n})", n + 1
        nombres.append(nombre)
    return nombres


def numero(valor: str) -> float | None:
    """`"1,234.5"`, `"12,5"` y `"$ 80"` son números; lo demás, `None`."""
    limpio = valor.strip().lstrip("$").replace(" ", "")
    if _MILES.match(limpio):
        limpio = limpio.replace(",", "")
    elif _COMA_DECIMAL.match(limpio):
        limpio = limpio.replace(",", ".")
    try:
        resultado = float(limpio)
    except ValueError:
        return None
    return resultado if math.isfinite(resultado) else None


def _coordenada(valor: str) -> float | None:
    """En una coordenada la coma siempre es decimal: `"20,671"` es 20.671, no
    los veinte mil del separador de miles."""
    return numero(valor.replace(",", "."))


def clave(valor: str, nivel: str) -> str | None:
    """CVEGEO normalizada, o `None` si no tiene la forma del nivel. Recupera
    el cero que Excel le come a los estados 01 a 09."""
    limpio = re.sub(r"[\s-]", "", valor).upper()
    if nivel == "municipio" and re.fullmatch(r"\d{4,5}", limpio):
        return limpio.zfill(5)
    if nivel == "ageb" and re.fullmatch(r"\d{8,9}[0-9A-Z]{4}", limpio):
        return limpio.zfill(13)
    return None


def _normal(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_acentos.strip().lower()


def sugerir(tabla: Tabla) -> dict | None:
    """Adivina la ubicación por nombre de columna y contenido. Solo llena el
    formulario: la persona confirma antes de guardar."""
    if tabla.geometrias is not None:
        return {"tipo": "vector"}
    nombres = {_normal(c): c for c in tabla.columnas}
    lat = next((nombres[n] for n in _NOMBRES_LAT if n in nombres), None)
    lon = next((nombres[n] for n in _NOMBRES_LON if n in nombres), None)
    if lat and lon:
        return {"tipo": "puntos", "lat": lat, "lon": lon}

    # Antes que la clave entera: la columna AGEB de un tabulado (`0026`) también
    # tiene la forma de un municipio de 4 dígitos.
    partes = _sugerir_partes(tabla, nombres)
    if partes:
        return partes

    muestra = tabla.filas[:200]
    for i, columna in enumerate(tabla.columnas):
        if not any(pista in _normal(columna) for pista in _PISTAS_CLAVE):
            continue
        valores = [f[i] for f in muestra if f[i]]
        for nivel in ("ageb", "municipio"):
            if valores and sum(clave(v, nivel) is not None for v in valores) >= 0.8 * len(valores):
                return {"tipo": nivel, "clave": columna}
    return None


def _sugerir_partes(tabla: Tabla, nombres: dict[str, str]) -> dict | None:
    """La clave partida en columnas, como en los tabulados de INEGI."""

    def buscar(*opciones: str) -> str | None:
        return next((nombres[o] for o in opciones if o in nombres), None)

    ent = buscar("entidad", "ent", "cve_ent")
    mun = buscar("mun", "cve_mun", "municipio")
    if not ent or not mun:
        return None
    # "municipio" a veces trae el nombre: las partes tienen que ser dígitos.
    for columna in (ent, mun):
        i = tabla.columnas.index(columna)
        if not all(f[i].isdigit() and len(f[i]) <= 3 for f in tabla.filas[:200] if f[i]):
            return None

    loc, ageb = buscar("loc", "cve_loc"), buscar("ageb", "cve_ageb")
    if loc and ageb:
        return {"tipo": "ageb", "partes": [ent, mun, loc, ageb]}
    return {"tipo": "municipio", "partes": [ent, mun]}


def columnas_numericas(tabla: Tabla) -> list[str]:
    """Columnas con al menos un número y nada que no lo sea. Una clave no es
    número: como tal perdería el cero de `01001` y saldría como `14,039`."""
    resultado = []
    for i, columna in enumerate(tabla.columnas):
        nombre = _normal(columna)
        if any(p in nombre for p in ("cvegeo", "clave", "cve_", "folio", "codigo", "telefono")):
            continue
        valores = [f[i] for f in tabla.filas if f[i]]
        ceros = any(re.fullmatch(r"0\d+", v) for v in valores)
        if valores and not ceros and all(numero(v) is not None for v in valores):
            resultado.append(columna)
    return resultado


def datos_de(tabla: Tabla, numericas: list[str]) -> list[dict]:
    """Cada renglón como `{columna: valor}`, con número real en las columnas
    numéricas y `None` donde la celda venía vacía (nunca un cero inventado)."""
    es_numerica = [c in numericas for c in tabla.columnas]

    def valor(celda: str, numerica: bool):
        if not celda:
            return None
        if not numerica:
            return celda
        cifra = numero(celda)
        return int(cifra) if cifra.is_integer() else cifra

    return [
        {c: valor(celda, n) for c, celda, n in zip(tabla.columnas, fila, es_numerica)}
        for fila in tabla.filas
    ]


def _indice(tabla: Tabla, columna: str | None) -> int:
    if columna not in tabla.columnas:
        raise ArchivoInvalido(f'El archivo no tiene la columna "{columna}".')
    return tabla.columnas.index(columna)


def ubicar_puntos(tabla: Tabla, col_lat: str, col_lon: str) -> dict:
    i_lat, i_lon = _indice(tabla, col_lat), _indice(tabla, col_lon)
    numericas = columnas_numericas(tabla)
    filas = []
    descartes = {"sin_dato": 0, "no_es_numero": 0, "fuera_de_mexico": 0}

    for fila, datos in zip(tabla.filas, datos_de(tabla, numericas)):
        crudo_lat, crudo_lon = fila[i_lat], fila[i_lon]
        if not crudo_lat or not crudo_lon:
            descartes["sin_dato"] += 1
            continue
        lat, lon = _coordenada(crudo_lat), _coordenada(crudo_lon)
        if lat is None or lon is None:
            descartes["no_es_numero"] += 1
        elif LAT_MEXICO[0] <= lat <= LAT_MEXICO[1] and LON_MEXICO[0] <= lon <= LON_MEXICO[1]:
            filas.append({"lat": lat, "lon": lon, "clave": None, "datos": datos})
        else:
            descartes["fuera_de_mexico"] += 1

    return {"filas": filas, "descartes": descartes, "numericas": numericas, "repetidas": 0}


def _indices_clave(tabla: Tabla, columnas: list[str] | None, nivel: str) -> list[int]:
    if not columnas:
        raise ArchivoInvalido("Falta decir en qué columna está la clave.")
    if len(columnas) > 1 and len(columnas) != len(_ANCHOS[nivel]):
        raise ArchivoInvalido(f"La clave de {nivel} se arma con {len(_ANCHOS[nivel])} columnas.")
    return [_indice(tabla, c) for c in columnas]


def _clave_de_fila(fila: list[str], indices: list[int], nivel: str) -> tuple[str, str | None]:
    """Texto crudo de la clave y la clave normalizada. Partida en columnas, cada
    parte recupera sus ceros: `1`, `1` son el municipio `01001`."""
    partes = [fila[i] for i in indices]
    if len(partes) == 1:
        return partes[0], clave(partes[0], nivel) if partes[0] else None
    if not all(partes):
        return "", None
    return "".join(partes), clave("".join(p.zfill(a) for p, a in zip(partes, _ANCHOS[nivel])), nivel)


def claves_de(tabla: Tabla, columnas: list[str] | None, nivel: str) -> set[str]:
    """Primer paso de `ubicar` por clave: las claves bien formadas, para que
    el servidor pregunte cuáles existen en el marco."""
    indices = _indices_clave(tabla, columnas, nivel)
    claves = {c for f in tabla.filas if (c := _clave_de_fila(f, indices, nivel)[1])}
    if len(claves) > MAX_POLIGONOS:
        raise ArchivoInvalido(f"El archivo tiene {len(claves):,} zonas distintas; el tope es {MAX_POLIGONOS:,}.")
    return claves


def ubicar_claves(tabla: Tabla, columnas: list[str] | None, nivel: str, existentes: set[str]) -> dict:
    indices = _indices_clave(tabla, columnas, nivel)
    numericas = columnas_numericas(tabla)
    filas = []
    vistas: set[str] = set()
    repetidas = 0
    descartes = {"sin_dato": 0, "clave_invalida": 0, "clave_desconocida": 0}

    for fila, datos in zip(tabla.filas, datos_de(tabla, numericas)):
        crudo, normal = _clave_de_fila(fila, indices, nivel)
        if not crudo:
            descartes["sin_dato"] += 1
        elif normal is None:
            descartes["clave_invalida"] += 1
        elif normal not in existentes:
            descartes["clave_desconocida"] += 1
        else:
            repetidas += normal in vistas
            vistas.add(normal)
            filas.append({"lat": None, "lon": None, "clave": normal, "datos": datos})

    return {"filas": filas, "descartes": descartes, "numericas": numericas, "repetidas": repetidas}
