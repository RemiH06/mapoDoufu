# Lo pesado de CPU (OR-Tools, Voronoi, coloreado) corre con asyncio.to_thread:
# dentro de un `async def` bloquearia el event loop para todas las peticiones.
import asyncio
import json
import logging
from typing import Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from mapo_core import (
    accesibilidad,
    buscador,
    consultas,
    cruce,
    datos_geo,
    datos_propios,
    localidades,
    perfil,
    riesgos,
    similares,
    transporte,
    vivienda_vista,
)
from mapo_core import zona as zona_comun
from mapo_core.coloreado_mapa import PoligonoColoreable, colorear_mapa
from mapo_core.consultas import INDICADORES_CHOROPLETH, TOLERANCIA_SIMPLIFICACION as _TOLERANCIA_SIMPLIFICACION, dibujo
from mapo_core.consultas import feature as _feature
from mapo_core.db import get_pool
from mapo_core.isocronas import MAX_ISOCRONAS, calcular_isocrona
from mapo_core.isocronas import poblacion as poblacion_isocronas
from mapo_core.osrm_client import OSRMClient
from mapo_core.voronoi import PuntoVoronoi, calcular_voronoi
from mapo_core.vrp import Parada, Vehiculo, resolver_vrp

# Sin /docs ni /openapi.json: el único cliente es `mapo`, y la lista de
# rutas solo le serviría a quien llegara a la red interna.
app = FastAPI(title="mapo_core", docs_url=None, redoc_url=None, openapi_url=None)
_log = logging.getLogger("mapo_core")

_osrm_client: OSRMClient | None = None


def get_osrm_client() -> OSRMClient:
    global _osrm_client
    if _osrm_client is None:
        _osrm_client = OSRMClient()
    return _osrm_client


@app.exception_handler(psycopg.OperationalError)
async def base_de_datos_no_disponible(request: Request, exc: psycopg.OperationalError) -> JSONResponse:
    # El texto de psycopg trae host, usuario y base: va al log, no a la respuesta.
    _log.error("Base no disponible en %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"error": "La base de datos de mapo_core no esta disponible ahorita mismo."},
    )


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}


def _geometria_sql(geometria: bool) -> str:
    """Las listas de nombres (selects de estado y municipio) no
    necesitan el poligono: con `geometria=false` la consulta no lo
    serializa y la respuesta baja de MB a KB."""
    return "ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s, true), 5)" if geometria else "NULL"


