# Limpieza de código, octubre 2026

Primera de las sesiones previas al rediseño visual. Línea base antes de
tocar nada: 134 tests en `mapo_core` y 237 en `mapo`, todos verdes.

- **Pantallas de una sola capa, retiradas.** `/coropletas`, `/voronoi`
  y `/coloreado` repetían capas que `/mapa` ya une (en la Fase 5 se
  habían dejado como acceso directo). Se borraron sus LiveViews, hooks
  (`CoropletaMap`, `VoronoiMap`, `ColoreadoMap`), tests y links de la
  navbar. Las tres URLs redirigen a `/mapa` (`PageController.a_mapa`).
  Antes de borrar se compararon los tests: `/mapa` no avisaba cuando
  mapo_core regresaba una colección vacía (coropleta y coloreado) y
  pintaba una capa vacía. Se pasó ese manejo a `/mapa` junto con los
  tests que faltaban ahí (`cve_mun` de 3 dígitos, `clase_actividad`,
  422 con su `detail`, 404, coloreado sin estado). `mapo` queda en 227
  tests.
- **Fondo animado:** `RUTAS_SIN_FONDO` (`metro_bg.js`) queda en `/mapa`
  y `/logistica`; antes listaba las pantallas borradas y le faltaba
  `/logistica`, que también es de mapa grande.
- **Tailwind por sondeo.** `tailwind --watch` no ve cambios porque
  Docker Desktop monta el código por 9p, sin inotify. El watcher de dev
  es ahora `MapoWeb.TailwindSondeo`. Detalle en `../desarrollo.md`.
- **Tests de `mapo_core` montados** en el compose; ya no hace falta
  reconstruir la imagen al cambiar un test.
- **Revisión en navegador:** `/mapa` y `/logistica` funcionan, pero se
  sienten pesadas y el mapa de `/logistica` se traba al moverlo. Se
  abrió una sesión de rendimiento antes del rediseño. La prueba de la
  sesión colaborativa entre dos máquinas quedó pendiente.
