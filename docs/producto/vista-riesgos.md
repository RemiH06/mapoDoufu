# Vista de riesgos

`/riesgos`: se elige una zona con el selector común (estado, municipios, metrópoli,
colonia, CP o un polígono dibujado; `zona.md`) o un círculo de 0.1 a 25 km en el plano, y
se ve cada peligro por separado, con su fuente, fecha, nivel geográfico y
método, y cuánta gente vive dentro de la zona y cerca de cada uno. Nunca un índice ni la
palabra "expuesta": las frases son de lugar ("a menos de 1,000 m de un sitio en rojo").

Se lee de tres formas (sesión 29g), con el mismo plano al lado:

- **Lista:** un renglón por peligro con su ícono, su clase y su cifra. Al abrir uno queda
  solo en el plano, con sus hechos, su fuente, su método (plegado) y su cita.
- **Matriz:** la zona completa y cada uno de sus municipios contra los siete peligros. Con
  varios municipios es la vista inicial. "Dejarla fija" conserva el renglón de la zona (hasta
  cuatro) para compararla con la siguiente; con otra cercanía se sueltan. No van en la URL.
- **Mapas:** un mapa chico por peligro, todos con el mismo recuadro.

"Abrir en el mapa" lleva la zona, la cercanía y el peligro elegido (o los de puntos) al
acetato "Riesgos" de `/mapa`. La vista no se integra a `/mapa`: allá se dibuja junto con
otras capas, aquí se cuenta la gente.

La zona consultada queda en la URL y cada bloque trae "Cómo citar" con su fuente y la
fecha del dato (`citar.md`).

## Bloques

| Bloque | Fuente (`../fuentes/`) | Qué dice |
|---|---|---|
| Quién vive en la zona | Censo 2020 por AGEB y localidades del ITER | Población y grupos (0 a 2, 3 a 5, 60 o más, con discapacidad, sin servicios de salud, lengua indígena) y viviendas sin agua entubada o sin drenaje |
| Calidad del agua superficial y subterránea | `renameca.md` | Sitios dentro y cerca por semáforo, parámetros que incumplen, gente cerca de un sitio en rojo |
| Descargas con permiso | `repda.md` | Puntos dentro y cerca, volumen por uso, gente cerca |
| Establecimientos del RETC | `retc.md` | Actividades, sustancias del último reporte (aire, agua, suelo), gente cerca |
| Focos de calor | `firms.md` | VIIRS por año en la zona, fuentes fijas aparte, gente cerca de los focos del último año |
| Agua subterránea disponible | `acuiferos.md` | Acuíferos que toca la zona, su balance, vedas y pozos de la red |
| Sequía | `sequia.md` | Último corte y cortes en D2 o peor de los últimos 5 años, por municipio |
| ANP | `anp.md` | Dentro o a qué distancia, hasta 50 km |
| Uso de suelo | `uso-suelo.md` | % de la zona por clase y agricultura en las series VI y VII |
| Qué se siembra | `siap.md` | Hectáreas por cultivo y modalidad del último cierre, de los municipios de la zona |
| Defunciones | `defunciones.md` | Por año, total y por 100 mil, tumores, renales y respiratorias; contexto, no causa |

"Cerca" se elige: 250 m, 500 m, 1 km, 2 km o 5 km.

## La celda: clase y cifra

| Peligro | Cifra | Segundo renglón | Clase |
|---|---|---|---|
| Agua superficial y subterránea | % de la gente cerca de un sitio en rojo | Sitios en rojo de los que hay dentro o cerca | Cortes fijos |
| Descargas, RETC, focos | % de la gente cerca de alguno | Cuántos hay dentro | Cortes fijos |
| Acuífero | % del área sobre acuíferos sin agua disponible | Cuántos de los que toca | Cortes fijos |
| Sequía | Categoría del último corte | Cortes de 5 años en D2 o peor | Color del Monitor |

Los cortes son 0, hasta 5, hasta 20, hasta 50 y más de 50 %, los mismos en todas las
columnas, en `/accesibilidad` y con cualquier zona: la clase no depende de con quién se
compara. Cada columna se lee sola; nunca se suman ni se promedian.

- **Sin medición no es cero.** Sin sitios de la RENAMECA dentro ni cerca, la celda dice "sin
  red" y va rayada. Igual "sin gente" (nadie vive ahí) y "sin dato" (INEGI reserva todo).
- La zona entera solo tiene categoría de sequía si todos sus municipios tienen la misma; si
  no, dice el rango ("hasta D0").
- Un municipio de una zona dibujada es la parte que está dentro de ella.
- ANP, uso de suelo, siembra y defunciones van como contexto, sin clase.

## Iconografía

