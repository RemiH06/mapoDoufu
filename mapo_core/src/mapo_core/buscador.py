"""Modo buscador (RF6, docs/producto/buscador.md).

Dos pasos, los dos deterministas:

1. `interpretar`: texto en español común -> una `Plantilla` (intención y
   parámetros de un conjunto cerrado) más lo que falta y lo que no se pudo
   entender. Sin modelo de lenguaje: normaliza, busca términos de la tabla de
   rubros, nombres de municipio, números con "minutos" o "años" y palabras de
   intención. No adivina: si dos rubros aparecen, no elige uno.
2. `resolver`: una plantilla completa -> capas y cifras, con las mismas
   consultas del modo técnico (`consultas.py`). Nunca un puntaje único: cada
   cifra va con su fórmula y cada hueco de datos se dice.
"""

from __future__ import annotations

import asyncio
import re
from functools import cache

from pydantic import BaseModel, Field

from mapo_core import consultas, rubros
from mapo_core import zonas as zonas_candidatas
from mapo_core.isocronas import calcular_isocrona
from mapo_core.voronoi import calcular_voronoi

INTENCIONES = {
    "donde_poner": "Dónde poner o dónde falta",
    "cuantos": "Contar negocios",
    "cuantos_cerca": "Contar negocios cerca de un punto",
    "donde_contratar": "Dónde buscar gente por edad",
    "perfil": "Perfil de un municipio",
}

# Solo los grupos que trae el censo por AGEB (docs/producto/buscador.md).
GRUPOS_EDAD = {
    (0, 2): "p_0a2",
    (3, 5): "p_3a5",
    (6, 11): "p_6a11",
    (12, 14): "p_12a14",
    (15, 17): "p_15a17",
    (18, 24): "p_18a24",
}
NOMBRES_EDAD = {
    "p_0a2": "0 a 2 años",
    "p_3a5": "3 a 5 años",
    "p_6a11": "6 a 11 años",
    "p_12a14": "12 a 14 años",
    "p_15a17": "15 a 17 años",
    "p_18a24": "18 a 24 años",
    "p_60ymas": "60 años o más",
}

# Arriba de esto no se dibuja un punto por negocio: el navegador se traba y
# a escala de ciudad son una mancha. La cifra sí se da.
MAX_PUNTOS = 5000

_REQUISITOS = {
    "donde_poner": ("rubro", "municipios"),
    "cuantos": ("rubro", "municipios"),
    "cuantos_cerca": ("rubro", "punto", "minutos"),
    "donde_contratar": ("edad", "municipios"),
    "perfil": ("municipio",),
}

# El orden importa: "¿dónde busco gente...?" es contratar aunque diga dónde.
_PALABRAS_INTENCION = [
    ("perfil", r"\bcomo es\b|\bcomo esta\b|\bperfil\b|\bhablame de\b"),
    (
        "donde_contratar",
        r"contrat|reclut|\bmano de obra\b|\bbusco (?:a )?(?:gente|personal|trabajadores|empleados)\b",
    ),
    ("cuantos", r"\bcuant[oa]s?\b|\bnumero de\b"),
    ("donde_poner", r"\bdonde\b|\bconviene\b|\bfalta(?:n)?\b|\bpongo\b|\bponer\b|\babro\b|\babrir\b"),
]
_CERCA = r"\bcerca\b|\ba la redonda\b|\balrededor\b|\bde aqui\b"
_PUBLICOS = r"\bpublic[oa]s?\b|\bdel gobierno\b|\bgubernamental(?:es)?\b"
# "Centro de salud" es un término de rubro, pero además quiere decir público.
_IMPLICA_PUBLICOS = r"\bcentros? de salud\b"


class Plantilla(BaseModel):
    intencion: str | None = None
    rubro: str | None = None
    sector: str | None = None
    municipios: list[str] = Field(default_factory=list)
    minutos: int | None = Field(default=None, gt=0)
    edad: str | None = None
    solo_publicos: bool = False
    lat: float | None = None
    lon: float | None = None


class PlantillaInvalida(ValueError):
    """La plantilla no se puede resolver: le falta algo o trae un valor fuera
    del conjunto cerrado."""

    def __init__(self, mensaje: str, faltan: list[str] | None = None):
        super().__init__(mensaje)
        self.faltan = faltan or []


