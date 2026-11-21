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
        "fuente_defunciones_municipal",
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
