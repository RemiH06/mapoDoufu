# Fuentes ambientales (en crudo, sin cargar)

Descargadas el 2026-11-13 para la sesión 22. Todavía no hay cargador ni
tabla en la base: esto es el inventario de lo que hay y de lo que se
revisó en los archivos reales.

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
