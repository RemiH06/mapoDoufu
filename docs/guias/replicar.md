# Replicar los paquetes de datos para otra zona

Guía para que otro equipo arme, con Mapo, lo mismo que se armó para Autlán y El
Grullo (paquete ambiental) y para la zona metropolitana de Guadalajara (dataset
de vivienda), en cualquier parte del país. Cada paso deja un archivo que dice de
dónde salió cada dato, para que el resultado se pueda rehacer y auditar.

Los detalles de cada fuente están en `../fuentes/`; el método del dataset de
vivienda, en `../producto/dataset-vivienda.md`; y lo que suele romperse, con
cómo detectarlo, en `../producto/pipeline-datos.md`.

## Qué hace falta

- Una máquina con Docker, `uv` y unos 60 GB libres (los crudos ambientales pesan
  3.1 GB; las imágenes de una zona como Autlán, unos 3 GB).
- Una copia del repo de Mapo con la base levantada (`../desarrollo.md`) y el
  estado de la zona cargado: `python -m mapo_core.cli estados|municipios|agebs`,
  `censo_poblacion --estado NN` y `denue --estado NN` (`../fuentes/`).
- Para la zona: una caja en grados (oeste, sur, este, norte), las claves de sus
  municipios (5 dígitos) y la zona UTM (13N en Jalisco occidental, EPSG:32613).

## Paquete ambiental

| Paso | Comando | Lo que deja para la trazabilidad |
|---|---|---|
| 1. Bajar los crudos | `scripts/crudos-ambientales.sh scripts/crudos-ambientales.tsv DESTINO` | `MANIFIESTO.tsv`: archivo, bytes, sha256, fecha y URL de cada descarga; `FALLAS.tsv` |
| 2. Capas de la base de Mapo | `scripts/ambiental/desde_mapo.sh SALIDA O S E N [contenedor base usuario]` | `SALIDA/mapo/agebs.csv`, `denue.csv` |
| 3. Recorte | `uv run --script scripts/ambiental/recorte.py --crudos DESTINO --salida SALIDA --caja=O,S,E,N --municipios EEMMM,...` | `procedencia.csv` (capa → archivo crudo, sha256, fecha, URL), `diccionario_capas.csv` (filas, fuente, `fecha_dato` en AAAA, AAAA-MM o AAAA-MM-DD, `fecha_texto` con el detalle, nivel, nota), `zona.txt` (caja, municipios, comando completo, sha256 del script) |
| 4. Imágenes | `uv run --script scripts/ambiental/imagenes.py --salida SALIDA/imagenes --caja=O,S,E,N --epsg 326ZZ --worldcover --bandas INICIO/FIN --lst AAAA/AAAA --indices AAAA-MM/AAAA-MM` | `procedencia_imagenes.csv`: cada escena (ID del STAC de Planetary Computer, fecha, nubosidad, mosaico) por producto y por bloque |
| 4b. Dosel (zona urbana) | `uv run --script scripts/ambiental/dosel.py --salida SALIDA/imagenes --caja=O,S,E,N --epsg 326ZZ` | `procedencia_dosel.csv` (mosaicos y URL), `dosel_fecha.tif` (fecha de la imagen de origen) |
| 4c. Edificios | `uv run --script scripts/ambiental/edificios.py --salida SALIDA --caja=O,S,E,N` | `procedencia_edificios.csv` (versión de Overture, consulta y edificios por fuente) |
| 4d. Especies (arborización) | `uv run --script scripts/ambiental/especies.py --salida SALIDA/especies --caja=O,S,E,N [--radio-km 30]` | `procedencia_especies.csv` (consulta de GBIF, cuadros, licencias, distribución) y `metodo_enciclovida` por especie |
| 5. Para Mapo | `uv run --script scripts/para_mapo.py SALIDA SALIDA_MAPO` | `para_mapo.csv`: archivo, qué es, qué se recortó, tamaño, si cabe. Cada capa vectorial lleva por renglón `fuente`, `url`, `fecha_dato`, `fecha_consulta` y `nivel`, sacadas de los dos CSV del paso 3 |

| 6. Para ArcGIS (opcional) | `"C:\Program Files\QGIS 4.2.3in\python-qgis.bat" scripts/ambiental/para_arcgis.py --paquete SALIDA --salida SALIDA_ARCGIS --nombre NOMBRE --diccionario-censo diccionario_datos_ageb_urbana_EE_cpv2020.csv --municipios municipios.geojson` | `LEEME_ArcGIS.txt` (qué es cada capa y cómo leerla), tabla `Diccionario_campos` (nombre, alias, nombre original y descripción de INEGI), tabla `Procedencia` |

El recorte también deja las manzanas con su censo (si `poblacion/manzanas_EE_2020.zip`
está en los crudos) y el viento de ERA5 en `tablas/`.

Notas:

- `--caja=` lleva signo igual: sin él, la longitud negativa se toma como opción.
- Para un producto de imagen ya hecho por otra versión del script,
  `imagenes.py ... --solo-procedencia` repite las búsquedas y anota las escenas sin
  bajar nada. La selección es determinista (las más despejadas por mosaico), así
  que da las mismas escenas mientras el catálogo no cambie.
- Los crudos de población (ITER) están solo para Jalisco: para otro estado, bajar
  su ITER de INEGI y ajustar la ruta en `recorte.py` (pendiente de generalizar;
  ver `../producto/plan-nacional.md`).
- Los rásters de relieve (Copernicus GLO-30) cubren solo Jalisco en los crudos.

### Para ArcGIS

El paquete está pensado para QGIS. `para_arcgis.py` hace una versión para ArcGIS Pro
(se corre con el Python de QGIS, que trae GDAL con OpenFileGDB):