@app.get("/geo/estados")
async def geo_estados(geometria: bool = True, pool: AsyncConnectionPool = Depends(get_pool)) -> dict:
    """Los 32 estados, con su poligono real (propio de mapo_core, ya
    no un passthrough de Gaiarda)."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            f"""SELECT cve_ent, nombre, {_geometria_sql(geometria)}
               FROM entidades ORDER BY cve_ent""",
            {"tolerancia": _TOLERANCIA_SIMPLIFICACION},
        )
        filas = await cursor.fetchall()

    features = [_feature(cve_ent, nombre, geom) for cve_ent, nombre, geom in filas]
    return {"type": "FeatureCollection", "features": features}


@app.get("/geo/municipios")
async def geo_municipios(
    cve_ent: str | None = None, geometria: bool = True, pool: AsyncConnectionPool = Depends(get_pool)
) -> dict:
    """Municipios, opcionalmente filtrados por estado, con su poligono real."""
    async with pool.connection() as conn:
        if cve_ent:
            cursor = await conn.execute(
                f"""SELECT cvegeo, cve_mun, nombre, {_geometria_sql(geometria)}
                   FROM municipios WHERE cve_ent = %(cve_ent)s ORDER BY cvegeo""",
                {"cve_ent": cve_ent, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
            )
        else:
            cursor = await conn.execute(
                f"""SELECT cvegeo, cve_mun, nombre, {_geometria_sql(geometria)}
                   FROM municipios ORDER BY cvegeo""",
                {"tolerancia": _TOLERANCIA_SIMPLIFICACION},
            )
        filas = await cursor.fetchall()

    features = [_feature(cvegeo, nombre, geom, {"cve_mun": cve_mun}) for cvegeo, cve_mun, nombre, geom in filas]
    return {"type": "FeatureCollection", "features": features}


@app.get("/geo/agebs")
async def geo_agebs(
    cve_ent: str, cve_mun: str | None = None, pool: AsyncConnectionPool = Depends(get_pool)
) -> dict:
    """AGEBs urbanas, con su poligono real. `cve_ent` obligatorio:
    sin esto podrian ser decenas de miles de poligonos."""
    async with pool.connection() as conn:
        if cve_mun:
            cursor = await conn.execute(
                f"""SELECT cvegeo, ST_AsGeoJSON({dibujo()}, 5)
                   FROM agebs WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s ORDER BY cvegeo""",
                {"cve_ent": cve_ent, "cve_mun": cve_mun, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
            )
        else:
            cursor = await conn.execute(
                f"""SELECT cvegeo, ST_AsGeoJSON({dibujo()}, 5)
                   FROM agebs WHERE cve_ent = %(cve_ent)s ORDER BY cvegeo""",
                {"cve_ent": cve_ent, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
            )
        filas = await cursor.fetchall()

    features = [_feature(cvegeo, cvegeo, geom) for cvegeo, geom in filas]
    return {"type": "FeatureCollection", "features": features}


_TABLA_POR_NIVEL = {"municipio": "municipios", "ageb": "agebs"}


class PeticionPorClave(BaseModel):
    nivel: Literal["municipio", "ageb"]
    claves: list[str] = Field(max_length=datos_propios.MAX_POLIGONOS)


@app.post("/geo/por_clave")
async def geo_por_clave(peticion: PeticionPorClave, pool: AsyncConnectionPool = Depends(get_pool)) -> dict:
    """Polígonos de una lista de claves, de cualquier estado. La clave que
    no exista en el marco cargado simplemente no regresa."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            f"""SELECT cvegeo, ST_AsGeoJSON({dibujo()}, 5)
               FROM {_TABLA_POR_NIVEL[peticion.nivel]} WHERE cvegeo = ANY(%(claves)s) ORDER BY cvegeo""",
            {"claves": peticion.claves, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
        )
        filas = await cursor.fetchall()
    return {"type": "FeatureCollection", "features": [_feature(c, c, geom) for c, geom in filas]}


async def _cuerpo_acotado(request: Request) -> bytes:
    """El archivo crudo, sin creerle a `Content-Length`. Phoenix ya limita el
    tamaño; esto cubre a quien llegue directo por la red interna."""
    cuerpo = bytearray()
    async for pedazo in request.stream():
        cuerpo += pedazo
        if len(cuerpo) > datos_propios.MAX_BYTES:
            raise HTTPException(status_code=413, detail="El archivo pasa de 50 MB.")
    return bytes(cuerpo)


async def _tabla(contenido: bytes, formato: str) -> datos_propios.Tabla:
    try:
        return await asyncio.to_thread(datos_geo.leer, contenido, formato)
    except datos_propios.ArchivoInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/datos/leer")
async def datos_leer(request: Request, formato: str) -> dict:
    """Columnas, una muestra y una sugerencia de ubicación. No guarda nada."""
    contenido = await _cuerpo_acotado(request)
    if formato in datos_geo.RASTER:
        try:
            return await asyncio.to_thread(datos_geo.leer_raster, contenido)
        except datos_propios.ArchivoInvalido as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    tabla = await _tabla(contenido, formato)
    return {
        "columnas": tabla.columnas,
        "muestra": tabla.filas[:5],
        "num_filas": len(tabla.filas),
        "avisos": tabla.avisos,
        "sugerencia": datos_propios.sugerir(tabla),
    }


@app.post("/datos/raster_valores")
async def datos_raster_valores(request: Request) -> Response:
    """Los valores de la primera banda en teselas WKB de PostGIS raster, para que
    Mapo los guarde y los consulte. Binario: 4 bytes con el largo de un JSON de
    información, ese JSON, y luego cada tesela con su largo en 4 bytes delante
    (todo en big endian). No guarda nada."""
    contenido = await _cuerpo_acotado(request)
    try:
        info, teselas = await asyncio.to_thread(datos_geo.valores_raster, contenido)
    except datos_propios.ArchivoInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    cabeza = json.dumps(info).encode()
    partes = [len(cabeza).to_bytes(4, "big"), cabeza]
    for t in teselas:
        partes += [len(t).to_bytes(4, "big"), t]
    return Response(content=b"".join(partes), media_type="application/octet-stream")


@app.post("/datos/ubicar")
async def datos_ubicar(
    request: Request,
    formato: str,
    tipo: Literal["puntos", "municipio", "ageb", "vector", "raster"],
    lat: str | None = None,
    lon: str | None = None,
    clave: list[str] | None = Query(default=None),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Los renglones ya ubicados y por qué se descartó el resto. No guarda nada.
    `clave` se repite cuando viene partida en varias columnas."""
    contenido = await _cuerpo_acotado(request)
    if tipo == "raster":
        try:
            return await asyncio.to_thread(datos_geo.ubicar_raster, contenido)
        except datos_propios.ArchivoInvalido as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    tabla = await _tabla(contenido, formato)
    try:
        if tipo == "vector":
            if tabla.geometrias is None:
                raise datos_propios.ArchivoInvalido("Ese archivo no trae geometrías.")
            resultado = await asyncio.to_thread(datos_geo.ubicar_vector, tabla)
        elif tipo == "puntos":
            resultado = await asyncio.to_thread(datos_propios.ubicar_puntos, tabla, lat, lon)
        else:
            claves = datos_propios.claves_de(tabla, clave, tipo)
            async with pool.connection() as conn:
                cursor = await conn.execute(
                    f"SELECT cvegeo FROM {_TABLA_POR_NIVEL[tipo]} WHERE cvegeo = ANY(%(claves)s)",
                    {"claves": list(claves)},
                )
                existentes = {fila[0] for fila in await cursor.fetchall()}
            resultado = await asyncio.to_thread(datos_propios.ubicar_claves, tabla, clave, tipo, existentes)
    except datos_propios.ArchivoInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    fechas, avisos_fechas = datos_propios.columnas_fecha(tabla)
    datos_propios.normalizar_fechas(resultado["filas"], fechas)
    return {
        "tipo": tipo,
        **resultado,
        "fechas": list(fechas),
        "columnas": tabla.columnas,
        "num_filas": len(tabla.filas),
        "avisos": tabla.avisos + avisos_fechas,
    }


