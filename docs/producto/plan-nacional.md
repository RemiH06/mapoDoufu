# Plan: los dos paquetes para todo el país

Los paquetes de Autlán y El Grullo (ambiental) y de la ZMG (vivienda) se hicieron
para una zona. Este plan dice qué falta para tener lo mismo en cualquier parte de
México y en qué orden. Lo que ya está hecho y cómo replicarlo a mano está en
`../guias/replicar.md`.

## Qué ya es nacional y qué no

| Pieza | Hoy | Para todo el país |
|---|---|---|
| Fuentes ambientales en crudo (RENAMECA, REPDA, RETC, FIRMS, SIAP, uso de suelo, acuíferos, ANP, defunciones) | Nacionales | Nada |
| Población por localidad (ITER) | Solo Jalisco (`iter_14_2020.zip`) | Bajar los 32 y que `recorte.py` tome el del estado de cada municipio |
| AGEB rurales y localidades con polígono | API de INEGI por municipio | Nada |
| Relieve | Mosaicos de Jalisco | Leer Copernicus GLO-30 del STAC de Planetary Computer por caja, como las imágenes |
| Imágenes (Sentinel-2, Landsat, WorldCover) | STAC, cualquier caja | Nada para una zona; para todo el país, ver abajo |
| Altura de dosel a 1 m (Meta y WRI) | `dosel.py`, cualquier caja | Nada para una zona; para el país, estadística por manzana o AGEB |
| Viento (ERA5) | API de Open-Meteo, centro de la caja | Climatología por mes y hora para cada celda de 0.25° de México (unas 3,000), desde el Climate Data Store |
| Censo por AGEB, DENUE, SESNSP | Los estados cargados en la base | Cargar los 32 estados |
| Colonias | No existen con polígono en ninguna fuente nacional | Pipeline de `colonias.md`: oficial, OSM, votación de direcciones sobre manzanas o dibujo del equipo |
| Manzanas | No están en la base | Polígonos del Marco Geoestadístico y censo por manzana de INEGI, por estado (Jalisco: 102,734 manzanas con censo). INEGI oculta valores en manzanas con pocas viviendas |
| OSM (agua, vías, parques, estaciones, amenidades) | Overpass por caja | Extracto de México de Geofabrik con fecha fija y `osmium` local: reproducible y sin depender del servidor público |
| GHSL, NO2 (TROPOMI) | Por caja | Global: mosaicos de GHSL de México; rejilla de NO2 nacional a 0.05° |
| Escuelas (SEP, PTRATIO) | `sep_cifras.py` por estado | Correrlo para los 32 |
| Predial (TAX) | Tablas de 10 municipios de la ZMG | Una tabla por municipio desde su ley de ingresos (congreso de cada estado) |
| Valor catastral (MEDV) | GDL, Zapopan, Tonalá, Ixtlahuacán | El cuello de botella: ver abajo |

## Cuánto pesa el país (medido el 2026-11-17)

Tamaños en la base de dev (con índices) y lo que daría el país completo. Las
estimaciones escalan lo medido en Jalisco por la proporción que Jalisco es del
total de esa fuente.

| Fuente | Hoy | País completo | ¿De un jalón? |
|---|---|---|---|
| SESNSP, delitos por municipio (2015 a 2025) | Ya nacional: 12 GB (5.7 de datos y 6.4 de índices), 30.7 millones de filas | Lo mismo | Ya está, y es lo que más pesa de la base. Si estorba, guardarlo por año en vez de por mes, o quitar índices que no se usan |
| OSRM (rutas en auto) | Ya nacional: 8 GB en disco, 5.1 GB de RAM sirviendo | Lo mismo | Ya está. Lo caro es rehacerlo: el preproceso llega a 14.8 GB de RAM (`../fuentes/osrm.md`) |
| DENUE | Jalisco: 484 MB, 401,813 negocios | Unos 6.4 GB, 5.3 millones de negocios (los ZIP de los 32 estados suman 521 MB) | Sí. Por estado con `cli denue`, unos 5 minutos por cada 400 mil: alrededor de hora y media en total |
| Censo 2020 por AGEB, localidad y municipio | Jalisco: 14 MB | Unos 200 MB | Sí, sin problema |
| Polígonos de AGEB urbanas | Jalisco: 5 MB | Unos 75 MB | Sí |
| Polígonos de municipios | Jalisco: 5.4 MB (125) | Unos 100 a 150 MB (2,469) | Sí |
| Estados | Ya nacional: 16 MB | Lo mismo | Ya está |
| ENIGH | Ya nacional: 14 MB | Lo mismo | Ya está |
| Imágenes (Sentinel-2, Landsat) | Por caja, fuera de la base | Cientos de GB por fecha | **No, y Mapo no las hospeda** (ver abajo) |
| Ediciones viejas de DENUE (estudio de sobrevivencia) | Fuera de la base | Unos 2 GB de ZIP por las cuatro ediciones del estudio | Sí, en disco; no van a la base |

Con todo lo que sí cabe, la base pasaría de 12 GB a unos 19 GB, y el respaldo
nocturno (`pg_dump` comprimido, hoy 244 MB) crecería en proporción. Lo único que
no tiene sentido tener completo son las imágenes.

## Unidades

- **Vivienda urbana:** las metrópolis de la delimitación de SEDATU, CONAPO e INEGI
  (Metrópolis de México 2020), con sus municipios. Un dataset y un modelo por
  metrópoli, como pidió el proyecto.
