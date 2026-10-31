# Desarrollo local

Todo corre en Docker; no hace falta Elixir ni Python instalados en la
máquina.

## Levantar

```bash
docker compose up -d
```

| Servicio | Puerto en el host | Qué es |
|---|---|---|
| `mapo` | 1864 (contenedor: 4000) | Phoenix LiveView, `http://localhost:1864` |
| `mapo_core` | 8010 | FastAPI |
| `db` | 5432 | Postgres 16 + PostGIS, bases `mapo_dev` y `mapo_test` |

Los tres escuchan solo en `127.0.0.1`: dev trae `/dev/mailbox`, el
dashboard y la base con `postgres/postgres`, y nada de eso debe verse
desde la red local. Para entrar desde otra máquina propia, usar
`tailscale serve --bg 1864` en vez de abrir el puerto: lo ve solo la
tailnet, y se apaga con `tailscale serve reset` al terminar.

Mapo corre en el 1864 porque el 4000 estaba ocupado en la máquina de
desarrollo. Por eso `config.exs` trae `url: [port: 1864]`: sin eso, los
links de los correos (confirmación, magic link, invitaciones) salen con
el puerto interno 4000.

Correos en desarrollo: `http://localhost:1864/dev/mailbox` (no hay
adapter de correo real todavía, ver `producto/requisitos.md`).

## Probar

```bash
docker compose exec mapo mix precommit          # formato + compilación + tests de mapo
docker compose exec mapo_core pytest            # tests de mapo_core, contra mapo_test
```

Los tests de `mapo_core` usan una base real (`mapo_test`), cada uno en
su propia transacción que se revierte al final. `conftest.py` fuerza
`DATABASE_NAME=mapo_test` aunque el compose traiga `mapo_dev`. El
compose monta `mapo_core/tests`, así que no hace falta reconstruir la
imagen después de cambiar un test.

## Cargar datos

```bash
docker compose exec mapo_core python -m mapo_core.cli estados
docker compose exec mapo_core python -m mapo_core.cli municipios --estado 14
docker compose exec mapo_core python -m mapo_core.cli agebs --estado 14
docker compose exec mapo_core python -m mapo_core.cli censo_poblacion --estado 14
docker compose exec mapo_core python -m mapo_core.cli denue --estado 14      # token en mapo_core/.env
docker compose exec mapo_core python -m mapo_core.cli enigh
docker compose exec mapo_core python -m mapo_core.cli enoe --anio 2025 --trimestre trim3
docker compose exec mapo_core python -m mapo_core.cli sesnsp --archivo data/sesnsp/<archivo>.csv
docker compose exec mapo_core python -m mapo_core.cli status
```

Detalle y particularidades de cada fuente en `fuentes/`. Los archivos
que se descargan a mano (SESNSP) van en `mapo_core/data/`, gitignorado
y montado en el contenedor.

## Troubleshooting ya resuelto

**Notas reales de troubleshooting en `mapo/Dockerfile`** (imagen base
`elixir:1.17-slim`, ambas ya corregidas):

- No trae `ca-certificates`, así que `mix local.hex` truena con
  `no_cacerts_found` al intentar hablar con Hex por HTTPS. Se
  corrigió instalando `ca-certificates` (y `git`, que también usa
  Phoenix) antes de cualquier comando `mix`.
- No trae `inotify-tools`, así que el live-reload (refrescar el
  navegador solo con guardar) no arranca dentro del contenedor: avisa
  con `warning`, no truena, pero se pierde la comodidad. Se corrigió
  agregando `inotify-tools` al mismo paso de `apt-get install`.
- El bind mount `./mapo:/app` en `docker-compose.yml` tapa el
  `mix.lock` que `mix deps.get` genera **dentro** de la imagen al
  construirla (nunca llega al disco real). Hay que correr `mix
  deps.get` una vez ya con el volumen montado
  (`docker compose run --rm mapo mix deps.get`) para que `mix.lock`
  quede en el host. Los directorios `_build/` y `deps/` sí tienen
  volúmenes nombrados propios en el compose, por eso no se pierden
  entre reinicios.
- No trae herramientas de compilación (`make`, gcc). `bcrypt_elixir`
  (dependencia que agrega `mix phx.gen.auth`) compila un NIF en C y
  truena con `"make" not found in the path`. Se corrigió agregando
  `build-essential` al mismo paso de `apt-get install`.
- `config/dev.exs` y `config/test.exs` traen `hostname: "localhost"`
  a fuerza para el `Repo`, que dentro de un contenedor apunta al
  propio contenedor, no al servicio `db`. Se corrigió cambiando ambos
  a `System.get_env("DATABASE_HOST", "localhost")`, con `DATABASE_HOST:
  db` puesto en `docker-compose.yml`. Aplica a cualquier config nueva
  que agregue conexión a la base.
