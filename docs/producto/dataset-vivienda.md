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
| NOX | `nox`, `nox_obs` | NO₂ troposférico medio de 2020 de Sentinel-5P en µmol/m², en la celda de 0.01° del punto de la AGEB, y cuántas observaciones lo promedian. Boston medía concentración en el aire; esto es la columna total sobre el suelo, con píxeles de unos 5 km | Hecho |
| RM | `rm`, `pct_viv_3ymas_cuartos`, `pct_viv_2ymas_dorm` | Cuartos promedio. El censo agrupa "3 o más", así que `rm` es una cota inferior y casi no varía (mediana 2.85): las otras dos columnas guardan la variación | Hecho |
| AGE | `age`, `age_1975` | Parte de la superficie construida en 2020 dentro de la AGEB que ya existía en 1990 (y en 1975), GHSL GHS-BUILT-S, 100 m. En Boston era vivienda anterior a 1940 | Hecho |
| DIS | `dis_km` | Distancia promedio a los 5 centros de empleo, ponderada por el empleo de cada uno. Hoy en línea recta; por calle con OSRM después | Hecho (línea recta) |
| RAD | `rad_km` | Distancia en línea recta a la vía rápida más cercana (OSM `motorway` y `trunk`). RAD de Boston es un índice de acceso | Hecho (línea recta) |
| TAX | `tax`, `tax_anio` | Predial anual por cada $10,000 de valor fiscal (la unidad de Boston) para una propiedad de $1,000,000, con la tabla de la ley de ingresos 2026 de cada municipio | Hecho |
| PTRATIO | `ptratio`, `ptratio_todas`, `ptratio_ciclo` | Alumnos por docente en educación básica escolarizada del municipio: públicas (como Boston) y todas. En Boston también era por municipio | Hecho (ciclo 2025-2026) |
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
| Los otros 8 de la ZMG | Tlaquepaque, Tonalá y Tlajomulco (unas 840 AGEB) no publican sus tablas en línea, y Wayback no guardó ninguna en la Biblioteca Virtual del Congreso (revisado el 2026-11-15) | Pedirlas por transparencia o buscarlas en el Periódico Oficial. Para normalizar Zapopan: no subió valores en 2020, 2021 ni 2022 (su Tesorería), y en 2025 subió 5 % |

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
   - Para `pdf_raster` (Zapopan 2026): `extraer_pdf_raster.py` hace OCR con
     RapidOCR y entrega las mismas `etiquetas` con posición en píxeles. Un número
     es valor si su letra mide al menos `--valor-desde-alto` px (Zapopan: valores
     de 85 a 100 px, manzanas de 40 a 75). Corrige las confusiones del OCR (`$` y
     `S` por 5, `O` por 0) y toma la corrida de dígitos más larga (`22$0` → 2250,
     `9/2100` → 2100). En la hoja 150 leyó 3750 y 2250; se le escaparon un 2800
     escrito en diagonal y un 2100 pegado a ruido. Recorta la leyenda de colonias
     de la derecha (`--ancho-mapa 0.80`).
   - `ubicar_pdf_mapa.py --ocr --escala-por-hoja`: el OCR pega las palabras
     (`RIOLERMA`), así que con `--ocr` las calles se emparejan por una llave
     compacta (sin espacios ni signos, con y sin el tipo de vía). Y como Zapopan
     va por zona catastral, `--escala-por-hoja` busca la escala de cada hoja con
     la misma orientación que la global.
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

## TAX: predial

En Boston TAX es una tasa por municipio. En la ZMG el predial es una **tarifa
progresiva** por tramos de valor fiscal, ((VF − LI) × T) + CF por bimestre, salvo en
Zapotlanejo, Juanacatlán y Acatlán, que cobran una tasa al millar más una cuota
fija. Por eso la tasa depende del valor, y `tax` se calcula para una propiedad de
referencia de $1,000,000: predial anual / VF × 10 000.

- **Tablas:** [`mapo_core/src/mapo_core/predial_tablas.csv`](../../mapo_core/src/mapo_core/predial_tablas.csv),
  versionadas en el repo, una fila por tramo (límite inferior, cuota fija, tasa)
  con nota donde la ley tiene una errata.
