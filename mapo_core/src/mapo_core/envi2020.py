"""Encuesta Nacional de Vivienda (ENVI) 2020, INEGI: renta y valor por estado.

Es la única fuente abierta con lo que se paga de renta (pregunta 5.2) y con el
valor en que se vendería la vivienda según quien la habita (5.9). Representativa
por estado, no más abajo. Levantada de octubre a diciembre de 2020. Ver
docs/fuentes/envi.md.

Se calcula por estado y nacional, con el factor de expansión. Medias y
porcentajes llevan error estándar por conglomerado último (estrato `EST_DIS`, UPM
`UPM_DIS`), linealizado como razón. Las medianas no llevan error: no se estima, y
la tabla lo deja nulo en vez de inventarlo.
"""

from __future__ import annotations

import csv
import io
import math
import zipfile
from collections import defaultdict

import httpx

from mapo_core.db import get_pool

URL = "https://www.inegi.org.mx/contenidos/programas/envi/2020/datosabiertos/conjunto_de_datos_envi_2020_csv.zip"
CSV = ("conjunto_de_datos_tvivienda_envi_2020/conjunto_de_datos/"
       "conjunto_de_datos_tvivienda_envi_2020.csv")

RENTADA = "1"
PROPIAS = {"4", "5"}  # propia que se está pagando y propia
# Rangos válidos del diccionario; 999999888 y 999999999 son "no sabe" y "no responde".
RENTA_VALIDA = (100, 50_000)
VALOR_VALIDO = (600, 45_000_000)


class ArchivoInvalido(Exception):
    pass


def _entero(texto: str) -> int | None:
    texto = (texto or "").strip()
    return int(texto) if texto.isdigit() else None


def leer(zip_bytes: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        texto = z.read(CSV).decode("utf-8", errors="replace")
    filas = list(csv.DictReader(io.StringIO(texto)))
    faltan = {"ENT", "EST_DIS", "UPM_DIS", "FACTOR", "P5_1", "P5_2", "P5_4", "P5_9"} - set(filas[0] if filas else [])
    if faltan:
        raise ArchivoInvalido(f"Faltan columnas en la ENVI: {sorted(faltan)}.")
    return [{
        "ent": f["ENT"], "estrato": f["EST_DIS"], "upm": f["UPM_DIS"], "w": float(f["FACTOR"]),
        "tenencia": f["P5_1"].strip(), "pago": _entero(f["P5_2"]), "contrato": f["P5_4"].strip(),
        "valor": _entero(f["P5_9"]),
    } for f in filas]


def razon(filas: list[dict], y, dominio) -> tuple[float | None, float | None, int]:
    """Media de `y` en `dominio`, con error estándar por conglomerado último.
    Regresa (estimación, error estándar, casos en muestra)."""
    num = den = 0.0
    n = 0
    for f in filas:
        if dominio(f):
            num += f["w"] * y(f)
            den += f["w"]
            n += 1
    if den == 0:
        return None, None, 0
    r = num / den
    # z por UPM: contribución linealizada de cada conglomerado, 0 si no tiene casos del dominio.
    z: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for f in filas:
        z[f["estrato"]][f["upm"]] += f["w"] * (y(f) - r) / den if dominio(f) else 0.0
    varianza = 0.0
    for upms in z.values():
        nh = len(upms)
        if nh < 2:
            continue  # un estrato con una sola UPM no aporta varianza estimable
        media = sum(upms.values()) / nh
        varianza += nh / (nh - 1) * sum((v - media) ** 2 for v in upms.values())
    return r, math.sqrt(varianza), n


def mediana(filas: list[dict], y, dominio) -> tuple[float | None, int]:
    casos = sorted((y(f), f["w"]) for f in filas if dominio(f))
    if not casos:
        return None, 0
    mitad = sum(w for _, w in casos) / 2
    acumulado = 0.0
    for valor, w in casos:
        acumulado += w
        if acumulado >= mitad:
            return float(valor), len(casos)
    return float(casos[-1][0]), len(casos)


def _en(rango, v):
    return v is not None and rango[0] <= v <= rango[1]


def indicadores(filas: list[dict]) -> list[dict]:
    """Por estado y nacional ('00'). Las mismas UPM sirven para los dos: el
    estrato de diseño es único en todo el país."""
    rentada = lambda f: f["tenencia"] == RENTADA
    con_renta = lambda f: rentada(f) and _en(RENTA_VALIDA, f["pago"])
    propia_con_valor = lambda f: f["tenencia"] in PROPIAS and _en(VALOR_VALIDO, f["valor"])

    salida = []
    for ent in ["00"] + sorted({f["ent"] for f in filas}):
        sub = filas if ent == "00" else [f for f in filas if f["ent"] == ent]
        def agrega(indicador, valor, ee, n):
            salida.append({"cve_ent": ent, "indicador": indicador, "valor": valor,
                           "error_estandar": ee, "n_muestra": n})

        agrega("viviendas", sum(f["w"] for f in sub), None, len(sub))
        agrega("pct_rentadas", *_pct(razon(sub, lambda f: rentada(f), lambda f: True)))
        agrega("pct_rentadas_con_contrato", *_pct(razon(sub, lambda f: f["contrato"] == "1", rentada)))
        agrega("renta_mensual_media", *razon(sub, lambda f: f["pago"], con_renta))
        m, n = mediana(sub, lambda f: f["pago"], con_renta)
        agrega("renta_mensual_mediana", m, None, n)
        m, n = mediana(sub, lambda f: f["valor"], propia_con_valor)
        agrega("valor_estimado_mediana", m, None, n)
    return salida


def _pct(estimacion):
    r, ee, n = estimacion
    return (None if r is None else 100 * r), (None if ee is None else 100 * ee), n


async def descargar(archivo: bytes | None = None) -> int:
    if archivo is None:
        async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as cliente:
            r = await cliente.get(URL)
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith("application/"):
                raise ArchivoInvalido(f"{URL} no regresó un ZIP (INEGI responde 200 con HTML si no existe).")
            archivo = r.content
    salida = indicadores(leer(archivo))

    columnas = ["cve_ent", "indicador", "valor", "error_estandar", "n_muestra"]
    pool = await get_pool()
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("DELETE FROM fuente_envi2020_entidad")
        async with conn.cursor().copy(f"COPY fuente_envi2020_entidad ({', '.join(columnas)}) FROM STDIN") as copia:
            for f in salida:
                await copia.write_row([f[c] for c in columnas])
    return len(salida)
