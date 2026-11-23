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
    dataset_vivienda,
    denue_downloader,
    enigh_downloader,
    eic2025,
    enoe_downloader,
    envi2020,
    precio_estimado,
    geo_downloader,
    iieg_oferta,
    imss_asegurados,
    iter_downloader,
    rubros,
    sesnsp_ingesta,
    shf_ipv,
    sniiv_financiamiento,
    taxonomia,
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


async def _localidades(args) -> None:
    from pathlib import Path

    await inicializar_esquema()
    archivo = Path(args.archivo).read_bytes() if args.archivo else None
    try:
        total, cuadres = await iter_downloader.descargar(archivo)
    except iter_downloader.ArchivoInvalido as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    poblacion = sum(t for _, t in cuadres.values())
    print(f"{total:,} localidades de {len(cuadres)} estados; población {poblacion:,}, cuadra con los totales.")


async def _denue(args) -> None:
    from pathlib import Path

    await inicializar_esquema()
    try:
        total, borrados = await denue_downloader.descargar_estado(
            args.estado, Path(args.archivo) if args.archivo else None
        )
    except denue_downloader.ArchivoInvalido as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(f"{total} negocios guardados/actualizados para el estado {args.estado}.")
    if borrados is None:
        print("AVISO: más del 10 % de los negocios de antes no vino en esta carga; no se borró ninguno. Revisar.")
    elif borrados:
        print(f"{borrados} negocios que ya no vienen en DENUE, borrados.")

    pool = await get_pool()
    async with pool.connection() as conn:
        cursor = await conn.execute(
            "SELECT DISTINCT clase_actividad FROM fuente_denue_negocios"
            " WHERE cve_ent = %(cve_ent)s AND clase_actividad IS NOT NULL",
            {"cve_ent": args.estado},
        )
        nuevas = rubros.sin_clasificar({fila[0] for fila in await cursor.fetchall()})
    if nuevas:
        print(f"AVISO: {len(nuevas)} clase(s) sin rubro; agregarlas a mapo_core/rubros/clases.csv:")
        for clase in nuevas:
            print(f"  {clase}")


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


async def _shf(_args) -> None:
    await inicializar_esquema()
    try:
        conteo = await shf_ipv.descargar()
    except shf_ipv.RespuestaInvalida as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(f"Índice SHF guardado: {conteo}")


async def _sniiv(args) -> None:
    await inicializar_esquema()
    estados = args.estado.split(",") if args.estado else None
    conteo = await sniiv_financiamiento.descargar(estados)
    print(f"Financiamientos del SNIIV: {sum(conteo.values()):,} filas en {len(conteo)} estados.")


async def _eic2025(args) -> None:
    from pathlib import Path

    await inicializar_esquema()
    try:
        zonas = await eic2025.descargar(Path(args.archivo).read_bytes() if args.archivo else None)
    except eic2025.ArchivoInvalido as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(f"Intercensal 2025, vivienda: {zonas}")


async def _envi(args) -> None:
    from pathlib import Path

    await inicializar_esquema()
    try:
        total = await envi2020.descargar(Path(args.archivo).read_bytes() if args.archivo else None)
    except envi2020.ArchivoInvalido as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(f"ENVI 2020: {total} indicadores por estado y nacional.")


async def _imss(args) -> None:
    import json
    from pathlib import Path

    await inicializar_esquema()
    rutas = [Path(a) for a in args.archivo]
    rutas = [f for r in rutas for f in (sorted(r.glob("asg-*.csv*")) if r.is_dir() else [r])]
    if not rutas:
        raise SystemExit("No hay archivos asg-AAAA-MM-DD.csv(.gz) que cargar.")
    try:
        resumen = await imss_asegurados.cargar(rutas)
    except imss_asegurados.ArchivoInvalido as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(json.dumps(resumen, ensure_ascii=False, indent=1))


async def _clues(args) -> None:
    import json
    from pathlib import Path

    from mapo_core import clues

    await inicializar_esquema()
    try:
        resumen = await clues.cargar(Path(args.archivo))
    except clues.ArchivoInvalido as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(json.dumps(resumen, ensure_ascii=False))


