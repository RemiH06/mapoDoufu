"""Conexion a la Postgres/PostGIS compartida con mapo (Elixir/Ecto).

mapo_core es dueno de sus propias tablas en esa misma base (nombres
que no chocan con las de Ecto: users, teams, team_memberships,
sesiones, anotaciones, invitaciones), sin pasar por Ecto para nada:
cada quien administra su parte con su propia herramienta. Sin ORM a
proposito, igual que el resto de mapo_core (vrp.py/isocronas.py/
voronoi.py son funciones + dataclasses directas, no un framework
pesado): SQL directo, funciones nativas de PostGIS.

Los poligonos viven directo en una columna `geometry`, no como ruta a
un archivo en disco (a diferencia del `geom_path` que usa Gaiarda):
un solo dato, fuente de verdad, sin necesitar un volumen aparte para
mapo_core (que hoy no tiene ninguno). La simplificacion para que
Leaflet no se ponga lento con demasiados vertices se aplica al leer
(`ST_Simplify` en la consulta), no al guardar.
"""

from __future__ import annotations

import os

from psycopg_pool import AsyncConnectionPool

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS entidades (
    cve_ent      TEXT PRIMARY KEY,
    nombre       TEXT NOT NULL,
    geom         geometry(MultiPolygon, 4326),
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_entidades_geom ON entidades USING GIST (geom);

CREATE TABLE IF NOT EXISTS municipios (
    cvegeo       TEXT PRIMARY KEY,
    cve_ent      TEXT NOT NULL,
    cve_mun      TEXT NOT NULL,
    nombre       TEXT NOT NULL,
    pob_total    INTEGER,
    geom         geometry(MultiPolygon, 4326),
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cve_ent, cve_mun)
);
CREATE INDEX IF NOT EXISTS idx_municipios_ent  ON municipios (cve_ent);
CREATE INDEX IF NOT EXISTS idx_municipios_geom ON municipios USING GIST (geom);