def faltantes(p: Plantilla) -> list[str]:
    """Huecos vacíos de la plantilla, en el orden en que se muestran."""
    if p.intencion is None:
        return ["intencion"]
    tiene = {
        "rubro": p.rubro is not None or p.sector is not None,
        "municipios": bool(p.municipios),
        "municipio": len(p.municipios) == 1,
        "punto": p.lat is not None and p.lon is not None,
        "minutos": p.minutos is not None,
        "edad": p.edad is not None,
    }
    return [r for r in _REQUISITOS[p.intencion] if not tiene[r]]


def catalogo() -> dict:
    """Lo que la pantalla necesita para las plantillas con huecos."""
    por_sector: dict[str, list[dict]] = {}
    for clave, r in rubros.rubros().items():
        por_sector.setdefault(r.sector, []).append({"rubro": clave, "nombre": r.nombre})
    return {
        "intenciones": [{"intencion": k, "nombre": v, "huecos": list(_REQUISITOS[k])} for k, v in INTENCIONES.items()],
        "sectores": [
            {"sector": s, "nombre": f["nombre"], "rubros": sorted(por_sector[s], key=lambda r: r["nombre"])}
            for s, f in rubros.sectores().items()
            if f["buscable"] == "si"
        ],
        "edades": [{"edad": k, "nombre": v} for k, v in NOMBRES_EDAD.items()],
        "indicadores_zonas": [{"indicador": k, "nombre": v} for k, v in zonas_candidatas.INDICADORES.items()],
    }


# --- Interpretar -------------------------------------------------------------


def _patron(termino: str) -> str:
    """Cada palabra admite su plural ("consultorios medicos")."""
    return r"\b" + r"\s".join(re.escape(p) + r"(?:s|es)?" for p in termino.split()) + r"\b"


@cache
def _patrones_rubros() -> list[tuple[re.Pattern, str, str]]:
    return [(re.compile(_patron(t)), tipo, clave) for t, (tipo, clave) in rubros.terminos().items()]


def _buscar_terminos(texto: str, cve_ent: str, municipios: list[tuple[str, str]]) -> list[tuple[int, int, str, str]]:
    """Todas las coincidencias (inicio, fin, tipo, clave), y luego se quedan
    las más largas sin traslape: "tienda de mascotas" le gana al municipio
    Mascota, "San Juan de los Lagos" a "Lagos"."""
    candidatos = []
    for patron, tipo, clave in _patrones_rubros():
        candidatos += [(m.start(), m.end(), tipo, clave) for m in patron.finditer(texto)]

    nombres = [(rubros.normalizar(n), cve) for cve, n in municipios]
    validos = {cve for cve, _ in municipios}
    nombres += [(a, cve) for a, cve in rubros.alias_municipios().get(cve_ent, []) if cve in validos]
    for nombre, cve in nombres:
        candidatos += [
            (m.start(), m.end(), "municipio", cve) for m in re.finditer(r"\b" + re.escape(nombre) + r"\b", texto)
        ]

    aceptados: list[tuple[int, int, str, str]] = []
    for c in sorted(candidatos, key=lambda c: (c[0] - c[1], c[0])):
        if all(c[1] <= a[0] or c[0] >= a[1] for a in aceptados):
            aceptados.append(c)
    return sorted(aceptados)


def _minutos(texto: str) -> int | None:
    if m := re.search(r"\b(\d{1,3})\s*(?:min|mins|minutos?)\b", texto):
        return int(m.group(1)) or None
    if re.search(r"\bmedia hora\b", texto):
        return 30
    if re.search(r"\buna hora\b", texto):
        return 60
    return None


