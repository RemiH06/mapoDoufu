# Lo pesado de CPU (OR-Tools, Voronoi, coloreado) corre con asyncio.to_thread:
# dentro de un `async def` bloquearia el event loop para todas las peticiones.
import asyncio
import json
from typing import Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from mapo_core import buscador, consultas, datos_propios
from mapo_core.coloreado_mapa import PoligonoColoreable, colorear_mapa
from mapo_core.consultas import INDICADORES_CHOROPLETH, TOLERANCIA_SIMPLIFICACION as _TOLERANCIA_SIMPLIFICACION
from mapo_core.consultas import feature as _feature
from mapo_core.db import get_pool
from mapo_core.enigh_resumen import resumen_por_municipio
from mapo_core.isocronas import calcular_isocrona
from mapo_core.osrm_client import OSRMClient
from mapo_core.voronoi import PuntoVoronoi, calcular_voronoi
from mapo_core.vrp import Parada, Vehiculo, resolver_vrp

app = FastAPI(title="mapo_core")

_osrm_client: OSRMClient | None = None


def get_osrm_client() -> OSRMClient:
    global _osrm_client
    if _osrm_client is None:
        _osrm_client = OSRMClient()
    return _osrm_client


@app.exception_handler(psycopg.OperationalError)
async def base_de_datos_no_disponible(request: Request, exc: psycopg.OperationalError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": "La base de datos de mapo_core no esta disponible ahorita mismo.", "detalle": str(exc)},
    )


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}


def _geometria_sql(geometria: bool) -> str:
    """Las listas de nombres (selects de estado y municipio) no
    necesitan el poligono: con `geometria=false` la consulta no lo
    serializa y la respuesta baja de MB a KB."""
    return "ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s), 5)" if geometria else "NULL"


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
                """SELECT cvegeo, ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s), 5)
                   FROM agebs WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s ORDER BY cvegeo""",
                {"cve_ent": cve_ent, "cve_mun": cve_mun, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
            )
        else:
            cursor = await conn.execute(
                """SELECT cvegeo, ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s), 5)
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
            f"""SELECT cvegeo, ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s), 5)
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


async def _tabla(request: Request, formato: str) -> datos_propios.Tabla:
    contenido = await _cuerpo_acotado(request)
    try:
        return await asyncio.to_thread(datos_propios.leer, contenido, formato)
    except datos_propios.ArchivoInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/datos/leer")
async def datos_leer(request: Request, formato: str) -> dict:
    """Columnas, una muestra y una sugerencia de ubicación. No guarda nada."""
    tabla = await _tabla(request, formato)
    return {
        "columnas": tabla.columnas,
        "muestra": tabla.filas[:5],
        "num_filas": len(tabla.filas),
        "avisos": tabla.avisos,
        "sugerencia": datos_propios.sugerir(tabla),
    }


