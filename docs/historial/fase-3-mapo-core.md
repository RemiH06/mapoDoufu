# Fase 3: Conexión mapo, mapo_core y Gaiarda


- Cliente HTTP en `mapo_core` hacia la API de Gaiarda
  (`gaiarda_client.py`): `estados`, `municipios`, `agebs`, `denue`
  (comercio), `censo_poblacion` (demografía), `sesnsp` (seguridad),
  `enigh_resumen` (consumo), `status`. Cubre exactamente los 5
  enfoques ya respaldados por fuente real, nada inventado de más
- Dos endpoints de prueba en `mapo_core` (`/gaiarda/status`,
  `/gaiarda/municipios`) que sí usan el cliente de punta a punta
- Manejo honesto de fallas: si Gaiarda no responde o truena, el
  endpoint regresa 502 con mensaje claro, no un 500 genérico opaco.
  Probado en vivo con Gaiarda apagado: `httpx.ConnectError` real,
  capturado limpio
- 16 tests nuevos en `mapo_core` (30 en total): el cliente probado con
  `httpx.MockTransport` (verifica URL y parámetros exactos que manda
  cada método), los endpoints probados con `dependency_overrides` de
  FastAPI
- **Probado contra una instancia viva de Gaiarda de verdad**, no solo
  mocks: se levantó Gaiarda desde el código del zip en un contenedor
  Docker temporal (`gaiarda estados` + `gaiarda municipios --estado
  14` reales), y se confirmó `mapo_core -> gaiarda/status` y
  `mapo_core -> gaiarda/municipios?cve_ent=14` trayendo datos reales
  (125 municipios de Jalisco, nombres correctos). También se confirmó
  que el 502 honesto sigue funcionando después de apagar Gaiarda otra
  vez. El contenedor era solo para esta prueba, no quedó corriendo
- **Cliente OSRM vendorizado en `mapo_core`** (`osrm_client.py`),
  adaptado de `gaiarda/src/gaiarda/ruteo_osrm.py`: async (httpx, no
  `requests`), variable de entorno propia `MAPO_OSRM_URL`
  (independiente de `GAIARDA_OSRM_URL`, mapo_core no depende del
  código de Gaiarda para nada). Mismo principio honesto: nunca truena,
  regresa `None` si el servicio no responde o si algún tramo no es
  alcanzable por carretera, para que quien llama caiga de vuelta a
  haversine
- **Motor VRP decidido y construido: OR-Tools** (no heurística
  propia). Se evaluó escribir el heurístico a mano (extender el TSP de
  Gaiarda a múltiples vehículos) y se descartó: VRP con capacidad y
  ventanas de tiempo es una clase de problema distinta, con riesgo
  real de bugs silenciosos (rutas que se ven razonables pero violan
  una restricción sin que nadie se entere). OR-Tools es lo que
  empresas reales de logística usan para esto. `mapo_core/vrp.py`:
  capacidad por vehículo + ventanas de tiempo opcionales, endpoint
  `POST /vrp/calcular`. Usa distancia y duración real por carretera
  (OSRM) cuando está disponible, con fallback honesto a línea recta si
  no; el campo `metodo` siempre dice cuál de los dos se usó
  (`carretera_real` / `linea_recta_aproximada`). Si no hay solución
  factible, regresa 422 explícito, no inventa una ruta incorrecta. 42
  tests pasando en `mapo_core`. **Probado en vivo contra el demo
  público real de OSRM**: circuito CDMX-Toluca-Cuernavaca-Puebla,
  `metodo: "carretera_real"`, 437.78 km reales
- **Sin construir todavía, fuera de alcance a propósito**: vendorizar
  el patrón de geocodificación por nombre contra OSM
  (`casetas/geocodificar.py` en Gaiarda). No hay todavía ningún caso
  de uso concreto en Mapo que lo necesite; se hace cuando aparezca uno
