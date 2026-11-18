"""Distancia de renglones de un equipo a las localidades del censo (ITER 2020).

Mapo manda las geometrías de los renglones en la petición, como en el cruce, y
aquí no se guardan. Mismo método que la distancia entre capas de Mapo
(`Mapo.Capas.Distancias`): el índice da un candidato en grados, su distancia en
metros sobre el elipsoide acota una caja, y dentro de la caja gana el de menos
metros. Ver docs/fuentes/localidades.md.
"""

from __future__ import annotations

import json

from psycopg_pool import AsyncConnectionPool

# Metros por grado, cota baja en México (latitud de 35° o menos).
POR_GRADO = 91_000.0

_FILTRO = "(%(ambito)s::text IS NULL OR l.ambito = %(ambito)s)"

CONSULTA = f"""
WITH g AS (
    SELECT t.id, ST_SetSRID(ST_GeomFromGeoJSON(t.gj), 4326) AS geom
    FROM unnest(%(ids)s::bigint[], %(geometrias)s::text[]) AS t(id, gj)
)
SELECT g.id, d.metros, d.cvegeo, d.nombre, d.nom_mun, d.ambito, d.pobtot, c.cuantos, c.poblacion
FROM g
LEFT JOIN LATERAL (
    SELECT ST_Distance(g.geom::geography, l.geom::geography) AS tope
    FROM localidades l WHERE {_FILTRO}
    ORDER BY g.geom <-> l.geom LIMIT 1
) cand ON true
LEFT JOIN LATERAL (
    SELECT ST_Distance(g.geom::geography, l.geom::geography) AS metros,
           l.cvegeo, l.nombre, l.nom_mun, l.ambito, l.pobtot
    FROM localidades l
    WHERE {_FILTRO} AND l.geom && ST_Expand(g.geom, cand.tope / {POR_GRADO})
    ORDER BY metros, l.id LIMIT 1
) d ON true
LEFT JOIN LATERAL (
    SELECT count(*) AS cuantos, sum(l.pobtot) AS poblacion
    FROM localidades l
    WHERE %(radio)s::float8 IS NOT NULL AND {_FILTRO}
      AND l.geom && ST_Expand(g.geom, %(radio)s::float8 / {POR_GRADO})
      AND ST_DWithin(g.geom::geography, l.geom::geography, %(radio)s::float8)
) c ON true
ORDER BY g.id
"""


async def distancia(
    pool: AsyncConnectionPool, filas: list[dict], radio: float | None, ambito: str | None
) -> dict:
    """`filas` es `[{id, geometria}]` con la geometría en GeoJSON. Regresa una
    fila por renglón y cuántas localidades entraron al cálculo."""
    params = {
        "ids": [f["id"] for f in filas],
        "geometrias": [json.dumps(f["geometria"]) for f in filas],
        "radio": radio,
        "ambito": ambito,
    }
    async with pool.connection() as conn:
        cursor = await conn.execute(
            f"SELECT count(*) FROM localidades l WHERE {_FILTRO}", {"ambito": ambito}
        )
        (total,) = await cursor.fetchone()
        if total == 0:
            return {"filas": [], "localidades": 0}
        cursor = await conn.execute(CONSULTA, params)
        resultado = await cursor.fetchall()

    campos = ["id", "metros", "cvegeo", "nombre", "nom_mun", "ambito", "pobtot", "cuantos", "poblacion"]
    salida = []
    for fila in resultado:
        d = dict(zip(campos, fila))
        d["metros"] = None if d["metros"] is None else round(d["metros"])
        if radio is None:
            d["cuantos"] = d["poblacion"] = None
        else:
            d["poblacion"] = int(d["poblacion"] or 0)
        salida.append(d)
    return {"filas": salida, "localidades": total}
