"""Fixtures compartidos: conexion real a `mapo_test` (la misma base
que ya usa `mapo`/Ecto para sus propios tests), no mocks. Cada test
que use el fixture `conn` corre en su propia transaccion, revertida al
final (mismo espiritu que `Ecto.Adapters.SQL.Sandbox`): no deja
basura entre tests, y no choca con los tests de Elixir corriendo en
paralelo (tablas distintas, misma base).
"""

from __future__ import annotations

import os

import pytest_asyncio
from psycopg_pool import AsyncConnectionPool

from mapo_core.db import SCHEMA

os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_USER", "postgres")
os.environ.setdefault("DATABASE_PASSWORD", "postgres")
# Los tests SIEMPRE usan mapo_test, sin importar que DATABASE_NAME ya
# venga fijado a mapo_dev en el entorno del contenedor (docker-compose.yml
# lo pone ahi para que el servidor de verdad sirva datos reales). Un
# setdefault no bastaria: DATABASE_NAME ya esta presente, nunca se
# activaria. Sin este override, los tests escribirian directo sobre
# los datos reales ya descargados (paso una vez, se detecto rapido
# porque trono con una llave duplicada, no se perdio nada, pero no
# puede volver a pasar).
os.environ["DATABASE_NAME"] = "mapo_test"


def _conninfo() -> str:
    return (
        f"host={os.environ['DATABASE_HOST']} dbname={os.environ['DATABASE_NAME']} "
        f"user={os.environ['DATABASE_USER']} password={os.environ['DATABASE_PASSWORD']}"
    )


@pytest_asyncio.fixture(scope="session")
async def _pool():
    pool = AsyncConnectionPool(_conninfo(), open=False)
    await pool.open()
    async with pool.connection() as conn:
        await conn.execute(SCHEMA)
        await conn.commit()
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def conn(_pool):
    """Una conexion de la base de test, con lo que se inserte en el
    test revertido al salir."""
    async with _pool.connection() as connection:
        yield connection
        await connection.rollback()


@pytest_asyncio.fixture
async def pool_de_una_conexion(conn):
    """Para tests de endpoints (FastAPI): un pool falso de una sola
    conexion, la misma que ya trae datos de prueba insertados por el
    test (via el fixture `conn`), para que el endpoint SI vea esos
    datos (con dos pools/conexiones distintas, uno con datos sin
    commitear, el otro no los veria: aislamiento de transacciones de
    Postgres). Se inyecta con `app.dependency_overrides[get_pool]`."""

    class _PoolDeUnaConexion:
        def connection(self):
            return _ConexionSinCerrar(conn)

    class _ConexionSinCerrar:
        def __init__(self, connection):
            self._connection = connection

        async def __aenter__(self):
            return self._connection

        async def __aexit__(self, *_exc):
            return False

    return _PoolDeUnaConexion()
