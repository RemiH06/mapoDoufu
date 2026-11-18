# Datos propios

Un equipo sube un archivo y lo ve como acetato en `/mapa`, sobre las mismas
láminas que las fuentes públicas, y puede cruzarlo con esas fuentes por zona.

## Qué se puede subir

| Cosa | Límite | Qué pasa al pasarlo |
|---|---|---|
| Formato | Ver la lista de abajo | Se rechaza |
| Archivo | 50 MB | Se rechaza |
| Equipo | 500 MB, sumando el tamaño de los archivos (de un ráster, lo que ocupen sus valores guardados si pesan más) | Se rechaza; hay que borrar una capa |
| Renglones | 50,000 por archivo | Se rechaza, no se recorta |
| Zonas o geometrías que no sean punto | 10,000 por capa | Se rechaza |
| Vértices | 2,000,000 por archivo | Se rechaza |
| Ráster | 200 millones de píxeles y 50 bandas | Se rechaza antes de decodificarlo |
| Valores de un ráster | 16 millones de píxeles | Se reduce por vecino más cercano y se dice |
| Columnas | 100 | Se rechaza |
| Celda | 500 caracteres | Se recorta y se avisa |
| Lecturas | 30 por hora por cuenta | Hay que esperar |
| XLSX o ZIP descomprimido | 200 MB y 1,000 piezas | Se rechaza antes de abrirlo |

El tope de renglones sale del plano: 50 mil puntos se arrastran bien en canvas,
y arriba de eso el costo cae en la laptop de quien mira.

| Tipo | Formatos | Cómo se lee |
|---|---|---|
| Tabla | `.csv`, `.xlsx` | CSV con coma, punto y coma, tabulador o barra, en UTF-8, UTF-16 o Windows-1252. Del XLSX, la primera hoja |
| Vectorial | `.geojson`, `.json`, `.zip` con shapefile, `.gpkg` | Una capa; si hay más se avisa cuál. Respeta la proyección que declare el archivo |
| Ráster | `.tif`, `.tiff` | La primera banda; si hay más se avisa. Necesita proyección |

Un shapefile sin `.cpg` se lee en UTF-8 si sus registros lo son, y si no, en
Latin-1. Se prueba solo la parte de registros: el encabezado del `.dbf` trae
fecha y conteos en binario que casi nunca son UTF-8 válido. Los de CONABIO
vienen así, y leídos en Latin-1 salían como "MESÃ“FILO".

Los archivos en metros, como los de INEGI en Lambert (EPSG:6372), se reproyectan
solos si declaran su proyección. Un shapefile sin `.prj` se toma como grados y se
avisa; si en realidad eran metros, sus renglones salen como "fuera de México" y
no se dibujan en otro lado. La proyección se lee solo como WKT (`.prj`, GeoPackage)
o `EPSG:n` (GeoJSON): GDAL descarga la que venga como URL, y eso dejaría que un
archivo hiciera al servidor visitar direcciones de su red.

## Cómo se ubica cada renglón

Mapo sugiere por nombre de columna y por contenido; la persona confirma.

- **Coordenadas:** latitud y longitud en grados decimales.
- **Clave de municipio:** 5 dígitos. Si son 4, se recupera el cero que Excel le
  come a los estados 01 a 09.
- **Clave de AGEB:** los 13 caracteres de la CVEGEO, que puede terminar en
  letra. Si son 12, igual.
- **Clave partida en columnas:** estado y municipio, o estado, municipio,
  localidad y AGEB, como en los tabulados de INEGI. Cada parte recupera sus ceros.

Un archivo vectorial o ráster trae su propia ubicación y no pregunta nada. Si un
vectorial solo trae puntos, queda como cualquier capa de puntos.

Lo que no se ubica no se guarda, y al terminar se dice cuánto fue y por qué: sin
dato, coordenada que no es número, fuera de México, clave con otra forma o clave
que no está en el marco cargado. El último caso incluye las zonas de un estado
que esta instalación no ha descargado. Si no se ubica ningún renglón, no se crea
la capa.