async def _accesibilidad(args) -> None:
    import os
    from pathlib import Path

    from mapo_core import accesibilidad
    from mapo_core.osrm_client import OSRMClient

    # Nunca el demo público: son cientos de miles de rutas, y no tiene perfil a pie.
    urls = {"pie": args.osrm_pie or os.environ.get("MAPO_OSRM_PIE_URL"),
            "auto": args.osrm_auto or os.environ.get("MAPO_OSRM_URL")}
    modos = args.modos or list(urls)
    faltan = [m for m in modos if not urls[m]]
    if faltan:
        raise SystemExit(f"Falta el OSRM propio para {', '.join(faltan)} (MAPO_OSRM_PIE_URL, MAPO_OSRM_URL"
                         " o --osrm-pie/--osrm-auto); el demo público no sirve para esto.")
    servicios = args.servicios or list(accesibilidad.SERVICIOS)
    desconocidos = [s for s in servicios if s not in accesibilidad.SERVICIOS]
    if desconocidos:
        raise SystemExit(f"Servicios desconocidos: {', '.join(desconocidos)}")
    await inicializar_esquema()
    clientes = {m: OSRMClient(base_url=urls[m]) for m in modos}
    try:
        await accesibilidad.cargar_estado(
            await get_pool(), args.estado, clientes, servicios=servicios,
            estaciones=Path(args.estaciones) if args.estaciones else None)
    except (accesibilidad.ErrorDeRed, accesibilidad.ConsultaInvalida) as exc:
        raise SystemExit(str(exc)) from None
    finally:
        for c in clientes.values():
            await c.aclose()


async def _transporte(args) -> None:
    import json
    from pathlib import Path

    from mapo_core import transporte

    claves = args.feeds or list(transporte.FEEDS)
    desconocidos = [c for c in claves if c not in transporte.FEEDS]
    if desconocidos:
        raise SystemExit(f"Feeds desconocidos: {', '.join(desconocidos)} (ver transporte.FEEDS)")
    if args.archivo and len(claves) != 1:
        raise SystemExit("--archivo va con un solo --feeds")
    await inicializar_esquema()
    pool = await get_pool()
    fallidos = []
    for clave in claves:
        feed = transporte.FEEDS[clave]
        try:
            if args.archivo:
                archivo, url = Path(args.archivo), f"archivo local ({Path(args.archivo).name})"
            else:
                archivo, url = transporte.descargar(feed, Path(args.carpeta))
            print(json.dumps(await transporte.cargar_feed(pool, feed, archivo, url), ensure_ascii=False), flush=True)
        except transporte.ArchivoInvalido as exc:
            # Uno que falla no tumba a los demás; el anterior de ese feed se queda.
            fallidos.append(clave)
            print(json.dumps({"feed": clave, "error": str(exc)}, ensure_ascii=False), flush=True)
    if fallidos:
        raise SystemExit(f"No se cargaron: {', '.join(fallidos)} (se conserva lo anterior)")


async def _transporte_osm(args) -> None:
    import json
    from pathlib import Path

    from mapo_core import transporte_osm

    await inicializar_esquema()
    try:
        resumen = await transporte_osm.cargar(await get_pool(), Path(args.archivo))
    except transporte_osm.ArchivoInvalido as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(json.dumps(resumen, ensure_ascii=False))


async def _censos_economicos(args) -> None:
    import json
    from pathlib import Path

    from mapo_core import censos_economicos as ce

    estados = args.estados or list(ce.ABREVIATURAS)
    desconocidos = [e for e in estados if e not in ce.ABREVIATURAS]
    if desconocidos:
        raise SystemExit(f"Estados desconocidos: {', '.join(desconocidos)}")
    await inicializar_esquema()
    pool = await get_pool()
    fallidos = []
    for e in estados:
        try:
            archivo = ce.descargar(e, Path(args.carpeta))
            print(json.dumps(await ce.cargar(pool, e, archivo), ensure_ascii=False), flush=True)
        except (ce.ArchivoInvalido, OSError) as exc:
            fallidos.append(e)
            print(json.dumps({"cve_ent": e, "error": str(exc)}, ensure_ascii=False), flush=True)
    if fallidos:
        raise SystemExit(f"No se cargaron: {', '.join(fallidos)} (se conserva lo anterior)")