- **Vivienda rural:** por estado, con AGEB rurales y localidades del ITER. El
  valor de referencia ahí son las tablas de valores rústicos (por hectárea y por
  zona), no las urbanas.
- **Ambiental:** cualquier caja con sus municipios. No tiene sentido precalcular
  un paquete por zona: se arma a pedido en minutos, salvo las imágenes.

## Imágenes para todo el país

Un compuesto de Sentinel-2 de 10 bandas a 10 m para México pesa cientos de GB por
fecha. **Decisión de Remi (2026-11-17): Mapo no hospeda rásteres públicos.** De
la data pública, los rásteres son lo único que pone cada equipo: los sube como
capa propia (`datos-propios.md`), con la procedencia que indica
`../guias/replicar.md`. Mapo sí da las herramientas para producirlos:

1. **Zona de estudio:** el compuesto de 10 m, NDVI, temperatura de superficie y
   WorldCover con `imagenes.py`, a pedido, como en Autlán y López Cotilla. El
   archivo se le entrega al equipo; no se queda en el servidor.
2. **Estadística zonal por AGEB o localidad** (NDVI o temperatura promedio de
   MODIS o Landsat agregado): es una tabla, no un ráster, y sí podría entrar a la
   base como cualquier fuente. Pendiente de decidir si vale la pena.

Por eso la sesión 19 trae "ráster con valor por píxel": si los rásteres vienen
del equipo, la capa propia tiene que poder consultarse, no solo verse.

## Valor catastral

Cada municipio publica sus tablas a su manera (mapa vectorial, mapa escaneado,
lista por colonia sin mapa) o no las publica. Lo que funciona:

1. **Registro:** `scripts/catastro/fuentes.csv` crece con un renglón por
   municipio: URL, formato, parámetros del extractor y estado de revisión.
2. **Adaptadores por formato**, no por municipio: ya hay PDF vectorial, PDF
   escaneado con OCR, ubicación por calles de OSM y por marcas UTM. Faltan
   listas por colonia (se necesitan polígonos de colonia, que INEGI no da con
   coordenadas) y planos índice.
3. **Revisión obligatoria** de cada municipio nuevo: error por hoja, vista sobre
   el mapa y correlación con escolaridad (`pipeline-datos.md`).
4. **Transparencia** donde no se publica: solicitud por la PNT pidiendo la tabla
   en formato vectorial.
5. **Donde no hay tabla, se estima y se dice:** una columna de valor estimado
   con su error medido dejando fuera municipios completos, nunca mezclada con la
   observada.

Empezar por las metrópolis más grandes: Valle de México, Monterrey, Puebla-Tlaxcala,
Toluca, Tijuana, León, Querétaro, Juárez, La Laguna y Mérida.

## Vistas temáticas

Hoy un paquete se ve subiéndolo como datos propios de un equipo
(`../guias/replicar.md`). Para datos de un estado o del país eso no escala. La
propuesta es una vista por tema (ambiental, precios de vivienda, y las que sigan),
hecha de **capas públicas**: las mismas para todos, con su procedencia a un clic.

- **Todo se cruza:** una vista es un punto de partida, no una barrera. Cualquier
  capa del catálogo (de cualquier tema) y los datos propios del equipo se pueden
  abrir y cruzar desde cualquier vista cuando la pregunta lo pide: el calor de una
  manzana con su valor catastral, o el dosel con la edad de quienes viven ahí.
- **Catálogo:** una tabla de capas con tema, fuente, fecha del dato, nivel
  (estado, municipio, AGEB, manzana, punto, ráster), licencia, cobertura (polígono
  de lo que ya está cargado) y procedencia. Una vista es un filtro del catálogo por
  tema, así que agregar un tema no pide código nuevo.
- **Vectoriales:** en PostGIS, servidas por caja visible y con umbral de zoom
  (manzanas solo de cerca), como ya se sirven las AGEB.
- **Rásters:** COG en disco, servidos en teselas por `mapo_core` leyendo solo la
  ventana pedida. Así se consulta el valor de un píxel y se resume por zona, cosa
  que la imagen de 2,048 px de los datos propios no permite.
- **Análisis:** resumen por zona dibujada o por AGEB y manzana, con cada capa por
  separado (nunca un puntaje único) y el cruce con los datos propios del equipo.
- **Crecer al país:** cargar un estado es correr los mismos comandos con otra
  clave; la cobertura del catálogo le dice a la vista qué hay y qué no en cada lugar.

Primero Jalisco, con lo que ya está en crudo; es una fase de producto aparte, con
su propia revisión de rendimiento.

Primera vista hecha (sesión 21): vivienda por municipio como acetato de `/mapa`
(`vista-vivienda.md`). Todavía sin catálogo: el acetato conoce sus indicadores.

## Orden

1. Generalizar lo que hoy es de Jalisco: ITER de los 32 estados y relieve desde
   el STAC. Con eso el paquete ambiental sale para cualquier caja.
2. Cargar censo, DENUE y SESNSP de los 32 estados.
3. Extracto local de OSM y la tabla de metrópolis con sus municipios.
4. Correr `dataset_vivienda` para cada metrópoli sin valor catastral: todas las
   columnas menos `medv` y `tax`.
5. Predial por municipio, empezando por las diez metrópolis.
6. Valor catastral municipio por municipio, con su revisión.
7. Estadística zonal nacional de NDVI y temperatura.
8. Vistas temáticas en Mapo, empezando por ambiental y vivienda de Jalisco.

Los pasos 1 a 4 son automatizables casi por completo; 5 y 6 necesitan revisión
humana por municipio, y son la mayor parte del trabajo.
