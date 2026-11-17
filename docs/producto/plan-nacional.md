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
| Censo por AGEB, DENUE, SESNSP | Los estados cargados en la base | Cargar los 32 estados |
| OSM (agua, vías, parques, estaciones, amenidades) | Overpass por caja | Extracto de México de Geofabrik con fecha fija y `osmium` local: reproducible y sin depender del servidor público |
| GHSL, NO2 (TROPOMI) | Por caja | Global: mosaicos de GHSL de México; rejilla de NO2 nacional a 0.05° |
| Escuelas (SEP, PTRATIO) | `sep_cifras.py` por estado | Correrlo para los 32 |
| Predial (TAX) | Tablas de 10 municipios de la ZMG | Una tabla por municipio desde su ley de ingresos (congreso de cada estado) |
| Valor catastral (MEDV) | GDL, Zapopan, Tonalá, Ixtlahuacán | El cuello de botella: ver abajo |

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
fecha. No se precalcula. Dos niveles:

1. **Nacional, por AGEB o localidad:** NDVI y temperatura de superficie como
   estadística zonal, de MODIS (250 m y 1 km) o Landsat agregado. Cabe en una
   tabla y entra a la base de Mapo como cualquier fuente.
2. **Zona de estudio:** el compuesto de 10 m con `imagenes.py`, a pedido, como
   en Autlán.

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

## Ver los datos en Mapo

Hoy un paquete se ve subiéndolo como datos propios de un equipo
(`../guias/replicar.md`). Para datos nacionales eso no escala: harían falta
**capas públicas**, las mismas para todos, servidas como teselas (vectoriales para
AGEB y localidades, ráster para NDVI y relieve) y con su procedencia a un clic.
Es una fase de producto aparte, con su propia revisión de rendimiento.

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
8. Capas públicas en Mapo.

Los pasos 1 a 4 son automatizables casi por completo; 5 y 6 necesitan revisión
humana por municipio, y son la mayor parte del trabajo.