**Números.** Una columna es numérica si todo lo que trae es número. `1,234.5`,
`12,5` y `$ 80` cuentan. `1,250` se lee como mil doscientos cincuenta aunque el
archivo use coma decimal, porque en México la coma separa miles; en coordenadas
la coma siempre es decimal. Una celda vacía queda sin dato, nunca en cero. Las
claves y los valores con ceros a la izquierda se quedan como texto.

**Fechas.** Una columna es de fecha si todo lo que trae es fecha: AAAA-MM-DD (con
hora o sin ella), DD/MM/AAAA, o AAAA-MM. Una de puros años solo si su nombre lo
dice (fecha, año, anio, year, periodo); `fecha_dato` y `fecha_consulta` aceptan
fechas parciales siempre. Se guardan en ISO (AAAA-MM-DD, con la hora si la
traían). Si todos los valores caben como día/mes y como mes/día, se toma
día/mes, como se escribe en México, y se avisa; si alguno solo cabe de una forma,
manda esa. Una fecha parcial ("2018", "2018-03") cuenta como su periodo completo:
entra en un rango si se traslapa con él.

## En el mapa

La pestaña "Tus datos" abre hasta tres capas de los equipos de la persona, cada
una con su tinta. Los puntos y geometrías se dibujan como tal, y las claves como
la zona del marco. Una capa de zonas o polígonos se puede pintar por una columna
numérica, con los mismos quintiles de la coropleta del censo, y lo que no trae
dato se ve como "sin dato". Si una zona tiene más de un renglón no se pinta:
sumar o promediar dependería de qué mide la columna, y Mapo no lo sabe. Para eso
está el cruce, donde la persona lo decide.

Una capa de puntos o geometrías con columnas de fecha trae un rango (desde,
hasta) para ver solo esos renglones; si el rango está al revés, no cambia nada.
En una capa por zona no hay rango: filtrar renglones cambiaría lo que se pinta
por zona sin decirlo.

Los datos de cada renglón no viajan con la capa: se piden al abrir su ficha. Para
dibujar, las geometrías se simplifican unos 5 m; lo guardado conserva todos sus
vértices.

Un ráster se guarda dos veces. Para verlo, reproyectado, reducido a 2,048 px por
lado y pintado por quintiles. Para consultarlo, los valores de su primera banda
en grados (EPSG:4326), en teselas de 256 x 256 de PostGIS raster, hasta 16
millones de píxeles: unos 18 m por píxel en una caja de 70 km. Si el archivo
trae más, se reduce por vecino más cercano, que no inventa valores, y el método
dice cuánto. Un clic sobre el ráster en `/mapa` da el valor del píxel, la
descripción de la banda si el GeoTIFF la trae (ahí va la escala: "LST °C × 100")
y el lado del píxel. Un ráster subido antes del 2026-11-18 solo tiene la imagen,
y la ficha pide subirlo otra vez.

Las teselas las arma `mapo_core` con el formato binario de PostGIS (WKB), que ya
abre el GeoTIFF con el driver fijo. Postgres no abre con GDAL ningún archivo que
haya subido alguien. Sin nodata declarado, o con uno que no cabe en el tipo de la
banda (un -9999 en 8 bits), los valores pasan a un tipo más ancho y su mínimo
marca el hueco, para que ningún valor real, ni el 0, se pierda.

## Cruce con fuentes públicas

Desde "Cruzar" en la lista de capas. Se cruzan capas de puntos, por municipio o
por AGEB. Una capa de geometrías o ráster no: un polígono puede caer en varias
zonas, y repartirlo pediría una regla inventada.

