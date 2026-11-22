# Fuentes económicas y municipales (noviembre 2026, sesión 28)

Cuatro fuentes nuevas en `/perfil`, sin pantallas nuevas: los Censos Económicos 2024, las
finanzas municipales de EFIPEM, el rezago social por AGEB de CONEVAL y los instrumentos de
planeación del Censo de Gobiernos Municipales 2025. Fichas en `../fuentes/`:
`censos-economicos.md`, `efipem.md`, `rezago-social.md` y `cngmd.md`.

## Qué se hizo

- **Cargadores:** `censos_economicos.py`, `efipem.py`, `rezago_social.py` y `cngmd.py` en
  `mapo_core`, cada uno con su comando de `cli` y su tabla. Los cuatro dicen lo reservado o
  no reportado como tal, nunca cero.
- **`/perfil_zona`** trae `economia`, `hacienda`, `rezago_social` y `planeacion`, cada una
  aparte, con su año.
- **`/perfil`:** el libro mayor suma "Tamaño de la economía, 2023" debajo del DENUE; la
  cédula censal, el rezago social por AGEB; y hay un sexto papel, "Hacienda municipal"
  (cuenta pública), con ingresos propios contra transferencias, predial, la serie de 2019 a
  2023, ingresos y egresos por capítulo y los instrumentos de planeación. Las notas del
  equipo también cuelgan de él (`hacienda` en `NotaPerfil`).
- Pruebas: `test_fuentes_municipales.py` (6) y una de LiveView. Capturas:
  `scripts/capturas/perfil28.js`.

## Por qué así

- **En `/perfil`, no en pantallas nuevas:** la 28 lo pedía así, y todo es por municipio
  menos el rezago social, que se resume en la gente de cada grado.
- **Censos Económicos sin AGEB:** INEGI no repitió en 2024 el producto por AGEB urbana de
  2019; los datos abiertos llegan a municipio.
- **De EFIPEM, solo tema y capítulo:** las partidas genéricas son 150 mil renglones por año
  y no cambian la lectura de "cuánto recauda y cuánto le transfieren". El predial sí se
  guarda aparte.
- **Del CNGMD, solo planeación:** es la única tabla que se leyó con su catálogo completo
  en la noche; catastro y protección civil necesitan el cuestionario de cada pregunta.
- **Cómo se encontraron las descargas:** las páginas de INEGI arman sus enlaces con
  JavaScript. Con Playwright se vio que piden la API de descarga masiva
  (`archivoscompaginacion?idBiinegi=...`), que devuelve la lista con la ruta de cada
  archivo.

## Bugs reales

- Una primera versión mostraba los conteos con `.0` (`89,635.0`): mapo_core los manda como
  flotantes. `entero/1` en el perfil.
- En celular, la columna del porcentaje de cada sector se salía del papel; ahora va entre
  paréntesis junto al nombre. Los nombres de los instrumentos pierden "del municipio o
  demarcación territorial".
