"""Cruce de una capa propia con fuentes públicas, por zona.

La capa llega en la petición y no se lee de la base: quién puede ver qué capa
se decide en `Mapo.Capas`, y así `mapo_core` nunca toca datos de un equipo.

Cada columna del resultado es una cifra por separado y dice cómo se calculó en
`metodo`. Nada se pondera ni se combina en un puntaje (RNF5). Una zona sin
renglones lleva `renglones: 0` y sus agregados en `null`: una suma de nada no
es cero, es que el archivo no trae dato ahí.
"""

from __future__ import annotations

from statistics import fmean, median

from psycopg_pool import AsyncConnectionPool

from mapo_core import consultas, datos_propios, rubros, zonas
from mapo_core.osrm_client import OSRMClient

_TABLAS = {"municipio": "municipios", "ageb": "agebs"}

_AGREGACIONES = {"suma": sum, "promedio": fmean, "mediana": median}

# Todos los negocios de DENUE, sin filtrar por rubro.
TODOS = "todos"


class CruceInvalido(Exception):
    pass


async def _zonas_de_puntos(pool: AsyncConnectionPool, tabla: str, filas: list[dict]) -> list[str | None]:
    """La zona de cada punto, en el orden de `filas`. El LIMIT 1 importa: un
    punto justo en la frontera de dos zonas tocaría las dos y contaría doble."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            f"""SELECT z.cvegeo
                FROM unnest(%(lats)s::float8[], %(lons)s::float8[]) WITH ORDINALITY p(lat, lon, i)
                LEFT JOIN LATERAL (
                    SELECT t.cvegeo FROM {tabla} t
                    WHERE ST_Intersects(t.geom, ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326))
                    ORDER BY t.cvegeo LIMIT 1
                ) z ON true
                ORDER BY p.i""",
            {"lats": [f["lat"] for f in filas], "lons": [f["lon"] for f in filas]},
        )
        return [zona for (zona,) in await cursor.fetchall()]


async def _universo(pool: AsyncConnectionPool, nivel: str, tocadas: set[str]) -> dict[str, dict]:
    """Las zonas del resultado: todas las del nivel de arriba que la capa toca,
    no solo las que traen renglones. Sin esto, no se ve dónde falta la capa."""
    async with pool.connection() as conn:
        if nivel == "ageb":
            cursor = await conn.execute(
                """SELECT a.cvegeo, m.nombre, a.cve_ageb
                   FROM agebs a
                   JOIN municipios m ON m.cve_ent = a.cve_ent AND m.cve_mun = a.cve_mun
                   WHERE a.cve_ent || a.cve_mun = ANY(%(claves)s) ORDER BY a.cvegeo""",
                {"claves": sorted({c[:5] for c in tocadas})},
            )
            return {c: {"municipio": nombre, "ageb": ageb} for c, nombre, ageb in await cursor.fetchall()}

        cursor = await conn.execute(
            "SELECT cvegeo, nombre FROM municipios WHERE cve_ent = ANY(%(claves)s) ORDER BY cvegeo",
            {"claves": sorted({c[:2] for c in tocadas})},
        )
        return {c: {"municipio": nombre} for c, nombre in await cursor.fetchall()}


async def _censo(pool: AsyncConnectionPool, nivel: str, claves: list[str], columnas: list[str]) -> dict[str, tuple]:
    """Valores tal como los publica INEGI. A nivel municipio se lee su renglón
    propio: sumar sus AGEB dejaría fuera a la población rural."""
    llave = "cvegeo" if nivel == "ageb" else "cve_ent || cve_mun"
    async with pool.connection() as conn:
        cursor = await conn.execute(
            f"""SELECT {llave}, {", ".join(columnas)} FROM fuente_censo_poblacion
                WHERE nivel = %(nivel)s AND {llave} = ANY(%(claves)s)""",
            {"nivel": nivel, "claves": claves},
        )
        return {fila[0]: fila[1:] for fila in await cursor.fetchall()}


async def _negocios(
    pool: AsyncConnectionPool, nivel: str, claves: list[str], clases: list[str] | None
) -> dict[str, int]:
    """Negocios por zona, con la clave que trae DENUE. El AGEB se compara por
    municipio y AGEB porque DENUE no trae la localidad de la CVEGEO."""
    filtro = "" if clases is None else "AND clase_actividad = ANY(%(clases)s)"
    async with pool.connection() as conn:
        cursor = await conn.execute(
            f"""SELECT cve_ent || cve_mun || coalesce(cve_ageb, ''), count(*)
                FROM fuente_denue_negocios
                WHERE cve_ent || cve_mun = ANY(%(municipios)s) {filtro}
                GROUP BY 1""",
            {"municipios": sorted({c[:5] for c in claves}), "clases": clases},
        )
        conteos = dict(await cursor.fetchall())

    if nivel == "ageb":
        return {c: conteos.get(c[:5] + c[9:], 0) for c in claves}

    por_municipio: dict[str, int] = {}
    for clave, conteo in conteos.items():
        por_municipio[clave[:5]] = por_municipio.get(clave[:5], 0) + conteo
    return {c: por_municipio.get(c, 0) for c in claves}


async def _minutos(
    pool: AsyncConnectionPool, osrm: OSRMClient, claves: list[str], clases: list[str]
) -> tuple[dict[str, float | None], str]:
    """Minutos de cada AGEB al negocio del rubro más cercano, con la misma
    matriz de las zonas candidatas. Un estado sin negocios deja `None`."""
    if len(claves) > zonas.MAX_AGEBS:
        raise CruceInvalido(
            f"Son {len(claves):,} AGEB: los minutos llegan a {zonas.MAX_AGEBS:,}. Quítalos o usa una capa más chica."
        )

    por_ageb: dict[str, float | None] = {}
    metodos = set()
    for cve_ent in sorted({c[:2] for c in claves}):
        cve_muns = sorted({c[2:5] for c in claves if c[:2] == cve_ent})
        agebs = await consultas.puntos_de_agebs(pool, cve_ent, cve_muns)
        negocios = await consultas.ubicaciones_de_clases(pool, cve_ent, clases)
        if agebs and negocios:
            minutos, metodo = await zonas.minutos_a_negocios(osrm, agebs, negocios)
            por_ageb |= minutos
            metodos.add(metodo)

    # Si un estado cayó a línea recta, se dice aunque otro haya salido por calle.
    return por_ageb, "linea_recta_aproximada" if "linea_recta_aproximada" in metodos else "carretera_real"


def _agregar(valores: list[float], agregacion: str) -> float | None:
    if not valores:
        return None
    resultado = round(float(_AGREGACIONES[agregacion](valores)), 6)
    return int(resultado) if resultado.is_integer() else resultado


def _validar(tipo: str, nivel: str, filas: list[dict], censo: list[str], denue: str | None, minutos: bool) -> None:
    if tipo == "municipio" and nivel == "ageb":
        raise CruceInvalido("Una capa por municipio no se puede partir en AGEB.")
    if tipo != "puntos" and any(not f.get("clave") for f in filas):
        raise CruceInvalido("Hay renglones sin clave.")
    if tipo == "puntos" and any(f.get("lat") is None or f.get("lon") is None for f in filas):
        raise CruceInvalido("Hay renglones sin coordenadas.")
    if invalidos := set(censo) - consultas.INDICADORES_CHOROPLETH:
        raise CruceInvalido(f"Indicador desconocido: {sorted(invalidos)[0]}.")
    if denue not in (None, TODOS) and denue not in rubros.rubros():
        raise CruceInvalido("Ese rubro no existe.")
    if minutos and (nivel != "ageb" or denue in (None, TODOS)):
        raise CruceInvalido("Los minutos piden nivel AGEB y un rubro.")


async def calcular(
    pool: AsyncConnectionPool,
    osrm: OSRMClient,
    *,
    tipo: str,
    nivel: str,
    filas: list[dict],
    agregaciones: dict[str, str],
    censo: list[str],
    denue: str | None,
    minutos: bool,
) -> dict:
    _validar(tipo, nivel, filas, censo, denue, minutos)

    if tipo == "puntos":
        claves = await _zonas_de_puntos(pool, _TABLAS[nivel], filas)
    else:
        claves = [f["clave"][:5] if nivel == "municipio" else f["clave"] for f in filas]

    tocadas = {c for c in claves if c}
    universo = await _universo(pool, nivel, tocadas) if tocadas else {}
    if not universo:
        raise CruceInvalido("Ningún renglón cae en una zona del marco cargado.")
    if len(universo) > datos_propios.MAX_POLIGONOS:
        raise CruceInvalido(
            f"Son {len(universo):,} zonas y el tope es {datos_propios.MAX_POLIGONOS:,}. Elige municipios en vez de AGEB."
        )

    grupos: dict[str, list[dict]] = {c: [] for c in universo}
    sin_zona = 0
    for clave, fila in zip(claves, filas):
        if clave in grupos:
            grupos[clave].append(fila["valores"])
        else:
            sin_zona += 1

    resultado = {clave: {**fijos, "renglones": len(grupos[clave])} for clave, fijos in universo.items()}
    fijas = list(next(iter(universo.values())))
    numericas = ["renglones"]
    metodo = ["renglones: cuántos renglones de la capa caen en cada zona. Cero dice que la capa no trae nada ahí."]
    avisos: list[str] = []

    for columna, agregacion in agregaciones.items():
        nombre = f"{columna}_{agregacion}"
        for clave, valores in grupos.items():
            presentes = [v[columna] for v in valores if v.get(columna) is not None]
            resultado[clave][nombre] = _agregar(presentes, agregacion)
        numericas.append(nombre)
        metodo.append(f"{nombre}: {agregacion} de {columna} en la zona. Las celdas vacías no cuentan.")

    ordenadas = list(universo)
    if censo:
        valores_censo = await _censo(pool, nivel, ordenadas, censo)
        for i, columna in enumerate(censo):
            for clave in ordenadas:
                fila = valores_censo.get(clave)
                resultado[clave][columna] = fila[i] if fila else None
            faltan = sum(resultado[c][columna] is None for c in ordenadas)
            if faltan:
                avisos.append(f"{columna}: {faltan:,} zonas sin dato en el censo (INEGI reserva las muy chicas).")
        numericas += censo
        metodo.append(f"{', '.join(censo)}: Censo 2020 de INEGI, tal como se publica por {"AGEB" if nivel == "ageb" else "municipio"}.")

    clases = None
    if denue:
        clases = None if denue == TODOS else rubros.clases_de(rubro=denue)
        nombre = "negocios_denue" if clases is None else f"negocios_{denue}"
        conteos = await _negocios(pool, nivel, ordenadas, clases)
        for clave in ordenadas:
            resultado[clave][nombre] = conteos[clave]
        numericas.append(nombre)
        cuales = "todos los negocios" if clases is None else f"negocios del rubro {rubros.rubros()[denue].nombre}"
        metodo.append(f"{nombre}: {cuales} de DENUE en la zona, según la clave que trae cada negocio.")

    if minutos:
        nombre = f"minutos_{denue}"
        por_ageb, como = await _minutos(pool, osrm, ordenadas, clases)
        for clave in ordenadas:
            resultado[clave][nombre] = por_ageb.get(clave)
        numericas.append(nombre)
        if como == "carretera_real":
            metodo.append(f"{nombre}: minutos en auto, por calle, de un punto dentro del AGEB al negocio más cercano.")
        else:
            metodo.append(f"{nombre}: línea recta a velocidad asumida, porque OSRM no respondió. No es tiempo por calle.")
            avisos.append("OSRM no respondió: los minutos son línea recta, no tiempo real por calle.")

    if sin_zona:
        marco = "AGEB urbano" if nivel == "ageb" else "municipio"
        avisos.append(f"{sin_zona:,} renglones no cayeron en ningún {marco} del marco cargado y no se contaron.")

    orden = sorted(resultado, key=lambda c: (-resultado[c]["renglones"], c))
    return {
        "nivel": nivel,
        "columnas": fijas + numericas,
        "numericas": numericas,
        "filas": [{"clave": c, "datos": resultado[c]} for c in orden],
        "renglones": len(filas) - sin_zona,
        "sin_zona": sin_zona,
        "zonas_con_renglones": sum(1 for c in resultado if resultado[c]["renglones"]),
        "metodo": metodo,
        "avisos": avisos,
    }