def _edad(texto: str) -> tuple[str | None, str | None]:
    """(indicador del censo, aviso). Un rango que no es un grupo del censo no
    se aproxima: se avisa."""
    if re.search(r"\badultos mayores\b|\btercera edad\b|\b60 (?:anos )?(?:o|y) mas\b|\bmayores de 60\b", texto):
        return "p_60ymas", None
    if m := re.search(r"\b(\d{1,3})\s+(?:a|y)\s+(\d{1,3})\s+anos\b", texto):
        rango = (int(m.group(1)), int(m.group(2)))
        if rango in GRUPOS_EDAD:
            return GRUPOS_EDAD[rango], None
        grupos = ", ".join(NOMBRES_EDAD.values())
        return None, (
            f"El censo por AGEB no trae el grupo de {rango[0]} a {rango[1]} años y no se aproxima. "
            f"Los grupos son: {grupos}."
        )
    if m := re.search(r"\bmayores de (\d{1,3})\b", texto):
        return None, f"El censo por AGEB no trae mayores de {m.group(1)}; el grupo más alto es 60 años o más."
    return None, None


def _nombre(tipo: str, clave: str, municipios: dict[str, str]) -> str:
    if tipo == "rubro":
        return rubros.rubros()[clave].nombre
    if tipo == "sector":
        return rubros.sectores()[clave]["nombre"]
    return municipios[clave]


def _avisos_de_marca(norm: str, encontrados: list[tuple[int, int, str, str]]) -> list[str]:
    """DENUE clasifica por giro: "oxxos" se resuelve como todos los minisúpers
    y hay que decirlo."""
    avisos = []
    for inicio, fin, tipo, clave in encontrados:
        if tipo != "rubro":
            continue
        rubro = rubros.rubros()[clave]
        if any(re.fullmatch(_patron(rubros.normalizar(m)), norm[inicio:fin]) for m in rubro.marcas):
            avisos.append(
                f"DENUE clasifica por giro, no por marca: la cifra son todos los negocios de "
                f"{rubro.nombre}, no solo los de la marca que nombraste."
            )
    return avisos


def giro_tecnico(texto: str) -> tuple[list[str] | None, str | None]:
    """Interpreta el filtro "giro" del modo técnico: (clases exactas, nombre de
    lo reconocido). Un término de la tabla da su rubro o sector; si no, las
    clases que contienen el texto, sin importar acentos. Sin coincidencia da
    (None, None) y `consultas.negocios` cae al ILIKE, para clases que todavía
    no están en la tabla."""
    norm = rubros.normalizar(texto)
    encontrados = _buscar_terminos(norm, "", [])
    if len(encontrados) == 1 and encontrados[0][:2] == (0, len(norm)):
        _, _, tipo, clave = encontrados[0]
        return rubros.clases_de(**{tipo: clave}), _nombre(tipo, clave, {})
    return rubros.clases_con_texto(texto) or None, None


