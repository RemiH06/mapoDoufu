"""Perfil de una zona cualquiera de la zona común (sesión 29h). Ver docs/producto/perfil.md.

Reglas: cada documento dice su nivel. El censo, DENUE y los minutos a servicios bajan
hasta la zona; lo que solo existe por municipio (Censos Económicos, IMSS, SESNSP,
EFIPEM, CNGMD) va de los municipios que toca, dicho así, y la ENOE es del estado. Nunca
un puntaje. Un dato reservado por INEGI no es cero.

Municipios enteros (un estado, municipios, una metrópoli) se suman por clave. Una
colonia, un CP o un dibujo se estiman repartiendo cada AGEB por área, como hace CONAPO
con sus colonias: contra 42 mil manzanas de Guadalajara, Zapopan y Tlaquepaque el error
mediano es de 20 % por colonia; contar la AGEB entera por su punto da 100 %
(docs/producto/perfil.md).
"""

from __future__ import annotations

import json

from psycopg.rows import dict_row

from mapo_core import accesibilidad, cngmd, consultas, efipem, imss_asegurados, rezago_social
from mapo_core import zona as zona_comun
from mapo_core.enigh_resumen import DIAS_POR_TRIMESTRE, _percentil_ponderado, _promedio_ponderado

ENTEROS = ("estado", "municipios", "metropoli")

# Bandas de la pirámide: (etiqueta, años que abarca, claves que se suman, claves que se
# restan). De 25 a 59 INEGI no la da por AGEB: sale de los mayores de 18. La última va
# abierta; se dibuja como si llegara a 85.
PIRAMIDE = (
    ("0 a 5", 6, ("P_0A2", "P_3A5"), ()),
    ("6 a 11", 6, ("P_6A11",), ()),
    ("12 a 17", 6, ("P_12A14", "P_15A17"), ()),
    ("18 a 24", 7, ("P_18A24",), ()),
    ("25 a 59", 35, ("P_18YMAS",), ("P_18A24", "P_60YMAS")),
    ("60 o más", 25, ("P_60YMAS",), ()),
)
_SEXOS = ("F", "M")

# Bienes y servicios de la vivienda, todos sobre TVIVPARHAB (ver consultas.DENOMINADORES_CENSO).
VIVIENDA = (
    ("VPH_AGUADV", "Agua entubada dentro"),
    ("VPH_DRENAJ", "Drenaje"),
    ("VPH_REFRI", "Refrigerador"),
    ("VPH_LAVAD", "Lavadora"),
    ("VPH_INTER", "Internet"),
    ("VPH_PC", "Computadora"),
    ("VPH_AUTOM", "Automóvil"),
    ("VPH_1DOR", "Un solo dormitorio"),
)

_TOTALES = ("POBTOT", "POBFEM", "POBMAS", "PEA", "POCUPADA", "PDESOCUP", "TOTHOG", "VIVTOT", "TVIVPARHAB",
            "VIVPAR_DES", "VIVPAR_UT")
_RAZONES = ("POB0_14", "P_15YMAS", "P_12YMAS", "P_12YMAS_F", "PEA_F", "PNACOE", "PSINDER", "PDER_IMSS", "OCUPVIVPAR",
            "TVIVPAR", "GRAPROES", "P_60YMAS")
GRUPOS = tuple(dict.fromkeys(s.grupo for s in accesibilidad.SERVICIOS.values()))
CLAVES = tuple(dict.fromkeys(
    _TOTALES + _RAZONES + tuple(k for k, _ in VIVIENDA)
    + tuple(f"{k}_{s}" for _, _, mas, menos in PIRAMIDE for k in mas + menos for s in _SEXOS) + GRUPOS))

# Sectores del SCIAN para DENUE (los dos primeros dígitos de la actividad, en la CLEE).
SECTORES = {
    "11": "Agropecuario", "21": "Minería", "22": "Agua y energía", "23": "Construcción", "31": "Manufactura",
    "32": "Manufactura", "33": "Manufactura", "43": "Comercio al por mayor", "46": "Comercio al por menor",
    "48": "Transporte y almacenes", "49": "Transporte y almacenes", "51": "Medios e información",
    "52": "Finanzas y seguros", "53": "Inmobiliarias y alquiler", "54": "Profesionales y técnicos",
    "55": "Corporativos", "56": "Apoyo a negocios", "61": "Educación", "62": "Salud y asistencia",
    "71": "Cultura y deporte", "72": "Alojamiento y comida", "81": "Otros servicios", "93": "Gobierno",
}

# Error mediano del reparto por área contra las manzanas del censo, según la gente que
# resulta: 1,212 colonias de Guadalajara, Zapopan y Tlaquepaque. Bajo 100 personas pasa
# de 200 %: no hay cifra que sirva.
ERROR_REPARTO = ((100, None), (500, 43), (1_500, 29), (5_000, 13), (20_000, 5), (float("inf"), 3))

