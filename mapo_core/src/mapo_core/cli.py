"""CLI de mapo_core para descargar sus propios datos geograficos/censo,
vendorizado del patron de linea de comandos de Gaiarda (argparse
plano, sin framework de CLI aparte). Se corre con:

    docker compose exec mapo_core python -m mapo_core.cli <comando>
"""

from __future__ import annotations

import argparse
import asyncio

from mapo_core import censo_downloader, geo_downloader
from mapo_core.db import cerrar_pool, get_pool, inicializar_esquema


async def _estados(_args) -> None:
    await inicializar_esquema()
    total = await geo_downloader.descargar_estados()
    print(f"{total} estados guardados/actualizados.")


async def _municipios(args) -> None:
    await inicializar_esquema()
    total = await geo_downloader.descargar_municipios(cve_ent=args.estado)
    print(f"{total} municipios guardados/actualizados.")


async def _agebs(args) -> None:
    await inicializar_esquema()
    total = await geo_downloader.descargar_agebs(cve_ent=args.estado)
    print(f"{total} AGEBs guardados/actualizados.")


async def _censo_poblacion(args) -> None:
    if not args.estado:
        raise SystemExit("censo_poblacion requiere --estado (el zip es por estado, no nacional)")
    await inicializar_esquema()
    total = await censo_downloader.descargar_estado(args.estado)
    print(f"{total} filas de censo guardadas/actualizadas para el estado {args.estado}.")


async def _status(_args) -> None:
    await inicializar_esquema()
    pool = await get_pool()
    tablas = ["entidades", "municipios", "agebs", "fuente_censo_poblacion"]
    async with pool.connection() as conn:
        for tabla in tablas:
            cursor = await conn.execute(f"SELECT count(*) FROM {tabla}")
            (total,) = await cursor.fetchone()
            print(f"{tabla}: {total} filas")


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mapo_core.cli")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    subparsers.add_parser("estados", help="Descarga los 32 estados con su poligono").set_defaults(fn=_estados)

    p_municipios = subparsers.add_parser("municipios", help="Descarga municipios con su poligono")
    p_municipios.add_argument("--estado", default=None, help="cve_ent, ej. 14 (default: los 32)")
    p_municipios.set_defaults(fn=_municipios)

    p_agebs = subparsers.add_parser("agebs", help="Descarga AGEBs urbanas con su poligono")
    p_agebs.add_argument("--estado", default=None, help="cve_ent, ej. 14 (default: los 32, pesado)")
    p_agebs.set_defaults(fn=_agebs)

    p_censo = subparsers.add_parser("censo_poblacion", help="Descarga el censo de poblacion de un estado")
    p_censo.add_argument("--estado", required=True, help="cve_ent, ej. 14 (obligatorio)")
    p_censo.set_defaults(fn=_censo_poblacion)

    subparsers.add_parser("status", help="Cuenta filas por tabla").set_defaults(fn=_status)

    return parser


async def _main_async() -> None:
    parser = _construir_parser()
    args = parser.parse_args()
    try:
        await args.fn(args)
    finally:
        await cerrar_pool()


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
