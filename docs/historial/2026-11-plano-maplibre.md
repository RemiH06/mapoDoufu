# Plano común con MapLibre y mapa base propio (sesión 29a)

Primera sesión del bloque 29a a 29m (separar las vistas por utilidad).
Los cinco mapas de Mapo dejan Leaflet y los mosaicos de OSM, y pasan a
un solo módulo, `assets/js/plano.js`, sobre MapLibre GL 6 con el mapa
base de Protomaps recortado a México y servido por Mapo mismo. El porqué
está en `docs/arquitectura/decisiones.md` ("Plano común"); la fuente, en
`docs/fuentes/plano.md`.

## Qué se hizo

- **Mapa base propio.** `scripts/plano/extraer.sh` recorta la build
  diaria de Protomaps al contorno de México con 10 km de margen: 1.2 GB
  (el recuadro de México pesaba 2.7). Phoenix lo sirve en
  `/mosaicos/mexico.pmtiles` con un segundo `Plug.Static` que lee la
  carpeta montada en `/plano` (`MAPO_PLANO_DATOS`); `Plug.Static` ya
  atiende `Range`. Letras (solo los rangos latinos, 2.2 MB), íconos y el
  worker de MapLibre van en `priv/static/plano/`.
- **`plano.js`.** Crea el plano con límites de México, controles en
  español, escala métrica y sin rotación; sigue el tema con un
  `MutationObserver` sobre `data-theme` (antes solo el botón movía el
  mapa; otra pestaña o el sistema, no); trae `clics()` (un solo clic por
  plano, gana la capa de arriba), `fuente`, `quitar`, `indexar`,
  `bordes`, `circulo`, `distancia`, `ficha` y `margenHoja`.
- **Velo de afuera de México** (`frontera.geojson`, el mundo menos el
  contorno de INEGI): de lejos los mosaicos traen el país vecino entero.
  El plano abre encuadrando México en lo que deja libre la hoja.
- **Las cinco vistas portadas:** `/riesgos` (con un control de casillas
  propio en lugar del de Leaflet), `/accesibilidad` (leyenda como control
  de MapLibre), `/logistica` (paradas como marcas arrastrables del DOM),
  `/sesiones/:id` y "Tus marcas" (`marcas.js`: puntos y notas en el DOM,
  trazos de los círculos como capa de líneas), y `/mapa` con `/buscador`
  (cada acetato es un grupo de capas `a-<id>:`; la pila se ordena
  moviendo grupos).
- **CSP:** fuera `https://*.tile.openstreetmap.org`; `worker-src 'self'`.
- **Fuera:** `assets/vendor/leaflet/` y `plano_tinta.js` (el retinte de
  los mosaicos por filtro SVG).
- **Scripts de capturas:** selectores de MapLibre, `planoMapo` en el
  elemento del plano para ubicar puntos (`map.project`), y GPU real en
  Windows (ver abajo).

## Bugs que aparecieron

- **El render de MapLibre tronaba al cambiar de tema** (`Cannot read
  properties of undefined (reading 'get')` en el dibujo de círculos).
  Llevarse las capas del hook al estilo nuevo con `transformStyle` y
  repintarlas en `styledata` las dejaba a medio cambio. Se cambió a: el
  estilo nuevo sin las capas del hook, y el hook las vuelve a poner en el
  primer `idle`.
- **Después, las capas desaparecían al cambiar de tema.** Con
  `diff: false` sí regresaban, pero se volvían a pedir todos los
  mosaicos (el plano se quedaba en blanco unos segundos en dev). Con el
  `diff` normal MapLibre conserva la fuente de mosaicos, pero repintar en
  cuanto `isStyleLoaded()` era cierto ponía las capas en el estilo viejo
  y el cambio las borraba. Esperar a `idle` resolvió los dos.
- **Un rectángulo del color del papel tapaba el plano en `/mapa`.** No
  era un elemento ni una capa: era la cinta volteada en vertical
  (y → alto − y) dibujada por el WebGL por software de Chromium sin
  cabeza. Con la GPU de Aerilate (ANGLE sobre D3D11) no aparece. Los
  scripts de capturas ya usan la GPU en Windows.
- **El plano de `/sesiones/:id` salía vacío en las capturas.** No era un
  bug: en dev cada pedazo del PMTiles tarda ~250 ms por el montaje de
  Windows a Docker, y el software de WebGL es lento; a los 20 s ya estaban
  los 2,110 objetos. Los scripts esperan a `areTilesLoaded()`.
- **Zoom un nivel arriba.** MapLibre usa mosaicos de 512 px: su zoom va
  un nivel abajo del de Leaflet. Se ajustaron los topes (15 → 14), el
  zoom de los puntos y paradas (14 → 13), el evento `centrar` del
  servidor (resta 1) y la clave de la vista guardada de la sesión
  (`:vista` → `:plano`, para no abrir un nivel más cerca).
- **Orden de `quitar` y `fuente`.** `quitar` ahora borra también las
  fuentes con su prefijo; en `/riesgos` se ponía la fuente y luego se
  quitaba antes de agregar la capa.

## Lo que se perdió a propósito

- La mezcla por acetato (`mix-blend-mode`, un canvas por acetato) y la
  entrada deslizada de la película: todo vive en un lienzo WebGL. La
  película se ve por su opacidad.
- El `autoPan` de las fichas de Leaflet: una ficha cerca de la cinta
  puede quedar en parte debajo de ella. Pasa a la 29d.

## Cómo se comprobó

- `mix precommit`: 421 pruebas, 0 fallas.
- `curl -r 0-126` a `/mosaicos/mexico.pmtiles`: 206 con 127 bytes; un
  archivo fuera de la lista, 404.
- En navegador (Chromium con GPU, escritorio, claro y oscuro):
  `/riesgos` con Autlán (contorno, cuatro peligros, casillas, fichas);
  `/accesibilidad` con Zapopan y Mezquitic (coropleta por minutos,
  destinos, leyenda, ficha de una AGEB); `/logistica` con cinco paradas,
  ruta por OSRM y ficha de una parada; `/mapa` con transporte de
  Guadalajara, con censo, área por negocio e isócrona juntos, y con el
  precio de oferta por AGEB (la ficha de la AGEB 3016 estimada dice
  "Estimado: de $940,000 a $4,840,000"); `/sesiones/1` con sus dos
  marcas. Cambio de tema en caliente en `/riesgos` y `/logistica`: el
  mapa base cambia y las capas regresan. `pantallas.js` en los tres
  tamaños sin errores de página ni scroll lateral.
