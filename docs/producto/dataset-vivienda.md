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
| MEDV | `medv`, `medv_calle` | Mediana del valor catastral de suelo ($/m²) de la AGEB: de zona y por tramo de calle, por separado | Guadalajara hecho; el resto, ver [MEDV](#medv-valor-catastral) |
| CRIM | `crim` | Delitos del año base por 100 mil habitantes del municipio (SESNSP / censo). En Boston también era por municipio | Hecho |
| ZN | `viv_ha` | Viviendas habitadas por hectárea. ZN es la parte del suelo zonificada para lote grande; la zonificación de los planes parciales no tiene descarga general, y la densidad mide lo mismo al revés | Sustituto |
| INDUS | `indus` | Parte del personal ocupado en industria, mayoreo, transporte y agro (sectores de `rubros/sectores.csv`), con el personal estimado por el punto medio del estrato de DENUE | Hecho |
| CHAS | `chas` | 1 si hay un río o canal de OSM (`waterway=river\|canal`) a 100 m o menos de la AGEB; los arroyos no cuentan | Hecho |
| NOX | `nox` | NO₂ troposférico medio de Sentinel-5P (unos 5 km por píxel) | Pendiente |
| RM | `rm`, `pct_viv_3ymas_cuartos`, `pct_viv_2ymas_dorm` | Cuartos promedio. El censo agrupa "3 o más", así que `rm` es una cota inferior y casi no varía (mediana 2.85): las otras dos columnas guardan la variación | Hecho |
| AGE | `age`, `age_1975` | Parte de la superficie construida en 2020 dentro de la AGEB que ya existía en 1990 (y en 1975), GHSL GHS-BUILT-S, 100 m. En Boston era vivienda anterior a 1940 | Hecho |
| DIS | `dis_km` | Distancia promedio a los 5 centros de empleo, ponderada por el empleo de cada uno. Hoy en línea recta; por calle con OSRM después | Hecho (línea recta) |
| RAD | `rad_km` | Distancia en línea recta a la vía rápida más cercana (OSM `motorway` y `trunk`). RAD de Boston es un índice de acceso | Hecho (línea recta) |
| TAX | `tax` | Tasa efectiva de predial del municipio a un valor fiscal de referencia. En la ZMG el predial es una tabla progresiva por tramos, ((VF − LI) × T) + CF por bimestre, no una tasa: hay que leer la tabla de la ley de ingresos 2020 de cada municipio | Pendiente |
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
| Zapopan 2026 | `Valor Catastral Zapopan 2026.pdf`, 544 hojas, 828 MB, más 11 PDF de tablas (construcción, rústico, plazas, parques industriales), en el bucket público `s3.zapopan.gob.mx/geomatica/tablasvalor/` | **Escaneo**: copia certificada del Periódico Oficial (18 de diciembre de 2025) con sellos encima, una imagen JPEG de 5100 × 3300 por hoja y ningún texto vectorial. Hojas por zona catastral ("ZONA CATASTRAL 34 4G5"), no por rejilla. Valores como números de 4 cifras sin `$`, más grandes que los números de manzana |
| Los otros 8 de la ZMG | Sin revisar | Por cada uno: Periódico Oficial del estado, Congreso, o su catastro |

Y en otras ciudades habrá tablas en texto por colonia, Excel, o capas en un
GeoServer. Un extractor por municipio no escala; un pipeline con etapas fijas y
**un adaptador por formato** sí.

### Pipeline

Cada etapa deja un archivo intermedio con columnas fijas. Así una etapa se puede
rehacer sin repetir las anteriores, y un formato nuevo solo pide su adaptador.
Los scripts viven en `scripts/catastro/` (se corren con `uv run --script`, sin
tocar las dependencias de `mapo_core`) y los datos en `mapo_core/data/catastro/`
(gitignorada).

1. **Registro de fuentes**, [`scripts/catastro/fuentes.csv`](../../scripts/catastro/fuentes.csv):
   municipio, año fiscal, formato, URL, archivo, EPSG de trabajo, tamaño de letra
   que separa valores de zona de valores de calle, unidad y fecha de consulta.
   Es lo único que se edita a mano cada año.
2. **Descarga** a `mapo_core/data/catastro/crudos/`. Para ubicar hacen falta
   también las calles con nombre de OSM de la zona (Overpass:
   `way["highway"]["name"](sur,oeste,norte,este); out geom;`), ODbL.
3. **Extracción → `etiquetas_<municipio>_<año>.csv`**, una fila por texto con
   `pagina`, `hoja`, `tipo` (`valor`, `hoja`, `clave`, `texto`), `texto`,
   `valor_m2`, `x`, `y` (centro en puntos de la hoja), `angulo` y `tamano`.
   Adaptador hecho: `extraer_pdf_mapa.py` (PyMuPDF). Separa "$ 2530 PASEO DE LOS
   LEONES" en valor y calle, y toma como clave de la hoja la etiqueta de hoja más
   grande (las de las vecinas van chicas).
4. **Ubicación → `valores.csv`** (`municipio`, `anio`, `pagina`, `hoja`,
   `valor_m2`, `tamano`, `clase`, `lon`, `lat`), con `hojas.csv` (calidad por
   hoja) y `control.csv`. Adaptador hecho: `ubicar_pdf_mapa.py`:
   - Supone lo que cumple un atlas catastral: todas las hojas a la misma escala y
     orientación. Escala, giro y espejo se estiman una vez, con una rejilla de
     candidatos sobre las seis hojas con más calles.
   - El desplazamiento de cada hoja sale por **votación de Hough**: cada etiqueta
     de calle vota por cada punto (cada 15 m) de las calles de OSM con su nombre
     normalizado (sin acentos, sin tipo de vía, abreviaturas expandidas, sin
     artículos). El desplazamiento verdadero junta los votos de todas las calles
     en una celda de 40 m; las calles homónimas de otras colonias se dispersan.
   - Luego **ICP**: cada etiqueta contra el punto más cercano de su calle,
     similitud por mínimos cuadrados (Umeyama), seis vueltas.
   - Una hoja se acepta con al menos 8 calles a menos de 40 m de su homónima,
     error mediano de 20 m o menos, y escala a menos de 10 % de la global.
   - `clase`: `zona` o `calle`, según el tamaño de letra del valor
     (`--zona-desde-tamano`, propio de cada atlas).
   - Para `pdf_raster` (Zapopan 2026) falta un adaptador de extracción con OCR
     (RapidOCR o Tesseract) que entregue las mismas `etiquetas`: números de 4
     cifras por tamaño de letra y nombres de calle, con posición en píxeles. La
     ubicación por Hough serviría igual, pero hay que probar si la escala es la
     misma en todas las hojas: al ir por zona catastral, puede que no.
   - Para tablas por colonia o por tramo (sin mapa), el adaptador uniría con
     polígonos de colonias o geocodificaría el tramo contra OSM. No hecho.
5. **Normalización:** pendiente. Hará falta al mezclar años (Zapopan es 2026):
   llevar los pesos al año base con los aumentos aprobados por el Congreso o el
   INPC.
6. **Agregación por AGEB**, en `dataset_vivienda --medv valores.csv[,otro.csv]`:
   - `medv`: mediana de los valores de **zona** dentro de la AGEB. Es el valor
     base de la colonia, lo más parecido al valor típico de Boston.
   - `medv_calle`: mediana de los valores por **tramo**, con 3 como mínimo. Los
     corredores comerciales la suben.
   - `medv_n`, `medv_calle_n`, `medv_anio` y `medv_metodo`, que dice de dónde salió
     el valor o por qué falta ("sin tabla de valores ubicada para este municipio",
     "sin valor de zona dentro de la AGEB"). Nunca se rellena con vecinas.

```bash
C=mapo_core/data/catastro
uv run --script scripts/catastro/extraer_pdf_mapa.py $C/crudos/guadalajara_2020.pdf   $C/etiquetas_14039_2020.csv --municipio 14039 --anio 2020
uv run --script scripts/catastro/ubicar_pdf_mapa.py $C/etiquetas_14039_2020.csv   $C/crudos/osm_calles_gdl.json $C/ubicado_14039_2020 --epsg 32613 --zona-desde-tamano 10
MSYS_NO_PATHCONV=1 docker compose exec mapo_core python -m mapo_core.cli dataset_vivienda   --estado 14 --municipios 002,039,044,051,070,097,098,101,120,124 --salida /app/data/vivienda_gdl   --medv /app/data/catastro/ubicado_14039_2020/valores.csv
```

**Para mantenerlo al día:** cada año, una fila por municipio en `fuentes.csv` y
las tres corridas. Si el municipio cambió de formato, falla la extracción o la
calidad de `hojas.csv`, y se ve ahí, no en el modelo.

### Validación: Guadalajara 2020 (2026-11-15)

- 174 páginas: 1 a 30 son tablas de construcción e índices, 144 son hojas de
  mapa (rejilla A a H, columnas 1 a 7, cuadrantes 1 a 4). 7,270 etiquetas de
  valor: 5,369 de tramo (7.9 y 6 puntos; 6 en el Centro, por densidad) y 1,716 de
  zona (12 puntos, junto al nombre de la colonia).
- Global: 1.62 m por punto (la hoja cubre unos 2 × 1.3 km), giro de 270° con
  espejo, que es la rotación de 90° de la página.
- 125 de 144 hojas aceptadas, con error mediano de 4.5 m contra OSM (el peor,
  7.4 m). Las 19 rechazadas son de la orilla, con 0 a 7 calles con nombre.
- Control independiente: 6,315 claves de manzana rotuladas en dos hojas. Sus dos
  ubicaciones quedan a 25 m en la mediana y a 91 m en el p90; cada hoja rotula la
  parte de la manzana que le toca, así que no se espera cero.
- A la vista sobre OSM: Providencia de $7,000 a $9,800, Américas $12,660, el
  Centro cerca de $20,000, el oriente de $2,000 a $4,000 y la barranca $250.
- 415 de 442 AGEB de Guadalajara con `medv`, 432 con alguna de las dos. Spearman
  de `medv` contra `graproes`: 0.80; contra `pct_sin_secundaria`: −0.77 (en
  Boston, MEDV contra LSTAT da −0.74).

## Insumos de CHAS, RAD y AGE

Se pasan al comando como archivos; sin ellos, las columnas quedan vacías.

```bash
# Overpass, caja de la zona (sur, oeste, norte, este)
way["waterway"~"^(river|canal|stream)$"](20.30,-103.70,20.90,-103.00); out geom;   # -> agua_zmg.json
way["highway"~"^(motorway|trunk)$"](20.30,-103.70,20.90,-103.00); out geom;         # -> vias_rapidas_zmg.json
```

GHSL: `GHS_BUILT_S_E{1975,1990,2020}_GLOBE_R2023A_54009_100`, el mosaico que
cubre la zona (`R7_C9` para Guadalajara; fila y columna salen de la posición en
Mollweide, mosaicos de 1000 km desde x = −18 041 000, y = 9 000 000), en
`https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A/`.

```bash
... dataset_vivienda ... --osm-agua /app/data/osm/agua_zmg.json   --osm-vias /app/data/osm/vias_rapidas_zmg.json --ghsl /app/data/ghsl
```

Validación en la ZMG: `age` mediana de 0.99 en Guadalajara (0.98 en el Centro),
0.42 en Zapopan y 0.02 en Tlajomulco; `rad_km` mediana de 0.8 km en Zapotlanejo a
6 km en Acatlán; `chas` vale 1 en 11 % de las AGEB de Guadalajara y 36 % de las de
Tlajomulco, por sus canales.

## Pendientes de las otras columnas

- `nox`: Sentinel-5P L2 NO₂ es por órbita (NetCDF), hay que promediarlo en
  rejilla; o las estaciones del SIMAJ. Pendiente de elegir.
- `dis_km` y `rad_km` por calle: la matriz de OSRM de las zonas candidatas.
- `tax`: tablas progresivas de cada municipio (Guadalajara publica la suya en
  `transparencia.guadalajara.gob.mx/sites/default/files/TasasTarifasImpuestoPredial20.pdf`).
- `ptratio`: no hay descarga abierta por escuela (2026-11-15): el formato 911
  solo se captura en `f911.sep.gob.mx`, y `datos.jalisco.gob.mx`, que tenía la
  estadística por CCT de 2016, ya no resuelve. En Boston PTRATIO era por
  municipio, y la consulta interactiva de la SEP (`planeacion.sep.gob.mx`) da
  alumnos y docentes por municipio y nivel: es la vía, a mano, un ciclo
  (2019-2020) y los municipios de la zona. Sin sustitutos inventados.
- `medv` de Zapopan (2026) y de los otros ocho municipios.
