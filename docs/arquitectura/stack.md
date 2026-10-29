# Stack técnico

## Stack técnico de Mapo (decidido)

Contexto: Remi quiere usar Mapo como excusa para aprender herramientas
fuera de React/Node/Python (que fue la elección "aburrida a propósito"
para Gaiarda, dado que ya había suficiente riesgo/complejidad nueva con
las fuentes de datos). Decisión tomada explícitamente: el aprendizaje
es el punto de esta primera versión, y las sesiones colaborativas en
tiempo real son necesarias desde la v1 (no se pueden aplazar), lo que
inclina la balanza directo hacia Elixir/Phoenix desde el arranque.

- **Elixir + Phoenix (LiveView)**: runtime cara al usuario. Auth,
  sesiones personales y de equipo, mapa colaborativo en vivo (varias
  personas viendo/anotando el mismo mapa a la vez, sin apenas
  JavaScript, el servidor empuja los cambios directo). Es la pieza que
  hace posible el requisito de sesiones que Gaiarda nunca necesitó.
- **Python**: núcleo de datos y motor de decisión, reutilizando
  Gaiarda tal cual (cliente OSRM, geocodificación por nombre contra
  OSM, las fuentes de datos). Aquí vive el motor VRP nuevo (múltiples
  vehículos, capacidad, ventanas de tiempo) que Gaiarda no tiene.
- **Comunicación entre los dos runtimes**: Elixir consume la API de
  Python por HTTP. La opción más simple, nada de RPC binario ni colas
  de mensajes por ahora. Implementado (`Mapo.MapoCore`, vía `Req`,
  usando la variable `MAPO_CORE_URL` que ya estaba en
  `docker-compose.yml` desde el arranque pero sin nada del lado de
  Elixir que la leyera): primer consumidor real es la pantalla de
  coropletas (`/coropletas`, ver `../historial/fase-5-modo-tecnico.md`;
  desde octubre de 2026 esa capa vive solo en `/mapa`).
- **Rust**: diferido. Entra vía `PyO3` como acelerador (ruteo a gran
  escala, cruces espaciales masivos) el día que el cómputo del VRP sea
  comprobadamente el cuello de botella, no antes.
- **Julia**: diferido. Entra si el análisis estadístico pesado (ENIGH
  ponderado, clustering espacial) resulta ser el cuello de botella, no
  antes.
- **HeidiSQL**: cliente de base de datos de escritorio, sin curva de
  aprendizaje, usable desde ya (no es específico de Mapo).
- **Gatling**: pruebas de carga, tiene sentido hasta que Mapo esté vivo
  y con usuarios reales, no desde el diseño inicial.

**Motor VRP (decidido): OR-Tools, no heurística propia.** Se evaluó
escribir el heurístico a mano (extender el TSP de Gaiarda, vecino más
cercano + 2-opt, a múltiples vehículos) y se descartó: VRP con
capacidad y ventanas de tiempo no es "TSP con más pasos", es una clase
de problema distinta (hay que decidir qué parada va con qué vehículo
*y* en qué orden, con verificación de factibilidad de capacidad/tiempo
en cada movimiento, más una fase de mejora con movimientos *entre*
rutas, no solo dentro de cada una). Es un proyecto de días a semanas
para que sea confiable, con el riesgo de que los bugs no truenen, solo
produzcan una ruta que se ve razonable pero viola una restricción sin
que nadie se entere. Se aplicó la misma lógica que ya se usó con
Haskell (evaluado y descartado como pieza de Mapo, recomendado
aprenderlo por su cuenta en vez de amarrado a un proyecto real): si
construir un solver VRP desde cero interesa por el aprendizaje en sí,
vale la pena como ejercicio aparte, no atado a que Mapo funcione.
OR-Tools es lo que empresas reales de logística usan para exactamente
este problema. Implementado en `mapo_core/vrp.py` +
`POST /vrp/calcular`. Ya usa distancia y duración real por carretera
(cliente OSRM vendorizado en `mapo_core/osrm_client.py`, adaptado de
`gaiarda/src/gaiarda/ruteo_osrm.py`) cuando el servicio responde, con
el mismo fallback honesto a línea recta que ya usaba Gaiarda si no.