**Nivel.** Puntos y AGEB se agregan por AGEB urbano o por municipio. Una capa por
municipio solo por municipio. Un punto pertenece a una sola zona, aunque caiga en
la frontera. Lo que no cae en ninguna, como un punto rural a nivel AGEB, no se
cuenta y se dice cuántos fueron.

**Zonas.** Salen todas las del nivel de arriba que la capa toca: todos los AGEB
de sus municipios, o todos los municipios de sus estados. Una zona sin renglones
lleva `renglones` en cero y sus agregados vacíos. El cero dice que la capa no trae
nada ahí. El tope son 10,000 zonas.

| Columna | Sale de | Nombre |
|---|---|---|
| Renglones | Siempre | `renglones` |
| Columna numérica de la capa | Suma, promedio o mediana, a elección. Las celdas vacías no cuentan | `ventas_suma` |
| Censo 2020 | Tal como lo publica INEGI para ese nivel. A nivel municipio, su renglón propio, con población rural. Lo reservado queda vacío | `pobtot` |
| Negocios de DENUE | Todos o de un rubro, por la clave que trae cada negocio. Quien no empata con un AGEB cuenta solo para el municipio | `negocios_denue`, `negocios_taqueria` |
| Minutos al negocio del rubro más cercano | La matriz de las zonas candidatas. Solo por AGEB, con un rubro y hasta 2,000 AGEB. Sin OSRM, línea recta, y se avisa | `minutos_taqueria` |

Cada cifra queda en su columna y nada se pondera: no hay puntaje. Junto al
resultado se dice cómo se calculó cada columna.

**Resultado.** Se revisa antes de guardarlo, con las primeras 20 zonas. Guardado es
una capa por zona: se pinta por columna en `/mapa`, abre su ficha, sigue los mismos
permisos y cuenta contra la cuota del equipo. No se actualiza si cambia la capa de
origen, y borrar el origen no la borra.

**CSV.** Una capa de cruce o de distancias se baja con un botón, en UTF-8 con BOM
para Excel. Trae la clave (o latitud y longitud, si son puntos; una geometría no
cabe en una celda), los nombres de columna de arriba y las celdas vacías donde
no hay dato.
Un texto que empiece con `=`, `+`, `-` o `@` lleva un apóstrofo para que Excel no
lo ejecute. Excel le come los ceros a las claves si se abre con doble clic.

Hay un tope de 60 cruces por hora por cuenta.

## Distancia entre capas

Desde "Distancia" en una capa de puntos o geometrías: de cada renglón al más
cercano de otra capa del mismo equipo. Responde preguntas como "qué escuelas
tienen una parcela agrícola a menos de 300 m" sin repartir nada entre zonas.

**Qué se mide.** Metros en línea recta sobre el elipsoide WGS84, de borde a
borde: 0 si se tocan o uno contiene al otro. El más cercano se busca en dos
pasos, porque un grado de longitud mide menos que uno de latitud y el más
cercano en grados no siempre lo es en metros: el índice da un candidato, su
distancia en metros acota una caja, y dentro de la caja gana el de menos
metros. Si dos empatan, gana uno de ellos.

**Localidades del censo.** Además de las capas del equipo, el destino puede ser
"Localidades del censo 2020": las 189,432 del país (todas, rurales o urbanas), con
la población a cierto radio. Ver `../fuentes/localidades.md`.

**Filtros.** Hasta dos condiciones por capa, que se cumplen las dos: la columna
contiene el texto, sin importar mayúsculas ni acentos. Si la capa tiene fechas,
además un rango (por ejemplo, focos de calor de una zafra: del 2024-11-01 al
2025-05-31). Una barra separa
alternativas dentro de una condición (`039|120`). Así, "clase contiene
educación y municipio contiene 039|120" deja las escuelas de Guadalajara y
Zapopan.

**Resultado.** Una capa nueva con la geometría completa del origen, sus
columnas y las nuevas, nombradas por la capa de destino:

