# Fuentes ambientales (en crudo, sin cargar)

Descargadas el 2026-11-13 para la sesión 22. No hay tabla en la base: se
usan recortándolas a una zona con `scripts/ambiental/recorte.py` (sección
"Recorte por zona"). Abajo, el inventario y lo revisado en los archivos
reales.

## Cómo se bajan

`scripts/crudos-ambientales.sh scripts/crudos-ambientales.tsv [destino]`.
El destino por omisión es `~/srv/mapo-crudos/ambiental/`, fuera del
repo y fuera de los volúmenes de la base. El script se puede relanzar:
salta lo que ya está y reanuda lo que quedó a medias. Deja
`MANIFIESTO.tsv` (archivo, bytes, sha256, fecha, url) y `FALLAS.tsv`.
Detecta los servidores que responden 200 con una página HTML en vez del
archivo. Primera corrida: 136 archivos, 3.1 GB, una sola falla (un
mosaico de relieve que cae en el mar).

Las páginas de INEGI arman sus ligas con JavaScript y no dan URL fija.
Uso de suelo, edafología, ANP y regiones hidrológicas se bajan de las
copias que publica el geoportal de CONABIO.

## Qué hay

| Carpeta | Fuente | Contenido revisado |
|---|---|---|
| `agua` | Conagua, RENAMECA | Superficial: 5,033 sitios. Subterránea: 2,875. Con latitud y longitud. Superficial: DBO, DQO, SST, coliformes fecales, E. coli, enterococos, oxígeno disuelto, toxicidad (Daphnia y Vibrio) y semáforo. Subterránea: alcalinidad, conductividad, SDT, fluoruros, dureza, coliformes, nitratos, As, Cd, Cr, Hg, Pb, Mn, Fe. **No mide plaguicidas.** Cada fila resume 2012 a 2025 (columna `AÑO` = `2012-2025`): no es serie de tiempo. Para una serie hacen falta los cortes por año (hay uno de 2021) |
| `agua` | Conagua | Cuerpos de agua (shapefile, 206 MB), plantas de tratamiento y potabilizadoras, estaciones hidrométricas, distritos de riego, coberturas de agua y drenaje |
| `acuiferos` | Conagua | Polígonos de los 653 acuíferos con la disponibilidad del 2023-11-09, la de 2020 para comparar, vedas y ordenamientos, red piezométrica 2022 y 2023 (puntos), estudios por acuífero |
| `concesiones` | Conagua, REPDA | Títulos, aprovechamientos superficiales y subterráneos, **descargas residuales** (33,807, con volumen, procedencia, cuerpo receptor y coordenadas en grados, minutos y segundos), zonas federales, obras. El CSV viene en UTF-8 |
| `emisiones` | SEMARNAT, RETC | Un Excel por año, 2004 a 2022, con latitud y longitud por establecimiento, SCIAN y actividad. El encabezado no está en el primer renglón: hay que buscarlo |
| `clima` | Conagua | Viento por estación: **solo una ventana corta de 2023 cada 10 minutos**, no hay historia. El histórico sale de ERA5 (sección "Viento") |
| `riesgo` | SMN, Conagua | Monitor de Sequía por municipio (histórico en `MunicipiosSequia.xlsx`), zonas inundables (PDF, sin vector), vulnerabilidad por municipio de Conagua (índices compuestos: mostrar sus componentes) |
| `territorio` | INEGI vía CONABIO | Uso de suelo y vegetación 1:250 000 series VI y VII (para ver cambio), edafología, ANP 2020, regiones hidrológicas |
| `agricultura` | SIAP | Cierre agrícola municipal 2003 a 2025: cultivo, ciclo, modalidad (riego o temporal), superficie sembrada, cosechada y siniestrada, volumen, valor |
| `agricultura` | SIAP, frontera agrícola serie II | Polígonos de superficie agrícola a escala 1:10 000, sobre imágenes SPOT 5 de 2010 y 2011 (publicada 2013-2014), con riego o temporal y su CADER. Ver "Frontera agrícola" |
| `incendios` | NASA FIRMS | Focos de calor de México: MODIS 2000 a 2025 y VIIRS S-NPP (375 m) 2012 a 2025, con fecha, hora, confianza y potencia radiativa |
| `salud` | INEGI | Defunciones registradas 2020 a 2023 (microdatos con municipio y causa CIE-10). Otros años usan otra ruta |
| `poblacion` | INEGI | ITER 2020 de Jalisco: localidades, también las rurales. Censo 2020 por manzana de Jalisco (`manzanas_14_2020.zip`, 102,734 manzanas urbanas, ~220 variables, latin-1) |
| `relieve` | Copernicus DEM GLO-30 | Mosaicos de 30 m que cubren Jalisco |

