"""Empleo formal: puestos de trabajo y salario de cotización registrados en el IMSS,
por municipio y grupo de actividad, de los datos abiertos de asegurados.

Un archivo por mes (`asg-AAAA-MM-DD.csv`, separado por `|`, latin-1, ~1.5 GB y
~4.6 millones de renglones). Se lee en flujo, se suma por municipio y grupo, y
solo lo sumado llega a la base. Se carga de archivos locales: el portal
(datos.imss.gob.mx) responde 503 a cualquier cliente que no sea un navegador.

El municipio es el del registro patronal, no donde vive ni donde trabaja la
persona; el salario es el base de cotización, con tope de 25 UMA. Las claves de
municipio son del IMSS: `imss_municipios.csv` (scripts/imss/equivalencia.py) las
lleva a INEGI; la Ciudad de México viene sin municipio y lo que no tiene
equivalencia queda en '000', sumado en su estado. Ver docs/fuentes/imss.md.
"""

from __future__ import annotations

import csv
import datetime
import gzip
import io
import re
from functools import cache
from pathlib import Path
from typing import Iterable

from mapo_core.db import get_pool

_AQUI = Path(__file__).parent
_NOMBRE = re.compile(r"asg-(\d{4})-(\d{2})-(\d{2})\.csv(\.gz)?$")
_COLUMNAS = ["cve_entidad", "cve_municipio", "sector_economico_1", "sector_economico_2", "rango_uma",
             "asegurados", "no_trabajadores", "ta", "teu", "tec", "tpu", "tpc", "ta_sal", "masa_sal_ta"]
_METRICAS = ["asegurados", "sin_empleo", "puestos", "permanentes", "eventuales", "puestos_con_salario",
             "masa_salarial", "puestos_rango_tope"]
SIN_MUNICIPIO = "000"

DIVISIONES = {
    "0": "Agricultura, ganadería, silvicultura, pesca y caza",
    "1": "Industrias extractivas",
    "3": "Industrias de transformación",
    "4": "Industria de la construcción",
    "5": "Industria eléctrica y suministro de agua",
    "6": "Comercio",
    "7": "Transportes y comunicaciones",
    "8": "Servicios para empresas, personas y el hogar",
    "9": "Servicios sociales y comunales",
}


class ArchivoInvalido(Exception):
    pass


@cache
def equivalencia() -> dict[str, tuple[str, str]]:
    """clave_imss -> (cve_ent, cve_mun de INEGI)."""
    with open(_AQUI / "imss_municipios.csv", encoding="utf-8", newline="") as f:
        return {r["clave_imss"]: (r["cve_ent"], r["cve_mun"]) for r in csv.DictReader(f)}


@cache
def grupos() -> dict[str, tuple[str, str]]:
    """grupo -> (división, nombre)."""
    with open(_AQUI / "imss_grupos.csv", encoding="utf-8", newline="") as f:
        return {r["grupo"]: (r["division"], r["nombre"]) for r in csv.DictReader(f)}


def periodo_de(ruta: Path) -> datetime.date:
    m = _NOMBRE.search(ruta.name)
    if not m:
        raise ArchivoInvalido(f"{ruta.name}: el nombre no es asg-AAAA-MM-DD.csv(.gz)")
    return datetime.date(int(m[1]), int(m[2]), int(m[3]))


def _lineas(ruta: Path) -> io.TextIOBase:
    crudo = gzip.open(ruta) if ruta.suffix == ".gz" else open(ruta, "rb")
    return io.TextIOWrapper(crudo, encoding="latin-1", newline="")


def leer(lineas: Iterable[str]) -> dict[tuple[str, str, str, str], list[float]]:
    """Renglones del archivo a sumas por (cve_ent, clave_imss, división, grupo),
    en el orden de `_METRICAS`."""
    lector = csv.reader(lineas, delimiter="|")
    cabecera = next(lector, None) or []
    faltan = [c for c in _COLUMNAS if c not in cabecera]
    if faltan:
        raise ArchivoInvalido(f"faltan columnas: {', '.join(faltan)}")
    i = {c: cabecera.index(c) for c in _COLUMNAS}

    suma: dict[tuple[str, str, str, str], list[float]] = {}
    for r in lector:
        if not r:
            continue
        ta = int(r[i["ta"]])
        valores = (
            int(r[i["asegurados"]]),
            int(r[i["no_trabajadores"]]),
            ta,
            int(r[i["tpu"]]) + int(r[i["tpc"]]),
            int(r[i["teu"]]) + int(r[i["tec"]]),
            int(r[i["ta_sal"]]),
            float(r[i["masa_sal_ta"]]),
            ta if r[i["rango_uma"]] == "W25" else 0,
        )
        llave = (r[i["cve_entidad"]].zfill(2), r[i["cve_municipio"]], r[i["sector_economico_1"]],
                 r[i["sector_economico_2"]])
        acumulado = suma.get(llave)
        if acumulado is None:
            suma[llave] = list(valores)
        else:
            for k, v in enumerate(valores):
                acumulado[k] += v
    return suma