def interpretar(texto: str, cve_ent: str, municipios: list[tuple[str, str]]) -> dict:
    """Texto libre -> plantilla con lo reconocido, lo que falta y los avisos.
    `municipios` son los (cve_mun, nombre) del estado elegido."""
    norm = rubros.normalizar(texto)
    encontrados = _buscar_terminos(norm, cve_ent, municipios)
    nombres_mun = dict(municipios)
    avisos: list[str] = []

    def de_tipo(tipo: str) -> list[str]:
        return list(dict.fromkeys(clave for _, _, t, clave in encontrados if t == tipo))

    p = Plantilla(municipios=de_tipo("municipio"))

    rubros_vistos, sectores_vistos = de_tipo("rubro"), de_tipo("sector")
    if len(rubros_vistos) > 1:
        nombres = ", ".join(_nombre("rubro", r, nombres_mun) for r in rubros_vistos)
        avisos.append(f"Reconocí varios rubros ({nombres}); elige uno.")
    elif rubros_vistos:
        p.rubro = rubros_vistos[0]
        otros = [s for s in sectores_vistos if s != rubros.rubros()[p.rubro].sector]
        if otros:
            avisos.append(f"Se usa el rubro {_nombre('rubro', p.rubro, nombres_mun)}, no el sector entero.")
    elif len(sectores_vistos) > 1:
        nombres = ", ".join(_nombre("sector", s, nombres_mun) for s in sectores_vistos)
        avisos.append(f"Reconocí varios sectores ({nombres}); elige uno.")
    elif sectores_vistos:
        p.sector = sectores_vistos[0]

    # Lo ya reconocido como término no cuenta para el resto: "baños públicos"
    # es un rubro, no el filtro `solo_publicos`.
    resto = norm
    for inicio, fin, _, _ in encontrados:
        resto = resto[:inicio] + " " * (fin - inicio) + resto[fin:]

    p.minutos = _minutos(resto)
    p.edad, aviso_edad = _edad(resto)
    if aviso_edad:
        avisos.append(aviso_edad)
    p.solo_publicos = bool(re.search(_PUBLICOS, resto) or re.search(_IMPLICA_PUBLICOS, norm))

    for intencion, patron in _PALABRAS_INTENCION:
        if re.search(patron, resto):
            p.intencion = intencion
            break
    if p.intencion == "cuantos" and (p.minutos or re.search(_CERCA, resto)):
        p.intencion = "cuantos_cerca"
    # Sin palabra de intención, minutos y edad solo caben en una.
    if p.intencion is None and p.minutos:
        p.intencion = "cuantos_cerca"
    if p.intencion is None and p.edad:
        p.intencion = "donde_contratar"

    if p.intencion == "perfil" and len(p.municipios) > 1:
        avisos.append("El perfil es de un municipio; elige cuál.")

    # Estas dos intenciones no usan rubro: se quita y se dice, no se ignora.
    if p.intencion in ("donde_contratar", "perfil") and (p.rubro or p.sector):
        nombre = _nombre("rubro" if p.rubro else "sector", p.rubro or p.sector, nombres_mun)
        avisos.append(
            f"El censo no dice quién trabaja en qué: se busca por edad, sin distinguir {nombre}."
            if p.intencion == "donde_contratar"
            else f"El perfil es del municipio entero, sin distinguir {nombre}."
        )
        p.rubro = p.sector = None

    avisos += _avisos_de_marca(norm, encontrados)

    if not encontrados and p.intencion is None:
        avisos.append("No reconocí ninguna pregunta, rubro ni municipio. Llena la plantilla a mano.")

    return {
        "plantilla": p.model_dump(),
        "faltan": faltantes(p),
        "avisos": avisos,
        "reconocidos": [
            {"fragmento": norm[i:f], "tipo": t, "clave": c, "nombre": _nombre(t, c, nombres_mun)}
            for i, f, t, c in encontrados
        ],
    }


# --- Resolver ----------------------------------------------------------------


def _validar(p: Plantilla) -> None:
    if p.intencion not in INTENCIONES:
        raise PlantillaInvalida("Falta la pregunta.", ["intencion"])
    if falta := faltantes(p):
        raise PlantillaInvalida("A la plantilla le faltan huecos: " + ", ".join(falta) + ".", falta)
    if p.rubro is not None and p.rubro not in rubros.rubros():
        raise PlantillaInvalida(f"Rubro desconocido: {p.rubro}.")
    if p.sector is not None and rubros.sectores().get(p.sector, {}).get("buscable") != "si":
        raise PlantillaInvalida(f"Sector desconocido o no buscable: {p.sector}.")
    if p.edad is not None and p.edad not in NOMBRES_EDAD:
        raise PlantillaInvalida(f"Grupo de edad desconocido: {p.edad}.")


def _que(p: Plantilla) -> str:
    """Nombre de lo que se busca, como lo lee quien pregunta."""
    nombre = rubros.rubros()[p.rubro].nombre if p.rubro else rubros.sectores()[p.sector]["nombre"]
    return f"{nombre} (solo sector público)" if p.solo_publicos else nombre


def _unidad(p: Plantilla) -> tuple[str, str]:
    """(plural, singular). Una comisaría o un hospital público no son negocios."""
    sector = rubros.rubros()[p.rubro].sector if p.rubro else p.sector
    if p.solo_publicos or sector == "gobierno_y_seguridad":
        return "unidades", "unidad"
    return "negocios", "negocio"


def _puntos(lista) -> list[dict]:
    return [{"lat": n.lat, "lon": n.lon, "nombre": n.nombre} for n in lista]


