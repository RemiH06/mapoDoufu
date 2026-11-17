# Pipeline de datos: dónde se rompe

Mapo arma datasets con fuentes públicas que nadie diseñó para leerse por
máquina. Todo lo de esta página se encontró con datos reales al armar el dataset
de vivienda (`dataset-vivienda.md`) y el paquete ambiental
(`../fuentes/ambientales.md`, `../fuentes/imagenes.md`) en noviembre de 2026.

Cada punto es un supuesto que hoy se cumple y que un pipeline automático no debe
dar por hecho. Para cada uno: qué pasa, cómo se detecta sin una persona y qué
hacer. La regla general: **un paso que no puede comprobar su resultado debe
fallar en voz alta**, no dejar un vacío silencioso ni un número plausible y falso.

## Obtener

| Fuente | Qué pasa | Cómo se detecta | Qué hacer |
|---|---|---|---|
| Catastro de Guadalajara | `catastro.guadalajara.gob.mx` no responde (desde Aerilate ni desde Pixilate, 2026-11-15) | Conexión rechazada o tiempo agotado | Wayback: `archive.org/wayback/available?url=...` y bajar con `id_` en la URL (sin la barra de Wayback). Anotar la fecha de la copia |
| Wayback | Descarga truncada: la primera bajada del PDF de GDL se cortó en 1 MB exacto | Tamaño contra el `length` del CDX, o el PDF no abre | `curl -C -` para reanudar; comparar tamaño o sha256 |
| Wayback | "Temporarily Offline" con código 200 y una página HTML | El archivo empieza con `<html` o `<!DOCTYPE` | Revisar los primeros bytes de todo lo descargado (`scripts/crudos-ambientales.sh` ya lo hace) |
| Transparencia de Guadalajara | Responde una página HTML en vez del PDF a clientes que no son navegador | Primeros bytes no son `%PDF` | Wayback (`TasasTarifasImpuestoPredial21.pdf` sí está) |
| Biblioteca Virtual del Congreso de Jalisco | Sin listado de carpeta (403) y el buscador `ingresos.cfm` da error de ColdFusion. Los archivos llevan un sufijo con la fecha de carga (`-300126`) que no se puede adivinar para otros años | 403, 404 | Probar el sufijo conocido del año; si falla, buscar el nombre exacto en un buscador. Guardar la URL encontrada en el registro de fuentes |
| Leyes de ingresos 2020 | No aparecieron en línea para la ZMG; las de 2026 sí | — | Usar el año disponible común a todos los municipios y decirlo (`tax_anio`) |
| `info.jalisco.gob.mx/.../leyes/<municipio>_<año>.pdf` | El patrón existió hasta 2013; ya no | 404 en todos | No depender de él |
| `datos.jalisco.gob.mx` | El dominio ya no resuelve | Error de DNS | Fuente perdida; buscar el dato en la dependencia federal |
| Zapopan, bucket de geomática | Lista pública y nombres de archivo que cambian cada año (`tablasvalor/` contra `tablasvalor/2026/`, con y sin acentos) | Listar el bucket (`?prefix=`) antes de bajar | Elegir por patrón, no por nombre fijo |
| Overpass | 502 y 504 cuando está saturado, con el cuerpo en texto | Cuerpo que no empieza con `{` | Reintentos con espera creciente (20, 40, 80 s…) o un espejo |
| Planetary Computer | Las URL firmadas caducan en cerca de una hora, y odc-stac firma al armar el cálculo (`patch_url`), no al leer: una mediana de una hora pierde lo que lee al final | `WarpOperationError` a los ~50 min; o, con `fail_on_error=False`, un hueco sin aviso (22 % del primer compuesto de Autlán) | Bloques que se calculan en minutos, `fail_on_error=True` con reintentos, y medir el porcentaje sin dato del producto final. Mirar una vista en color: la cifra de sin dato no ve un archivo sin `nodata` declarado |
| SEP, Principales cifras | El servidor no manda su certificado intermedio | `CERTIFICATE_VERIFY_FAILED` en Python (curl en Windows sí pasa) | Validar contra el almacén del sistema (`truststore`). Nunca `verify=False` |
| SEP, Principales cifras | Solo abre por municipio el ciclo vigente; con un ciclo anterior la lista de estados queda vacía | Lista `DDLEntidad` con una sola opción | Usar el ciclo vigente y guardar `ptratio_ciclo`. Para series, bajar cada año mientras está vigente |
| SEP, Principales cifras | Formulario en cascada: cada lista reinicia a las de abajo | El encabezado del resultado dice "ENTIDAD: TODAS" aunque se eligió una | Orden fijo: ciclo, escolaridad, nivel, control, estado, municipio. Comprobar el encabezado del resultado |
| Base de producción | Leerla desde una sesión de agente pide permiso explícito | — | Usar la base de desarrollo, que tiene los mismos datos cargados |

