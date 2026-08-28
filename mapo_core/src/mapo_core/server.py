import json

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from mapo_core.coloreado_mapa import PoligonoColoreable, colorear_mapa
from mapo_core.db import get_pool
from mapo_core.isocronas import calcular_isocrona
from mapo_core.osrm_client import OSRMClient
from mapo_core.voronoi import PuntoVoronoi, calcular_voronoi
from mapo_core.vrp import Parada, Vehiculo, resolver_vrp

app = FastAPI(title="mapo_core")

_osrm_client: OSRMClient | None = None

# Simplificacion aplicada al leer poligonos (no al guardar): mismo
# valor y misma razon que ya usaba Gaiarda, sin esto Leaflet se pone
# lento dibujando miles de vertices de mas.
_TOLERANCIA_SIMPLIFICACION = 0.0005

# Unicos indicadores permitidos como columna dinamica en el
# choropleth. Whitelist explicita, no se interpola el nombre de
# columna directo del query param (puerta a inyeccion SQL).
INDICADORES_CHOROPLETH = {
    "pobtot", "pobfem", "pobmas", "p_0a2", "p_3a5", "p_6a11", "p_12a14",
    "p_15a17", "p_18a24", "p_60ymas", "graproes", "pea", "pea_f", "pea_m",
    "pe_inac", "pocupada", "pdesocup", "pder_ss", "tothog", "vivtot",
    "tvivhab", "prom_ocup", "vph_inter", "vph_pc", "vph_autom", "vph_cel", "vph_snbien",
}


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


def _feature(cvegeo: str, nombre: str, geojson_geom: str | None, props_extra: dict | None = None) -> dict:
    propiedades = {"cvegeo": cvegeo, "nomgeo": nombre, **(props_extra or {})}
    return {
        "type": "Feature",
        "properties": propiedades,
        "geometry": json.loads(geojson_geom) if geojson_geom else None,
    }


@app.get("/geo/estados")
async def geo_estados(pool: AsyncConnectionPool = Depends(get_pool)) -> dict:
    """Los 32 estados, con su poligono real (propio de mapo_core, ya
    no un passthrough de Gaiarda)."""
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """SELECT cve_ent, nombre, ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s))
               FROM entidades ORDER BY cve_ent""",
            {"tolerancia": _TOLERANCIA_SIMPLIFICACION},
        )
        filas = await cursor.fetchall()

    features = [_feature(cve_ent, nombre, geom) for cve_ent, nombre, geom in filas]
    return {"type": "FeatureCollection", "features": features}