async def _efipem(args) -> None:
    import json
    from pathlib import Path

    from mapo_core import efipem

    await inicializar_esquema()
    try:
        resumen = await efipem.cargar(await get_pool(), Path(args.archivo))
    except (efipem.ArchivoInvalido, OSError) as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(json.dumps(resumen, ensure_ascii=False))


async def _rezago_social(args) -> None:
    import json
    from pathlib import Path

    from mapo_core import rezago_social

    await inicializar_esquema()
    try:
        resumen = await rezago_social.cargar(await get_pool(), Path(args.archivo))
    except (rezago_social.ArchivoInvalido, OSError) as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(json.dumps(resumen, ensure_ascii=False))


async def _metropolis(args) -> None:
    import json

    from mapo_core import zona

    await inicializar_esquema()
    try:
        resumen = await zona.cargar_metropolis(await get_pool())
    except zona.ZonaInvalida as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(json.dumps(resumen, ensure_ascii=False))


async def _colonias(args) -> None:
    import json
    from pathlib import Path

    from mapo_core import zona

    await inicializar_esquema()
    try:
        resumen = await zona.cargar_colonias(await get_pool(), Path(args.archivo))
    except (zona.ZonaInvalida, OSError, KeyError) as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(json.dumps(resumen, ensure_ascii=False))


async def _codigos_postales(args) -> None:
    import json
    from pathlib import Path

    from mapo_core import zona

    await inicializar_esquema()
    for archivo in args.archivos:
        try:
            print(json.dumps(await zona.cargar_codigos_postales(await get_pool(), Path(archivo)), ensure_ascii=False))
        except (zona.ZonaInvalida, OSError, KeyError) as exc:
            raise SystemExit(f"No se cargó {archivo}: {exc}") from None


async def _cngmd(args) -> None:
    import json
    from pathlib import Path

    from mapo_core import cngmd

    await inicializar_esquema()
    try:
        resumen = await cngmd.cargar(await get_pool(), Path(args.archivo))
    except (cngmd.ArchivoInvalido, OSError) as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(json.dumps(resumen, ensure_ascii=False))


async def _precio_estimado(args) -> None:
    from pathlib import Path

    await inicializar_esquema()
    try:
        total = await precio_estimado.cargar(Path(args.archivo).read_text(encoding="utf-8"))
    except precio_estimado.ArchivoInvalido as exc:
        raise SystemExit(f"No se cargó nada: {exc}") from None
    print(f"Precio por AGEB: {total} AGEB.")


