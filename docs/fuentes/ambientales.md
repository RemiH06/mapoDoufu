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
| `clima` | Conagua | Viento por estación: **solo una ventana corta de 2023 cada 10 minutos**, no hay historia. El viento histórico sigue sin fuente |
| `riesgo` | SMN, Conagua | Monitor de Sequía por municipio (histórico en `MunicipiosSequia.xlsx`), zonas inundables (PDF, sin vector), vulnerabilidad por municipio de Conagua (índices compuestos: mostrar sus componentes) |
| `territorio` | INEGI vía CONABIO | Uso de suelo y vegetación 1:250 000 series VI y VII (para ver cambio), edafología, ANP 2020, regiones hidrológicas |
| `agricultura` | SIAP | Cierre agrícola municipal 2003 a 2025: cultivo, ciclo, modalidad (riego o temporal), superficie sembrada, cosechada y siniestrada, volumen, valor |
| `incendios` | NASA FIRMS | Focos de calor de México: MODIS 2000 a 2025 y VIIRS S-NPP (375 m) 2012 a 2025, con fecha, hora, confianza y potencia radiativa |
| `salud` | INEGI | Defunciones registradas 2020 a 2023 (microdatos con municipio y causa CIE-10). Otros años usan otra ruta |
| `poblacion` | INEGI | ITER 2020 de Jalisco: localidades, también las rurales |
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
| `diccionario_capas.csv` | Por capa: archivo, filas, fuente, fecha del dato, nivel geográfico, URL y nota |
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

## Lo que falta

- **Plaguicidas en agua:** ninguna fuente abierta los mide. Solo estudios
  académicos, que entran como datos propios de un equipo.
- **Viento histórico:** las EMA del SMN solo publican los últimos días.
- **Atlas Nacional de Riesgos (CENAPRED):** se pide por correo.
- **Frontera agrícola (SIAP):** el visualizador no da descarga directa.
- **Red hidrográfica 1:50 000 y aguas subterráneas 1:250 000 (INEGI):** sin
  liga fija. La red de OSM que ya usa OSRM puede servir para los ríos.
- **Calidad del aire (SINAICA):** sin descarga masiva encontrada.
- **Escuelas:** DENUE ya las trae. El catálogo de la SEP no tiene descarga.

## Antes de cargar

- Revisar la licencia de cada fuente. La de Copernicus pide atribución.
- Validar contra cifras publicadas, como las demás fuentes: los datos de
  Conagua traen errores de captura (municipios que no corresponden a la
  coordenada).
