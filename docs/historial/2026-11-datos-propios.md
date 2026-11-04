# Datos propios, etapa tabular (noviembre 2026)

Primera parte de la sesión 14: CSV y XLSX como acetato en `/mapa`. La
especificación vigente está en `../producto/datos-propios.md`; aquí queda qué se
hizo y qué se aprendió.

## Qué quedó

- `mapo_core/datos_propios.py`: lee, aplica los límites y ubica. No guarda nada
  ni sabe de equipos.
- `POST /datos/leer`, `POST /datos/ubicar` y `POST /geo/por_clave`. Reciben el
  archivo crudo, sin `python-multipart`.
- `Mapo.Capas`, con tablas `capas` y `capa_filas`: cuota, permisos y aislamiento
  por equipo.
- `/teams/:id/datos`: subir, confirmar la ubicación, ver y borrar.
- Acetato "Tus datos" en `/mapa`, y `?capa=ID` para llegar desde el equipo.
- Dependencias nuevas en `mapo_core`: `openpyxl` y `defusedxml`. Con la segunda
  instalada, `openpyxl` rechaza entidades XML por su cuenta.

## Por qué así

- **Interpreta Python, autoriza Elixir.** `mapo_core` no tiene cuentas y solo se
  alcanza por la red interna. Por eso no guarda: cualquier permiso ahí sería un
  segundo lugar donde equivocarse.
- **Filas en tabla propia con geometría,** no un JSON dentro de `capas`, para que
  el cruce con fuentes públicas sea una consulta de PostGIS.
- **Sin guardar el original:** menos datos ajenos en la máquina, y ningún archivo
  subido queda en disco.
- **La cuota cuenta el archivo,** no lo guardado: es el número que la persona ve
  en su explorador, y no cambia si se ubican más o menos renglones.
- **Una capa a la vez:** las películas de `/mapa` son fijas, con un canvas por
  acetato. Varias capas propias a la vez piden panes dinámicos.
- **Tinta de consumo:** ningún otro acetato de `/mapa` la usa. Es prestada, no
  significa nada sobre los datos.

## Bugs reales

- **La coma decimal se confundía con miles.** `20,671` se leía como 20671 y caía
  fuera de México. Con 3,000 negocios reales de DENUE guardados como los guarda
  Excel en español salieron 41 descartes falsos; el fixture usaba `20,67` y no lo
  veía. La coordenada ahora tiene su propio parser.
- **`csv.field_size_limit` es global.** Ajustarlo a cada archivo bajó el límite a
  21 bytes y rompió las ingestas de ENIGH y SESNSP en el mismo proceso. Lo detectó
  correr todo `pytest`, no solo las pruebas nuevas. Se quedó el límite por defecto.
- **La ficha redondeaba.** `20.67` salía `20.7` porque usaba el formato de lectura
  de cifras. La ficha muestra el dato tal cual.
- **La escala venía en rosa** fijo de demografía sobre un acetato ocre, y los
  botones de orden quedaban debajo del rótulo a 1280 px. Solo se vio en navegador.

## Cifras de la prueba

Dev, con DENUE de Jalisco y censo de Guadalajara, en Chromium sin ventana:

| Archivo | Leer | Guardar | Resultado |
|---|---|---|---|
| CSV estilo Excel, 3,003 renglones | 0.4 s | 0.9 s | 3,001 ubicados, 1 sin dato, 1 en Nueva York |
| XLSX por AGEB, 443 renglones | 1.1 s | 0.4 s | 442 ubicados, 1 clave inventada |
| CSV de 50,000 renglones, 2.1 MB | 2.0 s | 8.1 s | 50,000 ubicados |

El arrastre de 50 mil puntos dio 60 fps, peor cuadro de 17 ms, sin errores en la
consola. Sin ventana no hay pintado real, así que esa cifra no prueba cómo se
siente: falta verlo en un navegador normal y en producción.

Un CSV con `<img onerror>` y `<script>` en encabezados y celdas se mostró como
texto en la muestra y en la ficha, sin ejecutar nada.