## Recorte por zona

Las fuentes no entran a la base de Mapo: se recortan a la zona de estudio y
salen como paquete para SIG. Sirve para cualquier parte del país; lo único
que cambia son la caja y los municipios.

```bash
# 1. Lo que ya está en la base de Mapo (AGEB con su censo y DENUE)
scripts/ambiental/desde_mapo.sh SALIDA OESTE SUR ESTE NORTE [CONTENEDOR BASE USUARIO]
# 2. Las fuentes en crudo
uv run --script scripts/ambiental/recorte.py --crudos ~/srv/mapo-crudos/ambiental   --salida SALIDA --caja=OESTE,SUR,ESTE,NORTE --municipios 14015,14037
```

`--caja=` va con signo igual: sin él, argparse toma la longitud negativa como
una opción. La caja recorta todo lo que trae coordenadas; los municipios
filtran lo que solo viene por municipio (SIAP, sequía, defunciones, plantas de
tratamiento) y suman sus localidades aunque caigan fuera de la caja.

Salida:

| Archivo | Contenido |
|---|---|
| `zona.gpkg` | Una capa por fuente, en EPSG:4326 |
| `tablas/*.csv` | SIAP, sequía, defunciones y PTAR de los municipios pedidos |
| `relieve.tif` | Copernicus GLO-30 recortado (mosaico de los cuadros que toca la caja) |
| `diccionario_capas.csv` | Por capa: archivo, filas, fuente, `fecha_dato` (AAAA, AAAA-MM o AAAA-MM-DD; el final si es un periodo; vacía si no se sabe), `fecha_texto` con el detalle, nivel geográfico, URL y nota |
| `zona.txt` | Caja, municipios, CRS, fecha, comando completo y sha256 del script |
| `procedencia.csv` | Por capa: archivo crudo, su sha256, fecha de descarga y URL (de `MANIFIESTO.tsv`) |

Las imágenes (`../fuentes/imagenes.md`) dejan su propio
`procedencia_imagenes.csv`. Cómo rehacer todo para otra zona y subirlo a Mapo:
`../guias/replicar.md`.

Lo que hace con cada formato, por si cambia en la siguiente descarga:

- **RENAMECA:** primera hoja del Excel, `LATITUD` y `LONGITUD` decimales.
- **REPDA:** coordenadas en grados, minutos y segundos en seis columnas; la
  longitud viene sin signo y se vuelve negativa. El uso del título sale de
  `CONCESIONES.csv`; `TITULAR` se omite porque puede ser una persona.
- **RETC:** un Excel por año con el encabezado en el renglón 7 a 10 (se busca el
  que dice latitud) y coordenadas como texto `20°41'27"`. Las columnas cambian
  entre años: se unen por nombre normalizado y queda la columna `anio`.
- **ITER:** coordenadas como `104°21'48.123" W`. GeoPackage no distingue
  mayúsculas, así que las decimales van en `lon_dec` y `lat_dec`. Se quitan los
  renglones de totales (`LOC` 0, 9998 y 9999).
- **Defunciones:** el archivo de datos cambia de carpeta según el año (2023 no
  usa `conjunto_de_datos/`): se toma el miembro más grande del zip.
- **PTAR:** sin coordenadas y en cp850. Se empata por nombre de municipio
  normalizado.
- **Vectoriales** (Conagua, INEGI, CONABIO): la caja se transforma al CRS de cada
  capa para filtrar al leer, y luego se recorta exacto en 4326.

**Zona rural:** Mapo solo carga AGEB urbanas (`geo-censo.md`), así que el recorte
pide al API de INEGI (`wscatgeo/v2/geo/agebr/{ent}/{mun}` y
`geo/localidades/pol/{ent}/{mun}/R|U`, marco de diciembre de 2025) las AGEB rurales
y los polígonos de las localidades con manzanas, para los municipios con alguna
localidad dentro de la caja. El censo por AGEB no existe en zona rural: a cada
AGEB rural se le suma la población de las localidades del ITER que caen dentro
(`pobtot_iter`, `vivhab_iter`, `localidades_iter`). Las rancherías sin manzanas no
tienen polígono y siguen como puntos en `localidades`. La guía del API con todas
sus rutas está en `inegi.org.mx/servicios/catalogounico.html`.

