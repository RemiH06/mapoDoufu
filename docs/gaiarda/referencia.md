# Gaiarda: referencia

Resumen de Gaiarda 0.3.0 ([RemiH06/Gaiarda](https://github.com/RemiH06/Gaiarda)), el proyecto
del que Mapo copia sus fuentes de datos. Sirve para no releer su repo
cada vez que se vendoriza algo. Cómo calcula rutas: `rutas.md`.

## Qué es

Gaiarda descarga, normaliza y sirve datos abiertos de México (INEGI y
otras fuentes públicas), con un dashboard para explorarlos en mapa.
Contesta "qué hay". Es el preludio de **Mapo** (ver
`../producto/vision.md`), que contestará "qué deberías hacer con eso".

## Estructura del repo (monorepo)

```
Gaiarda/
├── README.md                 llamativo: banner ASCII, badges, resumen del monorepo
├── LICENSE
├── .gitignore
├── docs/                      página de GitHub Pages (index.html + favicon.svg)
├── gaiarda/                    backend, Python
│   ├── pyproject.toml
│   ├── .env                    (token de DENUE, URL de OSRM propio; no se sube a git)
│   ├── .env.example              plantilla versionada de lo anterior
│   ├── docs/                      endpoints.md, osrm_propio.md, casetas.md, gaiarda-logo.png
│   ├── src/gaiarda/
│   │   ├── api.py                  cliente del Marco Geoestadístico
│   │   ├── db.py                    esquema de estados/municipios/localidades/agebs
│   │   ├── downloader.py            orquestador de descarga + checkpoint
│   │   ├── kml.py                    conversor GeoJSON -> KML
│   │   ├── geo_utils.py               índice espacial (shapely STRtree)
│   │   ├── log.py                     historial de descargas (tabla descargas_log)
│   │   ├── status.py                   qué hay descargado AHORA (conteos en vivo)
│   │   ├── comandos.py                  lógica de cada descarga, compartida entre CLI y consola web
│   │   ├── consola.py                    ejecuta comandos en hilo de fondo (para la consola del dashboard)
│   │   ├── rutas.py                       TSP de turismo + rutas guardadas + contexto de seguridad
│   │   ├── ruteo_osrm.py                   cliente del motor de ruteo real por carretera (OSRM)
│   │   ├── casetas_en_ruta.py               qué casetas cruza el trazado real de una ruta
│   │   ├── cli.py                            entrypoint de terminal (usa comandos.py + status.py)
│   │   ├── server.py                         API FastAPI (usa comandos.py + consola.py + rutas.py + ruteo_osrm.py + status.py + casetas_en_ruta.py)
│   │   └── fuentes/                          un subpaquete por fuente de datos (ver abajo)
│   └── tests/                                 214 tests, todos pasando
├── gaiarda-dashboard/                        frontend, React + Vite + TypeScript
│   ├── package.json
│   └── src/
│       ├── App.tsx                            shell, un solo estado de dark mode para toda la app
│       ├── pages/                              Dashboard.tsx (mapa principal), Rutas.tsx (turismo), Log.tsx (historial + status + consola)
│       ├── components/                          layout/, map/, ui/
│       ├── api/client.ts                         todas las llamadas al backend
│       ├── lib/                                   colorScale.ts, markerIcons.ts
│       └── styles/                                 metro.css (tema principal), odysseus.css (tema de Rutas)
└── .github/workflows/tests.yml                CI: pytest (backend) + lint/build (frontend), en cada push/PR
```

**Correrlo:**
```bash
# backend
cd gaiarda && pip install -e ".[dev,api]" && uvicorn gaiarda.server:app --reload --port 8420

# frontend, otra terminal
cd gaiarda-dashboard && npm install && npm run dev
```

## Las 8 fuentes de datos (`gaiarda/src/gaiarda/fuentes/`)

Cada una es un subpaquete independiente con `api.py` (cliente HTTP),
`db.py` (esquema SQLite), `downloader.py` (orquesta), `__init__.py`
(se registra sola en un catálogo central que el dashboard consulta).
**Excepción: casetas** no tiene `api.py`, ver su fila abajo.

| Fuente | Nivel | Notas importantes |
|---|---|---|
| **Geoestadístico** (no es "fuente", es el core) | estado/municipio/localidad/AGEB | Polígonos reales; `.geojson` se guarda **simplificado** (shapely, `preserve_topology=True`), `.kml` con precisión completa. Ojo: la base guarda la ruta del `.kml`, hay que hacer `.with_suffix(".geojson")` para leer el que sirve el dashboard |
| **CRE** | puntual (gasolineras) | Sin token. Actualiza cada 4h en la fuente real |
| **DENUE** | puntual (negocios) | **Requiere token gratis** (`GAIARDA_DENUE_TOKEN` en `.env`). Se enriquece automático con municipio/AGEB vía cruce espacial si ya tienes esos niveles descargados |
| **Censo de Población** | AGEB | 27 de 222 indicadores oficiales tienen columna propia (contados directo del esquema: 11 de población, 6 económicas, 1 de salud, 4 de hogares/vivienda, 5 de conectividad); el resto vive íntegro en un `datos_json` por fila, consultable con `json_extract()` |
| **SESNSP** | municipio | Incidencia delictiva, serie histórica completa, sin token |
| **ENIGH** | variable (17 tablas) | Microdatos de ingreso/gasto. `concentradohogar` + `gaiarda.fuentes.enigh.resumen` para análisis ponderado por municipio (factor de expansión). Su `__init__.py` tenía un bug real (le faltaba un guion bajo, `__init_.py`) que hacía que nunca se autorregistrara en el catálogo; ya corregido. Periodo de las cifras: **trimestral**, confirmado contra ficha oficial de INEGI; `por_dia=True` convierte a diario (÷91.25). **ADVERTENCIA**: ENIGH es representativo a nivel estado y dominio rural/urbano, NO a nivel municipio; `n_hogares_muestra` siempre viene en el resultado por eso, nunca ocultarlo. **Bug real serio, corregido (agosto 2026)**: `api.py` asumía el CSV separado por tabs; el real (nueva serie 2024) es separado por **coma**. Con el delimitador equivocado, `csv.DictReader` no encontraba ningún separador y guardaba el encabezado completo (~150 columnas) pegado como una sola columna gigante, sin tronar; 91,414 filas se guardaron así antes de detectarse contra una descarga real. Los tests tenían el mismo error en sus fixtures, por eso nunca lo atraparon. Fix: delimitador corregido a coma + candado de seguridad (`extraer_csv` truena si el resultado tiene ≤1 columna, en vez de guardar basura en silencio). Si tu base ya tiene la tabla corrupta, hay que `DROP TABLE fuente_enigh_concentradohogar` antes de recargar (`CREATE TABLE IF NOT EXISTS` no repara un esquema viejo) |
| **ENOE** | estado | Empleo trimestral, formato `.dbf` (no `.csv`), usa `dbfread`. Sin representatividad a nivel municipio |
| **Casetas** | puntual (geocodificado vía OSM) | Tarifas CAPUFE. **Sin descarga automática posible**: el portal de datos abiertos (`datos.gob.mx`) bloquea acceso automatizado (`robots.txt`), y la app de CAPUFE es JavaScript puro. Se carga desde un TSV que se extrae a mano (inspeccionando la red del navegador), con `gaiarda casetas --archivo`. La tabla de tarifas NO trae coordenadas: se geocodifica aparte cruzando nombres contra `barrier=toll_booth` de OpenStreetMap vía Overpass (`gaiarda casetas_geocodificar`), con desambiguación honesta (si dos candidatos son casi igual de parecidos, no adivina). Ver `gaiarda/docs/casetas.md` |

**Censos Económicos: pendiente indefinido.** El SAIC de INEGI no tiene
descarga directa confirmada (es un sistema de consulta interactivo, no
un endpoint simple). Se decidió que no vale la pena para Gaiarda de
todas formas, DENUE ya cubre lo que se necesitaba de ahí.

## Comandos del CLI

```
gaiarda estados | municipios | localidades | agebs | todo
gaiarda cre | sesnsp
gaiarda denue --estado 14 [--token TOKEN]
gaiarda censo_poblacion --estado 14
gaiarda enigh --tabla concentradohogar   (o --tabla todas, pide confirmación)
gaiarda enoe --anio 2025 --trimestre trim3
gaiarda casetas --archivo tarifas.tsv     (TSV obtenido a mano, ver docs/casetas.md)
gaiarda casetas_geocodificar              (cruza contra OpenStreetMap vía Overpass)
gaiarda log                               historial de descargas ya hechas
gaiarda status                            qué hay descargado AHORA, sin abrir la base
gaiarda completo                          TODO, 32 entidades, pide confirmación, tolera fallos por estado
```

## Dashboard: qué tiene

**Mapa principal** (`/`, tema Metro): selección de estado → municipios
→ AGEBs con clic directo en el mapa; capas de DENUE/CRE con
clustering; mapa de calor del censo con colores personalizables; todo
con un botón "Run" explícito (nada se busca solo al tocar un control).
Barra lateral redimensionable (arrastre con el mouse, 220-520px,
recordado en `localStorage`), vía el hook
`useAnchoRedimensionable` (reutilizable para otros paneles a futuro,
ej. el de Rutas, si hace falta).

**Rutas** (`/rutas`, tema Odysseus): trazado de viajes de **turismo**
(no logística de carga, eso es de Mapo). TSP heurístico (vecino más
cercano + 2-opt) sobre distancia **real por carretera** (motor OSRM,
vía `.env` configurable con `GAIARDA_OSRM_URL`; usa el demo público de
OSRM por default, con fallback honesto a línea recta/haversine si el
servicio no responde: el resultado siempre indica cuál de los dos se
usó). Soporta:
- Selección interestatal (los municipios se acumulan por estado, no se
  pierden al cambiar de estado en el selector)
- Inicio/fin forzoso por parada (si el mismo municipio es ambos, la
  ruta sale circular)
- Guardar/cargar/borrar rutas (SQLite, tabla `rutas_guardadas`)
- Contexto de seguridad por parada (conteos crudos de SESNSP, sin
  inventar un "puntaje" único a propósito)
- Presupuesto de gasolina estimado (precio promedio de CRE × distancia
  ÷ rendimiento ajustable)
- Presupuesto de casetas: qué casetas cruza el trazado real
  (`gaiarda.casetas_en_ruta`, cruce geométrico contra las casetas ya
  geocodificadas, tolerancia ~300m), sumado al presupuesto total.
  Marcadores dorados (`#C89030`) en el mapa, distintos del morado de
  la ruta. Solo aplica con `metodo: "carretera_real"` (sin trazado
  real no hay línea que cruzar contra nada)
- Gasto diario estimado en alimentos por parada (ENIGH, columna
  `alimentos`, convertida a diario). **Es por hogar, no por persona**:
  no hay ajuste per cápita en el cálculo (dividir entre integrantes
  del hogar), así que el número es "cuánto gasta el hogar completo al
  día", no "cuánto gasta cada quien". Siempre muestra
  `n_hogares_muestra` junto al número, por la advertencia de
  representatividad de ENIGH (ver tabla de fuentes arriba)
- Trazado real sobre las calles en el mapa (no solo líneas rectas
  entre paradas), en morado (`--wonder`, `#603890`) para no confundirse
  visualmente con el rojo de la selección de municipios

**Log** (`/log`): arriba, un panel de **status** en vivo (qué hay
descargado ahora mismo, por tema: geoestadístico, cada fuente, DENUE
por entidad, tablas de ENIGH/ENOE, rutas guardadas). Abajo, la consola
para lanzar descargas desde el navegador (corren en hilo de fondo, un
candado evita que se disparen dos a la vez) y el historial de
descargas. No incluye `completo` a propósito (se queda de terminal).

## Decisiones de arquitectura que vale la pena recordar

- **`comandos.py` es la única fuente de verdad** de qué hace cada
  descarga. CLI y consola web llaman a las mismas funciones.
- **Checkpoint** (`data/checkpoint.json`) en casi todo, para poder
  interrumpir y retomar sin repetir descargas ya hechas. **Bug real
  encontrado y corregido**: el checkpoint solo recuerda "esta clave
  ya se descargó", nunca verifica que los datos sigan en `geo.db`. Si
  la base se borra/recrea pero `checkpoint.json` sobrevive aparte
  (pasó de verdad: `enigh --tabla concentradohogar` regresaba "0
  filas guardadas" al instante, sin ningún error, porque el
  checkpoint ya lo marcaba como hecho de una corrida anterior). Fix:
  flag `--forzar` en `enigh`/`enoe` (CLI y consola web), que ignora
  el checkpoint para esa corrida. Los downloaders de estados/
  municipios/localidades/agebs NO tienen este flag todavía (mismo
  riesgo en teoría, pero no se ha reportado en la práctica; pendiente
  si algún día pasa ahí también).
- **Nunca se asume que un dato existe.** Todo lo que depende de otra
  fuente (AGEB para DENUE, municipios para el enriquecimiento
  espacial, motor de ruteo real para las distancias) se salta con
  aviso o cae a un fallback honesto si no está, no truena.
- El backend **cachea lecturas de `.geojson`** en memoria
  (`functools.lru_cache`) para no releer archivos en cada petición.
- `server.py` **sí carga `.env`** (bug real que se corrigió: antes
  solo `cli.py` lo hacía, así que correr el servidor directo con
  `uvicorn` nunca leía el token de DENUE ni la URL de OSRM propio).
- **Lección real del bug del delimitador de ENIGH**: un test que
  mockea/fabrica sus propios datos de prueba puede quedar pasando en
  verde para siempre validando una suposición incorrecta, si el
  fixture del test comparte el mismo error que el código que prueba
  (aquí, ambos asumían tabs). 220 tests en verde no detectaron el bug;
  lo detectó correr contra una descarga real. Cuando algo parsea datos
  de una fuente externa (formato de archivo, delimitador, nombres de
  columna), vale la pena, en algún momento, confirmarlo contra un dato
  real de verdad descargado, no solo contra un fixture que uno mismo
  construyó a partir de la misma suposición que se está probando.

## Pendientes de Gaiarda (0.3.0)

1. **Censos Económicos**: indefinido, ver nota arriba. Único pendiente
   de datos.
2. **OSRM propio**: ~~pendiente~~ **confirmado funcionando** (agosto
   2026, corrida real sobre México completo). Requirió subir la
   memoria de Docker/WSL2 a 16 GB (`osrm-extract` pica ~14.8 GB de
   pico; sin eso, moría en silencio a medio preprocesar por falta de
   memoria, tres intentos fallidos antes de dar con la cifra
   correcta). Guía completa con las cifras reales y el troubleshooting
   en `gaiarda/docs/osrm_propio.md`.
3. **Hospedaje: decidido que NO se estima.** Se evaluó usar la
   columna `vivienda` de ENIGH como proxy, y se descartó a propósito:
   es gasto de renta de residentes, no tarifa de hotel para alguien de
   fuera, categorías de gasto que no se corresponden. Gaiarda no tiene
   ninguna fuente de precios de hospedaje real (necesitaría un API de
   hoteles/Airbnb, fuera del alcance de datos abiertos gubernamentales
   usado hasta ahora). Si Mapo lo necesita, es una fuente de datos
   nueva por completo, no algo que se pueda derivar de lo que ya hay.

Todo lo demás de la lista larga que se fue armando en el camino
(clustering, selección de AGEB, guardar rutas, seguridad, consola de
descargas, log en el dashboard, rutas interestatales, inicio/fin
forzoso, `gaiarda status`, CI en GitHub, ruteo real por carretera,
presupuesto de casetas de cuota con geocodificación vía OSM, gasto
diario estimado por ENIGH) ya está construido y probado.

## Otras lecciones de Gaiarda

- **Selectores CSS descendiente contra compuesto:** `.metro .app-shell`
  (descendiente, mal) contra `.metro.app-shell` (compuesto, mismo
  elemento, correcto). Ese error rompió en silencio todas las reglas
  de altura y overflow del layout desde que se creó. Vale la pena
  revisar este patrón en cualquier CSS nuevo con clases de tema.
- **Stack del dashboard de Gaiarda:** React, Vite, TypeScript,
  react-leaflet y react-leaflet-cluster. Tipografías Space Mono y DM
  Sans para el tema Metro, IM Fell English para el tema Odysseus.
