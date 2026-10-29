# Geoestadístico y censo

## Corrección de arquitectura: Gaiarda vendorizado, no vivo (2026-08-24)

**Bug de arquitectura real, no de código**: `mapo_core` se había
construido con `gaiarda_client.py`, un cliente HTTP hacia un Gaiarda
corriendo aparte (`GAIARDA_API_URL`). Esto contradecía lo ya decidido
en `../arquitectura/stack.md` ("reutilizando Gaiarda tal cual... las
fuentes de datos", el mismo patrón que ya se había aplicado bien a
OSRM) y lo que el usuario aclaró explícito: *"todo lo que corre es
mapo, independientemente de gaiarda, lo único que se recicla es su
código."* `Gaiarda-main.zip` está en el repo exactamente para sacar
ese código, no para tener un Gaiarda vivo al lado.

**Corregido, alcance de esta pasada: geoestadístico (estados,
municipios, AGEBs) + censo de población**, vendorizados de verdad:

- `mapo_core` ahora tiene sus propias tablas
  (`entidades`/`municipios`/`agebs`/`fuente_censo_poblacion`/
  `descargas_checkpoint`) en la **misma Postgres/PostGIS que ya usa
  `mapo`** (servicio `db`, base `mapo_dev`/`mapo_test`), con su propio
  cliente (`psycopg` v3, sin ORM, mismo estilo directo que el resto de
  `mapo_core`), sin pasar por Ecto. Los polígonos viven en una columna
  `geometry` real (simplificados al leer con `ST_Simplify`, no al
  guardar), no como ruta a un archivo como hace Gaiarda
- `mapo_core/geo_downloader.py` y `censo_downloader.py`: vendorizados
  de `gaiarda/src/gaiarda/{api,downloader}.py` y
  `fuentes/censo_poblacion/{api,downloader}.py`, preservando los
  gotchas reales ya documentados por Gaiarda (`'-'`/`''` como dato
  faltante, decodificación UTF-8 con fallback a Latin-1, el candado
  contra el bug real de delimitador equivocado en el CSV, checkpoint
  por entidad para poder retomar a medias)
- CLI nuevo (`python -m mapo_core.cli estados|municipios|agebs|censo_poblacion|status`),
  mismo patrón que el CLI de Gaiarda
- Rutas renombradas porque el prefijo `/gaiarda/` ya sería mentiroso:
  `/geo/estados`, `/geo/municipios`, `/geo/agebs` (nueva),
  `/censo/choropleth`. Actualizado el único punto del lado Elixir que
  las conocía (`mapo/lib/mapo/mapo_core.ex`)
- `/geo/estados` y `/geo/municipios` aceptan `geometria=false` para
  traer solo nombres y claves (2.8 KB contra 2.9 MB de los estados con
  polígono); es lo que usan los selects de `/mapa` y `/perfil`. Todas
  las geometrías salen con 5 decimales (1 m), ver
  `docs/historial/2026-10-rendimiento.md`
- `gaiarda_client.py` y `perfil_zona.py` (el viejo, basado en
  `GaiardaClient`) eliminados por completo, junto con sus tests
- **Las 6 fuentes (geoestadístico, censo, DENUE, ENIGH, ENOE, SESNSP)
  ya quedaron vendorizadas y con datos reales cargados**, ver sus
  secciones propias más abajo. `/perfil_zona` ya trae las 5 secciones
  reales (demografía, comercio, consumo, seguridad, laboral). No queda
  ninguna fuente pendiente de vendorizar de las que Gaiarda cubría
- **Probado con datos reales de INEGI, no solo mocks**: se corrió el
  CLI completo contra el estado 14 (Jalisco): 32 estados, 125
  municipios (mismo número que ya se había confirmado antes con
  Gaiarda directo), 4,932 AGEBs, 5,307 filas de censo. Coropletas
  (`valor_choropleth: 1433` real para una AGEB), coloreado
  (`color_indice` real), y perfil de zona (`pobtot: 1385629` para
  Guadalajara, consistente con la cifra oficial conocida) confirmados
  con `curl` directo contra datos reales, no simulados
- 88 tests en `mapo_core` (conexión real a `mapo_test`, no mocks:
  fixture `conn`/`pool_de_una_conexion` en `conftest.py`, cada test en
  su propia transacción revertida al final, mismo espíritu que
  `Ecto.Adapters.SQL.Sandbox`), 229 tests en `mapo` (rutas renombradas,
  plantilla de `/perfil` actualizada al nuevo formato)
- Token de DENUE ya guardado en `mapo_core/.env` (gitignored, no se
  usa todavía) para cuando llegue esa fase
- **Bug real encontrado y corregido en el camino, de los que importan**:
  los tests de `mapo_core` estaban escribiendo en `mapo_dev` (la base
  con los datos reales recién descargados), no en `mapo_test`.
  `conftest.py` hacía `os.environ.setdefault("DATABASE_NAME",
  "mapo_test")`, pero `docker-compose.yml` ya trae `DATABASE_NAME:
  mapo_dev` fijado en el entorno del contenedor (para que el servidor
  de verdad sirva datos reales): `setdefault` nunca se activa si la
  variable ya existe. Se detectó rápido porque un test intentó
  insertar un "Jalisco" de prueba con `cve_ent='14'` y chocó con el
  Jalisco real recién descargado (`UniqueViolation`). Se verificó que
  los datos reales quedaron intactos (32/125/4,932/5,307 filas, sin
  cambios) antes y después del fix. Corregido con un override directo
  (`os.environ["DATABASE_NAME"] = "mapo_test"`, no `setdefault`) en
  `conftest.py`