- Una File Geodatabase con conjuntos por tema (Población, Agua, Emisiones y fuego,
  Territorio, Ciudad, Especies, Municipios, Clima), todo en UTM 13N (EPSG:32613).
- Nombres de campo que ArcGIS acepta y alias legibles: el nombre original o el
  indicador de INEGI (del diccionario de datos del censo por manzana, que viene en
  `poblacion/manzanas_EE_2020.zip` de los crudos).
- Conteos del censo y del ITER como números: `*` (reservado) y `N/D` quedan nulos.
  Enteros de 32 bits: la geodatabase clásica no tiene de 64 y GDAL los volvería
  decimales.
- Las tablas también sobre el mapa: marginación sobre los AGEB, un resumen por
  municipio (sequía, siembra, PTAR, defunciones; los polígonos salen de la base de
  Mapo con `--municipios`), el estatus de Enciclovida en cada registro de GBIF y el
  viento en el centro de su celda de ERA5.
- Imágenes en unidades reales (NDVI de -1 a 1, °C, metros), WorldCover con nombre y
  color de cada clase, y el relieve en UTM.
- Cuadra filas contra el original; si no, no termina.

Revisado el 2026-11-19 con el paquete del CP 45615 (39 capas y tablas; la población de
las manzanas suma 640,778 en los dos). No se probó en ArcGIS Pro (no hay licencia en
las máquinas del proyecto): la geodatabase se reabrió con GDAL.

### Verificar antes de entregar

1. **Población:** urbana por AGEB (`agebs.pobtot`) más rural (`agebs_rurales.pobtot_iter`)
   debe dar el total del censo de cada municipio. En Autlán dio exacto: 52,019 +
   12,912 = 64,931.
2. **FIRMS:** el conteo de un año contra una consulta a mano en el visor de FIRMS.
3. **Imágenes:** mirar una vista en color de cada compuesto. El porcentaje sin
   dato no basta: no detectó un hueco de 22 % en un archivo sin `nodata`
   declarado, ni las manchas de reflectancia negativa en las presas.
4. **Capas vacías:** que digan por qué en `diccionario_capas.csv` (por ejemplo,
   "la red no tiene sitios en la caja"), no que falten sin aviso.

5. **Datos de personas:** las defunciones salen como conteos por municipio (antes del
   2026-11-19 el recorte copiaba los microdatos: un certificado por renglón, con
   localidad, edad y causa) y el RETC sin nombre de establecimiento.

### Lo que no se publica en `docs/`

Los hallazgos de una zona (qué empresas aparecen, qué descargas hay cerca de
qué) no van a la documentación pública del repo: proximidad no es causa y
señalar a una empresa pide revisión legal. Van en el informe del equipo.

## Dataset de vivienda

| Paso | Comando | Trazabilidad |
|---|---|---|
| 1. Fuentes nacionales cargadas | censo, DENUE, SESNSP (`../fuentes/`) | Tablas de la base con su fecha de carga |
| 2. Valor catastral (si hay tablas) | `scripts/catastro/extraer_pdf_mapa.py` o `extraer_pdf_raster.py`, luego `ubicar_pdf_mapa.py` o `ubicar_por_marcas.py` | `scripts/catastro/fuentes.csv` (URL, archivo, parámetros por municipio), `etiquetas_*.csv`, `hojas.csv` (calidad por hoja), `valores.csv` |
| 3. Insumos de entorno | Overpass (agua, vías, parques, estaciones con `scripts/vivienda/transporte_masivo.py`), GHSL, DEM, `scripts/ambiental/no2_s5p.py`, `imagenes.py` (NDVI y LST), `scripts/vivienda/sep_cifras.py` | La fecha de cada extracto de OSM (`osm3s.timestamp_osm_base`), la procedencia de imágenes |
| 4. Armar | `python -m mapo_core.cli dataset_vivienda --estado NN --municipios MMM,... --salida ... [--medv ...] [--medv-2026 ...] [insumos]` | `LEEME.txt` (entradas usadas), `diccionario.csv` (método y vacíos por columna) |
| 5. Para Mapo | `uv run --script scripts/para_mapo.py CARPETA SALIDA_MAPO` | `para_mapo.csv` |

Comandos completos con los argumentos de la ZMG: `../producto/dataset-vivienda.md`.

### Verificar antes de entregar

1. Población por municipio contra el censo (Guadalajara: 1,385,621 en AGEB urbanas
   contra 1,385,629 en el municipio).
2. Rangos de cada columna en `diccionario.csv` y en el resumen que imprime el
   comando (p5, mediana, p95): porcentajes entre 0 y 100, altitudes razonables.
3. Valor catastral: error por hoja en `hojas.csv`, una vista sobre el mapa, y la
   correlación con la escolaridad por municipio.
4. Que ninguna tabla de valores cruce el límite de su municipio (lo impide el
   código; revisar que un municipio sin tabla dé 0 AGEB con `medv`).

## Ver los datos en Mapo

Los paquetes se suben como datos propios de un equipo (`../producto/datos-propios.md`):

1. Crear un equipo por proyecto en Mapo e invitar a sus miembros.
2. Correr `scripts/para_mapo.py` sobre el paquete: deja archivos que caben (50 MB,
   100 columnas, 50,000 renglones) y un `para_mapo.csv` con lo que recortó.
3. Subirlos en `/mapa`, pestaña "Tus datos". Cuenta: 500 MB por equipo y 30
   lecturas por hora por cuenta, así que un paquete grande se sube en varias horas
   o entre varias personas del equipo.
4. Se ven hasta tres capas a la vez. Un ráster se ve como imagen de su primera
   banda, sin consultar píxeles: para análisis, el paquete completo en QGIS.

Para Autlán: 48 archivos, 301 MB. Para el dataset de vivienda: 4 archivos, 5 MB.
