# Fase 0: Fundación


- Definir qué es Mapo, modos de uso, enfoques temáticos, casos de
  ejemplo iniciales
- Decidir stack: Elixir/Phoenix (sesiones, LiveView) + Python
  (datos/decisión), todo en Docker
- `git init`, README público, LICENSE (MIT), `.gitignore`
- Esqueleto `mapo_core/` (Python, FastAPI, `/salud` respondiendo), con
  test pasando
- Esqueleto `mapo/` (Elixir + Phoenix, LiveView, Ecto/Postgres,
  tailwind + daisyui), generado con `mix phx.new`
- `docker-compose.yml` con los tres servicios (`db`, `mapo_core`,
  `mapo`), probado de punta a punta: los tres arrancan y responden
- Assets de diseño (favicon, logo, temas metro/elixir) movidos a
  `design/`