## Leer

| Fuente | Qué pasa | Cómo se detecta | Qué hacer |
|---|---|---|---|
| Tablas de valores en PDF | Un municipio publica mapas vectoriales (GDL 2020) y otro un escaneo (Zapopan 2026: JPEG por hoja, sellos encima, sin texto) | Contar spans de texto por página: un escaneo solo tiene el encabezado | Adaptador por formato (`pdf_mapa`, `pdf_raster`), declarado en `scripts/catastro/fuentes.csv` |
| Tablas de valores escaneadas (OCR) | El OCR confunde `5` con `$` o `S` y `0` con `O`, pega ruido a los números (`9/2100`) y pega las palabras (`RIOLERMA`); los textos en diagonal se le escapan | Valores fuera de 3 a 6 cifras; calles que no empatan | Tabla de confusiones, corrida de dígitos más larga, llave de calle compacta. Contar cuántos valores salen por hoja y revisar las que den cero |
| Tablas de valores escaneadas (OCR) | El separador de miles parte los números ("38,400" quedaba en 400) y los números de manzana con cero a la izquierda ("080") parecen valores | Muchos valores bajos donde el mapa dice lo contrario | Quitar el separador antes de leer; un número que empieza en 0 es clave. Reglas en `clasificar()`, que `--reclasificar` vuelve a aplicar sin repetir el OCR |
| Tablas de valores escaneadas (OCR) | Números de manzana sin cero a la izquierda ("551") con letra tan grande como un valor | Proporción de múltiplos de 50: 91 % en valores reales, 8.5 % en los menores de 1,000 | `--valores-validos 100,50000,50` en `ubicar_pdf_mapa.py` |
| Tablas de valores, Zapopan | Los números de manzana se repiten en cada zona: no sirven para comparar hojas | — | Sin control por claves; solo el error contra OSM |
| Tablas de valores, años | Los aumentos anuales de cada municipio no se publican completos | — | No normalizar con un factor incompleto; año nominal y efecto fijo por municipio al modelar |
| RapidOCR | `opencv-python` pide `libGL`, que un servidor sin escritorio no tiene | `ImportError: libGL.so.1` | Sustituirlo por `opencv-python-headless` con `override-dependencies` de uv, sin instalar paquetes del sistema |
| Tablas de valores, GDL | El tamaño de letra distingue valor de zona (12 pt) y de calle (7.9 y 6 pt; 6 en el Centro por densidad) | Histograma de tamaños de las etiquetas de valor | El umbral es propio de cada atlas (`--zona-desde-tamano`); revisarlo con cada edición nueva |
| Tablas de valores, GDL | Valor y calle en el mismo span (`$ 2530 PASEO DE LOS LEONES`); claves de manzana pegadas (`D66A0922D66A0923`) | — | Separar por patrón en la extracción |
| Leyes de ingresos | Al extraer el texto, las columnas de las tablas del predial se mezclan y la tasa queda desplazada un renglón | La aritmética no cuadra: la cuota fija de un tramo debe ser la del anterior más el ancho por la tasa | Verificar cada tabla con esa regla (`test_tablas_de_predial_cuadran_tramo_a_tramo`) |
| Leyes de ingresos | Erratas en la ley misma: Ixtlahuacán empieza un tramo en 820,936.01 tras uno que acaba en 820,933.00; Tlaquepaque escribe `10.410.87`; Acatlán imprime "25%" en la columna "al millar" | La regla de continuidad, y tasas fuera de rango | Transcribir lo que dice la ley, anotar la lectura en la columna `nota` |
| Leyes de ingresos | La primera tabla con "Límite inferior" no siempre es la del predial: en Juanacatlán y Zapotlanejo es la de transmisiones patrimoniales; en Ixtlahuacán, la de incentivos por empleo | — | Anclar en la sección "Del Impuesto Predial" y en "se causará" |
| Leyes de ingresos | Dos formas: tarifa progresiva por tramos, o tasa al millar con cuota fija | — | Columna `tipo` en `predial_tablas.csv` |
| Censo 2020 | Las `VPH_*` se cuentan sobre `VIVPARH_CV`, no sobre `VIVPAR_HAB`: con el segundo, 5 % de las AGEB pasan de 100 % | Porcentajes mayores que 100 | Denominador correcto, y una prueba de rango |
| Censo 2020 | `*` es dato reservado y `N/D` no disponible | — | Vacío, nunca cero |
| Censo 2020 | Los cuartos se agrupan en "3 o más" | `rm` casi constante | Columnas de proporción además del promedio |
| DENUE | `cve_ageb` viene vacío a veces | — | Asignar la AGEB por geometría |
| RETC | El encabezado está entre los renglones 7 y 10 según el año; coordenadas como texto `20°41'27"`; columnas distintas por año | — | Buscar el renglón que dice latitud; parser de grados, minutos y segundos |
| REPDA | Coordenadas en seis columnas de grados, minutos y segundos, longitud sin signo; el CSV viene en UTF-8 y un nombre de archivo trae una Á mal codificada | Longitudes positivas | Negar la longitud en México; buscar el archivo por prefijo |
| ITER | Coordenadas `104°21'48.123" W`; renglones de totales (`LOC` 0, 9998, 9999) | — | Quitar totales antes de sumar |
| Defunciones | El archivo de datos cambia de carpeta según el año (2023 no usa `conjunto_de_datos/`) | — | Tomar el miembro más grande del zip |
| PTAR de Conagua | Sin coordenadas y en cp850 | Caracteres como `¢` en vez de `ó` | Empatar por nombre de municipio normalizado |
| RENAMECA | Cada fila resume 2012 a 2025: no es serie de tiempo | Columna `AÑO` con un rango | Decirlo en el diccionario |
| OSM, parques | `leisure=nature_reserve` incluye reservas de miles de hectáreas (La Primavera, 30,415 ha) | Parques de 313 ha en un círculo de 314 | Separar parques urbanos de reservas |
| OSM, transporte | Cada red etiqueta sus estaciones distinto; Mi Macro Calzada solo como andenes de su relación de ruta, y `network=Mi Macro` aparece en más de mil paradas comunes | Conteo de estaciones por red contra el número real (27 en Calzada) | Estaciones por red más andenes de relaciones de ruta (`scripts/vivienda/transporte_masivo.py`) |
| Sentinel-2 mensual en temporal de lluvias | De junio a octubre quedan de 2 a 8 % sin dato aunque nada falle: hay días nublados sin escena limpia | Aviso de hueco solo en meses de lluvia, en manchas, no en franjas | Es nubosidad, no error: decirlo; usar compuestos de varios meses si hace falta cobertura |
| GeoPackage | No distingue mayúsculas en nombres de campo (`LONGITUD` y `longitud` chocan) | `FieldError` al escribir | Nombres distintos (`lon_dec`) |
| Sentinel-2 | Desde la línea base 04.00 (enero de 2022) ESA suma 1000 a la reflectancia | Saltos en NDVI en 2022 | Restar por escena según `s2:processing_baseline` |
| TROPOMI | Valores de relleno (9.97e36) y píxeles con nubes | `qa_value` | Solo `qa_value > 0.75`; descartar el relleno |

