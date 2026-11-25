"""Zonas que se parecen (sesión 29h). Ver docs/producto/perfil.md.

Nunca un puntaje: cada variable dice por su cuenta si la otra zona cae en la banda de
la de referencia, y las zonas se ordenan por cuántas variables caen. La banda es una
fracción del rango intercuartil de esa variable entre las zonas comparadas (en
logaritmo las que abarcan órdenes de magnitud), y se da en sus unidades. Nada se pesa
ni se promedia. Un dato que falta no cuenta ni como parecido ni como distinto.

Un municipio se compara con municipios; una colonia, un CP o un dibujo, con colonias.
Las variables de cada municipio y colonia se calculan una vez por estado
(`cli similares`): son decenas de miles de cruces de AGEB con colonias.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np

from mapo_core import perfil as perfil_zona
from mapo_core import zona as zona_comun
from mapo_core.perfil import Censo, datos_sql, filas_de, params_muns, por_clave

MAX_RESULTADOS = 12
# Con menos gente, el reparto por área falla por 43 % o más (perfil.ERROR_REPARTO).
MIN_POBLACION_COLONIA = 500
MIN_COMPARADAS = 20
MARGENES = {"muy_cerca": 0.25, "cerca": 0.5, "holgado": 1.0}
DONDE = ("todo", "mismo", "otros")
ANIOS_DELITOS = 3

AREAS = {
    "poblacion": "Población",
    "vivienda": "Vivienda",
    "economia": "Negocios",
    "empleo": "Empleo y salud",
    "servicios": "Servicios a pie",
    "seguridad": "Seguridad",
    "hacienda": "Hacienda",
}
NIVELES = {"municipio": ("municipio", "municipios"), "colonia": ("colonia", "colonias")}


class ConsultaInvalida(ValueError):
    pass


@dataclass(frozen=True)
class Variable:
    clave: str
    area: str
    etiqueta: str
    unidad: str
    decimales: int = 1
    log: bool = False
    solo_municipio: bool = False
    # (arriba, abajo) del censo, en porcentaje; las demás se calculan aparte.
    razon: tuple[str, str] | None = None


VARIABLES = (
    Variable("poblacion", "poblacion", "Habitantes", "personas", 0, log=True, solo_municipio=True),
    Variable("densidad", "poblacion", "Densidad", "hab/km²", 0, log=True),
    Variable("menores15", "poblacion", "Menores de 15 años", "%", razon=("POB0_14", "POBTOT")),
    Variable("mayores60", "poblacion", "De 60 años o más", "%", razon=("P_60YMAS", "POBTOT")),
    Variable("escolaridad", "poblacion", "Escolaridad", "años", 1),
    Variable("nacidos_fuera", "poblacion", "Nacidos en otro estado", "%", razon=("PNACOE", "POBTOT")),
    Variable("ocupantes", "vivienda", "Personas por vivienda", "", 2),
    Variable("deshabitadas", "vivienda", "Viviendas deshabitadas", "%", razon=("VIVPAR_DES", "TVIVPAR")),
    Variable("un_dormitorio", "vivienda", "Con un solo dormitorio", "%", razon=("VPH_1DOR", "TVIVPARHAB")),
    Variable("internet", "vivienda", "Con internet", "%", razon=("VPH_INTER", "TVIVPARHAB")),
    Variable("computadora", "vivienda", "Con computadora", "%", razon=("VPH_PC", "TVIVPARHAB")),
    Variable("automovil", "vivienda", "Con automóvil", "%", razon=("VPH_AUTOM", "TVIVPARHAB")),
    Variable("negocios_mil", "economia", "Negocios por mil habitantes", "", 1, log=True),
    Variable("comercio", "economia", "Comercio al por menor", "% de los negocios"),
    Variable("comida", "economia", "Alojamiento y comida", "% de los negocios"),
    Variable("manufactura", "economia", "Manufactura", "% de los negocios"),
    Variable("personal_mil", "economia", "Personal ocupado por mil hab.", "", 0, log=True, solo_municipio=True),
    Variable("valor_persona", "economia", "Valor agregado por trabajador", "miles de pesos", 0, log=True,
             solo_municipio=True),
    Variable("activa", "empleo", "Económicamente activa", "% de 12 años o más", razon=("PEA", "P_12YMAS")),
    Variable("activa_mujeres", "empleo", "Mujeres activas", "% de 12 años o más", razon=("PEA_F", "P_12YMAS_F")),
    Variable("imss", "empleo", "Afiliación al IMSS", "%", razon=("PDER_IMSS", "POBTOT")),
    Variable("sin_salud", "empleo", "Sin servicios de salud", "%", razon=("PSINDER", "POBTOT")),
    Variable("puestos_mil", "empleo", "Puestos del IMSS por mil hab.", "", 0, log=True, solo_municipio=True),
    Variable("salario", "empleo", "Salario diario del IMSS", "pesos", 0, solo_municipio=True),
    *(Variable(f"a_pie_{s}", "servicios", titulo, "% a 15 min o menos")
      for s, titulo in (("centro_salud", "Centro de salud"), ("hospital_publico", "Hospital público"),
                        ("primaria_publica", "Primaria pública"), ("secundaria_publica", "Secundaria pública"),
                        ("media_superior_publica", "Bachillerato público"), ("supermercado", "Supermercado"),
                        ("parada_transporte", "Parada de transporte"))),
    Variable("robo_mil", "seguridad", "Robo por mil hab.", "al año", 1, solo_municipio=True),
    Variable("lesiones_mil", "seguridad", "Lesiones por mil hab.", "al año", 1, solo_municipio=True),
    Variable("familiar_mil", "seguridad", "Violencia familiar por mil hab.", "al año", 1, solo_municipio=True),
    Variable("homicidio_100mil", "seguridad", "Homicidio por 100 mil hab.", "al año", 1, solo_municipio=True),
    Variable("propios", "hacienda", "Ingresos que recauda", "%", solo_municipio=True),
    Variable("ingresos_hab", "hacienda", "Ingresos por habitante", "pesos", 0, log=True, solo_municipio=True),
    Variable("predial_hab", "hacienda", "Predial por habitante", "pesos", 0, log=True, solo_municipio=True),
)
DELITOS = {"robo_mil": ("Robo", 1_000), "lesiones_mil": ("Lesiones", 1_000),
           "familiar_mil": ("Violencia familiar", 1_000), "homicidio_100mil": ("Homicidio", 100_000)}


def de_nivel(nivel: str) -> tuple[Variable, ...]:
    return tuple(v for v in VARIABLES if nivel == "municipio" or not v.solo_municipio)


# ---------------------------------------------------------------- cálculo

def valores(censo: Censo, km2: float, sectores: dict[str, int] | None, servicios: list[dict],
            municipal: dict | None = None) -> dict[str, float | None]:
    """Las variables de una zona. `sectores` es {sector: negocios} con "total", o None si
    su estado no tiene DENUE; `municipal`, lo que solo existe por municipio."""
    pob = censo.total("POBTOT")
    salida: dict[str, float | None] = {
        v.clave: censo.razon(*v.razon) for v in VARIABLES if v.razon}
    salida["densidad"] = pob / km2 if pob and km2 else None
    salida["escolaridad"] = censo.promedio("GRAPROES", "P_15YMAS")
    salida["ocupantes"] = censo.razon("OCUPVIVPAR", "TVIVPARHAB", 1)
    total = (sectores or {}).get("total", 0)
    salida["negocios_mil"] = 1000 * total / pob if sectores is not None and pob else None
    for clave, nombre in (("comercio", "Comercio al por menor"), ("comida", "Alojamiento y comida"),
                          ("manufactura", "Manufactura")):
        # Con un puñado de negocios, el porcentaje no dice nada de la zona.
        salida[clave] = 100 * sectores.get(nombre, 0) / total if sectores and total >= 20 else None
    cerca = {s["clave"]: s.get("cerca_pct") for s in servicios}
    for v in VARIABLES:
        if v.area == "servicios":
            salida[v.clave] = cerca.get(v.clave.removeprefix("a_pie_"))
    if municipal is not None:
        salida["poblacion"] = pob
        por_hab = lambda x, n=1: n * x / pob if x is not None and pob else None  # noqa: E731
        salida["personal_mil"] = por_hab(municipal.get("personal"), 1000)
        salida["valor_persona"] = (1000 * municipal["vacb"] / municipal["personal"]
                                   if municipal.get("vacb") is not None and municipal.get("personal") else None)
        salida["puestos_mil"] = por_hab(municipal.get("puestos"), 1000)
        salida["salario"] = municipal.get("salario")
        for clave, (_tipo, por) in DELITOS.items():
            salida[clave] = por_hab(municipal.get(clave), por)
        salida["propios"] = municipal.get("propios")
        salida["ingresos_hab"] = por_hab(municipal.get("ingresos"))
        salida["predial_hab"] = por_hab(municipal.get("predial"))
    return {k: (round(v, 4) if v is not None and math.isfinite(v) else None) for k, v in salida.items()}


async def _municipales(conn, muns: list[str]) -> dict[str, dict]:
    """Lo que solo existe por municipio, de cada uno."""
    p = params_muns(muns)
    salida: dict[str, dict] = {m: {} for m in muns}
    for f in await filas_de(conn, f"""SELECT cve_ent || cve_mun AS mun, personal, vacb FROM fuente_ce2024_municipal
                                      WHERE sector = 'total' AND {por_clave()}""", p):
        salida[f["mun"]] |= {"personal": f["personal"], "vacb": f["vacb"]}
    for f in await filas_de(conn, f"""
            SELECT cve_ent || cve_mun AS mun, sum(puestos)::float AS puestos, sum(masa_salarial)::float AS masa,
                   sum(puestos_con_salario)::float AS con_salario
            FROM fuente_imss_asegurados i WHERE {por_clave('i')}
              AND periodo = (SELECT max(periodo) FROM fuente_imss_asegurados x WHERE x.cve_ent = i.cve_ent)
            GROUP BY 1""", p):
        salida[f["mun"]] |= {"puestos": f["puestos"],
                             "salario": f["masa"] / f["con_salario"] if f["con_salario"] else None}
    anios = [f["anio"] for f in await filas_de(conn, f"""
        SELECT anio FROM fuente_sesnsp_delitos_municipal WHERE {por_clave()}
        GROUP BY anio HAVING count(DISTINCT mes) = 12 ORDER BY anio DESC LIMIT {ANIOS_DELITOS}""",
        # Los meses publicados son los mismos para todos: basta un municipio por estado.
        params_muns([next(m for m in muns if m[:2] == e) for e in p["ents"]]))]
    tipos = {t: clave for clave, (t, _) in DELITOS.items()}
    if anios:
        for m in muns:
            salida[m] |= {clave: 0.0 for clave in DELITOS}
        for f in await filas_de(conn, f"""
                SELECT cve_ent || cve_mun AS mun, tipo_delito AS tipo, sum(cantidad)::float / %(n)s AS al_anio
                FROM fuente_sesnsp_delitos_municipal
                WHERE {por_clave()} AND anio = ANY(%(anios)s) AND tipo_delito = ANY(%(tipos)s) GROUP BY 1, 2""",
                {**p, "anios": anios, "n": len(anios), "tipos": list(tipos)}):
            salida[f["mun"]][tipos[f["tipo"]]] = f["al_anio"]
    for mun, h in (await perfil_zona.haciendas(conn, muns)).items():
        salida[mun] |= {"propios": h["propios_pct"], "ingresos": h["total"], "predial": h["predial"]}
    return salida


def _sectores_por_zona(filas: list[dict]) -> dict[str, dict[str, int]]:
    salida: dict[str, dict[str, int]] = {}
    for f in filas:
        d = salida.setdefault(f["zona"], {"total": 0})
        d["total"] += f["n"]
        if nombre := perfil_zona.SECTORES.get(f["sector"] or ""):
            d[nombre] = d.get(nombre, 0) + f["n"]
    return salida


async def cargar_estado(pool, cve_ent: str) -> dict:
    """Calcula y guarda (reemplaza) las variables de los municipios y las colonias de un
    estado. Necesita su censo, sus AGEB, DENUE y accesibilidad ya cargados; lo que falte
    queda null."""
    async with pool.connection() as conn:
        municipios = await filas_de(conn, """
            SELECT m.cvegeo, m.nombre, e.nombre AS estado, (ST_Area(m.geom::geography) / 1e6)::float AS km2
            FROM municipios m LEFT JOIN entidades e USING (cve_ent)
            WHERE m.cve_ent = %(e)s AND m.geom IS NOT NULL ORDER BY 1""", {"e": cve_ent})
        if not municipios:
            raise ConsultaInvalida(f"el estado {cve_ent} no tiene municipios cargados")
        muns = [m["cvegeo"] for m in municipios]
        con_denue = bool(await filas_de(conn, "SELECT 1 AS x FROM fuente_denue_negocios WHERE cve_ent = %(e)s LIMIT 1",
                                        {"e": cve_ent}))
        lugares = {u["clave"]: u for u in await filas_de(conn, f"""
            SELECT c.cvegeo AS clave, 'ageb' AS tipo, {datos_sql('c.datos_json')} AS d
            FROM fuente_censo_poblacion c WHERE c.nivel = 'ageb' AND c.cve_ent = %(e)s
            UNION ALL
            SELECT l.cvegeo, 'localidad', {datos_sql('l.datos')} FROM localidades l
            WHERE l.cve_ent = %(e)s AND coalesce(l.pobtot, 1) > 0
              AND NOT EXISTS (SELECT 1 FROM agebs a WHERE a.geom && l.geom AND ST_Covers(a.geom, l.geom))""",
            {"e": cve_ent})}
        minutos = await perfil_zona.minutos_de(conn, None, muns)

        # Municipios
        censos = {u["clave"]: u["d"] for u in await perfil_zona.lugares_enteros(conn, muns)}
        municipales = await _municipales(conn, muns)
        negocios = _sectores_por_zona(await filas_de(conn, """
            SELECT cve_ent || cve_mun AS zona, substr(clee, 6, 2) AS sector, count(*)::int AS n
            FROM fuente_denue_negocios WHERE cve_ent = %(e)s GROUP BY 1, 2""", {"e": cve_ent}))
        por_mun: dict[str, list[dict]] = {}
        for u in lugares.values():
            por_mun.setdefault(u["clave"][:5], []).append({**u, "peso": 1.0})
        filas = []
        for m in municipios:
            if m["cvegeo"] not in censos:
                continue
            censo = Censo([(censos[m["cvegeo"]], 1.0)])
            v = valores(censo, m["km2"], negocios.get(m["cvegeo"], {"total": 0}) if con_denue else None,
                        perfil_zona.servicios(por_mun.get(m["cvegeo"], []), minutos), municipales[m["cvegeo"]])
            filas.append(("municipio", f"mun:{m['cvegeo']}", m["nombre"], m["estado"], cve_ent, m["cvegeo"],
                          censo.total("POBTOT"), json.dumps(v)))

        # Colonias
        colonias = await filas_de(conn, """
            SELECT cve_col, nombre, clasif, cve_ent || cve_mun AS mun, nom_mun,
                   (ST_Area(geom::geography) / 1e6)::float AS km2
            FROM colonias WHERE cve_ent = %(e)s AND geom IS NOT NULL""", {"e": cve_ent})
        pesos: dict[str, list[tuple[str, float]]] = {}
        for f in await filas_de(conn, """
                SELECT c.cve_col AS zona, a.cvegeo AS clave,
                       CASE WHEN ST_Covers(c.geom, a.geom) THEN 1.0
                            ELSE least(1.0, ST_Area(ST_Intersection(ST_MakeValid(a.geom), c.geom))
                                            / nullif(ST_Area(a.geom), 0)) END::float AS peso
                FROM colonias c JOIN agebs a ON a.geom && c.geom AND ST_Intersects(a.geom, c.geom)
                WHERE c.cve_ent = %(e)s
                UNION ALL
                SELECT c.cve_col, l.cvegeo, 1.0::float FROM colonias c JOIN localidades l ON ST_Covers(c.geom, l.geom)
                WHERE c.cve_ent = %(e)s
                  AND NOT EXISTS (SELECT 1 FROM agebs a WHERE a.geom && l.geom AND ST_Covers(a.geom, l.geom))""",
                {"e": cve_ent}):
            pesos.setdefault(f["zona"], []).append((f["clave"], f["peso"]))
        negocios = _sectores_por_zona(await filas_de(conn, """
            WITH n AS MATERIALIZED (SELECT ST_SetSRID(ST_MakePoint(lon, lat), 4326) AS p, substr(clee, 6, 2) AS sector
                                    FROM fuente_denue_negocios WHERE cve_ent = %(e)s AND lat IS NOT NULL)
            SELECT c.cve_col AS zona, n.sector, count(*)::int AS n
            FROM n JOIN colonias c ON c.geom && n.p AND ST_Intersects(c.geom, n.p)
            WHERE c.cve_ent = %(e)s GROUP BY 1, 2""", {"e": cve_ent}))
        sin_gente = 0
        for c in colonias:
            suyos = [{**lugares[k], "peso": w} for k, w in pesos.get(c["cve_col"], []) if k in lugares]
            censo = Censo([(u["d"], u["peso"]) for u in suyos])
            pob = censo.total("POBTOT")
            if not pob:
                sin_gente += 1
                continue
            v = valores(censo, c["km2"], negocios.get(c["cve_col"], {"total": 0}) if con_denue else None,
                        perfil_zona.servicios(suyos, minutos))
            filas.append(("colonia", f"col:{c['cve_col']}", c["nombre"],
                          f"{zona_comun._clasif(c['clasif'])} · {c['nom_mun']}", cve_ent, c["mun"], pob, json.dumps(v)))

        async with conn.transaction():
            await conn.execute("DELETE FROM similares_zonas WHERE cve_ent = %s", (cve_ent,))
            async with conn.cursor() as cur:
                async with cur.copy("COPY similares_zonas (nivel, clave, nombre, detalle, cve_ent, mun, pobtot,"
                                    " valores) FROM STDIN") as copia:
                    for f in filas:
                        await copia.write_row(f)
    return {"cve_ent": cve_ent, "municipios": sum(f[0] == "municipio" for f in filas),
            "colonias": sum(f[0] == "colonia" for f in filas), "colonias_sin_gente": sin_gente,
            "colonias_comparables": sum(f[0] == "colonia" and f[6] >= MIN_POBLACION_COLONIA for f in filas)}


# ---------------------------------------------------------------- consulta

def _escala(v: Variable, x: float) -> float:
    # Un cero en una variable logarítmica (nadie, ningún negocio) queda en el piso.
    return math.log(max(x, 0.01)) if v.log else x


def banda(v: Variable, ref: float, comparadas: list[float], fraccion: float) -> dict:
    """La banda de una variable alrededor de la referencia, en sus unidades, y su reparto
    entre las zonas comparadas."""
    xs = np.array([_escala(v, x) for x in comparadas])
    p10, p25, p50, p75, p90 = np.percentile(xs, [10, 25, 50, 75, 90])
    medio = fraccion * (p75 - p25)
    r = _escala(v, ref)
    vuelta = (lambda y: math.exp(y)) if v.log else (lambda y: y)
    # Ninguna variable baja de cero, y un porcentaje no pasa de 100.
    tope = 100.0 if v.unidad.startswith("%") else math.inf
    return {"bajo": max(0.0, float(vuelta(r - medio))), "alto": min(tope, float(vuelta(r + medio))),
            "medio": float(medio),
            "p10": float(vuelta(p10)), "p50": float(vuelta(p50)), "p90": float(vuelta(p90)),
            "min": min(comparadas), "max": max(comparadas), "comparadas": len(comparadas)}


def comparar(v: Variable, ref: float | None, otro: float | None, b: dict | None) -> tuple[str, float]:
    """("parecida" | "mayor" | "menor" | "sin_dato", distancia en medias bandas). La
    distancia solo desempata el orden: no sale a la vista."""
    if ref is None or otro is None or b is None:
        return "sin_dato", 0.0
    d = _escala(v, otro) - _escala(v, ref)
    # Sin dispersión (todas iguales) solo es parecido lo idéntico.
    if abs(d) <= b["medio"] + 1e-9:
        return "parecida", abs(d) / b["medio"] if b["medio"] else 0.0
    return ("mayor" if d > 0 else "menor"), abs(d) / b["medio"] if b["medio"] else float("inf")


def nivel_de(z: dict) -> tuple[str | None, str | None]:
    """(nivel con que se compara, por qué no hay)."""
    if z["tipo"] == "municipios":
        if len(z["cvegeos"]) == 1:
            return "municipio", None
        return None, "Los similares se buscan para un solo municipio, una colonia, un código postal o un dibujo."
    if z["tipo"] in ("estado", "metropoli"):
        otra = "otro estado" if z["tipo"] == "estado" else "otra metrópoli"
        return None, f"No hay {otra} con todas sus fuentes cargadas con qué comparar."
    return "colonia", None


def _validar(areas: list[str], margen: str, donde: str) -> list[str]:
    if margen not in MARGENES:
        raise ConsultaInvalida(f"margen desconocido: {margen!r}")
    if donde not in DONDE:
        raise ConsultaInvalida(f"donde desconocido: {donde!r}")
    if malas := [a for a in areas if a not in AREAS]:
        raise ConsultaInvalida(f"áreas desconocidas: {', '.join(malas)}")
    return list(dict.fromkeys(areas))


async def _referencia(conn, z: dict, nivel: str) -> dict | None:
    """La zona de referencia: de la tabla si está, o calculada igual (un dibujo, un CP)."""
    clave = zona_comun.clave(z)
    filas = await filas_de(conn, "SELECT nombre, mun, pobtot, valores FROM similares_zonas"
                                 " WHERE nivel = %(n)s AND clave = %(c)s", {"n": nivel, "c": clave})
    if filas:
        return {**filas[0], "clave": clave}
    b = await perfil_zona.base(conn, z)
    if b is None:
        return None
    r = b["resuelta"]
    if nivel == "municipio":
        # Está en el marco pero no en la tabla: falta correr `cli similares` en su estado.
        return {"clave": clave, "nombre": r["nombre"], "mun": b["muns"][0], "pobtot": None, "valores": {}}
    denue = await perfil_zona.negocios(conn, z, b["muns"], False)
    sectores = None if denue is None else {"total": denue["total_negocios"], **dict(denue["sectores"])}
    return {"clave": clave, "nombre": r["nombre"], "mun": b["muns"][0], "pobtot": b["censo"].total("POBTOT"),
            "valores": valores(b["censo"], b["km2"], sectores, b["servicios"])}


async def buscar(pool, z: dict, *, areas: list[str], margen: str = "cerca", donde: str = "todo") -> dict | None:
    areas = _validar(areas, margen, donde)
    nivel, motivo = nivel_de(z)
    if nivel is None:
        return {"motivo": motivo, "resultados": []}
    async with pool.connection() as conn:
        ref = await _referencia(conn, z, nivel)
        if ref is None:
            return None
        todas = await filas_de(conn, """
            SELECT clave, nombre, detalle, cve_ent, mun, pobtot, valores, actualizado::date::text AS calculado
            FROM similares_zonas WHERE nivel = %(n)s AND pobtot >= %(min)s""",
            {"n": nivel, "min": MIN_POBLACION_COLONIA if nivel == "colonia" else 1})
        estados = [f["nombre"] for f in await filas_de(
            conn, "SELECT nombre FROM entidades WHERE cve_ent = ANY(%(e)s) ORDER BY nombre",
            {"e": sorted({f["cve_ent"] for f in todas})})]
    otras = [f for f in todas if f["clave"] != ref["clave"]]
    if len(otras) < MIN_COMPARADAS or not ref["valores"]:
        return {"motivo": f"Todavía no hay {NIVELES[nivel][1]} con qué comparar en este estado.", "resultados": []}

    variables = [v for v in de_nivel(nivel) if not areas or v.area in areas]
    if not variables:
        return {"motivo": f"Esas áreas no existen por {NIVELES[nivel][0]}.", "resultados": []}
    # La banda sale de todas las del nivel: no cambia con `donde`.
    bandas: dict[str, dict | None] = {}
    for v in variables:
        xs = [x for f in todas if (x := f["valores"].get(v.clave)) is not None]
        r = ref["valores"].get(v.clave)
        bandas[v.clave] = banda(v, r, xs, MARGENES[margen]) if r is not None and len(xs) >= MIN_COMPARADAS else None
    utiles = [v for v in variables if bandas[v.clave] is not None]
    if not utiles:
        return {"motivo": "No hay ningún dato de esas áreas para esta zona.", "resultados": []}
    candidatas = [f for f in otras if donde == "todo" or (f["mun"] == ref["mun"]) == (donde == "mismo")]
    filas = []
    for f in candidatas:
        estado = {v.clave: comparar(v, ref["valores"].get(v.clave), f["valores"].get(v.clave), bandas[v.clave])
                  for v in variables}
        con_dato = sum(e != "sin_dato" for e, _ in estado.values())
        # Con menos de la mitad de los datos no se sabe si se parece.
        if con_dato * 2 < len(utiles):
            continue
        parecidas = sum(e == "parecida" for e, _ in estado.values())
        filas.append((-parecidas, max((d for _, d in estado.values()), default=0.0), f["clave"], f, estado, con_dato))
    filas.sort(key=lambda x: x[:3])

    dato = lambda x: None if x is None else round(x, 2)  # noqa: E731
    return {
        "motivo": None,
        "nivel": nivel,
        "nivel_nombre": NIVELES[nivel][1],
        "referencia": {"clave": ref["clave"], "nombre": ref["nombre"], "pobtot": ref["pobtot"],
                       "chica": nivel == "colonia" and (ref["pobtot"] or 0) < MIN_POBLACION_COLONIA},
        "areas": [{"clave": a, "titulo": t} for a, t in AREAS.items() if any(v.area == a for v in de_nivel(nivel))],
        "comparadas": len(candidatas),
        "estados": estados,
        "min_poblacion": MIN_POBLACION_COLONIA if nivel == "colonia" else None,
        "calculado": max(f["calculado"] for f in todas),
        "fraccion": MARGENES[margen],
        "variables": [{"clave": v.clave, "area": v.area, "etiqueta": v.etiqueta, "unidad": v.unidad,
                       "decimales": v.decimales, "log": v.log, "valor": dato(ref["valores"].get(v.clave)),
                       "banda": bandas[v.clave] and {k: x for k, x in bandas[v.clave].items() if k != "medio"}}
                      for v in variables],
        "resultados": [{
            "clave": f["clave"], "nombre": f["nombre"], "detalle": f["detalle"], "pobtot": f["pobtot"],
            "parecidas": -menos, "con_dato": con_dato,
            "valores": {v.clave: {"valor": dato(f["valores"].get(v.clave)), "estado": estado[v.clave][0]}
                        for v in variables},
        } for menos, _, _, f, estado, con_dato in filas[:MAX_RESULTADOS]],
    }