- **Fuente:** las leyes de ingresos 2026 de la Biblioteca Virtual del Congreso de
  Jalisco (`congresoweb.congresojal.gob.mx/BibliotecaVirtual/legislacion/Ingresos/Documentos_PDF-Ingresos/`,
  archivos "Ley de Ingresos del Municipio de <nombre>, Jalisco para el ejercicio
  Fiscal 2026-300126.pdf"). Las de 2020 no aparecieron: el buscador del Congreso
  da error y Wayback solo guardó la tabla de Guadalajara desde 2021, que es igual
  a la de 2026. Por eso `tax_anio` es 2026 y no el año del censo.
- **Transcripción verificada:** al extraer el texto las columnas se mezclan, así
  que cada tabla se comprobó con su propia aritmética: la cuota fija de un tramo
  es la del anterior más el ancho del tramo por su tasa. Las 7 tablas progresivas
  cuadran tramo por tramo (`test_tablas_de_predial_cuadran_tramo_a_tramo`).
- **Valores (2026):** de 13.49 (Juanacatlán) a 19.45 (Ixtlahuacán) pesos al año
  por cada $10,000; Guadalajara 15.24, Zapopan 13.87. Es 0.15 %, unas 20 veces
  menos que el 3.3 % típico del Boston de 1970.
- **Otra zona:** agregar las filas de sus municipios al CSV. Lo que no esté queda
  vacío.

## PTRATIO: alumnos por docente

No hay descarga abierta por escuela: el formato 911 solo se captura en
`f911.sep.gob.mx`, y `datos.jalisco.gob.mx` (que tenía la estadística por CCT de
2016) ya no resuelve. Pero la consulta "Principales cifras" de la DGPPyEE
(`planeacion.sep.gob.mx/principalescifras/`) da alumnos, docentes y escuelas por
municipio, y en Boston PTRATIO también era por municipio.

```bash
uv run --script scripts/vivienda/sep_cifras.py --ciclo 2025-2026 --estado 14   --municipios 002,039,044,051,070,097,098,101,120,124 --salida mapo_core/data/sep/basica_2025-2026.csv
... dataset_vivienda ... --sep /app/data/sep/basica_2025-2026.csv
```

- Es un formulario ASP.NET: el script reenvía `__VIEWSTATE` en cada paso. El
  orden importa porque cada lista reinicia a las de abajo: ciclo, escolaridad,
  nivel, control, estado y municipio.
- **Solo el ciclo vigente:** al elegir un ciclo anterior, la lista de estados
  queda vacía (probado con 2019-2020, 2020-2021 y 2024-2025 el 2026-11-15). Por eso
  `ptratio_ciclo` es 2025-2026.
- El servidor no manda su certificado intermedio: el script valida contra el
  almacén del sistema (`truststore`), sin apagar la verificación.
- Educación básica escolarizada (preescolar, primaria y secundaria). `ptratio`
  con escuelas públicas, `ptratio_todas` con públicas y privadas.
- **Valores:** Guadalajara 17.24 (227,087 alumnos y 13,205 docentes en total),
  Zapopan 20.51, Tlajomulco 25.12. Ixtlahuacán da lo mismo en públicas que en
  todas: la SEP no le registra escuelas privadas de básica.

## NOX: NO₂ de Sentinel-5P

```bash
uv run --script scripts/ambiental/no2_s5p.py --caja=-103.70,20.30,-103.00,20.90   --anio 2020 --salida ~/srv/mapo-paquetes/zmg/no2_2020.tif
... dataset_vivienda ... --no2 /app/data/no2/no2_2020.tif
```

- **Por qué satélite y no estaciones:** el SIMAJ solo cubre Jalisco y SINAICA no
  tiene descarga masiva; TROPOMI cubre todo el país igual. A cambio, mide la
  columna troposférica (todo el NO₂ sobre el suelo), no la concentración que se
  respira, y su píxel mide unos 5.5 × 3.5 km: distingue el centro de la periferia,
  no una calle de la de junto.
- **Método** (detalle en `../fuentes/imagenes.md`): órbitas L2 OFFL de 2020 del
  STAC de Planetary Computer, leídas por rangos HTTP; solo `qa_value > 0.75`;
  cada píxel se reparte en una rejilla de 0.01° por su huella real y se promedia
  el año. 406 órbitas tocan la ZMG en 2020.
- **En el dataset:** el valor de la celda donde cae el punto de la AGEB, y
  `nox_obs`, cuántas observaciones lo sostienen.

## Pendientes de las otras columnas

- `dis_km` y `rad_km` por calle: la matriz de OSRM de las zonas candidatas.
- `medv` de Zapopan (2026) y de los otros ocho municipios.