def municipio_de(cve_ent: str, clave_imss: str) -> str:
    """cve_mun de INEGI, o '000' si la clave no tiene equivalencia en ese estado."""
    destino = equivalencia().get(clave_imss)
    return destino[1] if destino and destino[0] == cve_ent else SIN_MUNICIPIO


async def cargar(rutas: list[Path]) -> dict[str, dict]:
    """Carga cada mes (reemplaza el que ya hubiera). Regresa, por mes, los
    renglones, los puestos y las claves sin municipio con sus puestos."""
    pool = await get_pool()
    resumen = {}
    for ruta in rutas:
        periodo = periodo_de(ruta)
        with _lineas(ruta) as lineas:
            suma = leer(lineas)
        sin_mun: dict[str, int] = {}
        async with pool.connection() as conn, conn.transaction():
            await conn.execute("DELETE FROM fuente_imss_asegurados WHERE periodo = %s", (periodo,))
            columnas = ["periodo", "cve_ent", "cve_mun", "clave_imss", "division", "grupo", *_METRICAS]
            async with conn.cursor().copy(
                f"COPY fuente_imss_asegurados ({', '.join(columnas)}) FROM STDIN"
            ) as copia:
                for (cve_ent, clave, division, grupo), valores in suma.items():
                    cve_mun = municipio_de(cve_ent, clave)
                    if cve_mun == SIN_MUNICIPIO:
                        sin_mun[f"{cve_ent}:{clave}"] = sin_mun.get(f"{cve_ent}:{clave}", 0) + int(valores[2])
                    await copia.write_row([periodo, cve_ent, cve_mun, clave, division, grupo, *valores])
        resumen[periodo.isoformat()] = {
            "renglones": len(suma),
            "puestos": int(sum(v[2] for v in suma.values())),
            "sin_municipio": dict(sorted(sin_mun.items(), key=lambda x: -x[1])),
        }
    return resumen