**Isócronas (decidido): muestreo radial con OSRM, no un segundo motor
de ruteo.** Se evaluó agregar Valhalla u Openrouteservice
(traen isócronas nativas) contra samplear puntos en varias direcciones
con el servicio `table` de OSRM (que ya está integrado para VRP) y
armar el polígono con el punto más lejano alcanzable en cada
dirección. Se descartó el segundo motor: ya tenemos OSRM, meter otro
solo para esta capacidad duplicaría infraestructura (otro servicio que
levantar, correr y mantener) por una ganancia de precisión marginal
sobre el muestreo. Implementado en `mapo_core/isocronas.py` +
`POST /isocronas/calcular`, mismo patrón `metodo` honesto (`osrm_real`
vs. `circulo_aproximado`) que el resto del proyecto.

**Otros tipos de mapa que Mapo va a necesitar** (coropletas, Voronoi,
coloreado tipo teorema de las 4 colores): anotados y evaluados en
`../historial/fase-5-modo-tecnico.md`. **Coropletas ya construidas**: era puro
conectar y renderizar lo que Gaiarda ya resolvía del lado de datos
(`GET /choropleth/censo_poblacion`, confirmado leyendo su
`server.py`), no calcular de nuevo. **Voronoi ya construido también**,
este sí cómputo nuevo en `mapo_core` (`scipy.spatial.Voronoi` +
`shapely` para recortar a un polígono real, ver detalle en
`../historial/fase-5-modo-tecnico.md`). **Coloreado tipo teorema de las 4
colores ya construido**: grafo de adyacencia entre polígonos
(`shapely.STRtree` para no comparar todos contra todos) + Welsh-Powell
greedy. Con esto la lista completa de "otros tipos de mapa" que se
había pausado queda cerrada.

**Base de datos (decidido): Postgres, con PostGIS**. Se evaluó
explícitamente si convenía algo no estructurado (tipo datalake) para
lo que Mapo va a guardar (anotaciones colaborativas en tiempo real
sobre el mapa, resultados de VRP, rutas guardadas, historial del modo
buscador), y se descartó: un datalake resuelve un problema de volumen
y variedad que Mapo no tiene (las fuentes ya llegan gobernadas y
normalizadas vía Gaiarda). Lo semi-estructurado (JSON variable, igual
que `datos_json`/`resultado_json` en Gaiarda) lo cubre `jsonb` nativo
de Postgres, con índices GIN, mejor que el `json_extract()` de SQLite
que usa Gaiarda. Para las anotaciones geométricas en tiempo real
(requisito de colaboración, RF3) se agregó **PostGIS** (imagen
`postgis/postgis:16-3.4-alpine` en vez de `postgres:16-alpine` en
`docker-compose.yml`, extensión habilitada en `mapo_dev` y
`mapo_test`): tipos de geometría e índices espaciales nativos, en vez
de reimplementar en la app lo que Gaiarda hace a mano con `shapely`.
Si en algún momento aparece contenido genuinamente no estructurado
(documentos, imágenes subidas por usuarios), la respuesta sería
almacenamiento de objetos (S3/MinIO) para esos blobs puntuales, no
reestructurar la base.

Descartadas o de encaje dudoso para el tamaño real de Mapo: Erlang y
Scala (pensadas para escalas que Mapo probablemente no alcance pronto;
Elixir ya da lo bueno de Erlang con menos fricción), MXNet (el
ecosistema de ML se movió hacia PyTorch, MXNet está en declive), Pascal
(sin encaje natural en este stack), **Haskell** (evaluado y descartado
como pieza de Mapo: el nicho donde brillaría, correctitud a prueba de
balas para lógica compleja, ya lo cubre Rust con mejor ecosistema
práctico; sumarlo encima de Rust + Julia + Elixir sería un cuarto
paradigma nuevo de golpe, y el salto conceptual de Haskell es el más
grande de los cuatro. Recomendación: aprenderlo por su cuenta, no
atado a la fecha/alcance de un proyecto real).

Fuera del proyecto pero válidas siempre: Whimsical (diseñar el flujo de
Mapo antes de programarlo, útil desde el arranque), Vim (hábito de
flujo de trabajo, no depende del proyecto), Rsync (útil si se sincroniza
`data/` entre máquinas).
