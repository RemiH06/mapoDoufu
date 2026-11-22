# Vista de riesgos

`/riesgos`: se elige una zona (un municipio cargado en Mapo o un círculo de 0.1 a 25 km en
el plano) y se ve cada peligro por separado, con su fuente, fecha, nivel geográfico y
método, y cuánta gente vive dentro de la zona y cerca de cada uno. Nunca un índice ni la
palabra "expuesta": las frases son de lugar ("a menos de 1,000 m de un sitio en rojo").

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

## Cómo se cuenta la gente

AGEB urbanos con su censo donde están cargados (su punto interior dentro de la zona); en
el resto, el punto de cada localidad del ITER, salvo las que caen dentro de un AGEB
cargado. "Cerca de un peligro" es una sola área: la unión de los buffers (en metros) de
los peligros dentro o cerca de la zona. `*` de INEGI se cuenta aparte, no como cero.

Fuera de los estados con AGEB cargados, una ciudad entera es un punto: un círculo de 3 km
en Oaxaca de Juárez cuenta sus 304 mil habitantes. La vista lo avisa cuando pasa
(`urbanas_por_punto`).

## Dónde vive

- `mapo_core/src/mapo_core/riesgos.py`: la zona y su ampliación a "cerca" se calculan una
  vez (`preparar`) y viajan como parámetros; todo lo demás es punto en polígono con el
  índice espacial. Medir cada punto contra el contorno de un municipio en `geography`
  tardaba minutos.
- `GET /riesgos/zona?cve_ent&cve_mun` o `?lon&lat&radio_m`, más `cerca_m`.
- `mapo/lib/mapo_web/live/riesgos_live/index.ex` y `mapo/assets/js/riesgos_mapa.js`:
  formulario, hoja de bloques y plano con una capa por peligro de puntos.

## Tiempos (producción, 2026-11-19)

Autlán 1.3 s, Guadalajara 1.2 s, círculo de 3 km 0.2 s.