def _anio_antes(periodo: datetime.date) -> datetime.date:
    """Último día del mismo mes un año antes (29 de febrero -> 28)."""
    siguiente = datetime.date(periodo.year - 1 + periodo.month // 12, periodo.month % 12 + 1, 1)
    return siguiente - datetime.timedelta(days=1)


def _salario(masa: float, con_salario: int) -> float | None:
    return round(masa / con_salario, 2) if con_salario else None


def _variacion(actual: int, anterior: int | None) -> float | None:
    return round((actual - anterior) / anterior * 100, 2) if anterior else None


async def _periodos(conn, cve_ent: str) -> tuple[datetime.date | None, datetime.date | None]:
    """El mes más reciente del estado y, si está cargado, el mismo mes un año antes."""
    cursor = await conn.execute("SELECT max(periodo) FROM fuente_imss_asegurados WHERE cve_ent = %s", (cve_ent,))
    (ultimo,) = await cursor.fetchone()
    if ultimo is None:
        return None, None
    cursor = await conn.execute(
        "SELECT 1 FROM fuente_imss_asegurados WHERE cve_ent = %s AND periodo = %s LIMIT 1",
        (cve_ent, _anio_antes(ultimo)),
    )
    return ultimo, (_anio_antes(ultimo) if await cursor.fetchone() else None)


async def empleo_municipio(pool, cve_ent: str, cve_mun: str) -> dict | None:
    """Empleo formal del municipio en el mes más reciente: puestos, permanentes y
    eventuales, salario diario promedio, puestos en el rango del tope y reparto por
    división; la variación anual solo si el mismo mes del año anterior está cargado.
    None si el estado no tiene ningún mes."""
    async with pool.connection() as conn:
        periodo, anterior = await _periodos(conn, cve_ent)
        if periodo is None:
            return None
        cursor = await conn.execute(
            """SELECT division, sum(puestos), sum(permanentes), sum(eventuales), sum(puestos_con_salario),
                      sum(masa_salarial), sum(puestos_rango_tope), sum(sin_empleo)
               FROM fuente_imss_asegurados
               WHERE periodo = %s AND cve_ent = %s AND cve_mun = %s
               GROUP BY division""",
            (periodo, cve_ent, cve_mun),
        )
        por_division = await cursor.fetchall()
        cursor = await conn.execute(
            """SELECT coalesce(sum(puestos), 0) FROM fuente_imss_asegurados
               WHERE periodo = %s AND cve_ent = %s AND cve_mun = %s""",
            (periodo, cve_ent, SIN_MUNICIPIO),
        )
        (sin_municipio,) = await cursor.fetchone()
        puestos_antes = None
        if anterior:
            cursor = await conn.execute(
                """SELECT coalesce(sum(puestos), 0) FROM fuente_imss_asegurados
                   WHERE periodo = %s AND cve_ent = %s AND cve_mun = %s""",
                (anterior, cve_ent, cve_mun),
            )
            (puestos_antes,) = await cursor.fetchone()

    total = [sum(int(f[k]) for f in por_division) for k in (1, 2, 3, 4, 6, 7)]
    puestos, permanentes, eventuales, con_salario, tope, sin_empleo = total
    masa = sum(float(f[5]) for f in por_division)
    return {
        "periodo": periodo.isoformat(),
        "puestos": puestos,
        "permanentes": permanentes,
        "eventuales": eventuales,
        "salario_diario": _salario(masa, con_salario),
        "parte_rango_tope": round(tope / con_salario * 100, 2) if con_salario else None,
        "asegurados_sin_empleo": sin_empleo,
        "por_division": sorted(
            (
                {"division": d, "nombre": DIVISIONES.get(d, d), "puestos": int(p),
                 "salario_diario": _salario(float(m), int(cs))}
                for d, p, _pe, _ev, cs, m, _t, _se in por_division
                if d and int(p) > 0
            ),
            key=lambda x: -x["puestos"],
        ),
        "anual": {"periodo": anterior.isoformat(), "puestos": int(puestos_antes),
                  "variacion": _variacion(puestos, int(puestos_antes))} if anterior else None,
        "puestos_estado_sin_municipio": int(sin_municipio),
    }


async def empleo_por_grupos(pool, cve_ent: str, cve_muns: list[str], grupos_imss: list[str]) -> dict | None:
    """Para el buscador: por municipio, los puestos y el salario de los grupos del
    IMSS más cercanos al rubro, contra el total del municipio. None sin datos."""
    async with pool.connection() as conn:
        periodo, anterior = await _periodos(conn, cve_ent)
        if periodo is None:
            return None
        periodos = [periodo, anterior] if anterior else [periodo]
        cursor = await conn.execute(
            """SELECT periodo, cve_mun, grupo = ANY(%(grupos)s), sum(puestos), sum(puestos_con_salario),
                      sum(masa_salarial)
               FROM fuente_imss_asegurados
               WHERE periodo = ANY(%(periodos)s) AND cve_ent = %(e)s AND cve_mun = ANY(%(muns)s)
               GROUP BY 1, 2, 3""",
            {"grupos": grupos_imss, "periodos": periodos, "e": cve_ent, "muns": cve_muns},
        )
        filas = await cursor.fetchall()

    def de(p, mun, del_rubro):
        return next(((int(f[3]), int(f[4]), float(f[5])) for f in filas
                     if f[0] == p and f[1] == mun and f[2] == del_rubro), (0, 0, 0.0))

    municipios = []
    for mun in cve_muns:
        puestos, con_salario, masa = de(periodo, mun, True)
        resto = de(periodo, mun, False)[0]
        antes = de(anterior, mun, True)[0] if anterior else None
        municipios.append({
            "cve_mun": mun,
            "puestos_rubro": puestos,
            "puestos_total": puestos + resto,
            "salario_diario_rubro": _salario(masa, con_salario),
            "variacion_anual_rubro": _variacion(puestos, antes) if anterior else None,
        })
    return {
        "periodo": periodo.isoformat(),
        "periodo_anual": anterior.isoformat() if anterior else None,
        "grupos": [{"grupo": g, "nombre": grupos()[g][1]} for g in grupos_imss if g in grupos()],
        "municipios": municipios,
    }