| Columna | Qué es |
|---|---|
| `distancia_m_<destino>` | Metros al más cercano, redondeados |
| `<destino>_<columna>` | La columna que nombra al más cercano, y su `fuente` y `fecha_dato` si las trae |
| `<destino>_a_<radio>m` | Si se pide un radio: cuántos renglones del destino quedan a esa distancia o menos |

Antes de guardar se ven los 20 más cercanos y cuántos quedan dentro del radio.
Junto al resultado va cómo se calculó: capas, filtros, columnas y fecha del
cálculo. Nada se pondera. Hay un tope de 60 mediciones por hora por cuenta.

**Límites.** La distancia es tan precisa como las capas: un mapa 1:250 000,
como el de uso de suelo de INEGI, puede desviarse cientos de metros en sus
bordes, así que no sirve para afirmar 300 m. Cercanía no dice causa: el texto
dice "a 240 m de", nunca "expuesto a".

## Valor de un ráster

Desde "Ráster" en una capa de puntos o geometrías, si el equipo tiene algún
ráster con valores. Con los mismos filtros que la distancia.

| Desde | Sin radio | Con radio |
|---|---|---|
| Puntos | `<ráster>_valor`: el píxel donde cae el punto | Resumen de los píxeles a esa distancia o menos |
| Polígonos | Resumen de los píxeles adentro | Resumen de los píxeles a esa distancia del borde o adentro |

El resumen es `<ráster>_promedio`, `_min`, `_max` y `_pixeles` (cuántos
entraron). Un píxel entra si su centro cae en la zona; el sin dato no entra, y si
no entra ninguno, todo queda vacío. Para un ráster de clases, como WorldCover, el
promedio no dice nada: se piden valores ("40", o "10|20") y sale
`<ráster>_parte_40`, la parte de los píxeles con esos valores, de 0 a 1.

Los valores salen con la escala del archivo: si la banda es NDVI × 10000, el
promedio también. El resultado se guarda como capa, igual que la distancia, y
comparte con ella el tope de 60 cálculos por hora.

Las teselas se eligen por su caja (`ST_ConvexHull(rast) && zona`, con índice) y no
con `ST_Intersects`, que revisa cada tesela píxel por píxel: con 266 teselas eso
costaba 100 ms por renglón. Así, 113 círculos de 300 m sobre píxeles de 17 m
tardan 4 s.

## Procedencia

Seis columnas reservadas dicen de dónde sale cada renglón: `fuente`, `url`,
`fecha_dato`, `fecha_consulta`, `nivel` (registro oficial, prensa, testimonio)
y `verificado`. Si el archivo las trae, la ficha las muestra aparte, bajo
"Procedencia", y la `url` es liga solo si empieza con `http://` o `https://`.
Es el mismo esquema que el modo investigación de Bentos, para que un archivo
sirva a los dos. Mapo no las llena ni las revisa: son del archivo.

## Quién puede qué

Cualquier miembro del equipo ve las capas, sube archivos, cruza y baja el CSV. Borrar es de quien la
subió y de titulares y admins. Toda lectura pasa por la membresía de quien pide,
incluida la ficha, así que una capa ajena da el mismo resultado que una que no
existe, y al salir de un equipo se pierde el acceso sin recargar (abrir, repintar
y la ficha vuelven a preguntar).

## Qué se guarda

Solo los renglones ubicados, en `capas` y `capa_filas`, la imagen de un ráster
en `capa_rasters` y sus valores en `capa_raster_teselas`, y el nombre del archivo.
El archivo original vive en la memoria de la vista entre "Leer" y "Guardar" y no
se escribe en disco. Las capas entran al respaldo nocturno como el resto de la
base. `mapo_core` recibe los renglones de un cruce en la petición y no los guarda.

Mapo avisa al subir que no es para datos personales ni confidenciales. Una
instalación que quiera recibirlos necesita antes cifrado de disco, respaldos
cifrados fuera de la máquina y registro de accesos, y no debería correr en una
computadora de uso personal.