@app.get("/geo/municipios")
async def geo_municipios(
    cve_ent: str | None = None, pool: AsyncConnectionPool = Depends(get_pool)
) -> dict:
    """Municipios, opcionalmente filtrados por estado, con su poligono real."""
    async with pool.connection() as conn:
        if cve_ent:
            cursor = await conn.execute(
                """SELECT cvegeo, cve_mun, nombre, ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s))
                   FROM municipios WHERE cve_ent = %(cve_ent)s ORDER BY cvegeo""",
                {"cve_ent": cve_ent, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
            )
        else:
            cursor = await conn.execute(
                """SELECT cvegeo, cve_mun, nombre, ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s))
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
                """SELECT cvegeo, ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s))
                   FROM agebs WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s ORDER BY cvegeo""",
                {"cve_ent": cve_ent, "cve_mun": cve_mun, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
            )
        else:
            cursor = await conn.execute(
                """SELECT cvegeo, ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s))
                   FROM agebs WHERE cve_ent = %(cve_ent)s ORDER BY cvegeo""",
                {"cve_ent": cve_ent, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
            )
        filas = await cursor.fetchall()

    features = [_feature(cvegeo, cvegeo, geom) for cvegeo, geom in filas]
    return {"type": "FeatureCollection", "features": features}


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

    async with pool.connection() as conn:
        if cve_mun:
            cursor = await conn.execute(
                f"""SELECT a.cvegeo, ST_AsGeoJSON(ST_Simplify(a.geom, %(tolerancia)s)), c.{indicador}
                    FROM agebs a
                    LEFT JOIN fuente_censo_poblacion c
                      ON c.cvegeo = a.cvegeo AND c.nivel = 'ageb'
                    WHERE a.cve_ent = %(cve_ent)s AND a.cve_mun = %(cve_mun)s
                    ORDER BY a.cvegeo""",
                {"cve_ent": cve_ent, "cve_mun": cve_mun, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
            )
        else:
            cursor = await conn.execute(
                f"""SELECT a.cvegeo, ST_AsGeoJSON(ST_Simplify(a.geom, %(tolerancia)s)), c.{indicador}
                    FROM agebs a
                    LEFT JOIN fuente_censo_poblacion c
                      ON c.cvegeo = a.cvegeo AND c.nivel = 'ageb'
                    WHERE a.cve_ent = %(cve_ent)s
                    ORDER BY a.cvegeo""",
                {"cve_ent": cve_ent, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
            )
        filas = await cursor.fetchall()

    features = []
    for cvegeo, geom, valor in filas:
        if geom is None:
            continue
        features.append(_feature(cvegeo, cvegeo, geom, {"indicador": indicador, "valor_choropleth": valor}))

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
    dato confirmado."""
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
        solucion = resolver_vrp(
            paradas,
            vehiculos,
            deposito=solicitud.deposito,
            matriz_km=resultado_osrm["distancias_km"],
            matriz_min=resultado_osrm["duraciones_min"],
        )
        metodo = "carretera_real"
    else:
        solucion = resolver_vrp(
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

    return {
        "rutas": [
            {
                "vehiculo_id": r.vehiculo_id,
                "orden_paradas": r.orden_paradas,
                "distancia_km": r.distancia_km,
            }
            for r in solucion.rutas
        ],
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


async def _buscar_municipio(pool: AsyncConnectionPool, cve_ent: str, cve_mun: str) -> dict | None:
    async with pool.connection() as conn:
        cursor = await conn.execute(
            "SELECT nombre, ST_AsGeoJSON(geom) FROM municipios WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s",
            {"cve_ent": cve_ent, "cve_mun": cve_mun},
        )
        fila = await cursor.fetchone()
    if fila is None or fila[1] is None:
        return None
    nombre, geom = fila
    return {"nombre": nombre, "geometry": json.loads(geom)}


async def _negocios_de(
    pool: AsyncConnectionPool, cve_ent: str, cve_mun: str, clase_actividad: str | None
) -> list[PuntoVoronoi]:
    async with pool.connection() as conn:
        if clase_actividad:
            cursor = await conn.execute(
                """SELECT id, nombre, lat, lon FROM fuente_denue_negocios
                   WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s
                     AND lat IS NOT NULL AND lon IS NOT NULL
                     AND clase_actividad ILIKE %(patron)s""",
                {"cve_ent": cve_ent, "cve_mun": cve_mun, "patron": f"%{clase_actividad}%"},
            )
        else:
            cursor = await conn.execute(
                """SELECT id, nombre, lat, lon FROM fuente_denue_negocios
                   WHERE cve_ent = %(cve_ent)s AND cve_mun = %(cve_mun)s
                     AND lat IS NOT NULL AND lon IS NOT NULL""",
                {"cve_ent": cve_ent, "cve_mun": cve_mun},
            )
        filas = await cursor.fetchall()

    return [PuntoVoronoi(id=id_, nombre=nombre, lat=lat, lon=lon) for id_, nombre, lat, lon in filas]


@app.get("/voronoi/denue")
async def voronoi_denue(
    cve_ent: str,
    cve_mun: str,
    clase_actividad: str | None = None,
    pool: AsyncConnectionPool = Depends(get_pool),
) -> dict:
    """Voronoi de los negocios de DENUE en un municipio (opcionalmente
    filtrados por texto en `clase_actividad`), recortado al poligono
    real del municipio: "a cual de estos negocios le queda mas cerca
    cada lugar dentro del municipio"."""
    municipio = await _buscar_municipio(pool, cve_ent, cve_mun)
    if municipio is None:
        raise HTTPException(
            404,
            f"No se encontro el municipio {cve_ent}{cve_mun} (¿ya se corrio "
            "'python -m mapo_core.cli municipios --estado' para ese estado?).",
        )

    puntos = await _negocios_de(pool, cve_ent, cve_mun, clase_actividad)

    if len(puntos) < 3:
        raise HTTPException(
            422,
            f"Solo hay {len(puntos)} negocio(s) con esos filtros; se necesitan al menos 3 para un diagrama de Voronoi.",
        )

    try:
        resultado = calcular_voronoi(puntos, limite=municipio["geometry"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    return {"celdas": resultado.celdas, "metodo": resultado.metodo, "num_negocios": len(puntos)}


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
            "SELECT cvegeo, cve_mun, nombre, ST_AsGeoJSON(ST_Simplify(geom, %(tolerancia)s)) "
            "FROM municipios WHERE cve_ent = %(cve_ent)s ORDER BY cvegeo",
            {"cve_ent": cve_ent, "tolerancia": _TOLERANCIA_SIMPLIFICACION},
        )
        filas = await cursor.fetchall()

    poligonos = [
        PoligonoColoreable(id=cvegeo, geometria=json.loads(geom))
        for cvegeo, _cve_mun, _nombre, geom in filas
        if geom is not None
    ]
    resultado = colorear_mapa(poligonos)

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
async def perfil_zona(cve_ent: str, cve_mun: str, pool: AsyncConnectionPool = Depends(get_pool)) -> dict:
    """Perfil de un municipio: demografia (censo) y comercio (DENUE)
    ya con datos propios de mapo_core. Consumo (ENIGH) y seguridad
    (SESNSP) todavia no estan portados (igual que laboral/ENOE, que
    tampoco lo estaba del lado de Gaiarda): se marcan honestos como no
    disponibles, en vez de fingir que no hay datos (que es un mensaje
    distinto: "no hay negocios" no es lo mismo que "no hemos portado
    esa fuente todavia")."""
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
        "consumo_disponible": False,
        "seguridad_disponible": False,
        "laboral_disponible": False,
    }
