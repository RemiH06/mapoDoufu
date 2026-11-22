# Transporte público: GTFS abiertos y rutas de OSM

No hay una fuente nacional de rutas de transporte público: ni INEGI ni SEDATU las
publican, y cada ciudad publica su GTFS (horarios en el formato de Google) o no. Mapo junta
los GTFS abiertos que encontró y, donde no hay ninguno, las rutas de OpenStreetMap, dichas
como tales: sin horarios ni frecuencias. Lo usan el acetato "Transporte público" de `/mapa`
y dos servicios de `/accesibilidad` (`../producto/transporte.md`).

## Dónde se buscó (2026-11-22)

- **Mobility Database** (MobilityData): catálogo mundial, con CSV en
  https://files.mobilitydatabase.org/feeds_v2.csv. Trae 18 entradas de México, la
  mayoría viejas o inactivas.
- **Hub de Datos de Transporte Público en México** (Codeando México): 21 feeds de 8
  estados, con catálogo DCAT en https://hdtp.codeandomexico.org/datos/catalogo.json
  (licencia, productor, vigencia, SHA-256 y copia alojada de cada uno).
- Monterrey (Regio Ruta), Puebla, León, Tijuana y Juárez no publican GTFS abierto. Según
  ITDP, Monterrey publicó sus datos a través de Google Maps. Ni Google ni Moovit permiten
  guardar o redistribuir sus rutas: no son fuente. Quedan pendientes en `steps.md`.

## Los feeds

`FEEDS` en `mapo_core/transporte.py` es el catálogo curado: clave, productor, URL (la
original primero y la copia del hub después), página de origen y licencia tal como la
declara el feed (`None` si no declara ninguna). Al 2026-11-22:

| Feed | Ciudad | Productor | Licencia | Rutas | Frecuencia |
|---|---|---|---|---|---|
| `jal-setran` | ZMG, Puerto Vallarta, Tepatitlán, Lagos de Moreno, Zapotlanejo | SETRAN, publicado por Ualabee | no declara | 403 | sí (mayo a dic. 2026) |
| `cdmx-semovi` | Ciudad de México: Metro, RTP, Trolebús, Tren Ligero, Cablebús, corredores | SEMOVI | CC BY 4.0 | 292 | sí, de 2025 |
| `cdmx-metrobus` | Metrobús | Metrobús CDMX | ODC-BY 1.0 | 89 | sí |
| `cdmx-insurgente` | Tren El Insurgente | Codeando México (titular Banobras) | ODC-BY 1.0 | 1 | sí |
| `mex-toluca` | Toluca | SEMOV del Estado de México | no declara | 622 | relleno |
| `mex-jilotepec` | Jilotepec | Ayuntamiento de Jilotepec | CC BY 4.0 | 37 | sí |
| `yuc-vayven` | Mérida, Va y Ven | Agencia de Transporte de Yucatán | no declara | 175 | sí |
| `qro-qrobus` | Querétaro, Qrobús | AMEQ | no declara | 117 | sí, vencido el 2026-10-17 |
| `ags-concesionado` | Aguascalientes | Gobierno del Estado | CC BY-SA 4.0 | 48 | sí, vencido el 2025-12-31 |
| `mich-uruapan` | Uruapan | Codeando México | no declara | 70 | relleno |
| `mich-zamora` | Zamora | Ayuntamiento de Zamora | CC BY-SA 4.0 | 43 | sí |
| `mich-zitacuaro` | Zitácuaro | Codeando México | no declara | 148 | sí |
| `oax-oaxaca` | Oaxaca de Juárez | Codeando México | no declara | 110 | relleno |
| `oax-huatulco` | Huatulco | SEMOVI Oaxaca | ODC-BY 1.0 | 3 | sí |
| `oax-puertoescondido` | Puerto Escondido | Codeando México | no declara | 29 | sí |
| `oax-salinacruz` | Salina Cruz | SEMOVI Oaxaca | ODC-BY 1.0 | 22 | relleno |
| `bcs-cabo` | Cabo San Lucas | Codeando México con datos del IMPLAN | ODC-BY 1.0 | 22 | relleno |

Fuera a propósito: los GTFS de 2020 a 2024 del portal de Jalisco y del hub (Macrobús, Tren
Ligero, Mi Macro de Nubenautas, Vallarta de Busmaps), que el de SETRAN reemplaza; y Ecobici
y MiBici (GBFS, bicicletas, no rutas). El de SEMOVI trae Metrobús y El Insurgente viejos:
se excluyen esas agencias (`excluir_agencias`) porque tienen feed propio más nuevo.

**Licencias.** Ocho feeds no declaran licencia, entre ellos el de Jalisco. Mapo no
redistribuye ningún feed (no hay descarga del GTFS): muestra las rutas en el plano y
calcula sobre ellas, citando a su productor con la leyenda "sin licencia declarada".
Si un productor pide quitarlo, se quita su clave de `FEEDS` y se recarga.

## Cómo se lee

`python -m mapo_core.cli transporte [--feeds ...] [--carpeta data/transporte]` baja cada
feed, lo lee y lo reemplaza entero en una transacción (si falla, queda el anterior y los
demás siguen). `--archivo` carga un zip local para un solo feed. Tablas
`transporte_feeds`, `transporte_rutas` y `transporte_paradas`.