METODO_ENTEROS = "Censo 2020 de INEGI, total de cada municipio."
METODO_REPARTO = (
    "La gente de cada AGEB urbana se reparte por área: si la zona tiene la mitad de la AGEB, se lleva la mitad de"
    " su gente. Las localidades sin AGEB cuentan enteras si su punto cae dentro. Es una estimación (CONAPO hace lo"
    " mismo con sus colonias). Error mediano contra las manzanas del censo en 1,212 colonias de Guadalajara,"
    " Zapopan y Tlaquepaque: 43 % entre 100 y 500 habitantes, 29 % hasta 1,500, 13 % hasta 5,000 y 5 % o menos arriba."
)
CORTES_MIN = (15, 30)
# Menos de esta parte de una AGEB es el borde de los polígonos, que no coinciden al metro.
BORDE = 0.01


class ConsultaInvalida(ValueError):
    pass


def numero(d: dict | None, clave: str) -> float | None:
    """Un valor del censo. INEGI pone '*' donde reserva y 'N/D' donde no hay: None."""
    v = (d or {}).get(clave)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(v) if isinstance(v, str) else None
    except ValueError:
        return None


def redondo(x: float | None, n: int = 1) -> float | None:
    return None if x is None else round(x, n)


class Censo:
    """Lugares del censo (datos, peso): sumas y razones. Una razón solo usa los lugares
    que traen las dos partes: con el numerador reservado y el denominador no, saldría
    más baja de lo que es."""

    def __init__(self, lugares: list[tuple[dict, float]]):
        self.lugares = lugares

    def total(self, clave: str) -> int | None:
        valores = [v * w for d, w in self.lugares if (v := numero(d, clave)) is not None]
        return round(sum(valores)) if valores else None

    def razon(self, arriba: str, abajo: str, por: float = 100) -> float | None:
        n = m = 0.0
        for d, w in self.lugares:
            a, b = numero(d, arriba), numero(d, abajo)
            if a is not None and b is not None:
                n += a * w
                m += b * w
        return por * n / m if m > 0 else None

    def promedio(self, clave: str, peso: str) -> float | None:
        n = m = 0.0
        for d, w in self.lugares:
            v, p = numero(d, clave), numero(d, peso)
            if v is not None and p is not None:
                n += v * p * w
                m += p * w
        return n / m if m > 0 else None

    def reservados(self) -> int:
        return sum(any(d.get(k) == "*" for k in CLAVES) for d, _ in self.lugares)


def datos_sql(columna: str, claves: tuple[str, ...] = CLAVES) -> str:
    """Solo las claves que se usan (el renglón del censo trae más de 220). En tandas:
    jsonb_build_object acepta hasta 100 argumentos."""
    tandas = [claves[i:i + 45] for i in range(0, len(claves), 45)]
    return "(" + " || ".join(
        "jsonb_build_object(" + ", ".join(f"'{k}', {columna}->'{k}'" for k in t) + ")" for t in tandas) + ")"


def por_clave(alias: str = "") -> str:
    """Condición SQL de municipios enteros. Por pares y no con `cve_ent || cve_mun`: así
    entra el índice (los delitos son 30 millones de renglones)."""
    a = f"{alias}." if alias else ""
    return f"({a}cve_ent, {a}cve_mun) IN (SELECT * FROM unnest(%(pares_e)s::text[], %(pares_m)s::text[]))"


def params_muns(muns: list[str]) -> dict:
    return {"ents": sorted({m[:2] for m in muns}), "pares_e": [m[:2] for m in muns], "pares_m": [m[2:] for m in muns]}


async def filas_de(conn, sql: str, params: dict | None = None) -> list[dict]:
    cur = conn.cursor(row_factory=dict_row)
    await cur.execute(sql, params or {})
    return await cur.fetchall()


# ---------------------------------------------------------------- lugares

async def lugares_enteros(conn, muns: list[str]) -> list[dict]:
    """El renglón de cada municipio en el censo (no la suma de sus AGEB, que deja fuera
    al campo)."""
    return await filas_de(conn, f"""
        SELECT c.cvegeo AS clave, 'municipio' AS tipo, 1.0::float AS peso, {datos_sql('c.datos_json')} AS d
        FROM fuente_censo_poblacion c WHERE c.nivel = 'municipio' AND {por_clave('c')}""", params_muns(muns))


async def lugares_por_area(conn, z: dict) -> list[dict]:
    """AGEB que toca la zona con la parte de su área que queda dentro, y las localidades
    sin AGEB cuyo punto cae en ella."""
    cte, params = zona_comun.partida_sql(z)
    return await filas_de(conn, f"""
        WITH {cte}
        SELECT a.cvegeo AS clave, 'ageb' AS tipo, {datos_sql('c.datos_json')} AS d,
               CASE WHEN ST_Covers(z.geom, a.geom) THEN 1.0
                    ELSE least(1.0, ST_Area(ST_Intersection(ST_MakeValid(a.geom), z.geom)) / nullif(ST_Area(a.geom), 0))
               END::float AS peso
        FROM agebs a JOIN fuente_censo_poblacion c ON c.cvegeo = a.cvegeo AND c.nivel = 'ageb', z
        WHERE a.geom && z.geom AND ST_Intersects(a.geom, z.geom)
        UNION ALL
        SELECT l.cvegeo, 'localidad', {datos_sql('l.datos')}, 1.0::float
        FROM localidades l
        WHERE l.geom && (SELECT geom FROM z) AND {zona_comun.dentro('l.geom')} AND coalesce(l.pobtot, 1) > 0
          AND NOT EXISTS (SELECT 1 FROM agebs a WHERE a.geom && l.geom AND ST_Covers(a.geom, l.geom))""", params)