CREATE TABLE IF NOT EXISTS agebs (
    cvegeo       TEXT PRIMARY KEY,
    cve_ent      TEXT NOT NULL,
    cve_mun      TEXT NOT NULL,
    cve_loc      TEXT,
    cve_ageb     TEXT NOT NULL,
    ambito       TEXT,
    geom         geometry(MultiPolygon, 4326),
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agebs_mun  ON agebs (cve_ent, cve_mun);
CREATE INDEX IF NOT EXISTS idx_agebs_geom ON agebs USING GIST (geom);

-- Localidades del ITER 2020, urbanas y rurales, con su punto (iter_downloader.py).
CREATE TABLE IF NOT EXISTS localidades (
    id           BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    cvegeo       TEXT PRIMARY KEY,
    cve_ent      TEXT NOT NULL,
    cve_mun      TEXT NOT NULL,
    cve_loc      TEXT NOT NULL,
    nombre       TEXT NOT NULL,
    nom_mun      TEXT,
    tamloc       SMALLINT,
    ambito       TEXT,
    altitud      INTEGER,
    pobtot       INTEGER,
    datos        JSONB NOT NULL,
    geom         geometry(Point, 4326) NOT NULL,
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_localidades_geom ON localidades USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_localidades_mun  ON localidades (cve_ent, cve_mun);

CREATE TABLE IF NOT EXISTS fuente_censo_poblacion (
    cvegeo       TEXT PRIMARY KEY,
    nivel        TEXT NOT NULL,
    cve_ent      TEXT NOT NULL,
    cve_mun      TEXT,
    cve_loc      TEXT,
    cve_ageb     TEXT,
    nombre       TEXT,
    pobtot INTEGER, pobfem INTEGER, pobmas INTEGER,
    p_0a2 INTEGER, p_3a5 INTEGER, p_6a11 INTEGER, p_12a14 INTEGER,
    p_15a17 INTEGER, p_18a24 INTEGER, p_60ymas INTEGER,
    graproes REAL,
    pea INTEGER, pea_f INTEGER, pea_m INTEGER, pe_inac INTEGER,
    pocupada INTEGER, pdesocup INTEGER,
    pder_ss INTEGER,
    tothog INTEGER, vivtot INTEGER, tvivhab INTEGER, prom_ocup REAL,
    vph_inter INTEGER, vph_pc INTEGER, vph_autom INTEGER, vph_cel INTEGER, vph_snbien INTEGER,
    datos_json   JSONB NOT NULL,
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_censo_nivel   ON fuente_censo_poblacion (nivel);
CREATE INDEX IF NOT EXISTS idx_censo_cve_ent ON fuente_censo_poblacion (cve_ent);
CREATE INDEX IF NOT EXISTS idx_censo_cve_mun ON fuente_censo_poblacion (cve_ent, cve_mun);

CREATE TABLE IF NOT EXISTS fuente_denue_negocios (
    id              TEXT PRIMARY KEY,
    nombre          TEXT,
    razon_social    TEXT,
    clase_actividad TEXT,
    estrato         TEXT,
    calle           TEXT,
    colonia         TEXT,
    codigo_postal   TEXT,
    ubicacion       TEXT,
    telefono        TEXT,
    correo          TEXT,
    sitio_web       TEXT,
    tipo            TEXT,
    lat             REAL,
    lon             REAL,
    cve_ent         TEXT,
    cve_mun         TEXT,
    cve_ageb        TEXT,
    actualizado     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_denue_cve_ent ON fuente_denue_negocios (cve_ent);
CREATE INDEX IF NOT EXISTS idx_denue_cve_mun ON fuente_denue_negocios (cve_ent, cve_mun);
CREATE INDEX IF NOT EXISTS idx_denue_clase   ON fuente_denue_negocios (clase_actividad);
-- Sesión 18: CLEE y la plaza o mercado donde está el local (la API los llama
-- tipo_corredor_industrial, nom_corredor_industrial y numero_local).
ALTER TABLE fuente_denue_negocios ADD COLUMN IF NOT EXISTS clee         TEXT;
ALTER TABLE fuente_denue_negocios ADD COLUMN IF NOT EXISTS tipo_plaza   TEXT;
ALTER TABLE fuente_denue_negocios ADD COLUMN IF NOT EXISTS plaza        TEXT;
ALTER TABLE fuente_denue_negocios ADD COLUMN IF NOT EXISTS numero_local TEXT;

CREATE TABLE IF NOT EXISTS fuente_enigh_concentradohogar (
    folioviv     TEXT NOT NULL,
    foliohog     TEXT NOT NULL,
    ubica_geo    TEXT,
    cve_ent      TEXT,
    cve_mun      TEXT,
    factor       REAL,
    ing_cor      REAL,
    ingtrab      REAL,
    gasto_mon    REAL,
    alimentos    REAL,
    vivienda     REAL,
    transporte   REAL,
    educa_espa   REAL,
    salud        REAL,
    vesti_calz   REAL,
    transf_gas   REAL,
    percep_tot   REAL,
    erogac_tot   REAL,
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (folioviv, foliohog)
);
CREATE INDEX IF NOT EXISTS idx_enigh_cve_mun ON fuente_enigh_concentradohogar (cve_ent, cve_mun);

CREATE TABLE IF NOT EXISTS fuente_sesnsp_delitos_municipal (
    id             BIGSERIAL PRIMARY KEY,
    anio           INTEGER NOT NULL,
    mes            INTEGER NOT NULL,
    cve_ent        TEXT NOT NULL,
    entidad        TEXT,
    cve_mun        TEXT NOT NULL,
    municipio      TEXT,
    bien_juridico  TEXT,
    tipo_delito    TEXT,
    subtipo_delito TEXT,
    modalidad      TEXT,
    cantidad       INTEGER NOT NULL,
    actualizado    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (anio, mes, cve_ent, cve_mun, bien_juridico, tipo_delito, subtipo_delito, modalidad)
);
CREATE INDEX IF NOT EXISTS idx_sesnsp_mun_anio ON fuente_sesnsp_delitos_municipal (cve_ent, cve_mun, anio);
CREATE INDEX IF NOT EXISTS idx_sesnsp_tipo     ON fuente_sesnsp_delitos_municipal (tipo_delito);

CREATE TABLE IF NOT EXISTS fuente_enoe_tasa_desocupacion (
    cve_ent              TEXT NOT NULL,
    anio                 INTEGER NOT NULL,
    trimestre            TEXT NOT NULL,
    pea_ponderada        REAL NOT NULL,
    ocupada_ponderada    REAL NOT NULL,
    desocupada_ponderada REAL NOT NULL,
    tasa_desocupacion    REAL NOT NULL,
    actualizado          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cve_ent, anio, trimestre)
);

-- Vivienda (sesión 20). Ver docs/fuentes/{shf,sniiv,eic2025,envi}.md.
CREATE TABLE IF NOT EXISTS fuente_shf_ipv (
    nivel       TEXT NOT NULL,          -- nacional, estado, zm, municipio
    clave       TEXT NOT NULL,          -- '00', cve_ent, nombre de la ZM o cve_ent||cve_mun
    nombre      TEXT NOT NULL,
    categoria   TEXT NOT NULL,          -- 'General' en lo territorial; Nueva, Usada... en lo nacional
    anio        INTEGER NOT NULL,
    trimestre   INTEGER NOT NULL,
    indice      REAL NOT NULL,          -- 2018 = 100
    actualizado TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (nivel, clave, categoria, anio, trimestre)
);

CREATE TABLE IF NOT EXISTS fuente_sniiv_financiamiento (
    anio            INTEGER NOT NULL,
    meses           INTEGER NOT NULL,   -- meses publicados de ese año (12 salvo el último)
    cve_ent         TEXT NOT NULL,
    cve_mun         TEXT NOT NULL,      -- '000': no distribuido por municipio
    organismo       TEXT NOT NULL,
    destino_credito TEXT NOT NULL,
    valor_vivienda  TEXT NOT NULL,
    acciones        INTEGER NOT NULL,
    monto           DOUBLE PRECISION NOT NULL,
    actualizado     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio, cve_ent, cve_mun, organismo, destino_credito, valor_vivienda)
);

CREATE TABLE IF NOT EXISTS fuente_eic2025_vivienda (
    cvegeo         TEXT NOT NULL,
    nivel          TEXT NOT NULL,       -- nacional, estado, municipio, localidad
    cve_ent        TEXT NOT NULL,
    cve_mun        TEXT NOT NULL,
    cve_loc        TEXT NOT NULL,
    nombre         TEXT NOT NULL,
    indicador      TEXT NOT NULL,
    valor          DOUBLE PRECISION,    -- NULL con `nota` cuando INEGI no lo da
    error_estandar DOUBLE PRECISION,
    lim_inf        DOUBLE PRECISION,
    lim_sup        DOUBLE PRECISION,
    cv             DOUBLE PRECISION,
    nota           TEXT,                -- MI: muestra insuficiente; NA: no aplica
    actualizado    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cvegeo, indicador)
);
CREATE INDEX IF NOT EXISTS idx_eic2025_mun ON fuente_eic2025_vivienda (cve_ent, cve_mun);

CREATE TABLE IF NOT EXISTS fuente_envi2020_entidad (
    cve_ent        TEXT NOT NULL,       -- '00': nacional
    indicador      TEXT NOT NULL,
    valor          DOUBLE PRECISION,
    error_estandar DOUBLE PRECISION,    -- NULL en medianas: no se estima
    n_muestra      INTEGER NOT NULL,
    actualizado    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cve_ent, indicador)
);

