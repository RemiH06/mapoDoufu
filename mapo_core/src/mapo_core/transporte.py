"""Transporte público (sesión 27): rutas, paradas y frecuencias de los GTFS abiertos
de México, y rutas de OpenStreetMap donde no hay GTFS. Ver docs/fuentes/gtfs.md y
docs/producto/transporte.md.

No hay una fuente nacional: cada ciudad publica (o no) su GTFS. `FEEDS` es el
catálogo curado de lo que se encontró en Mobility Database y en el Hub de Datos de
Transporte Público de Codeando México (2026-11-22), con su productor y su licencia
tal como la declaran; `None` es que no declara ninguna.

De cada feed se guarda, por ruta, cuántas veces pasa en la hora pico de un día
hábil (de 7 a 9 de la mañana de un miércoles dentro de su vigencia) y, por parada,
cada cuánto pasa la ruta más frecuente que la toca. Nunca se mezclan las rutas de
OSM (sin horarios) con las del GTFS: OSM solo se muestra donde no hay GTFS.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import math
import re
import urllib.request
import zipfile
from array import array
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from mapo_core import zona as zona_comun

# Hora pico de la mañana, en segundos desde la medianoche del día de servicio.
PICO = (7 * 3600, 9 * 3600)
HORAS_PICO = (PICO[1] - PICO[0]) / 3600
# "Frecuente": cada 15 minutos o menos en la hora pico (4 pasadas por hora).
FRECUENTE_MIN = 15
# Un feed que pone la misma frecuencia a casi todas sus rutas la rellenó (Toluca,
# Uruapan y Oaxaca: 24 pasadas en dos horas en casi todas; Cabo San Lucas, cuyo autor
# dice que faltan): no se usa como frecuencia. Ver docs/fuentes/gtfs.md.
UNIFORME_RUTAS = 10
UNIFORME_PARTE = 0.8
# Topes para archivos de terceros.
MAX_DESCARGA = 300 * 1024 * 1024
MAX_DESCOMPRIMIDO = 3 * 1024 * 1024 * 1024
MAX_PROPORCION = 200  # descomprimido entre comprimido, por archivo grande
MAX_HORARIOS = 25_000_000
OSM = "osm"

LICENCIAS = {
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "ODC-BY-1.0": "https://opendatacommons.org/licenses/by/1-0/",
    "ODbL-1.0": "https://opendatacommons.org/licenses/odbl/1-0/",
}

HUB = "https://hdtp.codeandomexico.org"


@dataclass(frozen=True)
class Feed:
    clave: str
    titulo: str
    productor: str
    urls: tuple[str, ...]  # en orden: la original primero, la copia después
    pagina: str
    licencia: str | None  # clave de LICENCIAS; None = el feed no declara licencia
    via: str
    excluir_agencias: tuple[str, ...] = ()  # cubiertas por un feed más nuevo
    nota: str = ""


def _hub(ident: str) -> str:
    return f"{HUB}/gtfs/{ident}.zip"


_VIA_HUB = "Hub de Datos de Transporte Público en México (Codeando México)"
_VIA_MDB = "Mobility Database (MobilityData)"

FEEDS = {f.clave: f for f in (
    Feed("jal-setran", "Jalisco: ZMG, Puerto Vallarta, Tepatitlán, Lagos de Moreno y Zapotlanejo",
         "Secretaría de Transporte del Estado de Jalisco (SETRAN), publicado por Ualabee",
         ("https://ualabee.com/api/v3/cities/35/gtfs-feeds/public",),
         "https://mobilitydatabase.org/feeds/gtfs/mdb-3632", None, _VIA_MDB,
         nota="Reemplaza los GTFS de 2020 a 2024 del portal de Jalisco (vencidos)."),
    Feed("cdmx-semovi", "Ciudad de México: Metro, RTP, Trolebús, Tren Ligero, Cablebús y corredores",
         "Secretaría de Movilidad de la Ciudad de México (SEMOVI)",
         (_hub("mex-cdmx-cdmx"),), "https://datos.cdmx.gob.mx/dataset/gtfs", "CC-BY-4.0", _VIA_HUB,
         excluir_agencias=("MB", "INTERURBANO"),
         nota="Metrobús y El Insurgente salen de sus feeds propios, más nuevos."),
    Feed("cdmx-metrobus", "Ciudad de México: Metrobús", "Metrobús CDMX",
         (_hub("mex-cdmx-cdmx-metrobus"),), f"{HUB}/datos/mex-cdmx-cdmx-metrobus", "ODC-BY-1.0", _VIA_HUB),
    Feed("cdmx-insurgente", "Tren El Insurgente (Ciudad de México y Estado de México)",
         "Codeando México con OpenStreetMap y datos del operador (titular: Banobras)",
         (_hub("mex-cdmx-elinsurgente"),), f"{HUB}/datos/mex-cdmx-elinsurgente", "ODC-BY-1.0", _VIA_HUB),
    Feed("mex-toluca", "Toluca", "Secretaría de Movilidad del Estado de México",
         ("https://datos.movimex.gob.mx/gtfs/toluca.gtfs.zip", _hub("mex-mex-toluca")),
         "https://mobilitydatabase.org/feeds/gtfs/mdb-2865", None, _VIA_MDB),
    Feed("mex-jilotepec", "Jilotepec", "Dirección de Desarrollo Urbano de Jilotepec (titular: SEMOV del Estado de México)",
         ("https://www.jilotepecmex.gob.mx/gobdigital/mapa_transporte/gtfs.zip", _hub("mex-mex-jilotepec")),
         f"{HUB}/datos/mex-mex-jilotepec", "CC-BY-4.0", _VIA_HUB),
    Feed("yuc-vayven", "Mérida: Va y Ven", "Agencia de Transporte de Yucatán",
         ("https://transit-scheduler.com/api/export-gtfs/latest",),
         "https://mobilitydatabase.org/feeds/gtfs/mdb-3650", None, _VIA_MDB),
    Feed("qro-qrobus", "Querétaro: Qrobús", "Agencia de Movilidad del Estado de Querétaro (AMEQ)",
         ("https://qrobus.gob.mx/gtfs/latest", _hub("mex-qro-queretaro-qrobus")),
         f"{HUB}/datos/mex-qro-queretaro-qrobus", None, _VIA_HUB),
    Feed("ags-concesionado", "Aguascalientes", "Gobierno del Estado de Aguascalientes",
         ("https://www.aguascalientes.gob.mx/portalgea/file/otros/gdeda-aguascalientes-mx.zip", _hub("mex-ags-ags")),
         f"{HUB}/datos/mex-ags-ags", "CC-BY-SA-4.0", _VIA_HUB),
    Feed("mich-uruapan", "Uruapan", "Codeando México (titular: Instituto del Transporte del Estado de Michoacán)",
         (_hub("mex-mich-uruapan"),), f"{HUB}/datos/mex-mich-uruapan", None, _VIA_HUB),
    Feed("mich-zamora", "Zamora", "Dirección de Movilidad del Ayuntamiento de Zamora",
         (_hub("mex-mich-zamora"),), f"{HUB}/datos/mex-mich-zamora", "CC-BY-SA-4.0", _VIA_HUB),
    Feed("mich-zitacuaro", "Zitácuaro", "Codeando México (titular: Instituto del Transporte del Estado de Michoacán)",
         (_hub("mex-mich-zitacuaro"),), f"{HUB}/datos/mex-mich-zitacuaro", None, _VIA_HUB),
    Feed("oax-oaxaca", "Oaxaca de Juárez", "Codeando México (titular: SEMOVI Oaxaca)",
         (_hub("mex-oax-oaxaca"),), f"{HUB}/datos/mex-oax-oaxaca", None, _VIA_HUB),
    Feed("oax-huatulco", "Bahías de Huatulco", "Secretaría de Movilidad del Estado de Oaxaca",
         (_hub("mex-oax-huatulco"),), f"{HUB}/datos/mex-oax-huatulco", "ODC-BY-1.0", _VIA_HUB),
    Feed("oax-puertoescondido", "Puerto Escondido", "Codeando México (titular: SEMOVI Oaxaca)",
         (_hub("mex-oax-puertoescondido"),), f"{HUB}/datos/mex-oax-puertoescondido", None, _VIA_HUB),
    Feed("oax-salinacruz", "Salina Cruz", "Secretaría de Movilidad del Estado de Oaxaca",
         (_hub("mex-oax-salinacruz"),), f"{HUB}/datos/mex-oax-salinacruz", "ODC-BY-1.0", _VIA_HUB),
    Feed("bcs-cabo", "Cabo San Lucas", "Codeando México con datos del IMPLAN de Los Cabos",
         (_hub("mex-bcs-cabosanlucas"),), f"{HUB}/datos/mex-bcs-cabosanlucas", "ODC-BY-1.0", _VIA_HUB,
         nota="Incompleto según su autor: faltan frecuencias y tarifas."),
)}

# route_type de GTFS (básicos y extendidos) a un modo de Mapo.
_MODOS_BASICOS = {0: "tren_ligero", 1: "metro", 2: "tren", 3: "autobus", 4: "ferri", 5: "cable", 6: "cable",
                  7: "funicular", 11: "trolebus", 12: "monorriel"}
MODOS = {"metro": "Metro", "tren": "Tren", "tren_ligero": "Tren ligero", "monorriel": "Monorriel",
         "cable": "Cable", "funicular": "Funicular", "trolebus": "Trolebús", "autobus": "Autobús",
         "colectivo": "Colectivo", "ferri": "Ferri", "otro": "Otro"}


def modo(route_type) -> str:
    try:
        t = int(route_type)
    except (TypeError, ValueError):
        return "otro"
    if t in _MODOS_BASICOS:
        return _MODOS_BASICOS[t]
    centena = t // 100
    return {1: "tren", 2: "autobus", 4: "metro", 7: "autobus", 8: "trolebus", 9: "tren_ligero",
            10: "ferri", 12: "ferri", 13: "cable", 14: "funicular"}.get(centena, "otro")


class ArchivoInvalido(Exception):
    pass


# ---------------------------------------------------------------- lectura del GTFS

def _segundos(hora: str) -> int | None:
    """'25:10:00' -> 90600. GTFS permite horas de 24 en adelante (después de la medianoche)."""
    partes = (hora or "").strip().split(":")
    if len(partes) != 3:
        return None
    try:
        h, m, s = (int(p) for p in partes)
    except ValueError:
        return None
    if h < 0 or not 0 <= m < 60 or not 0 <= s < 61 or h > 72:
        return None
    return h * 3600 + m * 60 + s


def _fecha(texto: str) -> datetime.date | None:
    try:
        return datetime.datetime.strptime(texto.strip(), "%Y%m%d").date()
    except (ValueError, AttributeError):
        return None


def abrir(ruta: Path) -> zipfile.ZipFile:
    """El zip de un tercero: solo se leen por nombre los archivos de GTFS, nunca se
    extrae nada a disco; se rechaza lo que parezca una bomba de compresión."""
    try:
        z = zipfile.ZipFile(ruta)
    except zipfile.BadZipFile as exc:
        raise ArchivoInvalido(f"{ruta.name} no es un zip") from exc
    total = 0
    for i in z.infolist():
        total += i.file_size
        if i.file_size > 50 * 1024 * 1024 and i.file_size > MAX_PROPORCION * max(i.compress_size, 1):
            raise ArchivoInvalido(f"{i.filename}: proporción de compresión sospechosa")
    if total > MAX_DESCOMPRIMIDO:
        raise ArchivoInvalido(f"descomprimido pesa {total // 2**20} MB, más del tope")
    return z


def _miembro(z: zipfile.ZipFile, nombre: str) -> str | None:
    """Algunos feeds traen los .txt dentro de una carpeta."""
    for n in z.namelist():
        if n == nombre or n.endswith("/" + nombre):
            return n
    return None


def _filas(z: zipfile.ZipFile, nombre: str, obligatorio: bool = False):
    n = _miembro(z, nombre)
    if n is None:
        if obligatorio:
            raise ArchivoInvalido(f"falta {nombre}")
        return iter(())
    texto = io.TextIOWrapper(z.open(n), encoding="utf-8-sig", errors="replace", newline="")
    return ({(k or "").strip(): (v or "").strip() for k, v in fila.items()} for fila in csv.DictReader(texto))


def servicios_del_dia(calendario: list[dict], excepciones: list[dict], dia: datetime.date) -> set[str]:
    dias = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    activos = set()
    for c in calendario:
        ini, fin = _fecha(c.get("start_date", "")), _fecha(c.get("end_date", ""))
        if ini and fin and ini <= dia <= fin and c.get(dias[dia.weekday()]) == "1":
            activos.add(c["service_id"])
    for e in excepciones:
        if _fecha(e.get("date", "")) == dia:
            if e.get("exception_type") == "1":
                activos.add(e["service_id"])
            elif e.get("exception_type") == "2":
                activos.discard(e["service_id"])
    return activos


def vigencia(calendario: list[dict], excepciones: list[dict]) -> tuple[datetime.date | None, datetime.date | None]:
    fechas = [f for c in calendario for f in (_fecha(c.get("start_date", "")), _fecha(c.get("end_date", ""))) if f]
    fechas += [f for e in excepciones if e.get("exception_type") == "1" and (f := _fecha(e.get("date", "")))]
    return (min(fechas), max(fechas)) if fechas else (None, None)


def fecha_referencia(calendario: list[dict], excepciones: list[dict], viajes_por_servicio: Counter,
                     hoy: datetime.date) -> datetime.date | None:
    """El miércoles con más viajes de la vigencia: así no cae en un feriado ni en el
    resto de un feed cuyo servicio principal ya terminó (SEMOVI: casi todo acaba en
    2025 y solo una ruta sigue en 2026). Empate: el más cercano a hoy. Se busca en los
    últimos tres años y el próximo (los feeds hechos a mano dicen de 2000 a 2100)."""
    ini, fin = vigencia(calendario, excepciones)
    if ini is None:
        return None
    ancla = min(max(hoy, ini), fin)
    desde, hasta = max(ini, hoy - datetime.timedelta(days=3 * 365)), min(fin, hoy + datetime.timedelta(days=365))
    if desde > hasta:  # vencido hace más de tres años: su último año
        desde, hasta = max(ini, fin - datetime.timedelta(days=365)), fin
    dia = desde + datetime.timedelta(days=(2 - desde.weekday()) % 7)
    mejor, mejor_clave = None, None
    while dia <= hasta:
        viajes = sum(viajes_por_servicio[s] for s in servicios_del_dia(calendario, excepciones, dia))
        clave = (viajes, -abs((dia - ancla).days))
        if viajes and (mejor_clave is None or clave > mejor_clave):
            mejor, mejor_clave = dia, clave
        dia += datetime.timedelta(days=7)
    return mejor


def _interpolar(tiempos: list[int | None]) -> list[int | None]:
    """Las paradas sin hora (permitido en GTFS entre dos con hora) toman la hora
    proporcional por orden de parada."""
    conocidos = [i for i, t in enumerate(tiempos) if t is not None]
    if len(conocidos) < 2:
        return tiempos
    salida = list(tiempos)
    for a, b in zip(conocidos, conocidos[1:]):
        for i in range(a + 1, b):
            salida[i] = tiempos[a] + (tiempos[b] - tiempos[a]) * (i - a) // (b - a)
    return salida


def pasadas_en_pico(inicio: int, fin: int, cada: int, desfase: int) -> int:
    """Cuántas salidas de un viaje por frecuencia (de `inicio` a `fin`, cada `cada`
    segundos) pasan por una parada a `desfase` segundos del arranque dentro de PICO."""
    if cada <= 0 or fin <= inicio:
        return 0
    # salidas d = inicio + k*cada, d < fin; pasa en d + desfase, dentro de [PICO).
    k_min = max(0, math.ceil((PICO[0] - desfase - inicio) / cada))
    k_max = min(math.ceil((fin - inicio) / cada) - 1, math.ceil((PICO[1] - desfase - inicio) / cada) - 1)
    return max(0, k_max - k_min + 1)


def _salidas(inicio: int, fin: int, cada: int) -> int:
    return max(0, math.ceil((fin - inicio) / cada)) if cada > 0 and fin > inicio else 0


@dataclass
class Ruta:
    route_id: str
    agencia: str
    nombre_corto: str
    nombre_largo: str
    modo: str
    color: str
    viajes_dia: int = 0
    salidas_pico: int = 0  # del sentido más servido, en su parada más servida
    frecuencia_estimada: bool = False  # salió de frequencies.txt sin horas exactas
    lineas: list[list[tuple[float, float]]] = field(default_factory=list)


@dataclass
class Parada:
    stop_id: str
    nombre: str
    lat: float
    lon: float
    pasadas_ruta_max: int = 0  # en PICO, de la ruta y sentido que más pasa
    pasadas: int = 0  # en PICO, todas las rutas
    rutas: set[str] = field(default_factory=set)


@dataclass
class Lectura:
    rutas: dict[str, Ruta]
    paradas: dict[str, Parada]
    fecha_ref: datetime.date | None
    vigencia_ini: datetime.date | None
    vigencia_fin: datetime.date | None
    viajes_dia: int
    avisos: list[str]
    frecuencia_util: bool = True


def leer(ruta: Path, excluir_agencias: tuple[str, ...] = (), hoy: datetime.date | None = None) -> Lectura:
    hoy = hoy or datetime.date.today()
    avisos: list[str] = []
    with abrir(ruta) as z:
        agencias = {a.get("agency_id", ""): a.get("agency_name", "") for a in _filas(z, "agency.txt", True)}
        una_agencia = next(iter(agencias.values()), "") if len(agencias) == 1 else ""
        rutas: dict[str, Ruta] = {}
        fuera = 0
        for r in _filas(z, "routes.txt", True):
            ag = r.get("agency_id", "")
            if ag in excluir_agencias:
                fuera += 1
                continue
            rutas[r["route_id"]] = Ruta(r["route_id"], agencias.get(ag, una_agencia), r.get("route_short_name", ""),
                                        r.get("route_long_name", ""), modo(r.get("route_type")),
                                        r.get("route_color", "")[:6])
        if fuera:
            avisos.append(f"{fuera} rutas de {', '.join(excluir_agencias)} fuera: vienen de un feed más nuevo")
        calendario = list(_filas(z, "calendar.txt"))
        excepciones = list(_filas(z, "calendar_dates.txt"))
        viajes = {t["trip_id"]: t for t in _filas(z, "trips.txt", True) if t.get("route_id") in rutas}
        por_servicio = Counter(t.get("service_id") for t in viajes.values())
        ini, fin = vigencia(calendario, excepciones)
        dia = fecha_referencia(calendario, excepciones, por_servicio, hoy)
        activos = servicios_del_dia(calendario, excepciones, dia) if dia else set()
        if dia is None:
            avisos.append("sin calendario con viajes: no hay frecuencias")
        frecuencias: dict[str, list[tuple[int, int, int, bool]]] = defaultdict(list)
        for f in _filas(z, "frequencies.txt"):
            a, b = _segundos(f.get("start_time", "")), _segundos(f.get("end_time", ""))
            try:
                cada = int(f.get("headway_secs", ""))
            except ValueError:
                continue
            if a is not None and b is not None and cada > 0:
                frecuencias[f["trip_id"]].append((a, b, cada, f.get("exact_times") == "1"))

        paradas: dict[str, Parada] = {}
        for p in _filas(z, "stops.txt", True):
            if p.get("location_type", "0") not in ("", "0"):
                continue  # estaciones, entradas y nodos: no se sube ahí
            try:
                lat, lon = float(p["stop_lat"]), float(p["stop_lon"])
            except (KeyError, ValueError):
                continue
            if 14 <= lat <= 33.5 and -119 <= lon <= -85:
                paradas[p["stop_id"]] = Parada(p["stop_id"], p.get("stop_name", ""), lat, lon)

        # Horarios en arreglos compactos (Guadalajara: millones de renglones), solo de los
        # viajes del día y de un viaje por ruta y sentido (para trazarla si no hay shapes).
        # Las rutas que tocan cada parada salen de todos los viajes, de cualquier día.
        del_dia = {tid for tid, t in viajes.items() if t.get("service_id") in activos}
        muestra: dict[tuple[str, str], str] = {}
        for tid, t in viajes.items():
            muestra.setdefault((t["route_id"], t.get("direction_id", "")), tid)
        guardar_de = del_dia | set(muestra.values())
        indice: dict[str, int] = {}
        nombres_parada: list[str] = []
        horarios: dict[str, tuple[array, array, array]] = {}
        toca: set[tuple[str, int]] = set()
        n = 0
        for h in _filas(z, "stop_times.txt", True):
            n += 1
            if n > MAX_HORARIOS:
                raise ArchivoInvalido(f"más de {MAX_HORARIOS} renglones en stop_times.txt")
            tid = h.get("trip_id")
            t = viajes.get(tid)
            if t is None:
                continue
            sid = h.get("stop_id", "")
            i = indice.get(sid)
            if i is None:
                i = indice[sid] = len(nombres_parada)
                nombres_parada.append(sid)
            toca.add((t["route_id"], i))
            if tid not in guardar_de:
                continue
            try:
                orden = int(h.get("stop_sequence", ""))
            except ValueError:
                continue
            seg = _segundos(h.get("departure_time") or h.get("arrival_time", ""))
            a = horarios.get(tid)
            if a is None:
                a = horarios[tid] = (array("l"), array("l"), array("l"))
            a[0].append(orden)
            a[1].append(i)
            a[2].append(-1 if seg is None else seg)

        formas: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
        for s in _filas(z, "shapes.txt"):
            try:
                formas[s["shape_id"]].append((int(s["shape_pt_sequence"]), float(s["shape_pt_lat"]),
                                              float(s["shape_pt_lon"])))
            except (KeyError, ValueError):
                continue

    # Pasadas en PICO por (ruta, sentido, parada).
    pasadas: Counter = Counter()
    viajes_dia_total = 0
    for tid in del_dia:
        t = viajes[tid]
        filas = _ordenadas(horarios.get(tid), nombres_parada)
        if not filas:
            continue
        rid, sentido = t["route_id"], t.get("direction_id", "")
        tiempos = _interpolar([x[2] for x in filas])
        base = next((x for x in tiempos if x is not None), None)
        if base is None:
            continue
        # Un circuito toca la misma parada dos veces en un viaje: cuenta la primera,
        # o la ruta parecería pasar el doble de seguido (SEMOVI, rutas de RTP).
        vistas: set[str] = set()
        unicas = []
        for (_, sid, _), tt in zip(filas, tiempos):
            if tt is not None and sid not in vistas:
                vistas.add(sid)
                unicas.append((sid, tt))
        r = rutas[rid]
        if tid in frecuencias:
            for a, b, cada, exacto in frecuencias[tid]:
                r.viajes_dia += _salidas(a, b, cada)
                viajes_dia_total += _salidas(a, b, cada)
                r.frecuencia_estimada |= not exacto
                for sid, tt in unicas:
                    pasadas[(rid, sentido, sid)] += pasadas_en_pico(a, b, cada, tt - base)
        else:
            r.viajes_dia += 1
            viajes_dia_total += 1
            for sid, tt in unicas:
                if PICO[0] <= tt < PICO[1]:
                    pasadas[(rid, sentido, sid)] += 1

    por_sentido: dict[tuple[str, str], int] = defaultdict(int)
    for (rid, sentido, sid), k in pasadas.items():
        por_sentido[(rid, sentido)] = max(por_sentido[(rid, sentido)], k)
        p = paradas.get(sid)
        if p is not None and k:
            p.pasadas += k
            p.pasadas_ruta_max = max(p.pasadas_ruta_max, k)
    for (rid, _), k in por_sentido.items():
        rutas[rid].salidas_pico = max(rutas[rid].salidas_pico, k)
    for rid, i in toca:
        p = paradas.get(nombres_parada[i])
        if p is not None:
            p.rutas.add(rid)

    # Trazo: por sentido, la forma que más viajes usan; sin shapes, las paradas en orden.
    uso: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for tid, t in viajes.items():
        uso[(t["route_id"], t.get("direction_id", ""))][t.get("shape_id") or ("#" + tid)] += 1 + (tid in del_dia) * 1000
    for (rid, sentido), conteo in uso.items():
        clave = conteo.most_common(1)[0][0]
        if not clave.startswith("#") and len(formas.get(clave, ())) >= 2:
            linea = [(lat, lon) for _, lat, lon in sorted(formas[clave])]
        else:
            tid = muestra[(rid, sentido)]
            linea = [(paradas[sid].lat, paradas[sid].lon) for _, sid, _ in
                     _ordenadas(horarios.get(tid), nombres_parada) if sid in paradas]
        linea = [x for x in linea if 14 <= x[0] <= 33.5 and -119 <= x[1] <= -85]
        if len(linea) >= 2:
            rutas[rid].lineas.append(linea)

    sin_trazo = [r for r in rutas.values() if not r.lineas]
    if sin_trazo:
        avisos.append(f"{len(sin_trazo)} rutas sin viajes ni trazo: no se guardan")
        for r in sin_trazo:
            del rutas[r.route_id]
    paradas = {sid: p for sid, p in paradas.items() if p.rutas}
    if dia and fin and fin < hoy:
        avisos.append(f"vencido: su vigencia acabó el {fin.isoformat()}")
    if dia and (hoy - dia).days > 182 and not (fin and fin < hoy):
        avisos.append(f"las frecuencias son del {dia.isoformat()}: después de esa fecha el feed trae menos servicio")
    util = frecuencia_util([r.salidas_pico for r in rutas.values()])
    if not util:
        comun, _ = Counter(r.salidas_pico for r in rutas.values()).most_common(1)[0]
        avisos.append(f"frecuencia de relleno: {comun} pasadas de 7 a 9 en casi todas las rutas; no se usa")
    return Lectura(rutas, paradas, dia, ini, fin, viajes_dia_total, avisos, util)


def frecuencia_util(salidas: list[int]) -> bool:
    """False si el feed le puso la misma frecuencia a casi todas sus rutas."""
    if len(salidas) < UNIFORME_RUTAS:
        return True
    _, veces = Counter(salidas).most_common(1)[0]
    return veces / len(salidas) < UNIFORME_PARTE


def _ordenadas(a: tuple[array, array, array] | None, nombres: list[str]) -> list[tuple[int, str, int | None]]:
    if a is None:
        return []
    return sorted((o, nombres[i], None if t < 0 else t) for o, i, t in zip(*a))


def pasadas_frecuente() -> int:
    """Pasadas en PICO para contar como frecuente: 8 en dos horas = cada 15 minutos."""
    return math.ceil(HORAS_PICO * 60 / FRECUENTE_MIN)


def intervalo_min(salidas_pico: int) -> float | None:
    """Minutos entre una pasada y otra en la hora pico; None si no pasa."""
    return round(HORAS_PICO * 60 / salidas_pico, 1) if salidas_pico else None


# ---------------------------------------------------------------- descarga y carga

def descargar(feed: Feed, carpeta: Path, avisar=print) -> tuple[Path, str]:
    """(archivo, url de donde salió). Prueba las URL en orden; la original primero."""
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{feed.clave}.zip"
    errores = []
    for url in feed.urls:
        tmp = destino.with_suffix(".tmp")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mapo-transporte/0.1"})
            with urllib.request.urlopen(req, timeout=180) as resp, open(tmp, "wb") as fh:
                leidos = 0
                while bloque := resp.read(1 << 20):
                    leidos += len(bloque)
                    if leidos > MAX_DESCARGA:
                        raise ArchivoInvalido(f"pasa de {MAX_DESCARGA // 2**20} MB")
                    fh.write(bloque)
            abrir(tmp).close()
            tmp.replace(destino)
            return destino, url
        except (OSError, ArchivoInvalido) as exc:
            errores.append(f"{url}: {exc}")
            tmp.unlink(missing_ok=True)
            avisar(f"{feed.clave}: no se pudo bajar de {url} ({exc})")
    raise ArchivoInvalido("; ".join(errores))


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        while bloque := fh.read(1 << 20):
            h.update(bloque)
    return h.hexdigest()


def _ewkt(lineas: list[list[tuple[float, float]]]) -> str:
    partes = ",".join("(" + ",".join(f"{lon:.6f} {lat:.6f}" for lat, lon in linea) + ")" for linea in lineas)
    return f"SRID=4326;MULTILINESTRING({partes})"


async def guardar(pool: AsyncConnectionPool, feed: dict, rutas: list[dict], paradas: list[dict]) -> None:
    """Reemplaza un feed completo en una sola transacción: si algo falla, queda el anterior."""
    async with pool.connection() as conn:
        async with conn.transaction():
            for tabla in ("transporte_paradas", "transporte_rutas", "transporte_feeds"):
                await conn.execute(f"DELETE FROM {tabla} WHERE feed = %s", (feed["feed"],))
            await conn.execute(
                """INSERT INTO transporte_feeds (feed, titulo, productor, licencia, pagina, url, via, sha256, bytes,
                                                 vigencia_ini, vigencia_fin, fecha_ref, viajes_dia, rutas, paradas,
                                                 avisos, nota, frecuencia_util)
                   VALUES (%(feed)s, %(titulo)s, %(productor)s, %(licencia)s, %(pagina)s, %(url)s, %(via)s,
                           %(sha256)s, %(bytes)s, %(vigencia_ini)s, %(vigencia_fin)s, %(fecha_ref)s, %(viajes_dia)s,
                           %(rutas)s, %(paradas)s, %(avisos)s, %(nota)s, %(frecuencia_util)s)""",
                {**feed, "avisos": json.dumps(feed["avisos"], ensure_ascii=False)})
            async with conn.cursor() as cur:
                async with cur.copy("COPY transporte_rutas (feed, route_id, agencia, nombre_corto, nombre_largo, modo,"
                                    " color, viajes_dia, salidas_pico, frecuencia_estimada, geom) FROM STDIN") as copia:
                    for r in rutas:
                        await copia.write_row([feed["feed"], r["route_id"], r["agencia"], r["nombre_corto"],
                                               r["nombre_largo"], r["modo"], r["color"], r["viajes_dia"],
                                               r["salidas_pico"], r["frecuencia_estimada"], r["geom"]])
                async with cur.copy("COPY transporte_paradas (feed, stop_id, nombre, lat, lon, pasadas_ruta_max,"
                                    " pasadas, rutas) FROM STDIN") as copia:
                    for p in paradas:
                        await copia.write_row([feed["feed"], p["stop_id"], p["nombre"], p["lat"], p["lon"],
                                               p["pasadas_ruta_max"], p["pasadas"], p["rutas"]])
            await conn.execute(
                """UPDATE transporte_paradas p SET geom = ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)
                   WHERE p.feed = %s""", (feed["feed"],))
            await conn.execute(
                """UPDATE transporte_paradas p SET cve_ent = m.cve_ent, cve_mun = m.cve_mun
                   FROM municipios m WHERE p.feed = %s AND m.geom && p.geom AND ST_Covers(m.geom, p.geom)""",
                (feed["feed"],))


async def cargar_feed(pool: AsyncConnectionPool, feed: Feed, archivo: Path, url: str,
                      hoy: datetime.date | None = None) -> dict:
    lectura = leer(archivo, feed.excluir_agencias, hoy)
    if not lectura.rutas:
        raise ArchivoInvalido(f"{feed.clave}: ninguna ruta con trazo")
    fila = {
        "feed": feed.clave, "titulo": feed.titulo, "productor": feed.productor, "licencia": feed.licencia,
        "pagina": feed.pagina, "url": url, "via": feed.via, "sha256": _sha256(archivo),
        "bytes": archivo.stat().st_size, "vigencia_ini": lectura.vigencia_ini, "vigencia_fin": lectura.vigencia_fin,
        "fecha_ref": lectura.fecha_ref, "viajes_dia": lectura.viajes_dia, "rutas": len(lectura.rutas),
        "paradas": len(lectura.paradas), "avisos": lectura.avisos, "nota": feed.nota,
        "frecuencia_util": lectura.frecuencia_util,
    }
    rutas = [{"route_id": r.route_id, "agencia": r.agencia, "nombre_corto": r.nombre_corto,
              "nombre_largo": r.nombre_largo, "modo": r.modo, "color": r.color, "viajes_dia": r.viajes_dia,
              "salidas_pico": r.salidas_pico, "frecuencia_estimada": r.frecuencia_estimada, "geom": _ewkt(r.lineas)}
             for r in lectura.rutas.values()]
    paradas = [{"stop_id": p.stop_id, "nombre": p.nombre, "lat": p.lat, "lon": p.lon,
                "pasadas_ruta_max": p.pasadas_ruta_max, "pasadas": p.pasadas, "rutas": len(p.rutas)}
               for p in lectura.paradas.values()]
    await guardar(pool, fila, rutas, paradas)
    frecuentes = sum(1 for r in lectura.rutas.values() if lectura.frecuencia_util and r.salidas_pico
                     and intervalo_min(r.salidas_pico) <= FRECUENTE_MIN)
    return {"feed": feed.clave, "url": url, "fecha_ref": str(lectura.fecha_ref), "rutas": len(rutas),
            "paradas": len(paradas), "rutas_frecuentes": frecuentes, "frecuencia_util": lectura.frecuencia_util,
            "modos": dict(Counter(r.modo for r in lectura.rutas.values())), "avisos": lectura.avisos}


# ---------------------------------------------------------------- consulta

def clase_intervalo(minutos: float | None) -> str:
    if minutos is None:
        return "sin_dato"
    if minutos <= 10:
        return "10"
    if minutos <= FRECUENTE_MIN:
        return "15"
    if minutos <= 30:
        return "30"
    return "mas"


CLASES = {"10": "cada 10 min o menos", "15": "de 10 a 15 min", "30": "de 15 a 30 min", "mas": "más de 30 min",
          "sin_dato": "sin horario en hora pico"}


def _color(texto: str | None) -> str | None:
    """`route_color` del GTFS como `#RRGGBB`, o None si no viene o no es un color."""
    return f"#{texto.upper()}" if texto and re.fullmatch(r"[0-9A-Fa-f]{6}", texto) else None


class ZonaMuyGrande(ValueError):
    pass


async def zona(pool: AsyncConnectionPool, z: dict) -> dict | None:
    """Las rutas que pasan por una zona (zona.py) y sus paradas dentro de ella. Las del
    GTFS si alguna la toca; si ninguna, las de OSM, dichas como tales. None si la zona
    no toca nada cargado; `ZonaMuyGrande` si pasa de lo que se calcula (un estado)."""
    async with pool.connection() as conn:
        resuelta = await zona_comun.resolver(conn, z)
        if resuelta is None or not resuelta["estados"]:
            return None
        if motivo := zona_comun.demasiado_grande(resuelta["km2"]):
            raise ZonaMuyGrande(motivo)
        cte, params = zona_comun.partida_sql(z)
        cur = conn.cursor(row_factory=dict_row)
        consulta_rutas = f"""
            WITH {cte}
            SELECT r.feed, r.route_id, r.agencia, r.nombre_corto, r.nombre_largo, r.modo, r.color, r.viajes_dia,
                   r.salidas_pico, r.frecuencia_estimada, f.frecuencia_util,
                   ST_AsGeoJSON(ST_SimplifyPreserveTopology(r.geom, 0.0001), 4) AS gj
            FROM transporte_rutas r JOIN transporte_feeds f USING (feed)
            WHERE r.geom && (SELECT geom FROM z) AND {zona_comun.dentro('r.geom')}
              AND (r.feed = 'osm') = %(osm)s"""
        await cur.execute(consulta_rutas, {**params, "osm": False})
        rutas = await cur.fetchall()
        de_osm = not rutas
        if de_osm:
            await cur.execute(consulta_rutas, {**params, "osm": True})
            rutas = await cur.fetchall()
        # Sin rutas de OSM tampoco: se cita OSM igual, porque ahí se buscó.
        feeds_usados = sorted({r["feed"] for r in rutas}) or ([OSM] if de_osm else [])
        # Las paradas de una ruta repetidas en el mismo punto (feeds que dan una por
        # ruta) se juntan a ~10 m: cuenta la ruta que más pasa.
        await cur.execute(
            f"""WITH {cte}
               SELECT min(p.nombre) AS nombre, round(p.lat::numeric, 4)::float8 AS lat,
                      round(p.lon::numeric, 4)::float8 AS lon, sum(p.rutas) AS rutas,
                      max(p.pasadas_ruta_max) FILTER (WHERE f.frecuencia_util) AS ruta_max
               FROM transporte_paradas p JOIN transporte_feeds f USING (feed)
               WHERE p.geom && (SELECT geom FROM z) AND {zona_comun.dentro('p.geom')}
                 AND p.feed = ANY(%(feeds)s)
               GROUP BY 2, 3""",
            {**params, "feeds": feeds_usados})
        paradas = await cur.fetchall()
        await cur.execute(
            """SELECT feed, titulo, productor, licencia, pagina, via, vigencia_ini::text, vigencia_fin::text,
                      fecha_ref::text, rutas, paradas, avisos, nota, frecuencia_util, actualizado::date::text AS cargado,
                      vigencia_fin < current_date AS vencido
               FROM transporte_feeds WHERE feed = ANY(%(feeds)s) ORDER BY feed""", {"feeds": feeds_usados})
        feeds = await cur.fetchall()

    features = []
    por_clase: Counter = Counter()
    por_modo: Counter = Counter()
    for r in rutas:
        minutos = intervalo_min(r["salidas_pico"]) if r["frecuencia_util"] and not de_osm else None
        clase = clase_intervalo(minutos)
        por_clase[clase] += 1
        por_modo[r["modo"]] += 1
        features.append({"type": "Feature", "geometry": json.loads(r["gj"]), "properties": {
            "f": r["feed"], "id": r["route_id"], "n": r["nombre_corto"], "l": r["nombre_largo"], "a": r["agencia"],
            "modo": r["modo"], "int": minutos, "c": clase, "vd": None if de_osm else r["viajes_dia"],
            "est": r["frecuencia_estimada"], "col": _color(r["color"])}})
    # Masivo encima del camión; dentro de cada modo, lo más frecuente encima.
    orden_modo = {m: i for i, m in enumerate(("autobus", "trolebus", "otro", "ferri", "cable", "funicular",
                                              "tren_ligero", "monorriel", "tren", "metro"))}
    features.sort(key=lambda f: (orden_modo.get(f["properties"]["modo"], 2),
                                 1 / f["properties"]["int"] if f["properties"]["int"] else 0))
    paradas_gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
         "properties": {"n": p["nombre"], "c": clase_intervalo(intervalo_min(p["ruta_max"] or 0)), "r": p["rutas"]}}
        for p in paradas]}
    for f in feeds:
        f["licencia_url"] = LICENCIAS.get(f["licencia"]) if f["licencia"] else None
    return {
        "zona": {"clave": resuelta["clave"], "nombre": resuelta["nombre"]},
        "origen": OSM if de_osm else "gtfs",
        "rutas": {"type": "FeatureCollection", "features": features},
        "paradas": paradas_gj,
        "resumen": {"rutas": len(features), "por_modo": dict(por_modo), "por_clase": dict(por_clase),
                    "paradas": len(paradas)},
        "clases": CLASES,
        "modos": MODOS,
        "frecuente_min": FRECUENTE_MIN,
        "pico": "de 7:00 a 9:00 de un día hábil",
        "feeds": feeds,
    }