async def resolver(pool, osrm, cve_ent: str, p: Plantilla) -> dict:
    _validar(p)
    if p.intencion == "perfil":
        return {"intencion": "perfil", "perfil": {"cve_ent": cve_ent, "cve_mun": p.municipios[0]}}
    if p.intencion == "donde_contratar":
        return await _donde_contratar(pool, cve_ent, p)

    clases = rubros.clases_de(rubro=p.rubro, sector=p.sector, solo_publicos=p.solo_publicos)
    avisos = []
    if not clases:
        avisos.append(f"{_que(p)} no tiene ninguna clase de DENUE del sector público.")
    if p.rubro and rubros.rubros()[p.rubro].nota:
        avisos.append(rubros.rubros()[p.rubro].nota)

    if p.intencion == "cuantos_cerca":
        return await _cuantos_cerca(pool, osrm, p, clases, avisos)
    return await _por_municipio(pool, cve_ent, p, clases, avisos)


async def zonas(
    pool,
    osrm,
    cve_ent: str,
    p: Plantilla,
    *,
    indicador: str = "pobtot",
    minimo: float | None = None,
    minutos: float | None = None,
    orden: str = "indicador",
) -> dict:
    """Zonas candidatas de un `donde_poner`: AGEB que cumplen criterios a la
    vista, sin puntaje (docs/producto/buscador.md)."""
    _validar(p)
    if p.intencion != "donde_poner":
        raise PlantillaInvalida("Las zonas candidatas son de la pregunta dónde poner.")
    if indicador not in zonas_candidatas.INDICADORES:
        raise PlantillaInvalida(f"Indicador desconocido: {indicador}.")

    clases = rubros.clases_de(rubro=p.rubro, sector=p.sector, solo_publicos=p.solo_publicos)
    try:
        return await zonas_candidatas.calcular(
            pool,
            osrm,
            cve_ent,
            p.municipios,
            clases,
            indicador=indicador,
            minimo=minimo,
            minutos=minutos,
            orden=orden,
            unidad=_unidad(p)[0],
        )
    except zonas_candidatas.DemasiadasZonas as exc:
        raise PlantillaInvalida(str(exc)) from None


async def _por_municipio(pool, cve_ent: str, p: Plantilla, clases: list[str], avisos: list[str]) -> dict:
    """`cuantos` y `donde_poner`: conteo por municipio y puntos; `donde_poner`
    agrega la población, habitantes por negocio, el Voronoi de la competencia
    y la coropleta de población."""
    censo = await consultas.censo_municipios(pool, cve_ent, p.municipios, "pobtot")
    if len(censo) != len(set(p.municipios)):
        raise PlantillaInvalida("Algún municipio no está en la base.")

    conteo = await consultas.conteo_por_municipio(pool, cve_ent, p.municipios, clases)
    puntos = await consultas.negocios(pool, cve_ent, p.municipios, clases=clases) if clases else []

    total = sum(conteo.values())
    if len(puntos) < total:
        avisos.append(
            f"{total - len(puntos)} {_unidad(p)[0]} sin ubicación en DENUE: cuentan, pero no se dibujan."
        )

    filas = []
    for cve in p.municipios:
        nombre, poblacion = censo.get(cve, (cve, None))
        filas.append({"cve_mun": cve, "nombre": nombre, "negocios": conteo[cve], "poblacion": poblacion})

    capas: dict = {}
    cifras: dict = {"que": _que(p), "unidad": _unidad(p)[0], "municipios": filas, "total_negocios": total}

    if p.intencion == "donde_poner":
        _habitantes_por_negocio(cifras, filas, avisos)
        cifras["formula"] = f"habitantes por {_unidad(p)[1]} = población total ÷ {_unidad(p)[0]} del rubro"
        capas["coropleta"] = {
            "geojson": {"type": "FeatureCollection", "features": await consultas.coropleta(pool, "pobtot", cve_ent, p.municipios)},
            "indicador": "pobtot",
            "etiqueta": "Población total",
        }
        capas["voronoi"] = await _voronoi(pool, cve_ent, p.municipios, puntos, avisos)
    elif len(puntos) > MAX_PUNTOS:
        avisos.append(f"Son {len(puntos)} {_unidad(p)[0]}: demasiados para dibujar uno por uno. Se dan las cifras.")
    else:
        capas["puntos"] = _puntos(puntos)

    return {"intencion": p.intencion, "capas": capas, "cifras": cifras, "avisos": avisos}