async def lugares_servicios(conn, muns: list[str]) -> list[dict]:
    """AGEB y localidades de municipios enteros, con los grupos que usan los servicios."""
    return await filas_de(conn, f"""
        SELECT c.cvegeo AS clave, 'ageb' AS tipo, 1.0::float AS peso, {datos_sql('c.datos_json', GRUPOS)} AS d
        FROM fuente_censo_poblacion c JOIN agebs a ON a.cvegeo = c.cvegeo
        WHERE c.nivel = 'ageb' AND {por_clave('c')}
        UNION ALL
        SELECT l.cvegeo, 'localidad', 1.0::float, {datos_sql('l.datos', GRUPOS)}
        FROM localidades l
        WHERE {por_clave('l')} AND coalesce(l.pobtot, 1) > 0
          AND NOT EXISTS (SELECT 1 FROM agebs a WHERE a.geom && l.geom AND ST_Covers(a.geom, l.geom))""",
        params_muns(muns))


# ---------------------------------------------------------------- documentos de la zona

def error_reparto(pobtot: int | None) -> float | None:
    """Error mediano esperado del reparto, en %; None si es tan chica que ninguna cifra
    sirve."""
    if pobtot is None:
        return None
    return next(e for tope, e in ERROR_REPARTO if pobtot < tope)


def demografia(censo: Censo, km2: float, entera: bool) -> dict | None:
    pobtot = censo.total("POBTOT")
    if pobtot is None:
        return None
    bandas = []
    for etiqueta, anios, mas, menos in PIRAMIDE:
        banda: dict = {"etiqueta": etiqueta, "anios": anios}
        for s in _SEXOS:
            suma, hay = 0.0, False
            for d, w in censo.lugares:
                v = [numero(d, f"{k}_{s}") for k in mas]
                r = [numero(d, f"{k}_{s}") for k in menos]
                if None not in v + r:
                    suma += (sum(v) - sum(r)) * w
                    hay = True
            banda[s] = max(0, round(suma)) if hay else None
        bandas.append(banda)
    return {
        **{k.lower(): censo.total(k) for k in ("POBTOT", "POBFEM", "POBMAS", "PEA", "POCUPADA", "PDESOCUP", "TOTHOG")},
        "graproes": redondo(censo.promedio("GRAPROES", "P_15YMAS"), 2),
        "densidad": redondo(pobtot / km2) if km2 else None,
        "menores15_pct": redondo(censo.razon("POB0_14", "POBTOT")),
        "mayores60_pct": redondo(censo.razon("P_60YMAS", "POBTOT")),
        "nacidos_fuera_pct": redondo(censo.razon("PNACOE", "POBTOT")),
        "sin_salud_pct": redondo(censo.razon("PSINDER", "POBTOT")),
        "pea_pct": redondo(censo.razon("PEA", "P_12YMAS")),
        "piramide": bandas if all(b["F"] is not None and b["M"] is not None for b in bandas) else None,
        "reservados": censo.reservados(),
        "estimada": not entera,
        "error_pct": None if entera else error_reparto(pobtot),
        "metodo": METODO_ENTEROS if entera else METODO_REPARTO,
    }


def vivienda(censo: Censo) -> dict | None:
    if censo.total("TVIVPARHAB") is None:
        return None
    return {
        "total": censo.total("VIVTOT"),
        "habitadas": censo.total("TVIVPARHAB"),
        "deshabitadas": censo.total("VIVPAR_DES"),
        "temporales": censo.total("VIVPAR_UT"),
        "deshabitadas_pct": redondo(censo.razon("VIVPAR_DES", "TVIVPAR")),
        "ocupantes": redondo(censo.razon("OCUPVIVPAR", "TVIVPARHAB", 1), 2),
        "bienes": [{"clave": k, "etiqueta": e, "pct": redondo(censo.razon(k, "TVIVPARHAB"))} for k, e in VIVIENDA],
    }


async def precio_oferta(conn, lugares: list[dict]) -> dict | None:
    """Precio de oferta de las AGEB de la zona con anuncios (docs/producto/precio-estimado.md):
    mediana entre AGEB pesada por viviendas, y el rango. None si ninguna tiene."""
    pesos = {u["clave"]: u["peso"] * (numero(u["d"], "TVIVPARHAB") or 0) for u in lugares
             if u["tipo"] == "ageb" and u["peso"] >= BORDE}
    filas = await filas_de(conn, "SELECT cvegeo, valor FROM fuente_precio_estimado WHERE fuente = 'anuncios'"
                                 " AND valor IS NOT NULL AND cvegeo = ANY(%(c)s)", {"c": list(pesos)})
    pares = [(f["valor"], pesos[f["cvegeo"]]) for f in filas if pesos[f["cvegeo"]] > 0]
    if not pares:
        return None
    return {"mediana": _percentil_ponderado(pares, 50), "bajo": min(v for v, _ in pares),
            "alto": max(v for v, _ in pares), "agebs": len(pares), "agebs_zona": sum(p > 0 for p in pesos.values())}