async def _dataset_vivienda(args) -> None:
    from pathlib import Path

    municipios = [m.strip().zfill(3) for m in args.municipios.split(",")]
    valores = dataset_vivienda.leer_valores([Path(r) for r in args.suelo.split(",")]) if args.suelo else []
    valores_2026 = dataset_vivienda.leer_valores([Path(r) for r in args.suelo_2026.split(",")]) if args.suelo_2026 else []
    ghsl = None
    if args.ghsl:
        ghsl = {a: next(Path(args.ghsl).glob(f"GHS_BUILT_S_E{a}_*.tif"), None) for a in (1975, 1990, 2020)}
    oferta, municipal = None, None
    if args.oferta:
        if not args.oferta_colonias:
            raise SystemExit("--oferta requiere --oferta-colonias (mapa_venta.shp del IIEG)")
        anuncios = iieg_oferta.leer_anuncios(Path(args.oferta))
        oferta = (anuncios, iieg_oferta.leer_colonias(Path(args.oferta_colonias)), args.oferta_periodo)
        municipal = iieg_oferta.resumen_municipal(anuncios, args.oferta_periodo)
    filas, centros = await dataset_vivienda.construir(
        await get_pool(), args.estado, municipios, args.anio_crimen, valores,
        agua=Path(args.osm_agua) if args.osm_agua else None,
        vias=Path(args.osm_vias) if args.osm_vias else None,
        ghsl=ghsl, valores_2026=valores_2026,
        sep=Path(args.sep) if args.sep else None,
        no2=Path(args.no2) if args.no2 else None,
        entorno={
            "transporte": Path(args.transporte) if args.transporte else None,
            "parques": Path(args.osm_parques) if args.osm_parques else None,
            "dem": Path(args.dem) if args.dem else None,
            "altura": next(Path(args.ghsl).glob("GHS_BUILT_H_*.tif"), None) if args.ghsl else None,
            "ndvi": Path(args.ndvi) if args.ndvi else None,
            "lst": Path(args.lst) if args.lst else None,
        },
        oferta=oferta,
    )
    if not filas:
        raise SystemExit("Ninguna AGEB con censo para esos municipios: revisa que el estado esté cargado.")
    dataset_vivienda.escribir(filas, centros, Path(args.salida), {
        "estado": args.estado, "municipios": ",".join(municipios),
        "anio_base_censo": 2020, "anio_crimen": args.anio_crimen, "agebs": len(filas),
        "valores_catastrales": args.suelo or "ninguno",
        "valores_catastrales_2026": args.suelo_2026 or "ninguno",
        "osm_agua": args.osm_agua or "ninguno", "osm_vias": args.osm_vias or "ninguno",
        "ghsl": args.ghsl or "ninguno", "sep": args.sep or "ninguno", "no2": args.no2 or "ninguno",
        "predial": "predial_tablas.csv (leyes de ingresos 2026)",
        **{k: getattr(args, k) or "ninguno" for k in ("transporte", "osm_parques", "dem", "ndvi", "lst")},
        "oferta_iieg": f"{args.oferta} ({args.oferta_periodo})" if args.oferta else "ninguno",
        "oferta_colonias": args.oferta_colonias or "ninguno",
    }, municipal)
    print(f"{len(filas)} AGEB en {args.salida}. Centros de empleo: {centros}")
    for columna, (p5, p50, p95) in dataset_vivienda.resumen(filas).items():
        print(f"  {columna:26} p5={p5:<12} mediana={p50:<12} p95={p95}")


async def _taxonomia(args) -> None:
    municipios = [m.strip().zfill(3) for m in args.municipios.split(",")]
    filas, silueta = await taxonomia.calcular(await get_pool(), args.estado, municipios, args.zona)
    taxonomia.escribir(filas)
    print(f"{len(filas)} rubros en {taxonomia.ARCHIVO.name}, silueta {silueta:.2f}.")
    grupos: dict[int, list[str]] = {}
    for f in filas:
        grupos.setdefault(f["grupo"], []).append(f["rubro"])
    for g, claves in sorted(grupos.items()):
        descripcion = next(f["descripcion"] for f in filas if f["grupo"] == g)
        print(f"  {g}. {descripcion} ({len(claves)}): {', '.join(claves[:12])}{' ...' if len(claves) > 12 else ''}")


AMBIENTALES = {
    "acuiferos": ("ambiental_agua", "cargar_acuiferos"),
    "renameca": ("ambiental_agua", "cargar_renameca"),
    "repda": ("ambiental_agua", "cargar_repda"),
    "retc": ("ambiental_emisiones", "cargar_retc"),
    "siap": ("ambiental_municipal", "cargar_siap"),
    "firms": ("ambiental_emisiones", "cargar_firms"),
    "uso_suelo": ("ambiental_territorio", "cargar_uso_suelo"),
    "anp": ("ambiental_territorio", "cargar_anp"),
    "sequia": ("ambiental_municipal", "cargar_sequia"),
    "defunciones": ("ambiental_municipal", "cargar_defunciones"),
}


async def _ambiental(args) -> None:
    import importlib
    import json
    import time
    from pathlib import Path

    from mapo_core.crudos import CrudoFaltante

    await inicializar_esquema()
    crudos = Path(args.crudos)
    fuentes = args.fuente.split(",") if args.fuente else list(AMBIENTALES)
    desconocidas = [f for f in fuentes if f not in AMBIENTALES]
    if desconocidas:
        raise SystemExit(f"Fuentes desconocidas: {', '.join(desconocidas)}. Hay: {', '.join(AMBIENTALES)}")
    for fuente in fuentes:
        modulo, funcion = AMBIENTALES[fuente]
        inicio = time.monotonic()
        try:
            resumen = await getattr(importlib.import_module(f"mapo_core.{modulo}"), funcion)(crudos)
        except CrudoFaltante as exc:
            raise SystemExit(f"No se cargó {fuente}: {exc}") from None
        print(f"{fuente} ({time.monotonic() - inicio:.0f} s): {json.dumps(resumen, ensure_ascii=False, default=str)}")