- **Día de referencia:** el miércoles con más viajes de la vigencia del feed (en los
  últimos tres años y el próximo), y entre empates el más cercano a hoy. Así no cae en
  un feriado (`calendar_dates`) ni en el resto de un feed cuyo servicio principal ya
  terminó: el de SEMOVI dice "hasta 2026-12-31", pero casi todo acaba el 2025-12-31 y
  solo el Trolebús 13 sigue. Si el día es de hace más de medio año, se avisa.
- **Hora pico:** de 7:00 a 9:00 de ese día. Por ruta y sentido se cuenta cuántas veces
  pasa por su parada más servida; la ruta se queda con el sentido más servido. El
  intervalo es 120 minutos entre esas pasadas. "Frecuente" es cada 15 minutos o menos (8
  pasadas).
- **Viajes por frecuencia** (`frequencies.txt`): cada salida de `start_time` a
  `end_time` cada `headway_secs`, con el desfase de cada parada sacado de su plantilla.
  Si `exact_times` no es 1, la ruta queda con `frecuencia_estimada`: el feed da un
  intervalo, no un horario.
- **Paradas sin hora** (permitido entre dos con hora): hora proporcional por orden.
- **Circuitos:** un viaje que toca la misma parada dos veces cuenta una (con las dos,
  rutas de RTP salían el doble de frecuentes que su `headway_secs`).
- **Trazo:** por sentido, la forma (`shapes.txt`) que más viajes usan; sin forma, las
  paradas en orden. Rutas sin viajes ni trazo no se guardan (Qrobús lista 100 así).
- **Paradas:** solo `location_type` 0 dentro de la caja de México; cada una guarda las
  pasadas de la ruta que más pasa (`pasadas_ruta_max`), las de todas y cuántas rutas la
  tocan. Al cargar se les pone municipio con el marco geoestadístico.
- **Frecuencia de relleno:** si 80 % o más de las rutas de un feed (de 10 rutas en
  adelante) tienen la misma cantidad de pasadas, el feed la puso a mano y no dice nada:
  `frecuencia_util` falso, y ni el plano ni la accesibilidad la usan. Pasa en Toluca,
  Uruapan y Oaxaca (24 pasadas, cada 5 minutos, en casi todas), en Salina Cruz y en Cabo
  San Lucas, cuyo autor avisa que le faltan las frecuencias.
- **Archivos de terceros:** tope de 300 MB al bajar, 3 GB descomprimido y proporción de
  compresión sospechosa en archivos grandes; se leen por nombre sin extraer nada a disco
  (no hay rutas dentro del zip que puedan salirse); tope de 25 millones de horarios.
- **Memoria:** los horarios se guardan en arreglos compactos y solo de los viajes del
  día. El de Jalisco (52 MB, 358 MB de `stop_times.txt`) tarda 97 s en Aerilate.

## Validación

- **Contra el propio feed, rutas por frecuencia:** en las 300 rutas de SEMOVI con
  `frequencies.txt`, las pasadas de 7 a 9 de Mapo son las de `headway_secs` en 296 (±1).
  Las 4 que difieren tienen variantes que sirven paradas distintas: el conteo directo
  las suma y Mapo cuenta en cada parada. En Jalisco, las 4 rutas por frecuencia coinciden.
- **Contra el propio feed, rutas por horario:** salidas de 7 a 9 desde la primera parada,
  contadas aparte en `stop_times.txt`, contra Mapo: C01 20 y 20, C105 14 y 14, T14B 24 y
  24, Mi Tren L1 20 y 20, L3 34 y 35 (un tren que sale a las 6:5x pasa por media línea
  dentro de la ventana).
- **Contra lo que se conoce:** Mi Tren L1 cada 6 min, L3 cada 3.4 y L4 cada 2.5; Mi Macro
  Calzada cada 4 a 5 min; Metro de la CDMX cada 3 a 4 min según el feed (estimado).

## Rutas de OpenStreetMap

`scripts/transporte/rutas_osm.sh` (en Pixilate, sobre el pbf de México de Geofabrik que ya
baja `scripts/osrm/pie.sh`) saca las relaciones `route=bus|share_taxi|trolleybus|tram|
light_rail|subway|train|monorail|aerialway|ferry|funicular` con sus vías y les pone
coordenadas (`osmium tags-filter`, `add-locations-to-ways`, OPL con
`locations_on_ways`). 19 s y 27 MB. `python -m mapo_core.cli transporte_osm
rutas-AAMMDD.opl` las carga como el feed `osm` (`mapo_core/transporte_osm.py`): la fecha
del nombre es la del pbf y va a la cita.

Del 2026-11-20: 2,656 relaciones; 2,288 con vías (337 con sus vías fuera del extracto,
rutas que cruzan a Estados Unidos o incompletas). 2,146 de camión, 39 colectivos, 32 de
metro, 25 de trolebús, 16 de tren, 16 de ferri, 8 de tren ligero, 5 de cable y 1
monorriel; 8,429 paradas. Las paradas son los nodos con rol `stop` o `platform` que traen
alguna etiqueta. Autlán de Navarro, por ejemplo, no tiene ninguna ruta en OSM.

## Pendiente

- Monterrey, Puebla, León, Tijuana, Juárez: sin GTFS abierto.
- Refrescar: el de Jalisco vence el 2026-12-31; Querétaro y Aguascalientes ya vencieron
  (su URL original puede traer uno nuevo).
- Paradas de OSM en la accesibilidad (hoy solo GTFS: OSM no dice si la ruta opera).