async def _precio_enteros(conn, muns: list[str]) -> dict | None:
    return await precio_oferta(conn, await filas_de(conn, f"""
        SELECT c.cvegeo AS clave, 'ageb' AS tipo, 1.0::float AS peso, {datos_sql('c.datos_json', ('TVIVPARHAB',))} AS d
        FROM fuente_censo_poblacion c WHERE c.nivel = 'ageb' AND {por_clave('c')}""", params_muns(muns)))


async def tenencia(conn, municipios: list[dict]) -> list[dict]:
    """Propias y rentadas por municipio (Intercensal 2025), hasta 12 municipios."""
    if len(municipios) > 12:
        return []
    filas = await filas_de(conn, f"""
        SELECT cve_ent || cve_mun AS mun, indicador, valor FROM fuente_eic2025_vivienda
        WHERE nivel = 'municipio' AND {por_clave()} AND indicador IN ('PCN_VPH_PROPIA', 'PCN_VPH_ALQUI')""",
        params_muns([m["cvegeo"] for m in municipios]))
    valor = {(f["mun"], f["indicador"]): f["valor"] for f in filas}
    return [{"nombre": m["nombre"], "propias": valor.get((m["cvegeo"], "PCN_VPH_PROPIA")),
             "rentadas": valor.get((m["cvegeo"], "PCN_VPH_ALQUI"))}
            for m in municipios if (m["cvegeo"], "PCN_VPH_PROPIA") in valor]


def _primer_numero(texto: str) -> int:
    digitos = "".join(c for c in texto.split(" ")[0] if c.isdigit())
    return int(digitos) if digitos else 10**6


async def negocios(conn, z: dict, muns: list[str], entera: bool) -> dict | None:
    """DENUE de la zona: total, sectores, las diez clases más comunes y tamaño. None si
    ningún estado de la zona tiene DENUE cargado."""
    ents = sorted({m[:2] for m in muns})
    cargados = {f["e"] for f in await filas_de(
        conn, "SELECT e FROM unnest(%(e)s::text[]) e WHERE EXISTS"
              " (SELECT 1 FROM fuente_denue_negocios d WHERE d.cve_ent = e)", {"e": ents})}
    if not cargados:
        return None
    if entera:
        cte, donde, params = "", por_clave("n"), params_muns(muns)
    else:
        cte, params = zona_comun.partida_sql(z)
        cte = f"WITH {cte}"
        donde = ("n.lat BETWEEN (SELECT ST_YMin(geom) FROM z) AND (SELECT ST_YMax(geom) FROM z)"
                 " AND n.lon BETWEEN (SELECT ST_XMin(geom) FROM z) AND (SELECT ST_XMax(geom) FROM z) AND "
                 + zona_comun.dentro("ST_SetSRID(ST_MakePoint(n.lon, n.lat), 4326)"))
    filas = await filas_de(conn, f"""{cte}
        SELECT clase_actividad AS clase, substr(clee, 6, 2) AS sector, estrato, count(*) AS n
        FROM fuente_denue_negocios n WHERE {donde} GROUP BY 1, 2, 3""", params)
    total = 0
    clases: dict = {}
    sectores: dict = {}
    estratos: dict = {}
    for f in filas:
        total += f["n"]
        sector = SECTORES.get(f["sector"] or "")
        for cuenta, llave in ((clases, f["clase"]), (sectores, sector), (estratos, f["estrato"])):
            cuenta[llave] = cuenta.get(llave, 0) + f["n"]
    mas_a_menos = lambda d: [[k, n] for k, n in sorted(d.items(), key=lambda x: (-x[1], str(x[0]))) if k]  # noqa: E731
    return {
        "total_negocios": total,
        "top_clases_actividad": mas_a_menos(clases)[:10],
        "sectores": mas_a_menos(sectores),
        "sin_sector": sectores.get(None, 0),
        "estratos": [[k, n] for k, n in sorted(((k, n) for k, n in estratos.items() if k),
                                               key=lambda x: _primer_numero(x[0]))],
        "estados_sin_denue": [e for e in ents if e not in cargados],
    }


async def minutos_de(conn, claves: list[str] | None, muns: list[str]) -> dict[str, dict[str, float | None]]:
    """{servicio: {clave: minutos a pie}}. Una clave que no viene no se calculó; None es
    sin ruta por calle."""
    filas = await filas_de(conn, f"""
        SELECT servicio, clave, minutos FROM accesibilidad_minutos
        WHERE {por_clave()} AND modo = 'pie' AND (%(claves)s::text[] IS NULL OR clave = ANY(%(claves)s))""",
        {**params_muns(muns), "claves": claves})
    salida: dict[str, dict] = {}
    for f in filas:
        salida.setdefault(f["servicio"], {})[f["clave"]] = f["minutos"]
    return salida