@app.post("/datos/ubicar")
async def datos_ubicar(
    request: Request,
    formato: str,
    tipo: Literal["puntos", "municipio", "ageb"],
    lat: str | None = None,
    lon: str | None = None,
    clave: str | None = None,
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Los renglones ya ubicados y por qué se descartó el resto. No guarda nada."""
    tabla = await _tabla(request, formato)
    try:
        if tipo == "puntos":
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
    return {**resultado, "columnas": tabla.columnas, "num_filas": len(tabla.filas), "avisos": tabla.avisos}


@app.get("/censo/choropleth")
async def censo_choropleth(
    indicador: str,
    cve_ent: str,
    cve_mun: str | None = None,
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Cruza los poligonos de AGEB con el Censo de Poblacion por AGEB,
    por cvegeo (propio de mapo_core, ya no un passthrough de Gaiarda).
    Si falta el censo de un AGEB, el poligono trae `valor_choropleth:
    null`, nunca se inventa un cero."""
    if indicador not in INDICADORES_CHOROPLETH:
        raise HTTPException(400, f"indicador invalido. Usa uno de: {sorted(INDICADORES_CHOROPLETH)}")

    features = await consultas.coropleta(pool, indicador, cve_ent, [cve_mun] if cve_mun else None)
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
    cve_ent: str,
    cve_mun: str,
    clase_actividad: str | None = None,
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Voronoi de los negocios de DENUE en un municipio, recortado al
    poligono real del municipio: "a cual de estos negocios le queda mas
    cerca cada lugar dentro del municipio". `clase_actividad` filtra por
    un termino de la tabla de rubros o por texto en el nombre de la clase;
    `filtro` dice que rubro o sector se reconocio, o null."""
    limite = await consultas.limite_municipios(pool, cve_ent, [cve_mun])
    if limite is None:
        raise HTTPException(
            404,
            f"No se encontro el municipio {cve_ent}{cve_mun} (¿ya se corrio "
            "'python -m mapo_core.cli municipios --estado' para ese estado?).",
        )

    # El filtro acepta las mismas palabras que el buscador ("florería",
    # "policía"), no solo texto del nombre oficial de la clase.
    clases, filtro = buscador.giro_tecnico(clase_actividad) if clase_actividad else (None, None)
    patron = clase_actividad if clases is None else None
    puntos = await consultas.negocios(pool, cve_ent, [cve_mun], patron=patron, clases=clases)

    if aviso := consultas.aviso_voronoi(len(puntos)):
        raise HTTPException(422, aviso)

    try:
        resultado = await asyncio.to_thread(calcular_voronoi, puntos, limite=limite)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    return {"celdas": resultado.celdas, "metodo": resultado.metodo, "num_negocios": len(puntos), "filtro": filtro}


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
async def coloreado_municipios(cve_ent: str, pool: AsyncConnectionPool = Depends(get_pool)) -> dict:
    """Los municipios de un estado, cada uno con su `color_indice` ya
    calculado para que dos municipios vecinos nunca se vean del mismo
    color en un mapa categorico."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            "SELECT cvegeo, cve_mun, nombre, ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s), 5) "
            "FROM municipios WHERE cve_ent = %(cve_ent)s ORDER BY cvegeo",
            {"cve_ent": cve_ent, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
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


async def _seguridad_de(pool: AsyncConnectionPool, cve_ent: str, cve_mun: str) -> dict | None:
    """Delitos del año mas reciente disponible para este municipio,
    agrupados por tipo. A proposito NO se combina en un solo "puntaje
    de seguridad" (mismo criterio que ya usa Gaiarda en su feature de
    Rutas): eso implicaria decisiones de metodologia que no se deben
    esconder detras de un numero. None si no hay ningun dato cargado
    todavia para este municipio (SESNSP se carga a mano, ver
    `sesnsp_ingesta.py`)."""
    async with pool.connection() as conn:
        cursor_anio = await conn.execute(
            "SELECT max(anio) FROM fuente_sesnsp_delitos_municipal WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s",
            {"cve_ent": cve_ent, "cve_mun": cve_mun},
        )
        (anio,) = await cursor_anio.fetchone()
        if anio is None:
            return None

        cursor_tipos = await conn.execute(
            """SELECT tipo_delito, sum(cantidad) FROM fuente_sesnsp_delitos_municipal
               WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s AND anio = %(anio)s
               GROUP BY tipo_delito ORDER BY sum(cantidad) DESC""",
            {"cve_ent": cve_ent, "cve_mun": cve_mun, "anio": anio},
        )
        por_tipo = await cursor_tipos.fetchall()

    return {
        "anio": anio,
        "total_delitos": sum(cantidad for _tipo, cantidad in por_tipo),
        "por_tipo": [[tipo, cantidad] for tipo, cantidad in por_tipo],
    }


@app.get("/perfil_zona")
async def perfil_zona(cve_ent: str, cve_mun: str, pool: AsyncConnectionPool = Depends(get_pool)) -> dict:
    """Perfil de un municipio: demografia (censo), comercio (DENUE),
    consumo (ENIGH), seguridad (SESNSP) y laboral (ENOE), ya con datos
    propios de mapo_core. Laboral es la unica seccion a nivel entidad,
    no municipio (la ENOE no tiene representatividad municipal)."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """SELECT pobtot, pobfem, pobmas, graproes, pea, pocupada, pdesocup, tothog, vivtot
               FROM fuente_censo_poblacion
               WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s AND nivel = 'municipio'""",
            {"cve_ent": cve_ent, "cve_mun": cve_mun},
        )
        fila = await cursor.fetchone()

        cursor_total = await conn.execute(
            "SELECT count(*) FROM fuente_denue_negocios WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s",
            {"cve_ent": cve_ent, "cve_mun": cve_mun},
        )
        (total_negocios,) = await cursor_total.fetchone()

        cursor_clases = await conn.execute(
            """SELECT clase_actividad, count(*) FROM fuente_denue_negocios
               WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s AND clase_actividad IS NOT NULL
               GROUP BY clase_actividad ORDER BY count(*) DESC LIMIT 10""",
            {"cve_ent": cve_ent, "cve_mun": cve_mun},
        )
        top_clases = await cursor_clases.fetchall()

        consumo = await resumen_por_municipio(conn, cve_ent, cve_mun, columna="gasto_mon", por_dia=True)

    demografia = None
    if fila is not None:
        campos = ["pobtot", "pobfem", "pobmas", "graproes", "pea", "pocupada", "pdesocup", "tothog", "vivtot"]
        demografia = dict(zip(campos, fila))

    return {
        "cve_ent": cve_ent,
        "cve_mun": cve_mun,
        "demografia": demografia,
        "comercio": {
            "total_negocios": total_negocios,
            "top_clases_actividad": [[clase, cantidad] for clase, cantidad in top_clases],
        },
        "consumo": consumo,
        "seguridad": await _seguridad_de(pool, cve_ent, cve_mun),
        "laboral": await consultas.laboral_de(pool, cve_ent),
    }


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
        )
    except buscador.PlantillaInvalida as exc:
        raise HTTPException(422, {"mensaje": str(exc), "faltan": exc.faltan}) from None