**Manzanas:** el mismo API da sus polígonos por municipio
(`geo/mza/{ent}/{mun}`, con población y viviendas habitadas; Tlaquepaque: 7,637
manzanas, 6 MB, unos 12 vértices cada una). `geo/mza/{ent}/{mun}/{loc}/{ageb}` no
funciona: responde 404 aunque la AGEB exista. El recorte les une las ~220 variables
del censo 2020 por manzana (`c_*`) por la clave de 16 dígitos. El censo por manzana
solo cubre manzanas urbanas, y INEGI reserva con `*` los valores de manzanas con
pocas viviendas: no es cero.

Validación (zona del CP 45615, Tlaquepaque, 2026-11-17): 7,949 manzanas en la caja,
7,350 con renglón del censo; las 599 sin renglón son rurales o del marco de 2025
con clave nueva. La población del API y la del censo por manzana coinciden en el
100 % de las manzanas. En las 230 AGEB que caben enteras en la caja, la suma por
manzana da 552,100 contra 552,644 del censo por AGEB (99.9 %); 12 AGEB difieren
más de 1 %.

## Viento

Las estaciones de Conagua solo publican días recientes, así que el histórico sale
del reanálisis ERA5 de ECMWF, servido por el API de archivo de Open-Meteo (sin
cuenta; datos CC BY 4.0, uso libre no comercial del API). El recorte deja
`tablas/viento_horario.csv` (2015 a 2024, hora local, velocidad, ráfaga y
dirección de donde viene) y `tablas/viento_climatologia.csv` (por mes y hora:
velocidad media y p90, calma, dirección resultante, constancia y frecuencia por
rumbo).

ERA5 tiene celdas de 0.25° (~28 km): describe el régimen de la zona, no el viento
entre edificios ni el efecto de un cerro. ERA5-Land (0.1°) no trae viento en ese
API. Para un pipeline de producción conviene bajar ERA5 del Climate Data Store de
Copernicus (cuenta gratuita) en vez de depender del API.

**Lo que se repite en la ZMG** (celda 20.5, -103.25; 2015 a 2024, 87,672 horas):

- **Secas (febrero a mayo):** viento del oeste y suroeste, constante (resultante
  entre media de 0.7 a 0.85) y más fuerte en la tarde y la noche (2.5 m/s de 18 a
  24 h, 5 % de calma). Es lo más estable del año.
- **Lluvias y frío (junio a enero):** variable. Mañanas del este, tardes del
  oeste, y de 24 % a 41 % de horas en calma (julio el más quieto).
- **Mañanas de frío:** 39 % de calma de 6 a 12 h, cuando las inversiones térmicas
  atrapan contaminantes.
- **Entre años:** media de 1.54 a 1.70 m/s de 2015 a 2024; no hay tendencia.

Lo útil para Mapo es la climatología por mes y hora (una tabla pequeña por celda,
cubre todo el país), no la serie horaria.

### Validación: Autlán y El Grullo (2026-11-15)

Caja -104.65, 19.55, -103.95, 20.05; municipios 14015 y 14037.

- Población del ITER: Autlán de Navarro 64,931 y El Grullo 25,920, las cifras
  del censo 2020.
- 181 localidades de los dos municipios y 209 vecinas dentro de la caja.
- Zona rural: 65 AGEB rurales y 88 localidades con polígono. Población urbana por
  AGEB más la rural sumada del ITER: Autlán 52,019 + 12,912 = 64,931 y El Grullo
  22,738 + 3,182 = 25,920, exacto contra el censo.
- 653 focos VIIRS en 2024, lo mismo que la revisión a mano del 2026-11-13.
- RETC: 15 reportes de establecimientos dentro de la caja; REPDA: 12 descargas
  residuales. (Los nombres y giros no van aquí: `docs/` es pública y no señala
  empresas.)
- 0 sitios subterráneos de RENAMECA y 0 pozos piezométricos en la caja: no es
  error, la red no tiene puntos ahí.

## Marginación (CONAPO)

Índices de marginación 2020 de CONAPO, bajados de
https://www.gob.mx/conapo/documentos/indices-de-marginacion-2020-284372:

| Archivo | Qué es |
|---|---|
| `marginacion/imc_2020_colonias_shp.zip` | 74,226 colonias con polígono (Lambert ITRF 2008), nombre, CP, población estimada, componentes, índice y grado |
| `marginacion/imc_2020_colonias.zip` | La misma tabla en Excel |
| `marginacion/imu_2020_ageb.zip` | Por AGEB urbana, con la CVEGEO de 13 caracteres |