## Ubicar y calcular

| Paso | Supuesto | Cómo se comprueba | Si falla |
|---|---|---|---|
| Georreferencia de hojas (`ubicar_pdf_mapa.py`) | Todas las hojas del atlas comparten escala y orientación | Error mediano por hoja contra OSM y escala dentro de 10 % de la global (`hojas.csv`) | La hoja no se acepta; sus valores no entran |
| Emparejar calles con OSM | Los nombres coinciden tras normalizar (sin acentos, sin tipo de vía, abreviaturas expandidas) | Inliers por hoja | Ampliar la tabla de abreviaturas; las hojas de orilla con pocas calles quedan fuera |
| OSM | Es una foto del día de la descarga; las calles cambian | — | Guardar la fecha (`osm3s.timestamp_osm_base`) |
| Control de la georreferencia | Las claves de manzana repetidas en dos hojas marcan el mismo lugar | `control.csv`: mediana 25 m en GDL | Una clave puede rotularse dos veces en la misma hoja: comparar la ocurrencia más cercana |
| MEDV | Un valor de zona representa la AGEB donde cae | `medv_n` | Nunca rellenar con vecinas; `medv_metodo` dice por qué falta |
| Años | Censo 2020, predial 2026, escuelas 2025-2026, MEDV de GDL 2020 y de Zapopan 2026 | Columnas `*_anio` y `*_ciclo` | Deflactar antes de mezclar valores en pesos de años distintos |
| Imágenes | Una mediana de pocas escenas despejadas basta | Celdas sin dato en el resultado | Elegir por mosaico MGRS, no las más despejadas en total: si no, un mosaico se queda sin escenas |

## Herramientas locales

- **Git Bash** convierte `/app/data/...` en una ruta de Windows al pasarla a
  `docker compose exec`: anteponer `MSYS_NO_PATHCONV=1`.
- **argparse** toma `-104.65` como una opción: escribir `--caja=-104.65,...`.
- **pdftotext** de Git Bash es xpdf 4 y no tiene `-bbox`: usar PyMuPDF.