- **Tailwind se recompila por sondeo, no con `--watch`.** Docker
  Desktop monta el código con 9p, que no entrega eventos de inotify, y
  el binario de Tailwind 4 no tiene opción de sondeo. En dev, el watcher
  es `MapoWeb.TailwindSondeo` (`config/dev.exs`): revisa cada segundo
  el mtime de lo que Tailwind lee (`assets/` y `lib/mapo_web`) y
  recompila completo si algo cambió. Tarda de 3 a 5 segundos en
  reflejarse; recargar el navegador después. `docker compose exec mapo
  mix tailwind mapo` sigue sirviendo para forzarlo.
  El code reloader de Phoenix (`.ex`/`.heex`) y el watcher de esbuild
  (JS) no dependen de inotify y funcionan normal.
- **En dev cada página tarda 1 a 2.5 s en responder.** El code reloader
  corre `mix compile` en cada petición HTTP, y revisar el código por
  9p cuesta unos 4 ms por archivo (`compile.elixir` sin cambios: 0.6 s
  aislado, más con el sondeo de Tailwind compitiendo). Prod responde en
  30 ms. El socket `/live` no corre el reloader (`code_reloader: false`
  en `endpoint.ex`): si lo corre, el join pasa de los 2.5 s de
  `longPollFallbackMs`, LiveView cae a longpoll y sale el aviso de "No
  encontramos conexión a internet". La cura de fondo sería tener el
  código en el sistema de archivos de WSL en vez de montarlo desde
  Windows.
- **`mix phx.gen.context` en Phoenix 1.8 agrega "scope" automático si
  el nombre de un campo `:references` coincide con el patrón de
  dueño único** (ej. un `user_id` en un recurso nuevo): mete una
  columna `user_id` con `on_delete: :delete_all` y un changeset de
  3 argumentos que asume "este recurso le pertenece a un solo
  usuario". Pasó al generar `Team` (se me olvidó `--no-scope`, y para
  un equipo compartido por varias personas esa semántica es
  exactamente la incorrecta: si se borra el usuario dueño, se borraría
  el equipo entero). Se corrigió a mano: `teams` sin `user_id`, la
  propiedad sale de `team_memberships` (rol `owner`). Lección: antes de
  generar un recurso que NO es propiedad exclusiva de un solo usuario
  (equipos, cualquier cosa compartida), pasar `--no-scope` desde el
  principio, o revisar la migración/changeset generados antes de
  migrar. Para `Membership` sí hizo falta `--no-scope` explícito,
  porque el generador detecta el choque de nombre con `user_id` y
  truena pidiéndolo (`Reference :user_id has the same name as the
  scope schema key`).
- **Generadores de Phoenix con salida "You are generating into an
  existing context" o el resumen final de `phx.gen.auth` esperan
  confirmación `[Yn]` por stdin.** Sin TTY (como al correrlos vía
  `docker compose exec -T`), el prompt no se ve y el generador no
  crea nada, sin marcar error (exit code 0). Hay que anteponer `yes |`
  al comando para que no se quede esperando en silencio.
- **`geo_postgis`: el `types: Mapo.PostgresTypes` va en
  `config :mapo, Mapo.Repo, types: ...` (config/config.exs), NO como
  argumento de `use Ecto.Repo` en `repo.ex`.** Ponerlo ahí no truena
  ni avisa nada raro al compilar; el error real solo aparece hasta
  que se intenta leer/escribir una columna `geometry`
  (`Postgrex.QueryError: type 'geometry' can not be handled by the
  types module Postgrex.DefaultTypes`), que además pasa por el pool
  de conexiones y desconecta la conexión activa. Costó una vuelta
  completa de tests fallando para diagnosticarlo.
- **Autorización de un solo recurso (ej. `get_sesion!`) en dos pasos
  separados (buscar, luego autorizar) revela más de lo necesario**:
  alguien sin acceso puede distinguir "no existe" (`Ecto.NoResultsError`
  del primer paso) de "existe pero no es tuyo" (`MatchError` del
  segundo). La corrección es una sola consulta con join contra la
  membresía (mismo patrón que ya usaba `Teams.get_team!`), para que
  ambos casos regresen exactamente el mismo error. Vale la pena
  revisar esto en cualquier `get_*!` nuevo que dependa de una relación
  indirecta (a través de otra tabla) para la autorización, no solo de
  una columna directa en el propio registro.
- **`mix deps.get` avisó de una vulnerabilidad real y no relacionada**
  (`mix hex.audit`, no solo `deps.get`, da el detalle completo): dos
  CVEs en `bandit` (el servidor HTTP), una de severidad alta
  (agotamiento de recursos vía ventana de HTTP/2, deja procesos Plug
  atorados indefinidamente). Se corrigió con `mix deps.update bandit`
  (había una version parchada, publicada el mismo dia). Vale la pena
  correr `mix hex.audit` de cuando en cuando, no solo cuando `deps.get`
  lo menciona de pasada.
