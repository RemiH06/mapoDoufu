# Transporte público

Rutas, paradas y cada cuánto pasan, en el acetato "Transporte público" de `/mapa`, y la
gente que vive lejos de una parada en `/accesibilidad`. Las fuentes (GTFS abiertos de 17
feeds y rutas de OSM) y cómo se leen están en `../fuentes/gtfs.md`.

## El acetato en `/mapa`

Se elige una zona (la común, `zona.md`) y se pone "Transporte público" (enfoque
movilidad). mapo_core (`GET /transporte/zona?zona=`) manda las rutas que cruzan la zona y
sus paradas dentro de ella, hasta 5,000 km² (una metrópoli sí, un estado no: la cinta dice
por qué). `cve_ent` y `cve_mun` siguen sirviendo, como un municipio:

- **Del GTFS** si alguno toca la zona. Cada ruta lleva su intervalo en hora pico (de
  7 a 9 de un miércoles) y se pinta con más tinta y más grosor mientras más seguido
  pasa, en cinco clases: cada 10 min o menos, de 10 a 15, de 15 a 30, más de 30, y sin
  horario en hora pico (punteada). El transporte masivo (metro, tren, tren ligero,
  cable) va más grueso y con un halo de papel, encima de los camiones.
- **Color de cada ruta** (29d): si el feed trae `route_color` (hexadecimal válido; en la
  ZMG, 305 de 332 rutas), "Color de las rutas" en la cinta cambia la tinta única por el
  color de cada ruta; el grosor sigue diciendo la frecuencia y todas llevan halo, porque
  hay colores que se pierden en el fondo. Al poner el acetato se elige solo: el de cada
  ruta con 20 o menos, la tinta única con más (cientos de colores son confeti).
- **Resalte:** pasar el cursor por una ruta la dibuja encima, más gruesa y con halo de
  tinta de texto.
- **De OSM** si ningún GTFS lo toca: el trazo, sin horarios, todo punteado, y la cinta
  lo dice. Nunca se mezclan: donde hay GTFS, OSM no sale.
- **Sin nada:** "Ningún GTFS ni OpenStreetMap tiene rutas que pasen por Autlán de
  Navarro."
- Las paradas salen desde zoom 14, juntadas a ~10 m (los feeds que dan una parada por
  ruta repiten el punto), con la clase de la ruta que más pasa.
- Al tocar una ruta: nombre, modo, empresa, "Pasa cada 4 min de 7 a 9 de un día hábil" y
  viajes en el día; si el feed solo da intervalo, se dice que no es horario exacto.
- La cinta dice cuántas rutas pasan y cuántas cada 15 minutos o menos, y por cada feed su
  productor, su licencia ("Sin licencia declarada" si no la trae), el día con que se
  contaron las frecuencias, si venció y si su frecuencia es de relleno.
- Enlace permanente: `transporte=1` (con `zona`). "Cómo citar" cita a cada
  productor con la página del feed (`Cita.gtfs/2`), o a OSM con la fecha del extracto.

Guadalajara, 2026-11-25 de referencia: 251 rutas, 212 cada 15 minutos o menos (160 cada
10 o menos), 4,320 paradas. Puerto Vallarta: 44 rutas, 15 frecuentes.

## En `/accesibilidad`

Dos servicios nuevos, a pie, con toda la gente (`POBTOT`):

| Servicio | Destinos |
|---|---|
| Parada de transporte público | Toda parada de un GTFS con rutas |
| Parada con paso cada 15 minutos o menos | Paradas donde alguna ruta pasa 8 veces o más de 7 a 9; los feeds de frecuencia de relleno no cuentan |

Solo en los municipios con paradas de algún GTFS (`solo_cobertura`): fuera de las ciudades
con GTFS sí hay camiones, pero nadie publica dónde paran, y contar a esa gente como
"lejos" sería falso. Ahí la hoja dice "Ningún GTFS cargado tiene paradas en este
municipio: no se calcula". Las paradas en el mismo punto (~10 m) cuentan como una.

Guadalajara, a pie: 93 % de la gente vive a 5 minutos o menos de una parada; 8.2 %
(113,201 personas) a más de 5 minutos de una parada frecuente. En Jalisco calculan 4,161
lugares (los municipios de la ZMG, Vallarta, Tepatitlán, Lagos y Zapotlanejo); 10.8 s y
9.7 s por servicio.

## Lo que no hace

- No hay viajes puerta a puerta en transporte público (r5 u OpenTripPlanner): con
  frecuencias y OSRM a pie se responde "quién vive cerca de un servicio frecuente", que
  es lo que un municipio puede usar sin enrutador.
- Las paradas de OSM no cuentan en la accesibilidad: OSM no dice si la ruta opera.
- El contexto de demanda (medio y tiempo de traslado del censo ampliado) queda pendiente
  en `steps.md`.