Cada peligro tiene siempre el mismo ícono, figura y tinta, en la lista, la matriz, los mapas
chicos, el plano y el acetato de `/mapa`: círculo, agua (con el color del semáforo; el verde
va hueco); cuadro, descarga; rombo, establecimiento; triángulo, foco. La figura basta para
distinguirlos sin color. De lejos va la figura sola y de cerca (zoom 12) con su ícono. Los
íconos son de Maki (Mapbox) y Temaki (Rapid), los dos CC0; el agua superficial y las
descargas son propios. La sequía usa los colores del Monitor (SMN) en los dos temas. Las
cinco clases pasan 4.5:1 con su texto en claro y oscuro.

## Cómo se cuenta la gente

AGEB urbanos con su censo donde están cargados (su punto interior dentro de la zona); en
el resto, el punto de cada localidad del ITER, salvo las que caen dentro de un AGEB
cargado. "Cerca de un peligro" es estar a esos metros o menos del más cercano (árbol k-d en
coordenadas geocéntricas WGS84, exacto al milímetro). Hasta la 29f era la unión de buffers de
16 lados, que por dentro quedan hasta 2 % cortos. Comprobado contra `ST_DWithin` en
`geography`: 824,523 personas a 1 km de un establecimiento del RETC en Guadalajara, las
mismas. Cada municipio da lo mismo consultado solo que dentro de su metrópoli. `*` de INEGI se
cuenta aparte, no como cero.

Fuera de los estados con AGEB cargados, una ciudad entera es un punto: un círculo de 3 km
en Oaxaca de Juárez cuenta sus 304 mil habitantes. La vista lo avisa cuando pasa
(`urbanas_por_punto`).

## Dónde vive

- `mapo_core/src/mapo_core/riesgos.py`: la zona y su ampliación a "cerca" se calculan una
  vez (`preparar`), se parten en pedazos chicos (`_partida`) y todo lo demás es punto en
  polígono contra ellos. La gente de la zona se lee una sola vez (`_unidades`) y cada peligro
  la cuenta en Python, en total y por municipio (`medida`).
- `GET /riesgos/zona?zona=<clave de zona.py>&cerca_m=` (siguen valiendo `cve_ent` y
  `cve_mun`, o `lon`, `lat` y `radio_m`). Hasta 5,000 km²: un estado tardaría minutos. Cada
  bloque trae `medida` (`zona` y `municipios`) y `capa`, con `total` si se dibujan menos (2,000
  puntos); la zona, `limites` (sus municipios) y la gente de cada uno.
- `GET /riesgos/capas?zona=&cerca_m=&peligros=a,b`: solo lo que se dibuja, sin contar gente.
  Los polígonos de ANP y acuíferos van recortados al alrededor de la zona.
- Focos: los del último año con datos en el país, dentro o cerca de la zona. Antes era el
  último año en que la zona tuvo focos: una colonia sin focos desde 2018 decía "a menos de
  1 km de un foco de 2018". Los de fuente fija se dibujan, pero no cuentan.
- RETC: cada establecimiento cuenta donde dice su último reporte. Antes contaba en cualquier
  punto que hubiera tenido.
- Una metrópoli usa todos sus municipios en sequía, siembra y defunciones; con la parte
  mínima de área, la ZMG perdía El Salto y Juanacatlán.
- Los datos por municipio (sequía, cultivos, defunciones) usan los municipios que tienen
  al menos 5 % del área de la zona, por polígono; sin municipios cargados, los del ITER
  que caen dentro. Antes de la 29b iba solo por el ITER, y una colonia urbana, sin ningún
  punto del ITER adentro, se quedaba sin municipio.
- Si nadie vive cerca de un peligro, la gente cerca es 0, no "sin dato": la suma de cero
  renglones salía NULL. "Sin dato" queda para cuando hay lugares y todos traen `*`.
- `mapo/lib/mapo_web/live/riesgos_live/index.ex` y `mapo/assets/js/riesgos_mapa.js`:
  la hoja y el plano. La matriz, la celda y los íconos (`MapoWeb.Cotejo`, `MapoWeb.Iconos`)
  los comparte con `/accesibilidad`; las figuras (`peligros.js`), con `/mapa`; los mapas
  chicos se dibujan en lienzos 2D (`mapas_chicos.js`), sin un MapLibre por cada uno.

## Tiempos

En Aerilate (2026-11-25, Docker en Windows): López Cotilla 1.5 s, Guadalajara 2 a 4 s, la
ZMG 12 s. Antes de la 29g, 0.9, 7 y 64 a 76 s. Lo que pesaba: la gente de la zona leída seis
veces, el área de la zona recalculada por renglón en el uso de suelo (25 s), el punto de
dentro de cada AGEB recalculado contra cada pedazo (`OFFSET 0` lo evita) y la compilación de
PostgreSQL (`jit`), que se apaga en estas consultas.