def servicios(lugares: list[dict], minutos: dict[str, dict]) -> list[dict]:
    """Por servicio, la gente de su grupo a 15 minutos o menos a pie, de 15 a 30 y más.
    Lo no calculado y lo que no tiene ruta van aparte, nunca como lejos. Con más de la
    mitad del grupo sin calcular, la cifra engaña y no se da (`parcial`)."""
    salida = []
    for s in accesibilidad.SERVICIOS.values():
        por_lugar = minutos.get(s.clave)
        base = {"clave": s.clave, "titulo": s.titulo, "grupo_etiqueta": s.grupo_etiqueta}
        if not por_lugar:
            salida.append({**base, "calculado": False})
            continue
        tramos, sin_ruta, sin_calcular = [0.0, 0.0, 0.0], 0.0, 0.0
        for u in lugares:
            v = numero(u["d"], s.grupo)
            if v is None:
                continue
            v *= u["peso"]
            if u["clave"] not in por_lugar or (s.solo_agebs and u["tipo"] != "ageb"):
                sin_calcular += v
            elif (m := por_lugar[u["clave"]]) is None:
                sin_ruta += v
            else:
                tramos[sum(m > c for c in CORTES_MIN)] += v
        con_ruta = sum(tramos)
        parcial = sin_calcular > con_ruta + sin_ruta
        salida.append({**base, "calculado": True, "parcial": parcial, "tramos": [round(t) for t in tramos],
                       "con_ruta": round(con_ruta), "sin_ruta": round(sin_ruta), "sin_calcular": round(sin_calcular),
                       "cerca_pct": round(100 * tramos[0] / con_ruta, 1) if con_ruta > 0 and not parcial else None})
    return salida


async def rezago(conn, lugares: list[dict] | None, muns: list[str]) -> dict | None:
    """Grado de rezago social por AGEB urbana; con `lugares`, la gente de cada AGEB va
    repartida con su peso."""
    if not await filas_de(conn, "SELECT 1 AS x FROM fuente_rezago_social_ageb LIMIT 1"):
        return None
    por: dict = {}
    if lugares is None:
        for f in await filas_de(conn, "SELECT grado, count(*) AS n, sum(pobtot) AS p FROM fuente_rezago_social_ageb"
                                      f" WHERE {por_clave()} GROUP BY grado", params_muns(muns)):
            por[f["grado"]] = (f["n"], f["p"])
    else:
        pesos = {u["clave"]: u["peso"] for u in lugares if u["tipo"] == "ageb" and u["peso"] >= BORDE}
        for f in await filas_de(conn, "SELECT cvegeo, grado, pobtot FROM fuente_rezago_social_ageb"
                                      " WHERE cvegeo = ANY(%(c)s)", {"c": list(pesos)}):
            n, p = por.get(f["grado"], (0, None))
            if f["pobtot"] is not None:
                p = (p or 0.0) + f["pobtot"] * pesos[f["cvegeo"]]
            por[f["grado"]] = (n + 1, p)
    if not por:
        return {"sin_dato": True}
    # Sin personas: INEGI reserva la población de todas las AGEB de ese grado.
    return {"anio": 2020, "grados": [{"grado": g, "agebs": por[g][0], "personas": redondo(por[g][1], 0)}
                                     for g in rezago_social.GRADOS if g in por]}


# ---------------------------------------------------------------- documentos por municipio

async def economia(conn, muns: list[str]) -> dict | None:
    filas = await filas_de(conn, f"""
        SELECT sector, max(nombre) AS nombre, sum(ue) AS ue, sum(personal) AS personal,
               sum(remuneraciones) AS remuneraciones, sum(ingresos) AS ingresos, sum(vacb) AS vacb,
               count(*) FILTER (WHERE personal IS NULL) AS reservados
        FROM fuente_ce2024_municipal WHERE {por_clave()} GROUP BY sector""", params_muns(muns))
    if not filas:
        hay = await filas_de(conn, "SELECT 1 AS x FROM fuente_ce2024_municipal WHERE cve_ent = ANY(%(ents)s) LIMIT 1",
                             params_muns(muns))
        return {"sin_dato": True} if hay else None
    sectores = sorted((f for f in filas if f["sector"] != "total"),
                      key=lambda f: (f["personal"] is None, -(f["personal"] or 0)))
    return {"anio_datos": 2023, "total": next((f for f in filas if f["sector"] == "total"), None),
            "sectores": sectores, "reservados": sum(f["reservados"] for f in sectores)}


async def consumo(conn, muns: list[str]) -> dict | None:
    """Gasto de los hogares de la muestra en esos municipios, y el de su estado, que sí es
    representativo."""
    async def resumen(donde: str) -> dict | None:
        filas = await filas_de(conn, "SELECT factor, gasto_mon AS v FROM fuente_enigh_concentradohogar"
                                     f" WHERE {donde} AND factor IS NOT NULL AND gasto_mon IS NOT NULL",
                               params_muns(muns))
        pares = [(f["v"], f["factor"]) for f in filas]
        if not pares:
            return None
        return {"n_hogares_muestra": len(pares), "periodo": "diario",
                "promedio_ponderado": _promedio_ponderado(pares) / DIAS_POR_TRIMESTRE,
                "mediana": _percentil_ponderado(pares, 50) / DIAS_POR_TRIMESTRE}

    zona = await resumen(por_clave())
    estado = await resumen("cve_ent = ANY(%(ents)s)") if len({m[:2] for m in muns}) == 1 else None
    return {"zona": zona, "estado": estado} if zona or estado else None


