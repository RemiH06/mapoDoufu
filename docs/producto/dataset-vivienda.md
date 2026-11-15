# Dataset de vivienda por AGEB (tipo Boston Housing)

Una tabla por zona metropolitana con una fila por AGEB urbana y las variables
del Boston Housing (Harrison y Rubinfeld, 1978) traducidas a fuentes abiertas de
México. La primera es la de Guadalajara; el mismo comando sirve para cualquier
zona que tenga su estado cargado en Mapo.

Mapo arma la tabla y no ajusta modelos: un precio predicho por zona sería un
puntaje único (RNF5, `../arquitectura/decisiones.md`). El modelo vive en un
notebook aparte. La idea a futuro es un modelo por metrópoli y otro por grado de
ruralidad por estado, todos sobre tablas armadas igual.

## Cómo se arma

```bash
docker compose exec mapo_core python -m mapo_core.cli dataset_vivienda \
  --estado 14 --municipios 002,039,044,051,070,097,098,101,120,124 \
  --salida /app/data/vivienda_gdl
```

Desde Git Bash en Windows, antepón `MSYS_NO_PATHCONV=1`: sin eso, Git Bash
convierte `/app/data/...` en una ruta de Windows y la salida cae en otro lado.

Requisitos: el estado con `agebs`, `censo_poblacion`, `denue` y `sesnsp`
cargados (`../fuentes/`). Para la ZMG son los 10 municipios de la zona
metropolitana de CONAPO 2020. Para otra zona, sus claves de municipio.

Salida, en la carpeta indicada (dentro del contenedor, `/app/data` es
`mapo_core/data/` del repo, gitignorada):

| Archivo | Qué es |
|---|---|
| `vivienda_ageb.csv` | La tabla, una fila por AGEB urbana con censo |
| `vivienda_ageb.geojson` | Lo mismo con el polígono de cada AGEB |
| `diccionario.csv` | Columna, descripción, equivalente en Boston, fuente, nivel, método y cuántas AGEB quedaron vacías |
| `centros_empleo.csv` | Los 5 focos de empleo con que se calculó `dis_km` |
| `LEEME.txt` | Estado, municipios, año base y fecha |

Año base: el censo 2020. Todo lo que no es del censo se toma del año más cercano
a 2020 que exista, y el diccionario dice cuál.

## Equivalencias con Boston

`B` (proporción de población negra) no se replica: es la variable por la que
scikit-learn retiró el dataset en su versión 1.2, y no tiene sentido como
predictor de precio.

