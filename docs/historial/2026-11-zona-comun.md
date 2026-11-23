# Selector de zona común (sesión 29b)

Segunda sesión del bloque 29a a 29m. `/riesgos`, `/accesibilidad` y `/mapa` dejan sus
`<select>` de estado y municipio por un solo selector: estado, uno o varios municipios,
metrópoli, colonia, código postal o un polígono dibujado. Cómo se usa y cómo calcula cada
vista: `docs/producto/zona.md`; las fuentes: `docs/fuentes/zonas.md`.

## Qué se hizo

- **`mapo_core/zona.py`.** La clave de zona (`ent:14`, `mun:14039,14120`, `zm:14.1.01`,
  `cp:45615`, `col:14098_0135`, `pol:...`, `cir:...`): `validar` sin tocar la base,
  `geom_sql` con parámetros, `resolver` (nombre, polígono simplificado según el tamaño,
  km², municipios que toca, los que faltan) y `buscar` para el autocompletado.
  `GET /zona/buscar` y `GET /zona/resolver`.
- **Datos nuevos:** tabla `metropolis` (las 92 de *Metrópolis de México 2020*, del CSV
  de la sesión 22 más Los Cabos, que faltaba), `colonias` (74,226 de CONAPO 2020, todo el
  país) y `codigos_postales` (vacía hasta tener los polígonos de SEPOMEX).
- **Vistas generalizadas:** `riesgos.py` y `accesibilidad.py` aceptan cualquier zona;
  siguen aceptando `cve_ent` y `cve_mun`. Tope de 5,000 km² para no colgar la consulta
  con un estado.
- **Efecto borde del área por negocio:** el Voronoi cuenta los negocios de DENUE a 5 km o
  menos fuera de la zona (celdas `fuera`, con velo y punto hueco). En Guadalajara, con
  farmacias, 1,106 de fuera compiten y 76 se quedan con parte del municipio.
- **`MapoWeb.ZonaSelector`** (LiveComponent): sugerencias como botones (Enter toma la
  primera), chips para sumar y quitar municipios, "Dibujar en el plano" y "Que sea mi
  zona". Le manda `{:zona_elegida, zona}` a la vista. `assets/js/zona_plano.js` dibuja el
  contorno provisional y el polígono en cualquier plano; `clics()` de `plano.js` se calla
  mientras se dibuja.
- **Zona en la que opero:** `users.zona_operacion` (migración
  `20261123005613`), guardada desde el selector; las vistas abren con ella cuando el
  enlace no trae zona, sin consultar solas. Se dejó fuera de la configuración porque esa
  página pide volver a entrar; la 29j la lleva ahí.
- **Enlaces:** `zona=mun:14039,14120`, sin escapar los dos puntos ni la coma. Los de antes
  (`ent`, `mun`, `modo=circulo&lat&lon&radio`) siguen abriendo y se reescriben.
- **`/mapa`:** el selector va en el membrete; al cambiar de zona se vuelven a pedir las
  capas puestas que dependen de ella.
- `scripts/capturas/zona.js` recorre la colonia, el dibujo, la ZMG, el Voronoi y sumar un
  municipio.

## Lo que salió con datos reales

- **El CP de CONAPO no sirve.** El plan era armar el CP con las colonias de CONAPO. Contra
  DENUE en Jalisco, solo 68.7 % de los negocios cae en una colonia con su mismo CP, y en
  941 colonias una mayoría clara de negocios dice otro; en los casos comprobables acierta
  DENUE. Un polígono de CONAPO junta varias colonias de SEPOMEX: 673 CP contra 1,631. Se
  probó corregirlo por voto de DENUE y se quitó: seguía sin dar los CP que faltan. Los
  polígonos oficiales de SEPOMEX existen pero datos.gob.mx niega la descarga a programas;
  se bajan a mano (decisión de Remi, 2026-11-22).
- **CONAPO guarda los CP de la Ciudad de México sin el cero** (`9700`).
- **Faltaba Los Cabos** en la tabla de metrópolis: cruzando sus claves con las del PDF.
- **Una colonia urbana no tiene puntos del ITER adentro**, así que `/riesgos` no sabía de
  qué municipio era (sequía, cultivos, defunciones). Ahora va por polígono de municipio.
- **Con 1 % de área, el municipio vecino se colaba:** 81 colonias de Jalisco tienen de 1 a
  5 % en otro municipio por diferencias de límites (López Cotilla, 1.6 % en Tlajomulco).
  El mínimo quedó en 5 %.
- **"sin dato personas"** cuando nadie vivía cerca de un peligro: la suma de cero
  renglones salía NULL. Ahora es 0.
- **JIT de Postgres:** el punto en polígono contra una zona estimaba costos enormes y
  compilaba 1.4 s una consulta de 0.1 s. Las conexiones de `mapo_core` van sin JIT.
- **El dibujo se quedaba pintado al cerrarlo:** un `requestAnimationFrame` del mousemove
  lo volvía a pintar después de terminar.
- **Al sumar un municipio, el Voronoi se quedaba con la zona vieja** y la URL ya decía la
  nueva. Ahora `/mapa` vuelve a pedir las capas puestas.

## Pruebas

`mix precommit` (429 pruebas) y `pytest` (488), con `test_zona.py` (claves válidas y
raras, resolver de cada tipo, buscar, el cargador de SEPOMEX con un shapefile sintético y
la competencia de fuera en el Voronoi) y `Mapo.ZonaFixtures` para las vistas. Revisado en
navegador real con `scripts/capturas/zona.js` en escritorio y celular, claro y oscuro.

## Queda

- Bajar los polígonos de CP de SEPOMEX, cargarlos y medirlos contra DENUE.
- `/perfil` y `/buscador` todavía eligen por estado y municipio (29h y 29c); las capas de
  censo, vivienda, municipios y transporte de `/mapa` todavía piden un estado y un
  municipio (29d).
- La ZMG en `/riesgos` tarda 64 s en Aerilate: medir en Pixilate.