def _habitantes_por_negocio(cifras: dict, filas: list[dict], avisos: list[str]) -> None:
    """Razón con su fórmula a la vista, no una calificación (RNF5). Sin
    negocios o sin población, `null`: no se inventa."""
    for f in filas:
        f["habitantes_por_negocio"] = (
            round(f["poblacion"] / f["negocios"]) if f["negocios"] and f["poblacion"] is not None else None
        )
        if f["poblacion"] is None:
            avisos.append(f"{f['nombre']} no tiene población del censo cargada.")
    poblaciones = [f["poblacion"] for f in filas]
    cifras["total_poblacion"] = None if None in poblaciones else sum(poblaciones)
    cifras["habitantes_por_negocio"] = (
        round(cifras["total_poblacion"] / cifras["total_negocios"])
        if cifras["total_negocios"] and cifras["total_poblacion"] is not None
        else None
    )


async def _voronoi(pool, cve_ent: str, cve_muns: list[str], puntos, avisos: list[str]) -> dict | None:
    """Uno solo para todos los municipios, recortado a su unión: la
    competencia no se detiene en la frontera municipal (una florería de
    Zapopan le quita clientes a la de Guadalajara de enfrente)."""
    if aviso := consultas.aviso_voronoi(len(puntos)):
        avisos.append(aviso)
        return None
    limite = await consultas.limite_municipios(pool, cve_ent, cve_muns)
    try:
        resultado = await asyncio.to_thread(calcular_voronoi, puntos, limite=limite)
    except ValueError as exc:
        avisos.append(str(exc))
        return None
    return {"celdas": resultado.celdas, "metodo": resultado.metodo}


async def _cuantos_cerca(pool, osrm, p: Plantilla, clases: list[str], avisos: list[str]) -> dict:
    isocrona = await calcular_isocrona(osrm, p.lat, p.lon, p.minutos)
    if isocrona.metodo != "osrm_real":
        avisos.append("OSRM no respondió: el área es un círculo aproximado, no el alcance real por carretera.")
    dentro = await consultas.negocios_en_poligono(pool, isocrona.poligono, clases) if clases else []
    avisos.append("Solo se cuenta lo que trae ubicación en DENUE.")

    capas: dict = {"isocrona": {"poligono": isocrona.poligono, "metodo": isocrona.metodo}}
    if len(dentro) > MAX_PUNTOS:
        avisos.append(f"Son {len(dentro)} {_unidad(p)[0]}: demasiados para dibujar uno por uno.")
    else:
        capas["puntos"] = _puntos(dentro)

    return {
        "intencion": p.intencion,
        "capas": capas,
        "cifras": {
            "que": _que(p),
            "unidad": _unidad(p)[0],
            "total_negocios": len(dentro),
            "minutos": p.minutos,
            "metodo": isocrona.metodo,
        },
        "avisos": avisos,
    }


async def _donde_contratar(pool, cve_ent: str, p: Plantilla) -> dict:
    censo = await consultas.censo_municipios(pool, cve_ent, p.municipios, p.edad)
    if len(censo) != len(set(p.municipios)):
        raise PlantillaInvalida("Algún municipio no está en la base.")
    filas = [
        {"cve_mun": cve, "nombre": censo.get(cve, (cve, None))[0], "poblacion": censo.get(cve, (cve, None))[1]}
        for cve in p.municipios
    ]
    avisos = [f"{f['nombre']} no tiene ese dato del censo cargado." for f in filas if f["poblacion"] is None]
    laboral = await consultas.laboral_de(pool, cve_ent)
    if laboral is None:
        avisos.append("No hay ningún trimestre de la ENOE cargado para el estado.")
    else:
        avisos.append("La desocupación es de todo el estado: la ENOE no es representativa por municipio.")

    return {
        "intencion": p.intencion,
        "capas": {
            "coropleta": {
                "geojson": {
                    "type": "FeatureCollection",
                    "features": await consultas.coropleta(pool, p.edad, cve_ent, p.municipios),
                },
                "indicador": p.edad,
                "etiqueta": f"Población de {NOMBRES_EDAD[p.edad]}",
            }
        },
        "cifras": {"que": f"Población de {NOMBRES_EDAD[p.edad]}", "municipios": filas, "laboral": laboral},
        "avisos": avisos,
    }
