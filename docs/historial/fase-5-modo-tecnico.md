# Fase 5: Modo técnico


- **Mapas personalizables, capas múltiples**: pantalla `/mapa`
  (`MapaLive.Index`), consolida en un solo mapa lo que antes eran tres
  pantallas sueltas (coropletas, Voronoi, coloreado) más isócronas,
  cada una como una capa independiente que se prende y apaga sin
  afectar a las demás (varias activas al mismo tiempo).
  Estado/municipio compartido arriba; cada capa trae su propio
  control (indicador, giro, minutos). Isócrona funciona distinto: se
  activa el modo y luego se hace clic en el mapa para elegir el origen
  (`Mapo.MapoCore.isocrona_calcular/4`, primer POST con cuerpo JSON
  del cliente HTTP de Elixir hacia mapo_core). Hook `MapaTecnico` en
  Leaflet: como el contenedor del mapa es `phx-update="ignore"`, todo
  el estado de qué capa está prendida vive del lado del cliente, nunca
  en atributos re-renderizados; cada capa se comunica por su propio
  `push_event` (`capa_coropleta`, `capa_voronoi`, `capa_coloreado`,
  `capa_isocrona`, `modo_isocrona`). Las pantallas `/coropletas`,
  `/voronoi` y `/coloreado` se quedan tal cual, como acceso directo a
  una sola capa; `/mapa` no las reemplaza. 224 tests pasando en
  `mapo`. De paso: `attr :rest, :global` de `<.button>` en
  `core_components.ex` no incluía `type`, hacía falta para los botones
  "Quitar" (`type="button"`, para que no funcionen como submit del
  formulario de su propia capa)
- **Estadísticas cruzadas: "Perfil de zona"** (`/perfil`,
  `PerfilLive.Index`). Elige estado + municipio, junta en un solo
  reporte comercio (DENUE), demografía (censo), consumo (ENIGH) y
  seguridad (SESNSP). Es composición, no análisis nuevo: cada número
  viene directo de Gaiarda, ninguno se pondera ni se resume en un
  puntaje único. `mapo_core/perfil_zona.py` hace las 4 llamadas y
  resume comercio (conteo total + top 10 giros) y seguridad (solo el
  año más reciente, desglosado por tipo de delito); demografía y
  consumo se pasan casi tal cual, con `n_hogares_muestra` de ENIGH
  siempre visible. **Laboral (ENOE) queda fuera a propósito, marcado
  honesto** (`laboral_disponible: false`): confirmado leyendo
  `gaiarda/server.py` completo que Gaiarda todavía no expone ningún
  endpoint de *consulta* para ENOE (solo uno de *descarga*); no es una
  omisión de Mapo, es un hueco real de Gaiarda. `GET /perfil_zona` en
  `mapo_core`. 88 tests en `mapo_core`, 229 en `mapo`

### Otros tipos de mapa (coropletas, Voronoi, coloreado)

- **Coropletas**: era puro "conectar lo que ya existe", confirmado
  leyendo `gaiarda/src/gaiarda/server.py` directo del código fuente
  (no estaba documentado en `../gaiarda/referencia.md`, pero sí en el código
  real): Gaiarda ya cruza AGEB + censo por `cvegeo` en `GET
  /choropleth/censo_poblacion?indicador=...&cve_ent=...`, con
  `valor_choropleth: null` honesto si al AGEB le falta el dato.
  `mapo_core`: `GaiardaClient.choropleth_censo_poblacion` + tres
  passthroughs (`/gaiarda/estados`, `/gaiarda/municipios`,
  `/gaiarda/choropleth/censo_poblacion`). 58 tests en `mapo_core`.
  **Primera vez que `mapo` (Elixir) le pega a `mapo_core` por HTTP**:
  `Mapo.MapoCore` (usa `Req`), config `MAPO_CORE_URL` (ya existía en
  `docker-compose.yml`, no se usaba todavía). Pantalla `/coropletas`
  (`CoropletaLive.Index`, fuera de equipos/sesiones a propósito):
  selector de estado -> municipio (opcional) -> indicador (whitelist
  de 27, debe mantenerse igual al `INDICADORES_CHOROPLETH` de
  Gaiarda), hook `CoropletaMap` en Leaflet con escala de color de 5
  franjas + leyenda, gris explícito para AGEB sin dato. 196 tests
  pasando en `mapo`
- **Diagramas de Voronoi**: cómputo nuevo de verdad (a diferencia de
  coropletas), con `scipy.spatial.Voronoi` + `shapely`. `scipy`
  regresa regiones sin frontera para los puntos del borde (vértice
  `-1`); se reconstruyen a polígonos finitos extendiendo cada arista
  abierta más allá del punto (patrón ya documentado para este problema
  exacto) y se recortan con `shapely` contra un límite real (polígono
  de un municipio) o la caja envolvente de los puntos si no se da uno.
  Validado a mano con un cuadrado de 4 puntos: las celdas cubren
  exactamente el área del límite sin huecos ni traslapes. Casos
  degenerados (menos de 3 puntos, colineales) dan error claro. `POST
  /voronoi/calcular` (genérico) y `GET /voronoi/denue` (compone con
  Gaiarda: negocios de DENUE de un municipio, recortados a su
  polígono real). 72 tests en `mapo_core`. Pantalla `/voronoi`, hook
  `VoronoiMap` con un color distinto por negocio (ciclo de ángulo
  dorado) y marcador en la ubicación real sobre su propia celda. 206
  tests pasando en `mapo`. **Bug real encontrado y corregido**
  (afectaba también a coropletas): el selector de municipio guardaba
  el `cvegeo` completo (5 dígitos) como valor, pero los endpoints de
  Gaiarda piden `cve_mun` por separado (3 dígitos); con datos reales
  habría mandado un `cve_mun` incorrecto sin que nada tronara. Se
  agregó un test de regresión en ambas pantallas que compara el valor
  exacto mandado
- **Coloreado tipo "teorema de las 4 colores"**:
  `mapo_core/coloreado_mapa.py`. Grafo de adyacencia real (dos
  polígonos cuentan como vecinos solo si comparten un tramo de
  frontera, no solo una esquina) construido con un índice espacial
  `shapely.STRtree` en vez de comparar cada polígono contra todos los
  demás. Coloreado greedy tipo Welsh-Powell: ordena por número de
  vecinos, descendente, da el primer color libre. El resultado trae
  `num_colores` honesto (el teorema garantiza que 4 alcanzan, pero
  greedy no siempre encuentra esa coloración óptima). Validado con
  tests sobre una cuadrícula (equivalente a un tablero de ajedrez: da
  exactamente 2 colores). `POST /coloreado/calcular` (genérico) y `GET
  /coloreado/municipios` (compone con Gaiarda). 83 tests en
  `mapo_core`. Pantalla `/coloreado`, hook `ColoreadoMap` con paleta
  chica y fija. 212 tests pasando en `mapo`
- **Sin probar contra datos reales de Gaiarda todavía**: coropletas,
  Voronoi, coloreado, mapa técnico y perfil de zona están cubiertos
  por tests con datos simulados, pero nunca se han visto con AGEBs,
  censo y DENUE reales descargados (Gaiarda no corre en esta máquina).
  Confirmado en vivo que todos responden honesto (502) sin Gaiarda
  arriba, no un error opaco
