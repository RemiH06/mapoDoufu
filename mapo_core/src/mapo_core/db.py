"""Conexion a la Postgres/PostGIS compartida con mapo (Elixir/Ecto).

mapo_core es dueno de sus propias tablas en esa misma base (nombres
que no chocan con las de Ecto: users, teams, team_memberships,
sesiones, anotaciones, invitaciones), sin pasar por Ecto para nada:
cada quien administra su parte con su propia herramienta. Sin ORM a
proposito, igual que el resto de mapo_core (vrp.py/isocronas.py/
voronoi.py son funciones + dataclasses directas, no un framework
pesado): SQL directo, funciones nativas de PostGIS.

Los poligonos viven directo en una columna `geometry`, no como ruta a
un archivo en disco (a diferencia del `geom_path` que usa Gaiarda):
un solo dato, fuente de verdad, sin necesitar un volumen aparte para
mapo_core (que hoy no tiene ninguno). La simplificacion para que
Leaflet no se ponga lento con demasiados vertices se aplica al leer
(`ST_Simplify` en la consulta), no al guardar.
"""

from __future__ import annotations

import os

from psycopg_pool import AsyncConnectionPool

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS entidades (
    cve_ent      TEXT PRIMARY KEY,
    nombre       TEXT NOT NULL,
    geom         geometry(MultiPolygon, 4326),
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_entidades_geom ON entidades USING GIST (geom);

CREATE TABLE IF NOT EXISTS municipios (
    cvegeo       TEXT PRIMARY KEY,
    cve_ent      TEXT NOT NULL,
    cve_mun      TEXT NOT NULL,
    nombre       TEXT NOT NULL,
    pob_total    INTEGER,
    geom         geometry(MultiPolygon, 4326),
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cve_ent, cve_mun)
);
CREATE INDEX IF NOT EXISTS idx_municipios_ent  ON municipios (cve_ent);
CREATE INDEX IF NOT EXISTS idx_municipios_geom ON municipios USING GIST (geom);

CREATE TABLE IF NOT EXISTS agebs (
    cvegeo       TEXT PRIMARY KEY,
    cve_ent      TEXT NOT NULL,
    cve_mun      TEXT NOT NULL,
    cve_loc      TEXT,
    cve_ageb     TEXT NOT NULL,
    ambito       TEXT,
    geom         geometry(MultiPolygon, 4326),
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agebs_mun  ON agebs (cve_ent, cve_mun);
CREATE INDEX IF NOT EXISTS idx_agebs_geom ON agebs USING GIST (geom);

CREATE TABLE IF NOT EXISTS fuente_censo_poblacion (
    cvegeo       TEXT PRIMARY KEY,
    nivel        TEXT NOT NULL,
    cve_ent      TEXT NOT NULL,
    cve_mun      TEXT,
    cve_loc      TEXT,
    cve_ageb     TEXT,
    nombre       TEXT,
    pobtot INTEGER, pobfem INTEGER, pobmas INTEGER,
    p_0a2 INTEGER, p_3a5 INTEGER, p_6a11 INTEGER, p_12a14 INTEGER,
    p_15a17 INTEGER, p_18a24 INTEGER, p_60ymas INTEGER,
    graproes REAL,
    pea INTEGER, pea_f INTEGER, pea_m INTEGER, pe_inac INTEGER,
    pocupada INTEGER, pdesocup INTEGER,
    pder_ss INTEGER,
    tothog INTEGER, vivtot INTEGER, tvivhab INTEGER, prom_ocup REAL,
    vph_inter INTEGER, vph_pc INTEGER, vph_autom INTEGER, vph_cel INTEGER, vph_snbien INTEGER,
    datos_json   JSONB NOT NULL,
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_censo_nivel   ON fuente_censo_poblacion (nivel);
CREATE INDEX IF NOT EXISTS idx_censo_cve_ent ON fuente_censo_poblacion (cve_ent);
CREATE INDEX IF NOT EXISTS idx_censo_cve_mun ON fuente_censo_poblacion (cve_ent, cve_mun);

CREATE TABLE IF NOT EXISTS descargas_checkpoint (
    clave         TEXT PRIMARY KEY,
    completado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _conninfo() -> str:
    host = os.environ.get("DATABASE_HOST", "localhost")
    dbname = os.environ.get("DATABASE_NAME", "mapo_dev")
    user = os.environ.get("DATABASE_USER", "postgres")
    password = os.environ.get("DATABASE_PASSWORD", "postgres")
    return f"host={host} dbname={dbname} user={user} password={password}"


_pool: AsyncConnectionPool | None = None


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(_conninfo(), open=False)
        await _pool.open()
    return _pool


async def cerrar_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def inicializar_esquema(pool: AsyncConnectionPool | None = None) -> None:
    pool = pool or await get_pool()
    async with pool.connection() as conn:
        await conn.execute(SCHEMA)


async def esta_hecho(conn, clave: str) -> bool:
    cursor = await conn.execute(
        "SELECT 1 FROM descargas_checkpoint WHERE clave = %(clave)s", {"clave": clave}
    )
    return await cursor.fetchone() is not None


async def marcar_hecho(conn, clave: str) -> None:
    await conn.execute(
        """INSERT INTO descargas_checkpoint (clave) VALUES (%(clave)s)
           ON CONFLICT (clave) DO UPDATE SET completado_en = now()""",
        {"clave": clave},
    )
