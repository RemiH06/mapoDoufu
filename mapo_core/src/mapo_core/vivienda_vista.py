"""Vista de precios de vivienda: municipios de un estado coloreados por un
indicador de una sola fuente, y la ficha de un municipio con las cuatro
fuentes por separado (docs/producto/vista-vivienda.md).

Ninguna fuente da el precio de una zona (docs/historial/2026-11-fuentes-vivienda.md):
el SHF es cambio, no nivel; el SNIIV es lo prestado; la EIC no pregunta montos
y la ENVI solo llega a estado. Por eso cada indicador viaja con su fuente, su
nivel y su `metodo`, y nunca se juntan en un número.
"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from mapo_core import zona as zona_comun
from mapo_core.consultas import TOLERANCIA_SIMPLIFICACION, dibujo, feature
from mapo_core.precio_estimado import OBSERVADAS

SEGMENTOS = ["Económica", "Popular", "Tradicional", "Media", "Residencial", "Residencial plus", "No disponible"]

# clave -> (fuente, etiqueta, unidad, metodo). La clave es lo único que llega
# del navegador; nunca se interpola otra cosa en el SQL.
INDICADORES: dict[str, dict] = {
    "eic_alqui": {
        "fuente": "INEGI · Intercensal 2025",
        "etiqueta": "Viviendas rentadas",
        "unidad": "% de las habitadas",
        "eic": "PCN_VPH_ALQUI",
    },
    "eic_propia": {
        "fuente": "INEGI · Intercensal 2025",
        "etiqueta": "Viviendas propias",
        "unidad": "% de las habitadas",
        "eic": "PCN_VPH_PROPIA",
    },
    "eic_prest": {
        "fuente": "INEGI · Intercensal 2025",
        "etiqueta": "Viviendas prestadas",
        "unidad": "% de las habitadas",
        "eic": "PCN_VPH_PREST",
    },
    "eic_noescri": {
        "fuente": "INEGI · Intercensal 2025",
        "etiqueta": "Propias sin escrituras",
        "unidad": "% de las propias",
        "eic": "PCN_VPH_NOESCRI",
    },
    "eic_propresi": {
        "fuente": "INEGI · Intercensal 2025",
        "etiqueta": "Propias escrituradas a nombre de quien vive ahí",
        "unidad": "% de las propias",
        "eic": "PCN_VPH_PROPRESI",
    },
    "sniiv_acciones": {
        "fuente": "SNIIV · Financiamientos",
        "etiqueta": "Créditos y subsidios otorgados",
        "unidad": "acciones en el año",
    },
    "sniiv_promedio": {
        "fuente": "SNIIV · Financiamientos",
        "etiqueta": "Monto promedio por acción",
        "unidad": "miles de pesos",
    },
    "shf_anual": {
        "fuente": "SHF · Índice de precios de la vivienda",
        "etiqueta": "Cambio del índice SHF en un año",
        "unidad": "%",
    },
    # Por AGEB, no por municipio: la mediana de anuncios donde hay y un rango
    # donde no (docs/producto/precio-estimado.md).
    "precio_ageb": {
        "fuente": "IIEG, anuncios de venta · Mapo",
        "etiqueta": "Precio de oferta",
        "unidad": "pesos por vivienda, julio de 2024",
    },
}

EIC_FICHA = [
    ("VIVPARHAB", "Viviendas particulares habitadas", "viviendas"),
    ("PCN_VPH_PROPIA", "Propias", "% de las habitadas"),
    ("PCN_VPH_ALQUI", "Rentadas", "% de las habitadas"),
    ("PCN_VPH_PREST", "Prestadas", "% de las habitadas"),
    ("PCN_VPH_OTRASIT", "Otra situación", "% de las habitadas"),
    ("PCN_VPH_PROPRESI", "Escritura a nombre de quien vive ahí", "% de las propias"),
    ("PCN_VPH_PERNORES", "Escritura a nombre de otra persona", "% de las propias"),
    ("PCN_VPH_NOESCRI", "Sin escrituras", "% de las propias"),
    ("PCN_VPH_ESCRIDES", "Se desconoce", "% de las propias"),
]

ENVI_FICHA = [
    ("pct_rentadas", "Viviendas rentadas", "%"),
    ("pct_rentadas_con_contrato", "Rentadas con contrato", "% de las rentadas"),
    ("renta_mensual_media", "Renta mensual, media", "pesos"),
    ("renta_mensual_mediana", "Renta mensual, mediana", "pesos"),
    ("valor_estimado_mediana", "Valor estimado de la vivienda propia, mediana", "pesos"),
]


def catalogo() -> dict:
    return {
        "indicadores": [{"clave": k, **{c: v[c] for c in ("fuente", "etiqueta", "unidad")}} for k, v in INDICADORES.items()],
        "segmentos": SEGMENTOS,
    }


async def anios_sniiv(pool: AsyncConnectionPool) -> list[dict]:
    async with pool.connection() as conn:
        cursor = await conn.execute(
            "SELECT anio, max(meses) FROM fuente_sniiv_financiamiento GROUP BY anio ORDER BY anio DESC"
        )
        return [{"anio": a, "meses": m} for a, m in await cursor.fetchall()]


async def _geometrias(conn, cve_ent: str) -> list[tuple[str, str, str, str]]:
    cursor = await conn.execute(
        f"SELECT cvegeo, cve_mun, nombre, ST_AsGeoJSON({dibujo(param='t')}, 5) "
        "FROM municipios WHERE cve_ent = %(cve_ent)s ORDER BY cvegeo",
        {"cve_ent": cve_ent, "t": TOLERANCIA_SIMPLIFICACION},
    )
    return await cursor.fetchall()


async def _valores_eic(conn, cve_ent: str, codigo: str) -> dict[str, dict]:
    cursor = await conn.execute(
        """SELECT cve_mun, valor, cv, lim_inf, lim_sup, nota FROM fuente_eic2025_vivienda
           WHERE nivel = 'municipio' AND cve_ent = %(cve_ent)s AND indicador = %(ind)s""",
        {"cve_ent": cve_ent, "ind": codigo},
    )
    return {
        m: {"valor": v, "cv": cv, "lim_inf": li, "lim_sup": ls, "nota": nota}
        for m, v, cv, li, ls, nota in await cursor.fetchall()
    }


async def _valores_sniiv(conn, cve_ent: str, anio: int, segmento: str | None, promedio: bool) -> dict[str, dict]:
    cursor = await conn.execute(
        # El promedio solo con filas que traen monto: buena parte de los
        # mejoramientos llegan con monto 0 (docs/fuentes/sniiv.md).
        """SELECT cve_mun, sum(acciones), sum(monto), max(meses),
                  sum(acciones) FILTER (WHERE monto > 0)
           FROM fuente_sniiv_financiamiento
           WHERE cve_ent = %(cve_ent)s AND anio = %(anio)s AND cve_mun <> '000'
             AND (%(seg)s::text IS NULL OR valor_vivienda = %(seg)s)
           GROUP BY cve_mun""",
        {"cve_ent": cve_ent, "anio": anio, "seg": segmento},
    )
    out = {}
    for m, acciones, monto, meses, con_monto in await cursor.fetchall():
        valor = (round(monto / con_monto / 1000, 1) if con_monto else None) if promedio else acciones
        out[m] = {"valor": valor, "acciones": acciones, "meses": meses}
    return out


async def _valores_shf(conn, cve_ent: str) -> dict[str, dict]:
    """Cambio del último trimestre contra el mismo trimestre un año antes."""
    cursor = await conn.execute(
        """WITH ultimo AS (
             SELECT clave, max(anio * 10 + trimestre) AS t FROM fuente_shf_ipv
             WHERE nivel = 'municipio' AND categoria = 'General' AND clave LIKE %(pref)s
             GROUP BY clave)
           SELECT substr(u.clave, 3), a.anio, a.trimestre, a.indice, b.indice
           FROM ultimo u
           JOIN fuente_shf_ipv a ON a.nivel = 'municipio' AND a.categoria = 'General'
             AND a.clave = u.clave AND a.anio * 10 + a.trimestre = u.t
           LEFT JOIN fuente_shf_ipv b ON b.nivel = 'municipio' AND b.categoria = 'General'
             AND b.clave = u.clave AND b.anio = a.anio - 1 AND b.trimestre = a.trimestre""",
        {"pref": f"{cve_ent}%"},
    )
    return {
        m: {"valor": (ia / ib - 1) * 100 if ib else None, "periodo": f"{anio}T{tri}"}
        for m, anio, tri, ia, ib in await cursor.fetchall()
    }


def _metodo(clave: str, anio: int | None, meses: int | None, segmento: str | None, periodo: str | None) -> str:
    if clave == "precio_ageb":
        return ("Precio pedido por vivienda (casas y departamentos) en los anuncios de venta que junta el "
                "IIEG, julio de 2024; no es precio de cierre ni avalúo. Donde la AGEB tiene al menos tres "
                "anuncios, su mediana, y solo esas se colorean. Donde no, un rango con 80 % de cobertura "
                "medida contra los anuncios en AGEB que el modelo no vio: va con borde punteado, sin "
                "color salvo que el rango entero caiga en una clase (entonces tenue), y el rango sale "
                "al tocarla. El IIEG cubre seis municipios de la zona "
                "metropolitana de Guadalajara; los demás quedan sin dato.")
    if clave.startswith("eic_"):
        return ("Estimación por muestra de la Intercensal 2025, por municipio. Cada valor trae su "
                "coeficiente de variación; MI es muestra insuficiente y queda sin dato.")
    if clave.startswith("sniiv_"):
        parte = f"{anio}, {meses} de 12 meses" if meses and meses < 12 else f"{anio}"
        seg = f"segmento {segmento}" if segmento else "todos los segmentos"
        base = (f"Suma de lo registrado en el SNIIV ({parte}; {seg}; todos los organismos y destinos). "
                "Es lo prestado o subsidiado, no el precio de la vivienda.")
        if clave == "sniiv_promedio":
            base += (" Promedio = monto entre las acciones que traen monto, en miles de pesos: "
                     "muchos mejoramientos llegan con monto 0 y no cuentan.")
        return base
    return (f"Variación del índice SHF (2018 = 100) de {periodo or 'el último trimestre'} contra el mismo "
            "trimestre un año antes. Es cambio, no nivel: SHF lo publica solo para 74 municipios del país.")


async def _precio_agebs(pool: AsyncConnectionPool, estados: list[str], zona: dict | None) -> list[dict]:
    # Con zona, solo las AGEB con su punto de dentro en ella (zona.py).
    params = {"estados": estados, "t": TOLERANCIA_SIMPLIFICACION}
    previo, donde = "", ""
    if zona is not None:
        cte, condicion, extra = zona_comun.filtro_agebs(zona)
        previo = f"WITH {cte} " if cte else ""
        donde = f" AND {condicion}"
        params |= extra
    async with pool.connection() as conn:
        cursor = await conn.execute(
            f"""{previo}SELECT p.cvegeo, a.cve_ageb, m.nombre, p.cve_mun, p.fuente, p.valor, p.rango_bajo,
                      p.rango_alto, p.anio_tabla, p.cobertura, p.n_base, p.version, p.metodo,
                      -- Ni la cobertura ni ST_Simplify con true pierden una AGEB más
                      -- chica que la tolerancia (24 de la ZMG).
                      ST_AsGeoJSON({dibujo('a', 't')}, 5)
               FROM fuente_precio_estimado p
               JOIN agebs a ON a.cvegeo = p.cvegeo
               LEFT JOIN municipios m ON m.cve_ent = p.cve_ent AND m.cve_mun = p.cve_mun
               WHERE p.cve_ent = ANY(%(estados)s){donde} ORDER BY p.cvegeo""",
            params,
        )
        filas = await cursor.fetchall()
    features = []
    for cvegeo, ageb, mun, cve_mun, fuente, valor, bajo, alto, anio, cob, n, version, metodo, geom in filas:
        if geom is None:
            continue
        # Solo lo observado pinta. Un rango estimado no se vuelve color: su punto
        # medio pasaría por dato (docs/producto/precio-estimado.md).
        color = round(valor) if fuente in OBSERVADAS else None
        props = {"cve_ent": cvegeo[:2], "cve_mun": cve_mun, "valor_choropleth": color, "fuente": fuente,
                 "valor": valor, "rango_bajo": bajo, "rango_alto": alto, "anio_tabla": anio,
                 "cobertura": cob, "n_base": n, "version": version,
                 "metodo": metodo if fuente == "sin_base" else None}
        features.append(feature(cvegeo, f"AGEB {ageb}, {mun or cve_mun}", geom,
                                {k: v for k, v in props.items() if v is not None}))
    return features


async def municipios(
    pool: AsyncConnectionPool, estados: str | list[str], clave: str, anio: int | None = None,
    segmento: str | None = None, zona: dict | None = None,
) -> dict:
    """El indicador `clave` en los municipios de uno o varios estados (los que toca la
    zona: un municipio necesita a sus vecinos para leerse por quintiles), o en las AGEB
    de la zona si es el precio por AGEB. Cada municipio trae su `cve_ent`."""
    if clave not in INDICADORES:
        raise ValueError(f"indicador inválido: {clave}")
    estados = [estados] if isinstance(estados, str) else list(estados)
    if clave == "precio_ageb":
        ind = INDICADORES[clave]
        features = await _precio_agebs(pool, estados, zona)
        return {
            "type": "FeatureCollection",
            "features": features,
            "indicador": {"clave": clave, **{c: ind[c] for c in ("fuente", "etiqueta", "unidad")}},
            "nivel": "AGEB",
            "anio": None,
            "meses": None,
            "segmento": None,
            "metodo": _metodo(clave, None, None, None, None),
            # Versión de la tabla del estudio, para que la cita se pueda reproducir.
            "version": ", ".join(sorted({f["properties"]["version"] for f in features})) or None,
        }
    if segmento is not None and segmento not in SEGMENTOS:
        raise ValueError(f"segmento inválido: {segmento}")
    ind = INDICADORES[clave]
    meses = periodo = None
    features = []
    async with pool.connection() as conn:
        if clave.startswith("sniiv_") and anio is None:
            cursor = await conn.execute("SELECT max(anio) FROM fuente_sniiv_financiamiento WHERE meses = 12")
            (anio,) = await cursor.fetchone()
        for cve_ent in estados:
            geoms = await _geometrias(conn, cve_ent)
            if clave.startswith("eic_"):
                valores = await _valores_eic(conn, cve_ent, ind["eic"])
            elif clave.startswith("sniiv_"):
                valores = await _valores_sniiv(conn, cve_ent, anio, segmento, clave == "sniiv_promedio")
                meses = max([meses or 0, *(v["meses"] for v in valores.values())]) or None
            else:
                valores = await _valores_shf(conn, cve_ent)
                periodo = periodo or next((v["periodo"] for v in valores.values()), None)

            for cvegeo, cve_mun, nombre, geom in geoms:
                if geom is None:
                    continue
                v = valores.get(cve_mun, {})
                extra = {k: v.get(k) for k in ("cv", "lim_inf", "lim_sup", "nota", "acciones") if v.get(k) is not None}
                features.append(feature(cvegeo, nombre, geom,
                                        {"cve_ent": cve_ent, "cve_mun": cve_mun, "valor_choropleth": v.get("valor"), **extra}))

    return {
        "type": "FeatureCollection",
        "features": features,
        "indicador": {"clave": clave, **{c: ind[c] for c in ("fuente", "etiqueta", "unidad")}},
        "nivel": "municipio",
        "anio": anio,
        "meses": meses,
        "segmento": segmento,
        "metodo": _metodo(clave, anio, meses, segmento, periodo),
    }


async def ficha(pool: AsyncConnectionPool, cve_ent: str, cve_mun: str) -> dict | None:
    """Las cuatro fuentes de un municipio, cada una con su nivel. None si el
    municipio no está en la base."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            "SELECT nombre FROM municipios WHERE cve_ent = %(e)s AND cve_mun = %(m)s", {"e": cve_ent, "m": cve_mun}
        )
        fila = await cursor.fetchone()
        if fila is None:
            return None

        # SHF: la serie del municipio si SHF la publica; si no, la del estado, dicho.
        shf = None
        for nivel, clave in (("municipio", cve_ent + cve_mun), ("estado", cve_ent)):
            cursor = await conn.execute(
                """SELECT nombre, anio, trimestre, indice FROM fuente_shf_ipv
                   WHERE nivel = %(n)s AND clave = %(c)s AND categoria = 'General'
                   ORDER BY anio, trimestre""",
                {"n": nivel, "c": clave},
            )
            serie = await cursor.fetchall()
            if serie:
                ultimo = serie[-1]
                antes = next((s for s in serie if s[1] == ultimo[1] - 1 and s[2] == ultimo[2]), None)
                shf = {
                    "nivel": nivel,
                    "nombre": ultimo[0],
                    "serie": [[a, t, round(i, 2)] for _n, a, t, i in serie],
                    "ultimo": {"anio": ultimo[1], "trimestre": ultimo[2], "indice": round(ultimo[3], 2)},
                    "variacion_anual": round((ultimo[3] / antes[3] - 1) * 100, 2) if antes else None,
                }
                break

        cursor = await conn.execute(
            """SELECT max(anio) FROM fuente_sniiv_financiamiento
               WHERE cve_ent = %(e)s AND cve_mun = %(m)s AND meses = 12""",
            {"e": cve_ent, "m": cve_mun},
        )
        (anio,) = await cursor.fetchone()
        sniiv = None
        if anio is not None:
            cursor = await conn.execute(
                """SELECT valor_vivienda, sum(acciones), sum(monto),
                          sum(acciones) FILTER (WHERE monto > 0)
                   FROM fuente_sniiv_financiamiento
                   WHERE cve_ent = %(e)s AND cve_mun = %(m)s AND anio = %(a)s
                   GROUP BY valor_vivienda""",
                {"e": cve_ent, "m": cve_mun, "a": anio},
            )
            por = {s: (a, m, c) for s, a, m, c in await cursor.fetchall()}
            cursor = await conn.execute(
                """SELECT destino_credito, sum(acciones) FROM fuente_sniiv_financiamiento
                   WHERE cve_ent = %(e)s AND cve_mun = %(m)s AND anio = %(a)s
                   GROUP BY destino_credito ORDER BY sum(acciones) DESC LIMIT 4""",
                {"e": cve_ent, "m": cve_mun, "a": anio},
            )
            destinos = [[d, a] for d, a in await cursor.fetchall()]
            sniiv = {
                "anio": anio,
                "segmentos": [
                    {"segmento": s, "acciones": por[s][0], "monto": por[s][1], "con_monto": por[s][2] or 0,
                     "promedio": por[s][1] / por[s][2] if por[s][2] else None}
                    for s in SEGMENTOS if s in por
                ],
                "destinos": destinos,
            }

        cursor = await conn.execute(
            """SELECT indicador, valor, cv, lim_inf, lim_sup, nota FROM fuente_eic2025_vivienda
               WHERE nivel = 'municipio' AND cve_ent = %(e)s AND cve_mun = %(m)s
                 AND indicador = ANY(%(i)s)""",
            {"e": cve_ent, "m": cve_mun, "i": [c for c, _e, _u in EIC_FICHA]},
        )
        eic_filas = {i: (v, cv, li, ls, n) for i, v, cv, li, ls, n in await cursor.fetchall()}

        cursor = await conn.execute(
            """SELECT indicador, valor, error_estandar, n_muestra FROM fuente_envi2020_entidad
               WHERE cve_ent = %(e)s AND indicador = ANY(%(i)s)""",
            {"e": cve_ent, "i": [c for c, _e, _u in ENVI_FICHA]},
        )
        envi_filas = {i: (v, ee, n) for i, v, ee, n in await cursor.fetchall()}

    eic = [
        {"indicador": c, "etiqueta": e, "unidad": u, "valor": f[0], "cv": f[1], "lim_inf": f[2], "lim_sup": f[3], "nota": f[4]}
        for c, e, u in EIC_FICHA if (f := eic_filas.get(c))
    ]
    envi = [
        {"indicador": c, "etiqueta": e, "unidad": u, "valor": f[0], "error_estandar": f[1], "n_muestra": f[2]}
        for c, e, u in ENVI_FICHA if (f := envi_filas.get(c))
    ]
    return {
        "cve_ent": cve_ent,
        "cve_mun": cve_mun,
        "nombre": fila[0],
        "shf": shf,
        "sniiv": sniiv,
        "eic": eic or None,
        "envi": envi or None,
    }