Es un índice compuesto, y en Mapo nunca hay puntaje único: el recorte lo entrega
con sus once componentes, porcentajes del censo 2020 que se leen por separado
(`P6A14NAE` de 6 a 14 años que no va a la escuela, `SBASC` sin educación básica,
`PSDSS` sin servicios de salud, `OVSDE` sin drenaje, `OVSEE` sin electricidad,
`OVSAE` sin agua entubada, `OVPT` con piso de tierra, `OVHAC` con hacinamiento,
`OVSREF` sin refrigerador, `OVSINT` sin internet, `OVSCEL` sin celular). El índice
(`IM_2020`) y el grado (`GM_2020`) quedan como los publica CONAPO, con su nombre.

La población por colonia es estimada (trae decimales): CONAPO reparte la de las
manzanas que la colonia cubre. `CLASIF` dice si es colonia, fraccionamiento,
pueblo, residencial o zona militar.

En el recorte salen la capa `colonias_marginacion` (las que tocan la caja) y la
tabla `tablas/agebs_marginacion.csv` (los AGEB de los municipios pedidos, para
unir con `agebs` por `cvegeo`).

**Validación (2026-11-18).** En la caja del CP 45615, los 206 AGEB de Tlaquepaque y
Tlajomulco que trae CONAPO tienen la misma población que el censo por AGEB de
Mapo, sin una sola diferencia. Los 97 de la caja que no aparecen son de otros
municipios o no tienen población. La colonia López Cotilla (`14098_0135`) está.

## Frontera agrícola

La serie II del SIAP delimita la superficie agrícola a escala 1:10 000, 25 veces
más fina que uso de suelo (1:250 000). A esa escala, uso de suelo generaliza la
orilla de los pueblos y deja escuelas urbanas "dentro" de polígonos agrícolas;
para distancias de cientos de metros, esta es la capa.

**De dónde.** `infosiap.siap.gob.mx`, donde se publicaba, ya no resuelve
(2026-11-18), y las ligas de datos.gob.mx apuntan ahí. Se baja la copia del
Internet Archive del archivo original, que tiene el mismo digest en sus tres
capturas de 2022. Hay un KMZ por región; el de Centro-Oeste trae Colima,
Jalisco, Aguascalientes, Guanajuato y Michoacán (77 MB, 46,557 polígonos).
Otra región se agrega a `crudos-ambientales.tsv` con el mismo patrón.

**Cómo se lee.** Es un KMZ exportado de ArcGIS: los atributos vienen en una
tabla HTML dentro de `description`, que GDAL no separa en campos, así que
`recorte.py` los saca con expresiones regulares.

| Campo | Qué es |
|---|---|
| `CVE_EDO`, `NOMEDO` | Estado |
| `CVE_DDR`, `NOMDDR`, `CVE_CADER`, `NOMCADER` | Distrito de Desarrollo Rural y CADER |
| `SUP_HA_7mo` | Hectáreas del polígono completo (aunque el recorte lo corte) |
| `MOD_USO` | A, agricultura; P, pastos |
| `MOD_AGR` | R, riego; T, temporal |

No dice cultivo: para eso está el cierre agrícola municipal.

**Validación (2026-11-18).** El área de cada polígono leído, calculada en
EPSG:6372, coincide con `SUP_HA_7mo`: el cociente es 1.0000 del percentil 1 al
99. Jalisco suma 1,646,976 ha en 15,706 polígonos (1,515,987 de temporal y
130,988 de riego). Una nota del SIAP sobre Jalisco da 1,684,374 ha, 2 % más,
sin decir de qué serie.

**Límite.** Son 15 años: lo que se abrió al cultivo después no está, y lo que
se urbanizó sigue como agrícola.

## Lo que falta

- **Plaguicidas en agua:** ninguna fuente abierta los mide. Solo estudios
  académicos, que entran como datos propios de un equipo.
- **Viento medido a nivel de calle:** las EMA del SMN solo publican los últimos
  días; ERA5 cubre el régimen regional (sección "Viento").
- **Atlas Nacional de Riesgos (CENAPRED):** se pide por correo.
- **Frontera agrícola más reciente (SIAP, series III y IV):** el visualizador no
  da descarga; la serie II sí está (sección "Frontera agrícola").
- **Red hidrográfica 1:50 000 y aguas subterráneas 1:250 000 (INEGI):** sin
  liga fija. La red de OSM que ya usa OSRM puede servir para los ríos.
- **Calidad del aire (SINAICA):** sin descarga masiva encontrada.
- **Escuelas:** DENUE ya las trae. El catálogo de la SEP no tiene descarga.

## Antes de cargar

- Revisar la licencia de cada fuente. La de Copernicus pide atribución.
- Validar contra cifras publicadas, como las demás fuentes: los datos de
  Conagua traen errores de captura (municipios que no corresponden a la
  coordenada).