async def seguridad(conn, muns: list[str], pobtot: int | None) -> dict | None:
    """Delitos del último año de esos municipios por tipo, y el total de cada año. El
    año en curso dice cuántos meses trae; la tasa solo va con el año completo."""
    filas = await filas_de(conn, f"""
        SELECT anio, sum(cantidad)::bigint AS n, count(DISTINCT mes) AS meses FROM fuente_sesnsp_delitos_municipal
        WHERE {por_clave()} GROUP BY anio ORDER BY anio""", params_muns(muns))
    if not filas:
        return None
    ultimo = filas[-1]
    tipos = await filas_de(conn, f"""
        SELECT tipo_delito AS tipo, sum(cantidad)::bigint AS n FROM fuente_sesnsp_delitos_municipal
        WHERE {por_clave()} AND anio = %(anio)s GROUP BY 1 ORDER BY 2 DESC, 1""",
        {**params_muns(muns), "anio": ultimo["anio"]})
    return {"anio": ultimo["anio"], "meses": ultimo["meses"], "total_delitos": ultimo["n"],
            "por_mil": round(1000 * ultimo["n"] / pobtot, 1) if pobtot and ultimo["meses"] == 12 else None,
            "por_tipo": [[t["tipo"], t["n"]] for t in tipos],
            "serie": [{"anio": f["anio"], "total": f["n"], "meses": f["meses"]} for f in filas]}


async def empleo(conn, muns: list[str]) -> dict | None:
    """Puestos del IMSS de varios municipios, sumados en el mismo mes."""
    p = params_muns(muns)
    periodos = [x for e in p["ents"] if (x := await imss_asegurados._periodos(conn, e))[0]]
    if not periodos:
        return None
    periodo, anterior = min(periodos, key=lambda x: x[0])
    filas = await filas_de(conn, f"""
        SELECT division, sum(puestos)::bigint AS puestos, sum(permanentes)::bigint AS permanentes,
               sum(eventuales)::bigint AS eventuales, sum(puestos_con_salario)::bigint AS con_salario,
               sum(masa_salarial)::float AS masa, sum(puestos_rango_tope)::bigint AS tope
        FROM fuente_imss_asegurados WHERE periodo = %(per)s AND {por_clave()} GROUP BY division""",
        {**p, "per": periodo})
    contar = "SELECT coalesce(sum(puestos), 0)::bigint AS n FROM fuente_imss_asegurados WHERE periodo = %(per)s AND "
    antes = (await filas_de(conn, contar + por_clave(), {**p, "per": anterior}))[0]["n"] if anterior else None
    fuera = (await filas_de(conn, contar + "cve_ent = ANY(%(ents)s) AND cve_mun = %(sin)s",
                            {**p, "per": periodo, "sin": imss_asegurados.SIN_MUNICIPIO}))[0]["n"]
    suma = lambda k: sum(f[k] or 0 for f in filas)  # noqa: E731
    puestos, con_salario = suma("puestos"), suma("con_salario")
    return {
        "periodo": periodo.isoformat(), "puestos": puestos, "permanentes": suma("permanentes"),
        "eventuales": suma("eventuales"), "salario_diario": imss_asegurados._salario(suma("masa"), con_salario),
        "parte_rango_tope": round(suma("tope") / con_salario * 100, 2) if con_salario else None,
        "por_division": sorted(({"division": f["division"],
                                 "nombre": imss_asegurados.DIVISIONES.get(f["division"], f["division"]),
                                 "puestos": f["puestos"],
                                 "salario_diario": imss_asegurados._salario(f["masa"], f["con_salario"])}
                                for f in filas if f["division"] and f["puestos"] > 0), key=lambda x: -x["puestos"]),
        "anual": {"periodo": anterior.isoformat(), "puestos": antes,
                  "variacion": imss_asegurados._variacion(puestos, antes)} if anterior else None,
        "puestos_estado_sin_municipio": fuera,
    }


async def haciendas(conn, muns: list[str]) -> dict[str, dict]:
    """Por municipio, el total, los propios y el predial del último año que reportó."""
    por: dict[str, dict] = {}
    for f in await filas_de(conn, f"""
            SELECT cve_ent || cve_mun AS mun, anio, categoria, concepto, valor FROM fuente_efipem_municipal
            WHERE {por_clave()} AND tema = 'Ingresos' ORDER BY anio DESC""", params_muns(muns)):
        d = por.setdefault(f["mun"], {"anio": f["anio"], "total": None, "propios": 0.0, "predial": None})
        if f["anio"] != d["anio"]:
            continue
        if f["categoria"] == "Tema":
            d["total"] = f["valor"]
        elif f["concepto"] == efipem.PREDIAL:
            d["predial"] = f["valor"]
        elif f["concepto"] in efipem.PROPIOS:
            d["propios"] += f["valor"]
    for d in por.values():
        d["propios_pct"] = round(100 * d["propios"] / d["total"], 1) if d["total"] else None
    return por


