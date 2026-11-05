# Datos propios

Un equipo sube un archivo y lo ve como acetato en `/mapa`, sobre las mismas
láminas que las fuentes públicas, y puede cruzarlo con esas fuentes por zona.

## Qué se puede subir

| Cosa | Límite | Qué pasa al pasarlo |
|---|---|---|
| Formato | Ver la lista de abajo | Se rechaza |
| Archivo | 50 MB | Se rechaza |
| Equipo | 500 MB, sumando el tamaño de los archivos | Se rechaza; hay que borrar una capa |
| Renglones | 50,000 por archivo | Se rechaza, no se recorta |
| Zonas o geometrías que no sean punto | 10,000 por capa | Se rechaza |
| Vértices | 2,000,000 por archivo | Se rechaza |
| Ráster | 200 millones de píxeles y 50 bandas | Se rechaza antes de decodificarlo |
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

Los archivos en metros, como los de INEGI en Lambert (EPSG:6372), se reproyectan
solos si declaran su proyección. Un shapefile sin `.prj` se toma como grados y se
avisa; si en realidad eran metros, sus renglones salen como "fuera de México" y
no se dibujan en otro lado.

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

## En el mapa

La pestaña "Tus datos" abre hasta tres capas de los equipos de la persona, cada
una con su tinta. Los puntos y geometrías se dibujan como tal, y las claves como
la zona del marco. Una capa de zonas o polígonos se puede pintar por una columna
numérica, con los mismos quintiles de la coropleta del censo, y lo que no trae
dato se ve como "sin dato". Si una zona tiene más de un renglón no se pinta:
sumar o promediar dependería de qué mide la columna, y Mapo no lo sabe. Para eso
está el cruce, donde la persona lo decide.

Los datos de cada renglón no viajan con la capa: se piden al abrir su ficha. Para
dibujar, las geometrías se simplifican unos 5 m; lo guardado conserva todos sus
vértices.

Un ráster se reproyecta, se reduce a 2,048 px por lado y se guarda como imagen
pintada por quintiles. Se ve, pero no se puede consultar el valor de un píxel.

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

**CSV.** Una capa de cruce se baja con un botón, en UTF-8 con BOM para Excel. Trae
la clave, los nombres de columna de arriba y las celdas vacías donde no hay dato.
Un texto que empiece con `=`, `+`, `-` o `@` lleva un apóstrofo para que Excel no
lo ejecute. Excel le come los ceros a las claves si se abre con doble clic.

Hay un tope de 60 cruces por hora por cuenta.

## Quién puede qué

Cualquier miembro del equipo ve las capas, sube archivos, cruza y baja el CSV. Borrar es de quien la
subió y de titulares y admins. Toda lectura pasa por la membresía de quien pide,
incluida la ficha, así que una capa ajena da el mismo resultado que una que no
existe, y al salir de un equipo se pierde el acceso sin recargar.

## Qué se guarda

Solo los renglones ubicados, en `capas` y `capa_filas`, la imagen de un ráster
en `capa_rasters`, y el nombre del archivo.
El archivo original vive en la memoria de la vista entre "Leer" y "Guardar" y no
se escribe en disco. Las capas entran al respaldo nocturno como el resto de la
base. `mapo_core` recibe los renglones de un cruce en la petición y no los guarda.

Mapo avisa al subir que no es para datos personales ni confidenciales. Una
instalación que quiera recibirlos necesita antes cifrado de disco, respaldos
cifrados fuera de la máquina y registro de accesos, y no debería correr en una
computadora de uso personal.
