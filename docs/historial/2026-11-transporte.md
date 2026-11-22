# Transporte público (noviembre 2026, sesión 27)

Rutas, paradas y cada cuánto pasan, de los GTFS abiertos de México y de OSM donde no hay
GTFS. Fuente en `../fuentes/gtfs.md`; producto en `../producto/transporte.md`.

## Qué se hizo

- **Inventario:** Mobility Database y el Hub de Datos de Transporte Público de Codeando
  México; 17 feeds útiles en 9 estados, cada uno con su productor y su licencia tal como
  la declara. Google Maps y Moovit se descartaron: sus términos no dejan guardar ni
  redistribuir sus rutas. Monterrey, Puebla, León, Tijuana y Juárez quedan pendientes
  (decisión de Remi: con lo que hay).
- **Cargador:** `mapo_core/transporte.py` y `cli transporte`; tablas `transporte_feeds`,
  `transporte_rutas` y `transporte_paradas`.
- **OSM:** `scripts/transporte/rutas_osm.sh` (osmium en un contenedor de paso, sobre el
  pbf que ya bajaba el OSRM a pie), `mapo_core/transporte_osm.py` y `cli transporte_osm`.
- **Consulta:** `GET /transporte/zona` y el acetato "Transporte público" en `/mapa`, con
  enlace permanente (`transporte=1`) y "Cómo citar" por productor (`Cita.gtfs/2`, que
  arma una referencia fuera del catálogo cerrado).
- **Accesibilidad:** servicios `parada_transporte` y `parada_frecuente`, solo en los
  municipios con GTFS (`solo_cobertura`), con la cita de cada feed.
- Pruebas: `test_transporte.py` (9), dos más en `test_accesibilidad.py`, tres de LiveView
  y una de `Cita.gtfs`. Capturas: `scripts/capturas/transporte.js`.

## Por qué así

- **Frecuencia por ruta y sentido, no por poste.** El de Jalisco da una parada por ruta
  (14,508 paradas para 403 rutas): sumar pasadas por poste no dice nada. Se cuenta en la
  parada más servida de cada ruta y, en las paradas, cuenta la ruta que más pasa.
- **Un miércoles con servicio completo**, el de más viajes de la vigencia: el primer
  intento (el miércoles más cercano a hoy) dio cero viajes en el de SEMOVI, cuyo servicio
  principal acabó en 2025 aunque el calendario diga 2026.
- **Frecuencia de relleno detectada, no corregida.** Toluca, Uruapan y Oaxaca ponen 24
  pasadas en casi todas sus rutas; Cabo San Lucas lo admite. Se muestra el trazo y se dice
  que su frecuencia no sirve, en vez de pintar "cada 5 minutos" en toda la ciudad.
- **OSM no se mezcla con GTFS** ni entra a la accesibilidad: no dice si una ruta opera.
- **Licencias:** ocho feeds (Jalisco entre ellos) no declaran licencia. Mapo no
  redistribuye los feeds, los muestra y calcula citando a su productor con "sin licencia
  declarada". Es la opción que Remi tenía para decidir; si alguien pide quitar uno, se
  quita de `FEEDS`.

## Bugs reales

- **Circuitos contados dos veces:** al validar contra `headway_secs` del de SEMOVI, rutas
  de RTP salían con 25 pasadas donde el feed decía 15; el viaje toca la misma parada dos
  veces. Ahora cada viaje cuenta una vez por parada (296 de 300 rutas iguales).
- **El encuadre desde la URL:** al abrir `/mapa` con un acetato en la URL, el encuadre del
  estado (animado) llegaba justo antes que el de la capa, y Leaflet ignora un encuadre
  animado mientras otro sigue: el plano se quedaba en el estado. Ya pasaba con todos los
  acetatos; el del estado va sin animación.
- **Rutas de Git Bash:** `--carpeta /app/data/transporte` se volvió
  `C:/Program Files/Git/app/...` dentro del contenedor y los zips quedaron en una carpeta
  rara de su sistema de archivos. Con `MSYS_NO_PATHCONV=1` (anotado en `desarrollo.md`).
- **OPL sin coordenadas:** `osmium cat` a OPL no escribe la ubicación de los nodos de cada
  vía si no se pide `locations_on_ways=true`; sin ella, ninguna ruta tenía trazo.