async def hacienda_varios(conn, municipios: list[dict]) -> dict | None:
    """Cada municipio con su último año reportado, porque no todos reportan el mismo; la
    suma solo es de los que reportaron el último."""
    ultimo = (await filas_de(conn, "SELECT max(anio) AS a FROM fuente_efipem_municipal"))[0]["a"]
    if ultimo is None:
        return None
    por = await haciendas(conn, [m["cvegeo"] for m in municipios])
    tabla = [{"cvegeo": m["cvegeo"], "nombre": m["nombre"],
              **{k: por.get(m["cvegeo"], {}).get(k) for k in ("anio", "total", "propios_pct", "predial")}}
             for m in municipios]
    al_dia = [d for d in por.values() if d["anio"] == ultimo and d["total"]]
    suma = sum(d["total"] for d in al_dia)
    return {"varios": True, "anio": ultimo, "municipios": len(tabla), "reportaron": len(al_dia),
            "total_ingresos": suma or None,
            "propios_pct": round(100 * sum(d["propios"] for d in al_dia) / suma, 1) if suma else None,
            "predial": sum(d["predial"] or 0 for d in al_dia) if al_dia else None,
            "tabla": sorted(tabla, key=lambda t: -(t["total"] or 0))}


async def planeacion_varios(conn, muns: list[str]) -> dict | None:
    filas = await filas_de(conn, f"""
        SELECT instrumento, max(nombre) AS nombre, count(*) AS n, count(*) FILTER (WHERE existio = 'sí') AS si
        FROM fuente_cngmd_planeacion WHERE {por_clave()} AND instrumento = ANY(%(p)s) GROUP BY instrumento""",
        {**params_muns(muns), "p": list(cngmd.PRINCIPALES)})
    if not filas:
        return None
    filas.sort(key=lambda f: cngmd.PRINCIPALES.index(f["instrumento"]))
    return {"anio": 2024, "varios": True, "principales": filas}


# ---------------------------------------------------------------- plano

async def plano(conn, z: dict, resuelta: dict, entera: bool) -> dict:
    """Densidad por AGEB (por municipio si la zona es muy grande), para el plano, y las
    localidades sin AGEB como punto: en el campo, ahí vive casi toda la gente. En una zona
    chica van también las AGEB vecinas: una colonia sola no dice dónde está."""
    columnas = "c.pobtot AS p, (ST_Area(g.geom::geography) / 1e6)::float AS km2"
    if entera:
        por_municipio = resuelta["km2"] > zona_comun.MAX_KM2_CONSULTA
        tabla, nivel, nombre = ("municipios", "municipio", "g.nombre") if por_municipio else ("agebs", "ageb", "NULL")
        filas = await filas_de(conn, f"""
            SELECT g.cvegeo AS c, {nombre} AS n, {columnas}, true AS dentro,
                   ST_AsGeoJSON({consultas.dibujo('g')}, 5) AS gj
            FROM {tabla} g LEFT JOIN fuente_censo_poblacion c ON c.cvegeo = g.cvegeo AND c.nivel = '{nivel}'
            WHERE {por_clave('g')}""",
            {**params_muns([m["cvegeo"] for m in resuelta["municipios"]]),
             "tolerancia": consultas.TOLERANCIA_SIMPLIFICACION})
    else:
        nivel = "ageb"
        sql, params = zona_comun.geom_sql(z)
        x0, y0, x1, y1 = resuelta["bbox"]
        aire = max(x1 - x0, y1 - y0) * 0.35
        filas = await filas_de(conn, f"""
            WITH z AS MATERIALIZED ({sql})
            SELECT g.cvegeo AS c, NULL AS n, {columnas}, ST_Intersects(g.geom, z.geom) AS dentro,
                   ST_AsGeoJSON(ST_SimplifyPreserveTopology(g.geom, 0.00003), 5) AS gj
            FROM agebs g LEFT JOIN fuente_censo_poblacion c ON c.cvegeo = g.cvegeo AND c.nivel = 'ageb', z
            WHERE g.geom && ST_MakeEnvelope(%(x0)s, %(y0)s, %(x1)s, %(y1)s, 4326)""",
            {**params, "x0": x0 - aire, "y0": y0 - aire, "x1": x1 + aire, "y1": y1 + aire})
    puntos = [] if nivel == "municipio" else await _localidades_plano(conn, z, resuelta, entera)
    return {"nivel": nivel, "type": "FeatureCollection", "localidades": puntos, "features": [
        {"type": "Feature", "geometry": json.loads(f["gj"]),
         "properties": {"c": f["c"], "n": f["n"], "p": f["p"], "dentro": f["dentro"],
                        "d": round(f["p"] / f["km2"]) if f["p"] is not None and f["km2"] else None}}
        for f in filas if f["gj"]]}


