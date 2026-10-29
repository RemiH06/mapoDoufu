# Rendimiento, octubre 2026

Segunda sesión previa al rediseño. `/mapa` y `/logistica` se sentían
pesadas, el mapa de `/logistica` se trababa al moverlo y a veces salía
el aviso de "No encontramos conexión a internet".

## Cómo se midió

Chrome real (sin ventana) manejado con Playwright, con un usuario de
prueba. Mismo recorrido antes y después:

1. Abrir `/mapa` y esperar a que LiveView conecte.
2. Elegir Jalisco y Guadalajara.
3. Prender la coropleta del estado (4,761 AGEBs), el coloreado de
   municipios (125) y el Voronoi de farmacias en Guadalajara (1,148).
4. Tras cada capa, arrastrar el mapa y hacer zoom con la rueda tres
   veces mientras se cuentan cuadros con `requestAnimationFrame`.
5. En `/logistica`, poner 12 paradas, calcular y arrastrar.

"Cuadros lentos" son los que tardan más de 50 ms (se nota el tirón).
Se midió en dev (el contenedor de siempre) y en un build de producción
temporal (`MIX_ENV=prod`, `mix assets.deploy`).

## Números

| Paso | Antes (dev) | Después (dev) | Después (prod) |
|---|---|---|---|
| `/mapa` hasta conectar | 13.5 s, cae a longpoll | 3.3 s, websocket | 0.45 s |
| Elegir estado | 1.9 s | 0.06 s | 0.1 s |
| Coropleta: arrastre | 45 fps, 13 cuadros lentos, peor 150 ms | 59 fps, 1, peor 67 ms | 60 fps, 0, peor 33 ms |
| Coloreado: arrastre | 43 fps, 16 lentos, peor 167 ms | 58 fps, 0, peor 50 ms | 58 fps, 0, peor 50 ms |
| Voronoi: calcular | 6.7 s | 1.7 s | 1.7 s |
| Voronoi: arrastre | 31 fps, 29 lentos, peor 750 ms | 57 fps, 3, peor 83 ms | 57 fps, 2, peor 100 ms |
| `/logistica` con rutas: arrastre | 60 fps | 60 fps | 60 fps |

Respuestas de `mapo_core`:

| Endpoint | Antes | Después |
|---|---|---|
| `/geo/estados` para el select | 2.9 MB, 0.9 s | 2.8 KB, 0.01 s (`geometria=false`) |
| `/geo/municipios?cve_ent=14` para el select | 1.4 MB, 0.45 s | 13.6 KB, 0.01 s |
| `/censo/choropleth` de Jalisco | 2.1 MB | 1.8 MB (y 0.28 MB comprimido en el websocket) |
| `/voronoi/denue` farmacias de Guadalajara | 562 KB, 3.2 s | 378 KB, 0.57 s |
| `/voronoi/denue` Guadalajara sin filtro | 500 tras 12.7 s | 422 en 1 s, con mensaje |

En prod, mostrar la coropleta del estado tarda alrededor de 1.1 s:
unos 750 ms en el servidor (pedirla a `mapo_core`, decodificar,
codificar y comprimir 1.8 MB) y 300 ms en el navegador. Bajarlo más
pediría teselas vectoriales en vez de GeoJSON, y hoy no hace falta.

## Qué se encontró y qué se cambió

- **El `mount` de `/mapa` y `/perfil` pedía todas las geometrías** de
  estados (y luego de municipios) solo para llenar los selects, dos
  veces por carga (render muerto y conectado). Ahora
  `/geo/estados` y `/geo/municipios` aceptan `geometria=false` y
  `MapoCore.estados/0` y `municipios/1` lo usan.
- **Caída a longpoll y el aviso de "sin conexión".** Con el `mount`
  lento, el join tardaba más que `longPollFallbackMs` (2.5 s) y
  LiveView cambiaba a longpoll. En dev además el code reloader corre en
  cada conexión y en cada sondeo de longpoll, y tarda 1 a 2 s por el
  montaje 9p (ver `../desarrollo.md`). Se juntaban las dos cosas y los
  sondeos se vencían. Ahora el socket `/live` no corre el reloader
  (`code_reloader: false` en `endpoint.ex`); la carga HTTP de cada
  página sigue recompilando.
- **Leaflet en SVG.** Cada polígono era un nodo del DOM; con miles,
  arrastrar se trababa. Los dos mapas usan `preferCanvas: true`. Los
  popups siguen funcionando igual.
- **Decimales de más.** `ST_AsGeoJSON` sacaba hasta 9 decimales y el
  Voronoi (shapely) 15 o más, con una simplificación de unos 50 m.
  Ahora salen con 5 (1 m). Se comprobó con Jalisco que el coloreado
  encuentra los mismos 303 pares de municipios vecinos con y sin
  redondeo.
- **El límite del Voronoi no se simplificaba:** recortar cada celda
  contra el polígono completo del municipio era lo que tardaba 3 s.
  Ahora usa la misma simplificación que el resto.
- **Websocket comprimido** (`compress: true`): el GeoJSON baja de 3 a
  6 veces. Importa al hostear y entrar por Tailscale, no en local.
- **`/logistica` reencuadraba en cada clic.** Cada parada nueva hacía
  `fitBounds` y movía el mapa bajo el cursor. Ya no; solo se encuadra
  al llegar las rutas calculadas.

Bugs reales que salieron al medir:

- **Voronoi con negocios en la misma coordenada** (plazas, edificios)
  tronaba con `KeyError` (500): scipy no da región a un punto
  repetido. Ahora comparten una celda con `num_puntos` y el popup dice
  "y N más en el mismo punto". En Guadalajara hay 97,128 negocios en
  80,697 coordenadas distintas.
- **Voronoi sin tope:** Guadalajara sin filtro son 97 mil celdas. Ahora
  arriba de 5,000 negocios responde 422 pidiendo filtrar por giro.
- **`/logistica` nunca encuadraba las rutas:** `capasRutas` era un
  `layerGroup`, que no tiene `getBounds()`, y el `fitBounds` lanzaba un
  error en consola. Ahora es `featureGroup`.

Sospechosos descartados: el fondo animado (`metro_bg.js`) ya estaba
oculto y pausado en `/mapa` y `/logistica`, y `/logistica` no manda
eventos al servidor mientras se arrastra. En headless `/logistica`
siempre corrió a 60 fps.

## Lo que queda

- En dev cada carga HTTP sigue tardando 1 a 2.5 s por el code reloader
  sobre 9p. Es solo de desarrollo; prod responde en 30 ms. Ver
  `../desarrollo.md`.
- Falta confirmar en un navegador con ventana que `/logistica` ya no
  se traba: en headless nunca se reprodujo el tirón.