async def _status(_args) -> None:
    await inicializar_esquema()
    pool = await get_pool()
    tablas = [
        "entidades", "municipios", "agebs", "localidades", "fuente_censo_poblacion",
        "fuente_denue_negocios", "fuente_enigh_concentradohogar", "fuente_sesnsp_delitos_municipal",
        "fuente_enoe_tasa_desocupacion", "fuente_shf_ipv", "fuente_sniiv_financiamiento",
        "fuente_eic2025_vivienda", "fuente_envi2020_entidad", "fuente_precio_estimado",
        "fuente_acuiferos", "fuente_acuiferos_ordenamientos", "fuente_piezometria", "fuente_renameca_sitios",
        "fuente_repda_descargas", "fuente_retc_establecimientos", "fuente_retc_emisiones", "fuente_siap_agricola",
        "fuente_firms_focos", "fuente_uso_suelo", "fuente_anp", "fuente_sequia_municipal",
        "fuente_defunciones_municipal", "fuente_imss_asegurados",
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

    p_loc = subparsers.add_parser(
        "localidades", help="Carga las localidades del ITER 2020 de todo el país (reemplaza las de antes)"
    )
    p_loc.add_argument("--archivo", default=None, help="ZIP ya bajado (iter_00_cpv2020_csv.zip)")
    p_loc.set_defaults(fn=_localidades)

    p_denue = subparsers.add_parser(
        "denue", help="Carga los negocios de DENUE de un estado desde la descarga masiva (reemplaza los de antes)"
    )
    p_denue.add_argument("--estado", required=True, help="cve_ent, ej. 14 (obligatorio)")
    p_denue.add_argument(
        "--archivo", default=None, help="ZIP ya bajado (denue_NN_csv.zip); sin esto se baja de INEGI"
    )
    p_denue.set_defaults(fn=_denue)

    p_tax = subparsers.add_parser(
        "taxonomia", help="Agrupa rubros por su patrón en una zona y escribe rubros/taxonomia.csv"
    )
    p_tax.add_argument("--estado", required=True)
    p_tax.add_argument("--municipios", required=True, help="cve_mun separados por coma")
    p_tax.add_argument("--zona", required=True, help="Nombre de la zona, como se muestra en pantalla")
    p_tax.set_defaults(fn=_taxonomia)

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

    subparsers.add_parser(
        "shf", help="Índice SHF de precios de la vivienda, serie completa (reemplaza la de antes)"
    ).set_defaults(fn=_shf)

    p_sniiv = subparsers.add_parser(
        "sniiv", help="Financiamientos para vivienda del SNIIV por municipio (reemplaza los estados pedidos)"
    )
    p_sniiv.add_argument("--estado", default=None, help="cve_ent separadas por coma (default: los 32)")
    p_sniiv.set_defaults(fn=_sniiv)

    p_eic = subparsers.add_parser(
        "eic2025", help="Bloque de vivienda de la Intercensal 2025 por municipio (reemplaza el de antes)"
    )
    p_eic.add_argument("--archivo", default=None, help="ZIP ya bajado (conjunto_de_datos_eic2025_105_csv.zip)")
    p_eic.set_defaults(fn=_eic2025)

    p_envi = subparsers.add_parser(
        "envi", help="Renta y valor de la vivienda por estado, de la ENVI 2020 (reemplaza los de antes)"
    )
    p_envi.add_argument("--archivo", default=None, help="ZIP ya bajado (conjunto_de_datos_envi_2020_csv.zip)")
    p_envi.set_defaults(fn=_envi)

    p_imss = subparsers.add_parser(
        "imss", help="Empleo formal del IMSS por municipio y grupo, de archivos ya bajados (reemplaza esos meses)"
    )
    p_imss.add_argument(
        "archivo", nargs="+", help="asg-AAAA-MM-DD.csv o .csv.gz, o una carpeta con ellos (data/imss)"
    )
    p_imss.set_defaults(fn=_imss)

    p_clues = subparsers.add_parser(
        "clues", help="Establecimientos de salud del catálogo CLUES (reemplaza el catálogo completo)"
    )
    p_clues.add_argument("archivo", help="ESTABLECIMIENTO_SALUD_AAAAMM.xlsx de la DGIS (data/clues)")
    p_clues.set_defaults(fn=_clues)

    p_acc = subparsers.add_parser(
        "accesibilidad", help="Minutos a pie y en auto de cada AGEB o localidad a cada servicio (reemplaza el estado)"
    )
    p_acc.add_argument("--estado", required=True, help="cve_ent de 2 dígitos")
    p_acc.add_argument("--servicios", nargs="+", help="claves de accesibilidad.SERVICIOS (todas si no se dice)")
    p_acc.add_argument("--modos", nargs="+", choices=["pie", "auto"])
    p_acc.add_argument("--estaciones", help="CSV red,nombre,lon,lat (scripts/vivienda/transporte_masivo.py)")
    p_acc.add_argument("--osrm-pie", help="URL del OSRM con foot.lua (si no, MAPO_OSRM_PIE_URL)")
    p_acc.add_argument("--osrm-auto", help="URL del OSRM con car.lua (si no, MAPO_OSRM_URL)")
    p_acc.set_defaults(fn=_accesibilidad)

    p_tr = subparsers.add_parser(
        "transporte", help="GTFS de transporte público de transporte.FEEDS (reemplaza cada feed cargado)"
    )
    p_tr.add_argument("--feeds", nargs="+", help="claves de transporte.FEEDS (todas si no se dice)")
    p_tr.add_argument("--carpeta", default="data/transporte", help="donde se guardan los zip bajados")
    p_tr.add_argument("--archivo", help="zip local en vez de bajarlo (con un solo --feeds)")
    p_tr.set_defaults(fn=_transporte)

    p_tr_osm = subparsers.add_parser(
        "transporte_osm", help="Rutas de transporte de OSM de todo el país (scripts/transporte/rutas_osm.sh)"
    )
    p_tr_osm.add_argument("archivo", help="rutas-AAMMDD.opl")
    p_tr_osm.set_defaults(fn=_transporte_osm)

    p_ce = subparsers.add_parser(
        "censos_economicos", help="Censos Económicos 2024 por municipio y sector (reemplaza cada estado)"
    )
    p_ce.add_argument("--estados", nargs="+", help="cve_ent de 2 dígitos (todos si no se dice)")
    p_ce.add_argument("--carpeta", default="data/censos_economicos", help="donde se guardan los zip bajados")
    p_ce.set_defaults(fn=_censos_economicos)

    p_ef = subparsers.add_parser("efipem", help="Finanzas públicas municipales de INEGI (reemplaza todo)")
    p_ef.add_argument("archivo", help="efipem_municipal_csv.zip de INEGI")
    p_ef.set_defaults(fn=_efipem)

    p_grs = subparsers.add_parser("rezago_social", help="Grado de Rezago Social por AGEB urbana 2020 (CONEVAL)")
    p_grs.add_argument("archivo", help="GRS_AGEB_urbana_2020.xlsx")
    p_grs.set_defaults(fn=_rezago_social)

    p_metro = subparsers.add_parser(
        "metropolis", help="Metrópolis de México 2020 con sus municipios, del CSV del paquete (reemplaza todo)"
    )
    p_metro.set_defaults(fn=_metropolis)

    p_col = subparsers.add_parser(
        "colonias", help="Colonias del índice de marginación urbana 2020 de CONAPO, todo el país (reemplaza todo)"
    )
    p_col.add_argument("archivo", help="imc2020_shp.zip (zona.COLONIAS_URL)")
    p_col.set_defaults(fn=_colonias)

    p_cp = subparsers.add_parser(
        "codigos_postales", help="Polígonos de CP de SEPOMEX, un CP_XX.zip por estado (reemplaza ese estado)"
    )
    p_cp.add_argument("archivos", nargs="+", help="CP_14.zip ... de datos.gob.mx")
    p_cp.set_defaults(fn=_codigos_postales)

    p_cngmd = subparsers.add_parser(
        "cngmd", help="Instrumentos de planeación territorial del CNGMD 2025 (reemplaza todo)"
    )
    p_cngmd.add_argument("archivo", help="conjunto_de_datos_ins_plan_ord_jur_cngmd2025_csv.zip")
    p_cngmd.set_defaults(fn=_cngmd)

    p_precio = subparsers.add_parser(
        "precio_estimado", help="Precio por AGEB del estudio de precio estimado (reemplaza el de antes)"
    )
    p_precio.add_argument("--archivo", required=True,
                          help="CSV del notebook, ej. /app/data/precio_estimado/precio_ageb_v1.csv")
    p_precio.set_defaults(fn=_precio_estimado)

    p_amb = subparsers.add_parser(
        "ambiental", help="Carga las fuentes ambientales desde los crudos ya bajados (reemplaza las de antes)"
    )
    p_amb.add_argument("--crudos", required=True,
                       help="Carpeta de scripts/crudos-ambientales.sh dentro del contenedor, ej. /app/data/crudos-ambiental")
    p_amb.add_argument("--fuente", default=None, help=f"Separadas por coma (default: todas): {', '.join(AMBIENTALES)}")
    p_amb.set_defaults(fn=_ambiental)

    p_viv = subparsers.add_parser(
        "dataset_vivienda", help="Arma el dataset tipo Boston Housing por AGEB de una zona metropolitana"
    )
    p_viv.add_argument("--estado", required=True, help="cve_ent, ej. 14")
    p_viv.add_argument("--municipios", required=True, help="cve_mun separadas por coma, ej. 039,120")
    p_viv.add_argument("--salida", required=True, help="Carpeta de salida (dentro del contenedor, ej. /app/data/...)")
    p_viv.add_argument("--anio-crimen", type=int, default=2020, help="Año de SESNSP para CRIM (default: 2020, el del censo)")
    p_viv.add_argument(
        "--suelo", default=None,
        help="valores.csv de scripts/catastro/ubicar_pdf_mapa.py, separados por coma (rutas dentro del contenedor)",
    )
    p_viv.add_argument("--suelo-2026", default=None,
                       help="valores.csv de tablas 2026, separados por coma (columna suelo_2026_m2)")
    p_viv.add_argument("--osm-agua", default=None, help="JSON de Overpass con waterway (para CHAS)")
    p_viv.add_argument("--osm-vias", default=None, help="JSON de Overpass con highway=motorway|trunk (para RAD)")
    p_viv.add_argument("--ghsl", default=None, help="Carpeta con los GHS_BUILT_S de 1975, 1990 y 2020 (para AGE)")
    p_viv.add_argument("--sep", default=None, help="CSV de scripts/vivienda/sep_cifras.py (para PTRATIO)")
    p_viv.add_argument("--no2", default=None, help="GeoTIFF de scripts/ambiental/no2_s5p.py (para NOX)")
    p_viv.add_argument("--transporte", default=None, help="CSV de scripts/vivienda/transporte_masivo.py")
    p_viv.add_argument("--osm-parques", default=None, help="JSON de Overpass con leisure=park|garden|nature_reserve")
    p_viv.add_argument("--dem", default=None, help="DEM en grados (Copernicus GLO-30) que cubra la zona")
    p_viv.add_argument("--ndvi", default=None, help="s2_indices_<mes>.tif de scripts/ambiental/imagenes.py")
    p_viv.add_argument("--lst", default=None, help="lst_secas_<año>.tif de scripts/ambiental/imagenes.py")
    p_viv.add_argument("--oferta", default=None,
                       help="BD_SECTOR_INMOBILIARIO_<mes>_<año>.xlsx del IIEG (para MEDV, solo Jalisco)")
    p_viv.add_argument("--oferta-colonias", default=None, help="mapa_venta.shp del IIEG")
    p_viv.add_argument("--oferta-periodo", default="2024-07", help="Mes de los anuncios, AAAA-MM")
    p_viv.set_defaults(fn=_dataset_vivienda)

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