async def _localidades_plano(conn, z: dict, resuelta: dict, entera: bool) -> list[list]:
    """[lon, lat, personas o None si INEGI las reserva, nombre] de las localidades sin AGEB."""
    if entera:
        cte, donde, params = "", por_clave("l"), params_muns([m["cvegeo"] for m in resuelta["municipios"]])
    else:
        cte, params = zona_comun.partida_sql(z)
        cte, donde = f"WITH {cte}", f"l.geom && (SELECT geom FROM z) AND {zona_comun.dentro('l.geom')}"
    return [[round(f["lon"], 5), round(f["lat"], 5), f["p"], f["n"]] for f in await filas_de(conn, f"""{cte}
        SELECT ST_X(l.geom) AS lon, ST_Y(l.geom) AS lat, l.pobtot AS p, l.nombre AS n FROM localidades l
        WHERE {donde} AND coalesce(l.pobtot, 1) > 0
          AND NOT EXISTS (SELECT 1 FROM agebs a WHERE a.geom && l.geom AND ST_Covers(a.geom, l.geom))
        ORDER BY l.pobtot DESC NULLS LAST""", params)]


# ---------------------------------------------------------------- el perfil

async def base(conn, z: dict) -> dict | None:
    """Lo que comparten el perfil y los similares: la zona resuelta, sus lugares y sus
    minutos a servicios. None si la zona no toca nada cargado."""
    resuelta = await zona_comun.resolver(conn, z)
    if resuelta is None or not resuelta["municipios"]:
        return None
    entera = z["tipo"] in ENTEROS
    if not entera and (motivo := zona_comun.demasiado_grande(resuelta["km2"])):
        raise ConsultaInvalida(motivo)
    muns = [m["cvegeo"] for m in resuelta["municipios"]]
    if entera:
        lugares = await lugares_enteros(conn, muns)
        de_servicios = await lugares_servicios(conn, muns)
    else:
        lugares = de_servicios = await lugares_por_area(conn, z)
    # Una AGEB que la zona apenas roza puede ser de un municipio que no "toca" (5 %).
    # De municipios enteros, todas: filtrar por miles de claves tardaba más que leerlas.
    minutos = await minutos_de(conn, None if entera else [u["clave"] for u in de_servicios],
                               sorted({*muns, *(u["clave"][:5] for u in de_servicios)}))
    # El área de `resolver` va redondeada a hectáreas: en una colonia chica movería la densidad.
    return {"resuelta": resuelta, "km2": await zona_comun.area_km2(conn, z), "entera": entera, "muns": muns, "lugares": lugares,
            "censo": Censo([(u["d"], u["peso"]) for u in lugares]), "servicios": servicios(de_servicios, minutos)}


async def perfil(pool, z: dict) -> dict | None:
    async with pool.connection() as conn:
        b = await base(conn, z)
        if b is None:
            return None
        resuelta, muns, entera, censo = b["resuelta"], b["muns"], b["entera"], b["censo"]
        uno = muns[0] if len(muns) == 1 else None
        viv = vivienda(censo)
        if viv is not None:
            viv["precio"] = await _precio_enteros(conn, muns) if entera else await precio_oferta(conn, b["lugares"])
            viv["tenencia"] = await tenencia(conn, resuelta["municipios"])
        # Los delitos son de los municipios: su tasa va sobre la gente de los municipios.
        de_muns = b["lugares"] if entera else await lugares_enteros(conn, muns)
        salida = {
            "zona": {**resuelta, "entera": entera},
            "agebs": sum(u["tipo"] == "ageb" and u["peso"] >= BORDE for u in b["lugares"]),
            "localidades": sum(u["tipo"] == "localidad" for u in b["lugares"]),
            "demografia": demografia(censo, b["km2"], entera),
            "rezago_social": await rezago(conn, None if entera else b["lugares"], muns),
            "vivienda": viv,
            "servicios": b["servicios"],
            "comercio": await negocios(conn, z, muns, entera),
            "economia": await economia(conn, muns),
            "consumo": await consumo(conn, muns),
            "seguridad": await seguridad(conn, muns, Censo([(u["d"], 1.0) for u in de_muns]).total("POBTOT")),
            "plano": await plano(conn, z, resuelta, entera),
        }
        if uno is None:
            salida |= {"empleo_formal": await empleo(conn, muns),
                       "hacienda": await hacienda_varios(conn, resuelta["municipios"]),
                       "planeacion": await planeacion_varios(conn, muns)}
    # Estas piden su propia conexión: con la de arriba tomada, se quedarían esperando.
    if uno is not None:
        salida |= {"empleo_formal": await imss_asegurados.empleo_municipio(pool, uno[:2], uno[2:]),
                   "hacienda": await efipem.municipio(pool, uno[:2], uno[2:]),
                   "planeacion": await cngmd.municipio(pool, uno[:2], uno[2:])}
    estados = resuelta["estados"]
    salida["laboral"] = await consultas.laboral_de(pool, estados[0]) if len(estados) == 1 else None
    return salida
