"""CLI de mapo_core para descargar sus propios datos geograficos/censo,
vendorizado del patron de linea de comandos de Gaiarda (argparse
plano, sin framework de CLI aparte). Se corre con:

    docker compose exec mapo_core python -m mapo_core.cli <comando>
"""

from __future__ import annotations

import argparse
import asyncio

from mapo_core import (
    censo_downloader,
    denue_downloader,
    enigh_downloader,
    enoe_downloader,
    geo_downloader,
    sesnsp_ingesta,
)
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


async def _denue(args) -> None:
    await inicializar_esquema()
    try:
        total = await denue_downloader.descargar_estado(args.estado, token=args.token)
    except denue_downloader.TokenFaltante as exc:
        raise SystemExit(str(exc)) from None
    print(f"{total} negocios guardados/actualizados para el estado {args.estado}.")


async def _enigh(_args) -> None:
    await inicializar_esquema()
    total = await enigh_downloader.descargar()
    print(f"{total} hogares de ENIGH (concentradohogar) guardados/actualizados.")


async def _sesnsp(args) -> None:
    await inicializar_esquema()
    total = await sesnsp_ingesta.cargar_archivo(args.archivo)
    print(f"{total} filas de incidencia delictiva guardadas/actualizadas desde {args.archivo}.")


async def _enoe(args) -> None:
    await inicializar_esquema()
    try:
        total = await enoe_downloader.descargar_trimestre(args.anio, args.trimestre)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print(f"{total} entidades con tasa de desocupacion guardada/actualizada para {args.anio} {args.trimestre}.")


async def _status(_args) -> None:
    await inicializar_esquema()
    pool = await get_pool()
    tablas = [
        "entidades", "municipios", "agebs", "fuente_censo_poblacion",
        "fuente_denue_negocios", "fuente_enigh_concentradohogar", "fuente_sesnsp_delitos_municipal",
        "fuente_enoe_tasa_desocupacion",
    ]
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

    p_denue = subparsers.add_parser("denue", help="Descarga los negocios de DENUE de un estado")
    p_denue.add_argument("--estado", required=True, help="cve_ent, ej. 14 (obligatorio)")
    p_denue.add_argument(
        "--token", default=None, help="Token de INEGI (default: variable de entorno GAIARDA_DENUE_TOKEN)"
    )
    p_denue.set_defaults(fn=_denue)

    subparsers.add_parser(
        "enigh", help="Descarga concentradohogar de ENIGH (consumo, tabla nacional unica)"
    ).set_defaults(fn=_enigh)

    p_sesnsp = subparsers.add_parser(
        "sesnsp",
        help="Carga incidencia delictiva municipal desde un CSV descargado a mano (sin endpoint publico automatizable)",
    )
    p_sesnsp.add_argument("--archivo", required=True, help="Ruta al CSV de SESNSP ya descargado")
    p_sesnsp.set_defaults(fn=_sesnsp)

    p_enoe = subparsers.add_parser(
        "enoe", help="Descarga la tasa de desocupacion por entidad de un trimestre de ENOE"
    )
    p_enoe.add_argument("--anio", required=True, type=int, help="Ej. 2025 (obligatorio, solo 2023 en adelante)")
    p_enoe.add_argument("--trimestre", required=True, help="trim1, trim2, trim3 o trim4 (obligatorio)")
    p_enoe.set_defaults(fn=_enoe)

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
