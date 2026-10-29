# Pantalla de logística (septiembre 2026)

## Pantalla de logística para el motor VRP (2026-09-27)

- [x] **`/logistica` ya existe**: el motor VRP (RF7) ya estaba
      construido y probado en `mapo_core` (`POST /vrp/calcular`), pero
      nadie podía usarlo desde la interfaz. Nueva pantalla siguiendo el
      mismo patrón que `/mapa`/`/voronoi` (panel lateral + mapa grande)

**Backend, un cambio real antes de que la pantalla tuviera sentido**:
`/vrp/calcular` regresaba `orden_paradas` (índices) y `distancia_km`,
pero ninguna geometría real de la ruta: `osrm_client.geometria_ruta`
existía desde antes (vendorizado del patrón de Rutas de Gaiarda) pero
nadie lo llamaba. Se conectó: cada ruta del VRP ahora trae `geometria`
(GeoJSON LineString real, vía OSRM) cuando el método fue
`carretera_real`, o `null` si cayó a línea recta (ahí no hay carretera
real que pedir) o si esa llamada en particular no respondió. Probado
contra el servicio real de OSRM (demo público): CDMX-Puebla-Toluca-CDMX,
387.3 km reales, geometría con 5,260 puntos reales.

**Interfaz**: cada clic en el mapa agrega una parada (la primera es el
depósito, sin selector aparte: decisión de alcance, más simple que
dejar elegir depósito manualmente); panel lateral con la lista de
paradas (demanda editable por parada, quitar una a una), número de
vehículos y capacidad uniforme por vehículo. Al calcular, cada ruta se
pinta de un color distinto: polyline real si hay `geometria`, línea
punteada si no (señal visual de que es aproximada, además del badge de
`metodo`). Mismo patrón de clic-acumula-puntos que ya usa el mapa
colaborativo de sesiones (`collab_map.js`), no el de activar/desactivar
que usa la isócrona.

**Alcance deliberado, no implementado en esta pasada**: ventanas de
tiempo por parada (el backend ya las soporta, la interfaz no las
expone todavía, sin caso de uso concreto que lo pidiera) y capacidad
distinta por vehículo (todos los vehículos comparten la misma
capacidad en la interfaz, aunque el backend soporta capacidades
heterogéneas).

- Agregado `Mapo.MapoCore.vrp_calcular/4`, ruta `/logistica` (mismo
  `live_session` autenticado que las demás pantallas de mapa), link en
  la navbar
- 2 tests nuevos en `mapo_core` (134 en total: geometría real cuando
  hay carretera real, geometría null si esa llamada puntual falla),
  8 tests nuevos en `mapo` (237 en total: agregar/quitar paradas,
  depósito siempre la primera, calcular con <2 paradas, solución real,
  422 infactible con el mensaje de detalle)
- **No probado en navegador real** (sin acceso a uno en este entorno):
  verificado con `mix precommit` (formato + 237 tests), `mix
  assets.build` (esbuild compila el hook nuevo sin errores), y `curl`
  contra `/vrp/calcular` real. Falta que el usuario confirme la
  experiencia real de clic-en-mapa en el navegador