-- Valor de suelo por AGEB (sesión 23c): resultado del estudio
-- estudios/precio_estimado/, cargado con `cli precio_estimado`. Ver
-- docs/producto/precio-estimado.md.
CREATE TABLE IF NOT EXISTS fuente_precio_estimado (
    cvegeo      TEXT PRIMARY KEY,
    cve_ent     TEXT NOT NULL,
    cve_mun     TEXT NOT NULL,
    fuente      TEXT NOT NULL,          -- catastro, modelo o sin_base
    valor       DOUBLE PRECISION,       -- catastro: $/m² del año de la tabla
    rango_bajo  DOUBLE PRECISION,       -- modelo: rango en $/m²
    rango_alto  DOUBLE PRECISION,
    anio_tabla  INTEGER,                -- año de la tabla de valores del municipio
    cobertura   DOUBLE PRECISION,       -- modelo: medida en AGEB no vistas del municipio
    n_base      INTEGER,                -- catastro: etiquetas; modelo: AGEB de ajuste
    metodo      TEXT NOT NULL,
    version     TEXT NOT NULL,
    actualizado TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_precio_estimado_mun ON fuente_precio_estimado (cve_ent, cve_mun);

-- Ambientales (sesión 22). Cargadas de los crudos (`cli ambiental`). Ver
-- docs/fuentes/ambientales.md y la ficha de cada fuente.
CREATE TABLE IF NOT EXISTS fuente_acuiferos (
    clave            TEXT PRIMARY KEY,   -- CLV_ACUI de Conagua (4 dígitos)
    nombre           TEXT NOT NULL,
    cve_ent          TEXT NOT NULL,      -- estado al que Conagua asigna el acuífero
    region           TEXT,               -- región hidrológico-administrativa
    area_km2         DOUBLE PRECISION,
    recarga          DOUBLE PRECISION,   -- hm³/año, todas las columnas de volumen
    descarga_natural DOUBLE PRECISION,   -- descarga natural comprometida (DNC)
    vcas             DOUBLE PRECISION,   -- concesionado o asignado en el REPDA
    veala            DOUBLE PRECISION,   -- en libre alumbramiento
    vaptyr           DOUBLE PRECISION,   -- pendiente de título y registro
    vaprh            DOUBLE PRECISION,   -- por reservas e instrumentos
    veas             DOUBLE PRECISION,   -- extracción total (suma de los cuatro)
    disponibilidad   DOUBLE PRECISION NOT NULL,  -- DMA: R - DNC - VEAS, negativa es déficit
    fecha_dof        DATE NOT NULL,
    geom             geometry(MultiPolygon, 4326),
    actualizado      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_acuiferos_geom ON fuente_acuiferos USING GIST (geom);

CREATE TABLE IF NOT EXISTS fuente_acuiferos_ordenamientos (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo         TEXT NOT NULL,          -- veda, suspension, reglamento
    nombre       TEXT NOT NULL,
    nombre_dof   TEXT,
    fecha_dof    DATE,
    clave_acuifero TEXT,
    clasificacion TEXT,
    url_dof      TEXT,
    geom         geometry(MultiPolygon, 4326),
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_acu_ord_geom ON fuente_acuiferos_ordenamientos USING GIST (geom);

CREATE TABLE IF NOT EXISTS fuente_piezometria (
    pozo          TEXT PRIMARY KEY,
    nombre        TEXT,
    clave_acuifero TEXT,
    elev_brocal   DOUBLE PRECISION,      -- m sobre el nivel del mar
    pne           JSONB NOT NULL,        -- {"1996": m, ...} profundidad al nivel estático
    geom          geometry(Point, 4326) NOT NULL,
    actualizado   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_piezometria_geom ON fuente_piezometria USING GIST (geom);

CREATE TABLE IF NOT EXISTS fuente_renameca_sitios (
    clave        TEXT NOT NULL,
    tipo         TEXT NOT NULL,          -- superficial, subterranea
    nombre       TEXT,
    organismo    TEXT,
    estado       TEXT,
    municipio    TEXT,
    cuenca       TEXT,                   -- superficial: cuenca; subterránea: acuífero
    cuerpo       TEXT,
    subtipo      TEXT,
    periodo      TEXT NOT NULL,          -- '2012-2025': cada fila resume el periodo
    semaforo     TEXT,                   -- el de Conagua, tal cual
    parametros   JSONB NOT NULL,         -- {"DBO_mg/L": {"valor": "<2", "calidad": "Excelente"}}
    geom         geometry(Point, 4326),
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tipo, clave)
);
CREATE INDEX IF NOT EXISTS idx_renameca_geom ON fuente_renameca_sitios USING GIST (geom);

CREATE TABLE IF NOT EXISTS fuente_repda_descargas (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titulo        TEXT NOT NULL,
    anexo         TEXT,
    uso           TEXT,                  -- uso que ampara el título
    cve_ent       TEXT,
    cve_mun       TEXT,
    municipio     TEXT,
    cuenca        TEXT,
    volumen_anual DOUBLE PRECISION,      -- m³
    procedencia   TEXT,
    cuerpo_receptor TEXT,
    tipo_descarga TEXT,
    afluente      TEXT,
    forma         TEXT,
    fecha_registro DATE,
    geom          geometry(Point, 4326),
    actualizado   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_repda_desc_geom ON fuente_repda_descargas USING GIST (geom);

CREATE TABLE IF NOT EXISTS fuente_retc_establecimientos (
    anio         INTEGER NOT NULL,
    nra          TEXT NOT NULL,          -- número de registro ambiental
    scian        TEXT,
    actividad    TEXT,
    sector       TEXT,
    estado       TEXT,
    municipio    TEXT,
    geom         geometry(Point, 4326),
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio, nra)
);
CREATE INDEX IF NOT EXISTS idx_retc_est_geom ON fuente_retc_establecimientos USING GIST (geom);

CREATE TABLE IF NOT EXISTS fuente_retc_emisiones (
    anio           INTEGER NOT NULL,
    nra            TEXT NOT NULL,
    sustancia      TEXT NOT NULL,
    cas            TEXT,
    aire_kg        DOUBLE PRECISION,
    agua_kg        DOUBLE PRECISION,
    suelo_kg       DOUBLE PRECISION,
    transferencias JSONB NOT NULL,       -- {"reciclado": kg, ...}
    actualizado    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_retc_emi ON fuente_retc_emisiones (anio, nra);

CREATE TABLE IF NOT EXISTS fuente_siap_agricola (
    anio         INTEGER NOT NULL,
    cve_ent      TEXT NOT NULL,
    cve_mun      TEXT NOT NULL,
    ciclo        TEXT NOT NULL,
    modalidad    TEXT NOT NULL,          -- Riego o Temporal
    cultivo      TEXT NOT NULL,
    unidad       TEXT NOT NULL,          -- del volumen de producción
    sembrada     DOUBLE PRECISION,       -- ha
    cosechada    DOUBLE PRECISION,
    siniestrada  DOUBLE PRECISION,
    volumen      DOUBLE PRECISION,
    valor        DOUBLE PRECISION,       -- pesos de cada año, sin deflactar
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio, cve_ent, cve_mun, ciclo, modalidad, cultivo, unidad)
);
CREATE INDEX IF NOT EXISTS idx_siap_mun ON fuente_siap_agricola (cve_ent, cve_mun);

CREATE TABLE IF NOT EXISTS fuente_firms_focos (
    sensor       TEXT NOT NULL,          -- VIIRS_SNPP o MODIS
    fecha        DATE NOT NULL,
    hora         TEXT NOT NULL,          -- HHMM en UTC, como la publica FIRMS
    confianza    TEXT,                   -- VIIRS: l, n, h; MODIS: 0 a 100
    frp          DOUBLE PRECISION,       -- potencia radiativa, MW
    dia_noche    TEXT,
    tipo         SMALLINT,               -- 0 vegetación, 1 volcán, 2 fuente fija, 3 costa
    geom         geometry(Point, 4326) NOT NULL,
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_firms_geom  ON fuente_firms_focos USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_firms_fecha ON fuente_firms_focos (sensor, fecha);

CREATE TABLE IF NOT EXISTS fuente_uso_suelo (
    serie        SMALLINT NOT NULL,      -- 6 (2014) o 7 (2018)
    descripcion  TEXT NOT NULL,
    codigo       TEXT,
    geom         geometry(MultiPolygon, 4326) NOT NULL,
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_uso_suelo_geom ON fuente_uso_suelo USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_uso_suelo_serie ON fuente_uso_suelo (serie);

CREATE TABLE IF NOT EXISTS fuente_anp (
    id           TEXT PRIMARY KEY,
    nombre       TEXT NOT NULL,
    categoria    TEXT,
    estados      TEXT,
    superficie_ha DOUBLE PRECISION,      -- la del decreto, terrestre más marina
    terrestre_ha DOUBLE PRECISION,
    marina_ha    DOUBLE PRECISION,
    primer_decreto DATE,
    ultimo_dof   DATE,
    geom         geometry(MultiPolygon, 4326),
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_anp_geom ON fuente_anp USING GIST (geom);

CREATE TABLE IF NOT EXISTS fuente_sequia_municipal (
    cve_ent      TEXT NOT NULL,
    cve_mun      TEXT NOT NULL,
    fecha        DATE NOT NULL,          -- fecha de corte del Monitor
    categoria    TEXT NOT NULL,          -- D0 a D4, o 'sin' (sin anomalía)
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cve_ent, cve_mun, fecha)
);
CREATE INDEX IF NOT EXISTS idx_sequia_fecha ON fuente_sequia_municipal (fecha);

CREATE TABLE IF NOT EXISTS fuente_defunciones_municipal (
    anio_registro INTEGER NOT NULL,
    cve_ent      TEXT NOT NULL,          -- de residencia habitual; '99' no especificado
    cve_mun      TEXT NOT NULL,
    causa        TEXT NOT NULL,          -- CIE-10 a tres caracteres (C34, N18...)
    sexo         SMALLINT NOT NULL,      -- 1 hombre, 2 mujer, 9 no especificado
    edad_grupo   SMALLINT NOT NULL,      -- edad_agru de INEGI (1 menores de un año ... 30 no especificada)
    defunciones  INTEGER NOT NULL,
    actualizado  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio_registro, cve_ent, cve_mun, causa, sexo, edad_grupo)
);
CREATE INDEX IF NOT EXISTS idx_defun_mun ON fuente_defunciones_municipal (cve_ent, cve_mun);

-- Empleo formal del IMSS (sesión 25). Ver docs/fuentes/imss.md. Un renglón por
-- mes, clave de municipio del IMSS y grupo de actividad.
CREATE TABLE IF NOT EXISTS fuente_imss_asegurados (
    periodo             DATE NOT NULL,      -- último día del mes
    cve_ent             TEXT NOT NULL,
    cve_mun             TEXT NOT NULL,      -- '000': sin municipio (CDMX entera, claves sin equivalencia)
    clave_imss          TEXT NOT NULL,      -- cve_municipio del IMSS ('NA' en la CDMX)
    division            TEXT NOT NULL,      -- sector_economico_1; '' asegurados sin empleo
    grupo               TEXT NOT NULL,      -- sector_economico_2
    asegurados          INTEGER NOT NULL,
    sin_empleo          INTEGER NOT NULL,   -- no_trabajadores
    puestos             INTEGER NOT NULL,   -- ta
    permanentes         INTEGER NOT NULL,   -- tpu + tpc
    eventuales          INTEGER NOT NULL,   -- teu + tec
    puestos_con_salario INTEGER NOT NULL,   -- ta_sal
    masa_salarial       DOUBLE PRECISION NOT NULL,  -- masa_sal_ta, pesos diarios
    puestos_rango_tope  INTEGER NOT NULL,   -- ta en rango_uma W25 (más de 24 y hasta 25 UMA)
    actualizado         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (periodo, cve_ent, clave_imss, division, grupo)
);
CREATE INDEX IF NOT EXISTS idx_imss_mun ON fuente_imss_asegurados (cve_ent, cve_mun, periodo);

-- Establecimientos de salud (CLUES de la DGIS, sesión 26). Ver docs/fuentes/clues.md.
CREATE TABLE IF NOT EXISTS fuente_clues (
    clues           TEXT PRIMARY KEY,
    cve_institucion TEXT NOT NULL,
    institucion     TEXT NOT NULL,
    cve_ent         TEXT NOT NULL,
    cve_mun         TEXT NOT NULL,
    cve_loc         TEXT NOT NULL,
    tipo            TEXT NOT NULL,      -- DE CONSULTA EXTERNA, DE HOSPITALIZACIÓN, DE APOYO, DE ASISTENCIA SOCIAL
    tipologia       TEXT NOT NULL,
    subtipologia    TEXT NOT NULL,
    nombre          TEXT NOT NULL,
    estatus         TEXT NOT NULL,      -- EN OPERACION, FUERA DE OPERACION...
    nivel           TEXT NOT NULL,
    estrato         TEXT NOT NULL,
    unidad_movil    TEXT NOT NULL,      -- '' si es fija
    publica         BOOLEAN NOT NULL,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    geom            geometry(Point, 4326),
    corte           TEXT NOT NULL,      -- mes del catálogo, AAAA-MM
    actualizado     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_clues_ent ON fuente_clues (cve_ent, tipo);

-- Accesibilidad a servicios (sesión 26). Ver docs/producto/accesibilidad.md. Minutos
-- de cada AGEB urbano o localidad sin AGEB a su servicio más cercano por calle.
CREATE TABLE IF NOT EXISTS accesibilidad_destinos (
    cve_ent   TEXT NOT NULL,
    servicio  TEXT NOT NULL,
    id        TEXT NOT NULL,      -- id de DENUE, CLUES o 'red|estación'
    nombre    TEXT NOT NULL,
    lat       DOUBLE PRECISION NOT NULL,
    lon       DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (cve_ent, servicio, id)
);
CREATE TABLE IF NOT EXISTS accesibilidad_minutos (
    cve_ent   TEXT NOT NULL,
    servicio  TEXT NOT NULL,
    modo      TEXT NOT NULL,      -- pie | auto
    clave     TEXT NOT NULL,      -- cvegeo del AGEB (13) o de la localidad (9)
    cve_mun   TEXT NOT NULL,
    minutos   REAL,               -- null: ninguno de los vecinos tiene ruta
    destino   TEXT,               -- id del más cercano por calle
    linea_m   REAL NOT NULL,      -- metros en línea recta al más cercano en línea recta
    PRIMARY KEY (cve_ent, servicio, modo, clave)
);
CREATE INDEX IF NOT EXISTS idx_acc_minutos_mun ON accesibilidad_minutos (cve_ent, cve_mun, modo);
CREATE TABLE IF NOT EXISTS accesibilidad_cargas (
    cve_ent     TEXT NOT NULL,
    servicio    TEXT NOT NULL,
    modo        TEXT NOT NULL,
    origenes    INTEGER NOT NULL,
    destinos    INTEGER NOT NULL,
    sin_ruta    INTEGER NOT NULL,
    fuente      TEXT NOT NULL,      -- de dónde salieron los destinos, con su fecha
    red         TEXT NOT NULL,      -- datos de OSM y perfil de OSRM
    segundos    REAL NOT NULL,
    actualizado TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cve_ent, servicio, modo)
);

CREATE TABLE IF NOT EXISTS descargas_checkpoint (
    clave         TEXT PRIMARY KEY,
    completado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _conninfo() -> str:
    host = os.environ.get("DATABASE_HOST", "localhost")
    dbname = os.environ.get("DATABASE_NAME", "mapo_dev")
    user = os.environ.get("DATABASE_USER", "postgres")
    password = os.environ.get("DATABASE_PASSWORD", "postgres")
    return f"host={host} dbname={dbname} user={user} password={password}"


_pool: AsyncConnectionPool | None = None


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(_conninfo(), open=False)
        await _pool.open()
    return _pool


async def cerrar_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def inicializar_esquema(pool: AsyncConnectionPool | None = None) -> None:
    pool = pool or await get_pool()
    async with pool.connection() as conn:
        await conn.execute(SCHEMA)


async def esta_hecho(conn, clave: str) -> bool:
    cursor = await conn.execute(
        "SELECT 1 FROM descargas_checkpoint WHERE clave = %(clave)s", {"clave": clave}
    )
    return await cursor.fetchone() is not None


async def marcar_hecho(conn, clave: str) -> None:
    await conn.execute(
        """INSERT INTO descargas_checkpoint (clave) VALUES (%(clave)s)
           ON CONFLICT (clave) DO UPDATE SET completado_en = now()""",
        {"clave": clave},
    )