def _zona_de(zona: str | None, cve_ent: str | None = None, cve_mun: str | None = None) -> dict:
    """La zona de una consulta: su clave (zona.py) o, como antes de la 29b, un estado
    y quizá un municipio. 422 si no hay ninguna o la clave no es válida."""
    if zona is None and cve_ent:
        zona = f"mun:{cve_ent}{cve_mun}" if cve_mun else f"ent:{cve_ent}"
    if zona is None:
        raise HTTPException(422, "hace falta una zona")
    try:
        return zona_comun.validar(zona)
    except zona_comun.ZonaInvalida as exc:
        raise HTTPException(422, str(exc)) from None


async def _resuelta(pool: AsyncConnectionPool, z: dict) -> dict:
    async with pool.connection() as conn:
        resuelta = await zona_comun.resolver(conn, z)
    if resuelta is None or not resuelta["estados"]:
        raise HTTPException(404, "No hay nada cargado en Mapo con esa zona.")
    return resuelta


@app.get("/censo/choropleth")
async def censo_choropleth(
    indicador: str,
    zona: str | None = Query(default=None, max_length=6_000),
    cve_ent: str | None = Query(default=None, pattern=r"^\d{2}$"),
    cve_mun: str | None = Query(default=None, pattern=r"^\d{3}$"),
    extra: list[str] = Query(default=[], max_length=consultas.MAX_EXTRAS),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Cruza los poligonos de AGEB con el Censo de Poblacion por AGEB,
    por cvegeo (propio de mapo_core, ya no un passthrough de Gaiarda).
    Con `zona`, los AGEB con su punto de dentro en ella; si no, los de un
    estado o un municipio, como antes. Si falta el censo de un AGEB, el
    poligono trae `valor_choropleth: null`, nunca se inventa un cero."""
    if indicador not in INDICADORES_CHOROPLETH:
        raise HTTPException(400, f"indicador invalido. Usa uno de: {sorted(INDICADORES_CHOROPLETH)}")
    if invalidas := [e for e in extra if e not in INDICADORES_CHOROPLETH and e not in consultas.DENOMINADORES_CENSO]:
        raise HTTPException(400, f"columna extra invalida: {invalidas}")

    if zona is None:
        if not cve_ent:
            raise HTTPException(422, "hace falta una zona")
        features = await consultas.coropleta(pool, indicador, cve_ent, [cve_mun] if cve_mun else None, extras=extra)
    else:
        features = await consultas.coropleta(pool, indicador, None, None, zona=_zona_de(zona), extras=extra)
    return {"type": "FeatureCollection", "features": features}


class ParadaEntrada(BaseModel):
    lat: float
    lon: float
    demanda: int = 0
    ventana_inicio_min: int | None = None
    ventana_fin_min: int | None = None


class SolicitudVRP(BaseModel):
    paradas: list[ParadaEntrada]
    capacidades_vehiculos: list[int]
    deposito: int = 0
    velocidad_kmh: float = 40.0


@app.post("/vrp/calcular")
async def vrp_calcular(
    solicitud: SolicitudVRP, osrm: OSRMClient = Depends(get_osrm_client)
) -> dict:
    """VRP con capacidad y ventanas de tiempo, via OR-Tools. Intenta
    distancia y duracion real por carretera (OSRM) primero; si el
    servicio no responde o algun tramo no es alcanzable, cae de vuelta
    a linea recta (haversine), igual que el fallback honesto que ya
    usa Gaiarda. El campo `metodo` de la respuesta siempre dice cual
    de los dos se uso, nunca se le hace pasar una aproximacion por un
    dato confirmado. Cada ruta trae ademas `geometria` (GeoJSON
    LineString siguiendo la carretera real, via OSRM), o `null` si el
    metodo ya cayo a linea recta (ahi no hay carretera real que pedir)
    o si esa llamada en particular no respondio."""
    if solicitud.deposito < 0 or solicitud.deposito >= len(solicitud.paradas):
        raise HTTPException(400, "deposito debe ser un indice valido de paradas")

    paradas = [
        Parada(
            lat=p.lat,
            lon=p.lon,
            demanda=p.demanda,
            ventana_inicio_min=p.ventana_inicio_min,
            ventana_fin_min=p.ventana_fin_min,
        )
        for p in solicitud.paradas
    ]
    vehiculos = [Vehiculo(capacidad=c) for c in solicitud.capacidades_vehiculos]

    resultado_osrm = await osrm.matriz_carretera([(p.lat, p.lon) for p in paradas])

    if resultado_osrm is not None:
        solucion = await asyncio.to_thread(
            resolver_vrp,
            paradas,
            vehiculos,
            deposito=solicitud.deposito,
            matriz_km=resultado_osrm["distancias_km"],
            matriz_min=resultado_osrm["duraciones_min"],
        )
        metodo = "carretera_real"
    else:
        solucion = await asyncio.to_thread(
            resolver_vrp,
            paradas,
            vehiculos,
            deposito=solicitud.deposito,
            velocidad_kmh=solicitud.velocidad_kmh,
        )
        metodo = "linea_recta_aproximada"

    if solucion is None:
        raise HTTPException(
            422, "No se encontro una solucion factible con esas restricciones."
        )

    rutas = []
    for r in solucion.rutas:
        geometria = None
        if metodo == "carretera_real":
            coords_orden = [(paradas[i].lat, paradas[i].lon) for i in r.orden_paradas]
            geometria = await osrm.geometria_ruta(coords_orden)
        rutas.append(
            {
                "vehiculo_id": r.vehiculo_id,
                "orden_paradas": r.orden_paradas,
                "distancia_km": r.distancia_km,
                "geometria": geometria,
            }
        )

    return {
        "rutas": rutas,
        "distancia_total_km": solucion.distancia_total_km,
        "metodo": metodo,
    }


class SolicitudIsocrona(BaseModel):
    lat: float
    lon: float
    minutos: float
    num_direcciones: int = 16


@app.post("/isocronas/calcular")
async def isocronas_calcular(
    solicitud: SolicitudIsocrona, osrm: OSRMClient = Depends(get_osrm_client)
) -> dict:
    """Poligono del area alcanzable desde (lat, lon) en `minutos`,
    por carretera real (OSRM) si esta disponible; circulo aproximado
    si no. El campo `metodo` siempre dice cual de los dos se uso."""
    if solicitud.minutos <= 0:
        raise HTTPException(400, "minutos debe ser mayor que 0")
    if solicitud.num_direcciones < 3:
        raise HTTPException(400, "num_direcciones debe ser al menos 3")

    resultado = await calcular_isocrona(
        osrm,
        solicitud.lat,
        solicitud.lon,
        solicitud.minutos,
        num_direcciones=solicitud.num_direcciones,
    )

    return {"poligono": resultado.poligono, "metodo": resultado.metodo}


class SolicitudPoblacionIsocronas(BaseModel):
    poligonos: list[dict] = Field(min_length=1, max_length=MAX_ISOCRONAS)


@app.post("/isocronas/poblacion")
async def isocronas_poblacion(
    solicitud: SolicitudPoblacionIsocronas, pool: AsyncConnectionPool = Depends(get_pool)
) -> dict:
    """Cuánta gente vive dentro de cada isócrona, en todas y en alguna (Censo 2020 por
    AGEB y localidad, por su punto). Polígonos GeoJSON de `/isocronas/calcular`."""
    for p in solicitud.poligonos:
        if p.get("type") not in ("Polygon", "MultiPolygon") or len(json.dumps(p)) > 200_000:
            raise HTTPException(422, "cada isócrona es un polígono GeoJSON")
    try:
        return await poblacion_isocronas(pool, solicitud.poligonos)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


class PuntoVoronoiEntrada(BaseModel):
    lat: float
    lon: float
    id: str
    nombre: str | None = None


class SolicitudVoronoi(BaseModel):
    puntos: list[PuntoVoronoiEntrada]
    limite: dict | None = None


@app.post("/voronoi/calcular")
def voronoi_calcular(solicitud: SolicitudVoronoi) -> dict:
    """Diagrama de Voronoi de `puntos`: para cada uno, el area mas
    cercana a el que a cualquier otro. Recortado a `limite` (geometria
    GeoJSON) si se da, o a la caja envolvente de los puntos si no. El
    campo `metodo` siempre dice cual de los dos se uso."""
    puntos = [PuntoVoronoi(lat=p.lat, lon=p.lon, id=p.id, nombre=p.nombre) for p in solicitud.puntos]

    try:
        resultado = calcular_voronoi(puntos, limite=solicitud.limite)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    return {"celdas": resultado.celdas, "metodo": resultado.metodo}


@app.get("/voronoi/denue")
async def voronoi_denue(
    zona: str | None = Query(default=None, max_length=6_000),
    cve_ent: str | None = None,
    cve_mun: str | None = None,
    clase_actividad: str | None = None,
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Voronoi de los negocios de DENUE de una zona (clave de zona.py, o un municipio
    como antes), recortado a ella: "a cuál de estos negocios le queda más cerca cada
    lugar de la zona". Los negocios a `COMPETENCIA_M` o menos fuera de la zona también
    compiten (sus celdas salen con `fuera`): sin ellos, el de junto al límite se quedaba
    con todo el borde. `clase_actividad` filtra por un término de la tabla de rubros o
    por texto en el nombre de la clase; `filtro` dice qué rubro o sector se reconoció."""
    try:
        z = zona_comun.validar(zona if zona is not None else f"mun:{cve_ent}{cve_mun}")
    except zona_comun.ZonaInvalida as exc:
        raise HTTPException(422, str(exc)) from None
    async with pool.connection() as conn:
        resuelta = await zona_comun.resolver(conn, z)
    if resuelta is None:
        raise HTTPException(404, "No hay nada cargado en Mapo con esa zona.")

    # El filtro acepta las mismas palabras que el buscador ("florería",
    # "policía"), no solo texto del nombre oficial de la clase.
    clases, filtro = buscador.giro_tecnico(clase_actividad) if clase_actividad else (None, None)
    patron = clase_actividad if clases is None else None
    puntos, sin_denue = await consultas.negocios_de_zona(pool, z, patron=patron, clases=clases)

    if aviso := consultas.aviso_voronoi(len(puntos)):
        raise HTTPException(422, aviso)

    try:
        resultado = await asyncio.to_thread(calcular_voronoi, puntos, limite=resuelta["geojson"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    return {
        "celdas": resultado.celdas,
        "metodo": resultado.metodo,
        "num_negocios": sum(1 for p in puntos if not p.fuera),
        "num_fuera": sum(1 for p in puntos if p.fuera),
        "competencia_m": consultas.COMPETENCIA_M,
        "sin_denue": sin_denue,
        "zona": {"clave": resuelta["clave"], "nombre": resuelta["nombre"]},
        "filtro": filtro,
    }


class PoligonoColoreableEntrada(BaseModel):
    id: str
    geometria: dict


class SolicitudColoreado(BaseModel):
    poligonos: list[PoligonoColoreableEntrada]


@app.post("/coloreado/calcular")
def coloreado_calcular(solicitud: SolicitudColoreado) -> dict:
    """Coloreado tipo "teorema de las 4 colores": un indice de color
    por poligono, para que dos poligonos vecinos nunca compartan
    color. `num_colores` dice honestamente cuantos hicieron falta (el
    algoritmo greedy no siempre llega exactamente a 4, aunque el
    teorema garantice que alcanzan)."""
    poligonos = [PoligonoColoreable(id=p.id, geometria=p.geometria) for p in solicitud.poligonos]
    resultado = colorear_mapa(poligonos)
    return {"color_por_id": resultado.color_por_id, "num_colores": resultado.num_colores}


@app.get("/coloreado/municipios")
async def coloreado_municipios(
    zona: str | None = Query(default=None, max_length=6_000),
    cve_ent: str | None = Query(default=None, pattern=r"^\d{2}$"),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Los municipios de los estados que toca la zona (o de un estado, como antes),
    cada uno con su `color_indice` ya calculado para que dos municipios vecinos nunca
    se vean del mismo color en un mapa categorico. Son los del estado entero y no
    solo los de la zona: una colonia sola no tiene vecinos que distinguir."""
    estados = [cve_ent] if zona is None and cve_ent else (await _resuelta(pool, _zona_de(zona)))["estados"]
    async with pool.connection() as conn:
        cursor = await conn.execute(
            f"SELECT cvegeo, cve_mun, nombre, ST_AsGeoJSON({dibujo()}, 5) "
            "FROM municipios WHERE cve_ent = ANY(%(estados)s) ORDER BY cvegeo",
            {"estados": estados, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
        )
        filas = await cursor.fetchall()

    poligonos = [
        PoligonoColoreable(id=cvegeo, geometria=json.loads(geom))
        for cvegeo, _cve_mun, _nombre, geom in filas
        if geom is not None
    ]
    resultado = await asyncio.to_thread(colorear_mapa, poligonos)

    features = [
        _feature(
            cvegeo,
            nombre,
            geom,
            {"cve_mun": cve_mun, "color_indice": resultado.color_por_id.get(cvegeo)},
        )
        for cvegeo, cve_mun, nombre, geom in filas
    ]

    return {
        "type": "FeatureCollection",
        "features": features,
        "num_colores": resultado.num_colores,
    }


@app.get("/perfil_zona")
async def perfil_zona(
    zona: str | None = Query(default=None, max_length=6_000),
    cve_ent: str | None = Query(default=None, pattern=r"^\d{2}$"),
    cve_mun: str | None = Query(default=None, pattern=r"^\d{3}$"),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Perfil de una zona (clave de zona.py, o un municipio como antes de la 29h): cada
    documento con su nivel y su fuente. Ver docs/producto/perfil.md."""
    try:
        resultado = await perfil.perfil(pool, _zona_de(zona, cve_ent, cve_mun))
    except perfil.ConsultaInvalida as exc:
        raise HTTPException(422, str(exc)) from None
    if resultado is None:
        raise HTTPException(404, "la zona no toca nada cargado en Mapo")
    return resultado


@app.get("/perfil_zona/similares")
async def perfil_similares(
    zona: str = Query(max_length=6_000),
    areas: str = Query(default="", max_length=200),
    margen: str = Query(default="cerca", max_length=20),
    donde: str = Query(default="todo", max_length=20),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Zonas del mismo nivel que se parecen en las áreas pedidas, con el desglose
    variable por variable. Sin puntaje. Ver docs/producto/perfil.md."""
    try:
        resultado = await similares.buscar(pool, _zona_de(zona), areas=[a for a in areas.split(",") if a],
                                           margen=margen, donde=donde)
    except (similares.ConsultaInvalida, perfil.ConsultaInvalida) as exc:
        raise HTTPException(422, str(exc)) from None
    if resultado is None:
        raise HTTPException(404, "la zona no toca nada cargado en Mapo")
    return resultado


@app.get("/buscador/catalogo")
def buscador_catalogo() -> dict:
    """Intenciones, sectores con sus rubros y grupos de edad: lo que llena
    las plantillas con huecos del modo buscador."""
    return buscador.catalogo()


class SolicitudInterpretar(BaseModel):
    texto: str = Field(max_length=300)
    cve_ent: str


@app.post("/buscador/interpretar")
async def buscador_interpretar(solicitud: SolicitudInterpretar, pool: AsyncConnectionPool = Depends(get_pool)) -> dict:
    """Pregunta en español común -> plantilla con lo reconocido, lo que falta
    y los avisos. Determinista, sin modelo de lenguaje (docs/producto/buscador.md)."""
    municipios = await consultas.municipios_de(pool, solicitud.cve_ent)
    return buscador.interpretar(solicitud.texto, solicitud.cve_ent, municipios)


@app.post("/buscador/sugerir")
async def buscador_sugerir(solicitud: SolicitudInterpretar, pool: AsyncConnectionPool = Depends(get_pool)) -> dict:
    """Autocompletado de la pregunta con el mismo vocabulario del analizador:
    inicios de pregunta y rubros, sectores y municipios que empiezan con lo
    último que se escribió."""
    municipios = await consultas.municipios_de(pool, solicitud.cve_ent)
    return buscador.sugerir(solicitud.texto, solicitud.cve_ent, municipios)


class SolicitudResolver(BaseModel):
    cve_ent: str
    plantilla: buscador.Plantilla


@app.post("/buscador/resolver")
async def buscador_resolver(
    solicitud: SolicitudResolver,
    pool: AsyncConnectionPool = Depends(get_pool),
    osrm: OSRMClient = Depends(get_osrm_client),
) -> dict:
    """Plantilla completa -> capas y cifras, con las mismas consultas del
    modo técnico. 422 con `faltan` si a la plantilla le falta un hueco."""
    try:
        return await buscador.resolver(pool, osrm, solicitud.cve_ent, solicitud.plantilla)
    except buscador.PlantillaInvalida as exc:
        raise HTTPException(422, {"mensaje": str(exc), "faltan": exc.faltan}) from None


class SolicitudZonas(BaseModel):
    cve_ent: str
    plantilla: buscador.Plantilla
    indicador: str = "pobtot"
    minimo: float | None = Field(default=None, ge=0)
    minutos: float | None = Field(default=None, ge=0)
    orden: Literal["indicador", "minutos"] = "indicador"
    sentido: Literal["lejos", "cerca"] = "lejos"


@app.post("/buscador/zonas")
async def buscador_zonas(
    solicitud: SolicitudZonas,
    pool: AsyncConnectionPool = Depends(get_pool),
    osrm: OSRMClient = Depends(get_osrm_client),
) -> dict:
    """Zonas candidatas de un `donde_poner`. Va aparte de `/buscador/resolver`
    porque la primera vez tarda segundos: los minutos se calculan con OSRM y
    luego mover un criterio solo vuelve a filtrar."""
    try:
        return await buscador.zonas(
            pool,
            osrm,
            solicitud.cve_ent,
            solicitud.plantilla,
            indicador=solicitud.indicador,
            minimo=solicitud.minimo,
            minutos=solicitud.minutos,
            orden=solicitud.orden,
            sentido=solicitud.sentido,
        )
    except buscador.PlantillaInvalida as exc:
        raise HTTPException(422, {"mensaje": str(exc), "faltan": exc.faltan}) from None


@app.post("/buscador/patron")
async def buscador_patron(solicitud: SolicitudResolver, pool: AsyncConnectionPool = Depends(get_pool)) -> dict:
    """Si el rubro se agrupa, en qué plazas, junto a qué y dónde. Aparte de
    `/buscador/resolver` porque tarda unos segundos (199 sorteos)."""
    try:
        return await buscador.patron(pool, solicitud.cve_ent, solicitud.plantilla)
    except buscador.PlantillaInvalida as exc:
        raise HTTPException(422, {"mensaje": str(exc), "faltan": exc.faltan}) from None


class FilaCruce(BaseModel):
    lat: float | None = None
    lon: float | None = None
    clave: str | None = None
    valores: dict[str, float | None] = {}


class SolicitudCruce(BaseModel):
    tipo: Literal["puntos", "municipio", "ageb"]
    nivel: Literal["municipio", "ageb"]
    filas: list[FilaCruce] = Field(min_length=1, max_length=datos_propios.MAX_FILAS)
    agregaciones: dict[str, Literal["suma", "promedio", "mediana"]] = Field(
        default={}, max_length=datos_propios.MAX_COLUMNAS
    )
    censo: list[str] = []
    denue: str | None = None
    minutos: bool = False


class FilaGeometria(BaseModel):
    id: int
    geometria: dict


class SolicitudLocalidades(BaseModel):
    filas: list[FilaGeometria] = Field(min_length=1, max_length=datos_propios.MAX_FILAS)
    radio: float | None = Field(default=None, gt=0, le=100_000)
    ambito: Literal["rural", "urbana"] | None = None


@app.post("/localidades/distancia")
async def localidades_distancia(
    solicitud: SolicitudLocalidades, pool: AsyncConnectionPool = Depends(get_pool)
) -> dict:
    """De cada renglón a la localidad del censo más cercana, en metros, y con
    `radio`, cuántas hay y cuánta gente vive en ellas a esa distancia o menos."""
    from shapely.geometry import shape

    filas = [f.model_dump() for f in solicitud.filas]
    try:
        for f in filas:
            shape(f["geometria"])
    except Exception as exc:  # shapely lanza de todo con un GeoJSON roto
        raise HTTPException(status_code=422, detail="Alguna geometría no se pudo leer.") from exc
    return await localidades.distancia(pool, filas, solicitud.radio, solicitud.ambito)


@app.post("/cruce/calcular")
async def cruce_calcular(
    solicitud: SolicitudCruce,
    pool: AsyncConnectionPool = Depends(get_pool),
    osrm: OSRMClient = Depends(get_osrm_client),
) -> dict:
    """Una capa contra fuentes públicas, por zona. 422 con el motivo en texto."""
    try:
        return await cruce.calcular(
            pool,
            osrm,
            tipo=solicitud.tipo,
            nivel=solicitud.nivel,
            filas=[f.model_dump() for f in solicitud.filas],
            agregaciones=solicitud.agregaciones,
            censo=solicitud.censo,
            denue=solicitud.denue,
            minutos=solicitud.minutos,
        )
    except cruce.CruceInvalido as exc:
        raise HTTPException(422, str(exc)) from None


@app.get("/vivienda/catalogo")
async def vivienda_catalogo(pool: AsyncConnectionPool = Depends(get_pool)) -> dict:
    """Indicadores de la vista de precios, segmentos y años del SNIIV con
    cuántos meses trae cada uno."""
    return {**vivienda_vista.catalogo(), "anios_sniiv": await vivienda_vista.anios_sniiv(pool)}


@app.get("/vivienda/municipios")
async def vivienda_municipios(
    indicador: str = Query(),
    zona: str | None = Query(default=None, max_length=6_000),
    cve_ent: str | None = Query(default=None, pattern=r"^\d{2}$"),
    anio: int | None = Query(default=None, ge=2000, le=2100),
    segmento: str | None = Query(default=None),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Municipios de los estados que toca la zona (o de un estado, como antes) con el
    valor de un indicador de una sola fuente, su nivel y su `metodo`; el precio por
    AGEB, solo dentro de la zona. Sin dato es `null`, nunca cero."""
    if zona is None and cve_ent:
        estados, z = [cve_ent], None
    else:
        z = _zona_de(zona)
        estados = (await _resuelta(pool, z))["estados"]
    try:
        return await vivienda_vista.municipios(pool, estados, indicador, anio, segmento or None, zona=z)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@app.get("/vivienda/ficha")
async def vivienda_ficha(
    cve_ent: str = Query(pattern=r"^\d{2}$"),
    cve_mun: str = Query(pattern=r"^\d{3}$"),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """SHF, SNIIV, Intercensal 2025 y ENVI de un municipio, por separado."""
    ficha = await vivienda_vista.ficha(pool, cve_ent, cve_mun)
    if ficha is None:
        raise HTTPException(404, "municipio no encontrado")
    return ficha


# Las tablas que se citan desde la app. Las que no traen versión propia se citan
# por la fecha en que se cargaron: DENUE cambia cada semestre con el mismo
# nombre (docs/producto/citar.md). La clave es lo único que llega de `mapo`.
TABLAS_CITABLES = {
    "censo": ("fuente_censo_poblacion", True),
    "denue": ("fuente_denue_negocios", True),
    "municipios": ("municipios", True),
    "eic2025": ("fuente_eic2025_vivienda", True),
    "sniiv": ("fuente_sniiv_financiamiento", True),
    "shf": ("fuente_shf_ipv", False),
    "envi": ("fuente_envi2020_entidad", False),
    "precio": ("fuente_precio_estimado", True),
    "imss": ("fuente_imss_asegurados", True),
    "ce2024": ("fuente_ce2024_municipal", True),
    "efipem": ("fuente_efipem_municipal", True),
    "rezago": ("fuente_rezago_social_ageb", True),
    "cngmd": ("fuente_cngmd_planeacion", True),
}


@app.get("/fuentes/carga")
async def fuentes_carga(
    tabla: str,
    cve_ent: str | None = Query(default=None, pattern=r"^\d{2}$"),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Fecha de la última carga de una tabla, del estado si la tabla es por
    estado. `null` si la tabla está vacía."""
    if tabla not in TABLAS_CITABLES:
        raise HTTPException(400, f"tabla desconocida: {tabla}")
    nombre, por_estado = TABLAS_CITABLES[tabla]
    filtro = " WHERE cve_ent = %(e)s" if por_estado and cve_ent else ""
    async with pool.connection() as conn:
        cursor = await conn.execute(f"SELECT max(actualizado)::date::text FROM {nombre}{filtro}", {"e": cve_ent})
        (fecha,) = await cursor.fetchone()
    return {"tabla": tabla, "cargada": fecha}


@app.get("/zona/buscar")
async def zona_buscar(q: str = Query(default="", max_length=80), pool: AsyncConnectionPool = Depends(get_pool)) -> dict:
    """Sugerencias del selector de zona: estados, metrópolis, municipios, colonias y CP."""
    async with pool.connection() as conn:
        return await zona_comun.buscar(conn, q)


@app.get("/zona/resolver")
async def zona_resolver(
    clave: str = Query(max_length=6_000), pool: AsyncConnectionPool = Depends(get_pool)
) -> dict:
    """Una clave de zona (zona.py) a nombre, polígono, área y municipios. 422 si la
    clave no es válida; 404 si no hay nada cargado con ella."""
    try:
        z = zona_comun.validar(clave)
    except zona_comun.ZonaInvalida as exc:
        raise HTTPException(422, str(exc)) from None
    async with pool.connection() as conn:
        resuelta = await zona_comun.resolver(conn, z)
    if resuelta is None:
        raise HTTPException(404, "no hay nada cargado en Mapo con esa zona")
    return resuelta


@app.get("/accesibilidad/zona")
async def accesibilidad_zona(
    zona: str | None = Query(default=None, max_length=6_000),
    cve_ent: str | None = Query(default=None, pattern=r"^\d{2}$"),
    cve_mun: str | None = Query(default=None, pattern=r"^\d{3}$"),
    modo: str = Query(default="pie"),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Cuánta gente de una zona (clave de zona.py, o un municipio como antes) vive a
    cada minuto de cada servicio, a pie o en auto, y los minutos de cada lugar para el
    plano. Ver docs/producto/accesibilidad.md."""
    if zona is None and not (cve_ent and cve_mun):
        raise HTTPException(422, "hace falta una zona")
    try:
        modo = accesibilidad.modo_valido(modo)
        z = zona_comun.validar(zona if zona is not None else f"mun:{cve_ent}{cve_mun}")
    except (accesibilidad.ConsultaInvalida, zona_comun.ZonaInvalida) as exc:
        raise HTTPException(422, str(exc)) from None
    try:
        resultado = await accesibilidad.zona(pool, z, modo)
    except accesibilidad.ConsultaInvalida as exc:
        raise HTTPException(422, str(exc)) from None
    if resultado is None:
        raise HTTPException(404, "la zona no toca nada cargado en Mapo")
    return resultado


@app.get("/transporte/zona")
async def transporte_zona(
    zona: str | None = Query(default=None, max_length=6_000),
    cve_ent: str | None = Query(default=None, pattern=r"^\d{2}$"),
    cve_mun: str | None = Query(default=None, pattern=r"^\d{3}$"),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Rutas y paradas de transporte público que pasan por una zona (clave de zona.py,
    o un municipio como antes): las del GTFS con su frecuencia en hora pico o, si no
    hay GTFS, las de OSM. Hasta `MAX_KM2_CONSULTA`. Ver docs/fuentes/gtfs.md."""
    if zona is None and not (cve_ent and cve_mun):
        raise HTTPException(422, "hace falta una zona")
    try:
        resultado = await transporte.zona(pool, _zona_de(zona, cve_ent, cve_mun))
    except transporte.ZonaMuyGrande as exc:
        raise HTTPException(422, str(exc)) from None
    if resultado is None:
        raise HTTPException(404, "la zona no toca nada cargado en Mapo")
    return resultado


@app.get("/riesgos/capas")
async def riesgos_capas(
    zona: str = Query(max_length=6_000),
    peligros: str = Query(max_length=200),
    cerca_m: int = Query(default=1000),
) -> dict:
    """Lo que se dibuja de cada peligro pedido (claves separadas por coma), sin contar
    gente: el acetato "Riesgos" de /mapa."""
    try:
        resultado = await riesgos.capas(
            riesgos.zona_valida(clave=zona), riesgos.cerca_valido(cerca_m), riesgos.peligros_validos(peligros))
    except riesgos.ZonaInvalida as exc:
        raise HTTPException(422, str(exc)) from None
    if resultado is None:
        raise HTTPException(404, "la zona no toca nada cargado en Mapo")
    return resultado


@app.get("/riesgos/zona")
async def riesgos_zona(
    cve_ent: str | None = Query(default=None, pattern=r"^\d{2}$"),
    cve_mun: str | None = Query(default=None, pattern=r"^\d{3}$"),
    lon: float | None = Query(default=None, ge=-119, le=-85),
    lat: float | None = Query(default=None, ge=14, le=33.5),
    radio_m: float | None = Query(default=None, ge=100, le=riesgos.RADIO_MAX_M),
    zona: str | None = Query(default=None, max_length=6_000),
    cerca_m: int = Query(default=1000),
) -> dict:
    """Cada peligro de la zona por separado, con la gente que vive dentro y cerca.
    `zona` es la clave de la zona común (zona.py). Ver docs/producto/vista-riesgos.md."""
    clave = zona
    try:
        zona = riesgos.zona_valida(cve_ent, cve_mun, lon, lat, radio_m, clave=clave)
        cerca = riesgos.cerca_valido(cerca_m)
    except riesgos.ZonaInvalida as exc:
        raise HTTPException(422, str(exc)) from None
    try:
        resultado = await riesgos.resumen(zona, cerca)
    except riesgos.ZonaInvalida as exc:
        raise HTTPException(422, str(exc)) from None
    if resultado is None:
        raise HTTPException(404, "municipio no encontrado")
    return resultado