| Boston | Columna | Cómo se calcula | Estado |
|---|---|---|---|
| MEDV | `medv` | Mediana del valor catastral de suelo ($/m²) de la AGEB | Pendiente, ver [MEDV](#medv-valor-catastral) |
| CRIM | `crim` | Delitos del año base por 100 mil habitantes del municipio (SESNSP / censo). En Boston también era por municipio | Hecho |
| ZN | `viv_ha` | Viviendas habitadas por hectárea. ZN es la parte del suelo zonificada para lote grande; la zonificación de los planes parciales no tiene descarga general, y la densidad mide lo mismo al revés | Sustituto |
| INDUS | `indus` | Parte del personal ocupado en industria, mayoreo, transporte y agro (sectores de `rubros/sectores.csv`), con el personal estimado por el punto medio del estrato de DENUE | Hecho |
| CHAS | `chas` | La AGEB toca un río, canal o barranca de OSM | Pendiente |
| NOX | `nox` | NO₂ troposférico medio de Sentinel-5P (unos 5 km por píxel) | Pendiente |
| RM | `rm`, `pct_viv_3ymas_cuartos`, `pct_viv_2ymas_dorm` | Cuartos promedio. El censo agrupa "3 o más", así que `rm` es una cota inferior y casi no varía (mediana 2.85): las otras dos columnas guardan la variación | Hecho |
| AGE | `age` | Parte de la superficie construida en la AGEB que ya existía en 1990 (GHSL GHS-BUILT-S, 100 m). En Boston era vivienda anterior a 1940 | Pendiente |
| DIS | `dis_km` | Distancia promedio a los 5 centros de empleo, ponderada por el empleo de cada uno. Hoy en línea recta; por calle con OSRM después | Hecho (línea recta) |
| RAD | `rad` | Minutos por calle a la vía rápida más cercana (OSM `motorway` y `trunk`) | Pendiente |
| TAX | `tax` | Tasa de predial del municipio, de su ley de ingresos | Pendiente |
| PTRATIO | `ptratio` | Alumnos por docente. La estadística 911 por escuela no tiene descarga confirmada | Pendiente |
| LSTAT | `pct_sin_secundaria`, `pct_sin_servicios_salud`, `pct_piso_tierra`, `graproes` | Componentes separados, sin índice compuesto | Hecho |
| (extra) | `pct_viv_deshabitadas`, `pct_viv_auto`, `pct_viv_internet` | Columnas que Boston no tiene y aquí sí hay | Hecho |

### Detalles que importan

- **Denominador de las `VPH_*`:** es `VIVPARH_CV` (viviendas habitadas con
  características), no `VIVPAR_HAB`. Con `VIVPAR_HAB` el 5 % de las AGEB de la ZMG
  pasaban de 100 % de viviendas con auto. Lo mostraron los datos reales, no los
  tests.
- **Valores reservados:** el censo pone `*` donde una cifra identificaría a
  alguien (AGEB con muy pocas viviendas). Quedan vacíos; el diccionario cuenta
  cuántos. En la ZMG, `rm` queda vacío en 515 de 2,068 AGEB por eso.
- **Centros de empleo:** la rejilla de 1 km con más personal estimado, sin dos
  centros a menos de 4 km. No depende de la ciudad, así que corre igual en otra
  zona. En la ZMG salen el Centro de Guadalajara (33 mil personas estimadas),
  el corredor de López Mateos, Andares, y los centros de Tlaquepaque y Tonalá.
- **Personal por estrato:** DENUE da rangos ("11 a 30 personas"). Se usa el punto
  medio, y 300 para "251 y más". Es una estimación y lo dice el diccionario.

### Validación (ZMG, 2026-11-15)

- 2,068 AGEB urbanas con censo, 5,108,068 habitantes (la ZMG tiene 5.27
  millones; el resto vive en zona rural).
- Guadalajara suma 1,385,621 en AGEB urbanas contra 1,385,629 en el municipio.
- CRIM de Guadalajara en 2020: 39,698 delitos entre 1,385,629 habitantes da
  2,865 por 100 mil, el valor de la tabla.

## MEDV: valor catastral

No hay precio de vivienda abierto por AGEB:

- El índice de la SHF llega a municipio y sale de avalúos de crédito.
- El registro de vivienda de EconLab (Banxico) es de acceso restringido.
- Properati ya no publica México.
- Los portales de anuncios prohíben la extracción en sus términos.

Lo más cercano son las **tablas de valores unitarios de suelo** que cada
municipio publica para el predial y que aprueba el Congreso del estado: un valor
en $/m² por calle, tramo, colonia o zona.

**Es valor fiscal, no de mercado.** Suele quedar por debajo del comercial y se
actualiza con aumentos parejos (Jalisco aprobó de 3 % a 8 % para 2027). Sirve
como variable objetivo porque ordena las zonas igual que el mercado, no porque dé
el precio. El notebook lo tiene que decir.

### Por qué es difícil

Cada municipio lo publica distinto y cambia de un año a otro:

| Municipio | Lo que hay | Formato |
|---|---|---|
| Guadalajara 2020 | 174 hojas, una por cuadrante de la ciudad | Mapa vectorial en PDF: etiquetas `$ 2300` sobre calles, nombres de calle y claves de manzana, **sin georreferencia**. El servidor de catastro no responde (2026-11-15): la copia sale de Wayback |
| Zapopan 2026 | `Valor Catastral Zapopan 2026.pdf`, 544 hojas, 828 MB, más 11 PDF de tablas (construcción, rústico, plazas, parques industriales) | Mapas en PDF sin georreferencia (sin diccionario `/Measure` ni `/LGIDict`), en el bucket público `s3.zapopan.gob.mx/geomatica/tablasvalor/` |
| Los otros 8 de la ZMG | Sin revisar | Por cada uno: Periódico Oficial del estado, Congreso, o su catastro |

Y en otras ciudades habrá tablas en texto por colonia, Excel, o capas en un
GeoServer. Un extractor por municipio no escala; un pipeline con etapas fijas y
**un adaptador por formato** sí.

### Pipeline

Cada etapa deja un archivo intermedio con columnas fijas. Así una etapa se puede
rehacer sin repetir las anteriores, y un formato nuevo solo pide su adaptador.

1. **Registro de fuentes** (`catastro/fuentes.csv`): municipio, año fiscal, URL,
   formato (`pdf_mapa`, `pdf_tabla`, `xlsx`, `shp`, `wfs`), unidad, tipo de valor
   (suelo urbano, rústico, corredor) y fecha de consulta. Es lo único que se edita
   a mano cada año.
2. **Descarga** al almacén de crudos con su sha256, como las fuentes ambientales
   (`MANIFIESTO.tsv`). Detecta páginas HTML servidas en vez del archivo.
3. **Extracción → `etiquetas`**: una fila por texto útil, con `municipio`,
   `anio`, `hoja`, `tipo` (`valor`, `calle`, `colonia`, `clave`), `texto`,
   `valor_m2`, y su posición en la hoja (`x_hoja`, `y_hoja`) o su geometría si ya
   viene georreferenciado. Adaptadores:
   - `pdf_mapa`: `pdftotext -bbox-layout` da cada palabra con su caja. Los valores
     se reconocen por el patrón `$ 1,234`, y las calles por estar en el
     nomenclátor de OSM del municipio.
   - `pdf_tabla` y `xlsx`: filas de calle o colonia con su valor, sin posición.
   - `shp` y `wfs`: ya traen geometría y saltan la etapa 4.
4. **Ubicación → `valores`** (punto o polígono con `valor_m2`):
   - Para `pdf_mapa`, georreferencia por hoja. Las etiquetas de calle son puntos
     de control: cada nombre se empareja con la calle homónima de OSM (búsqueda
     difusa, sin acentos ni abreviaturas como `AV` o `C.`) y se ajusta una
     transformación afín de la hoja a coordenadas con RANSAC, que descarta los
     emparejamientos falsos (calles que se repiten en otra colonia). Con la afín,
     cada etiqueta de valor queda en el mapa. Se guarda la calidad por hoja: error
     medio en metros e inliers. Una hoja con pocos inliers o error alto se marca
     y no entra.
   - Para tablas por colonia, unión con polígonos de colonias. Para tablas por
     calle o tramo, geocodificación del tramo contra OSM.
5. **Normalización**: pesos nominales del año fiscal llevados al año base con
   los aumentos aprobados por el Congreso, o con el INPC si no se conocen. Las
   etiquetas que no son suelo urbano (rústico, plazas, parques industriales) se
   separan.
6. **Agregación por AGEB**: mediana de los valores dentro de la AGEB, con `n` y
   rango intercuartil. Con menos de 3 valores, `medv` queda vacío y `metodo` dice
   por qué. Nunca se rellena con un promedio de vecinos dentro de Mapo; eso, si
   se hace, va en el notebook.

**Para mantenerlo al día:** cada año se agrega una fila por municipio en
`fuentes.csv` y se corre de nuevo. Si el municipio cambió de formato, falla la
etapa 3 o la calidad de la etapa 4, y se ve en el reporte, no en el modelo.

**Validación:** puntos de control apartados (el error de ubicación en metros), y
el orden de las zonas contra lo conocido (Providencia y Puerta de Hierro arriba,
la periferia de Tlajomulco abajo). La tendencia por municipio se compara con el
índice SHF.

### Estado

- Probado a mano: el texto del PDF de Guadalajara 2020 sale con `pdftotext`, con
  valores y nombres de calle legibles (hoja 40: `$ 2300` en Huentitán el Alto,
  `$ 2530` en Paseo de los Leones).
- Falta: implementar las etapas 3 a 6 y medir la calidad de la georreferencia.

## Pendientes de las otras columnas

- `chas`, `rad`: un extracto de OSM de la zona (el `mexico-latest.osm.pbf` de
  OSRM ya está en Pixilate) y `rad` con la matriz de OSRM.
- `age`: GHSL GHS-BUILT-S, épocas 1975 a 2020, CC BY 4.0.
- `nox`: Sentinel-5P L2 NO₂ por el STAC de Planetary Computer, media anual 2020.
- `dis_km` por calle: la misma matriz de OSRM de las zonas candidatas.
- `tax`: tasa del predial de cada municipio (ley de ingresos 2020).
- `ptratio`: buscar la estadística por escuela de la SEP; si no existe, decir
  que falta antes que inventar un sustituto.
