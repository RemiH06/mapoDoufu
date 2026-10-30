# Estructura del repo

```
.
├── README.md
├── LICENSE                  MIT
├── docker-compose.yml       db (Postgres + PostGIS) + mapo_core + mapo
├── docs/                    esta documentación
├── design/                  favicon.svg (definitivo), mapo-logo.png (boceto),
│                            mesa_planeacion/ (prototipos de la mesa y el generador
│                            del plano de la portada), demos de tema viejas
├── mapo/                    Elixir + Phoenix LiveView (módulos Mapo / MapoWeb)
│   ├── lib/mapo/            contextos: Accounts, Teams, Sesiones, Notas, MapoCore (cliente HTTP)
│   ├── lib/mapo_web/live/   una carpeta por pantalla (mapa_live, perfil_live, logistica_live, ...)
│   │                        y marcas.ex (eventos de marcas, compartido por /mapa y la sesión)
│   └── assets/js/           hooks de Leaflet, marcas.js (dibujo de marcas) y la portada (sin npm; Leaflet y anime.js
│                            vendorizados en assets/vendor/)
└── mapo_core/               Python + FastAPI. Datos y motor de decisión
    ├── src/mapo_core/
    │   ├── server.py        rutas HTTP
    │   ├── cli.py           carga de fuentes (python -m mapo_core.cli ...)
    │   ├── db.py            conexión psycopg v3 a la misma Postgres, sin ORM
    │   ├── *_downloader.py  una por fuente (geo, censo, denue, enigh, enoe)
    │   ├── sesnsp_ingesta.py  carga manual de SESNSP
    │   ├── vrp.py  isocronas.py  voronoi.py  coloreado_mapa.py  enigh_resumen.py
    │   └── osrm_client.py
    ├── tests/
    └── data/                archivos descargados a mano (gitignorado)
```

## Cómo se hablan las piezas

- `mapo` es la única cara al usuario. Autenticación, equipos, sesiones
  colaborativas (PubSub + Presence) y todas las pantallas.
- `mapo` le pide a `mapo_core` por HTTP (`Mapo.MapoCore`, con `Req`,
  URL en `MAPO_CORE_URL`) todo lo que es cálculo o datos de fuentes.
- Las dos piezas comparten la misma Postgres: `mapo` usa Ecto para sus
  tablas (usuarios, equipos, sesiones, anotaciones, notas_perfil); `mapo_core` usa
  `psycopg` directo para las tablas de fuentes (`entidades`,
  `municipios`, `agebs`, `fuente_*`, `descargas_checkpoint`).
- `mapo_core` usa OSRM (ruteo por carretera) para VRP e isócronas. Ver
  `../fuentes/osrm.md`.
- Gaiarda no corre en ningún lado: su código se copió y adaptó dentro
  de `mapo_core`. Ver `decisiones.md`.
