![Made with Python](https://forthebadge.com/images/badges/made-with-python.svg)
[![forthebadge](https://forthebadge.com/badges/made-with-elixir.svg)](https://forthebadge.com)
![Uses Git](http://ForTheBadge.com/images/badges/uses-git.svg)
![Build with Love](http://ForTheBadge.com/images/badges/built-with-love.svg)

```ascii
███╗   ███╗ █████╗ ██████╗  ██████╗
████╗ ████║██╔══██╗██╔══██╗██╔═══██╗
██╔████╔██║███████║██████╔╝██║   ██║
██║╚██╔╝██║██╔══██║██╔═══╝ ██║   ██║
██║ ╚═╝ ██║██║  ██║██║     ╚██████╔╝
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝      ╚═════╝
        by Hex (@RemiH06)          version 0.1.0
```

![Maintained](https://img.shields.io/badge/Maintained%3F-yes-green.svg?style=for-the-badge)
![MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)

## Qué es Mapo

Mapo es un sistema de apoyo a decisiones construido sobre datos
abiertos de México. A partir de información geoespacial, demográfica,
económica y de seguridad, ayuda a responder preguntas que ya traen una
decisión implícita: dónde conviene abrir un negocio, en qué colonias
buscar cierto perfil de población, o dónde le faltan servicios
públicos al gobierno.

Se construye sobre Gaiarda, el proyecto hermano que descarga y
organiza esos datos. Gaiarda contesta qué hay; Mapo contesta qué
conviene hacer con eso.

**Mapo, powered by Gaiarda.**

Ofrece dos formas de consultarlo:

- **Modo técnico**: mapas personalizables, con capas y estadísticas
  cruzadas de múltiples fuentes, isócronas y otras vistas espaciales.
- **Modo buscador**: preguntas simples en lenguaje natural acotado
  (por ejemplo, "¿dónde pongo una floristería?"), resueltas por un
  sistema experto sobre los mismos datos del modo técnico, sin generar
  texto libre.

La documentación completa (producto, arquitectura, fuentes de datos e
historial) vive en [`docs/`](docs/README.md).

## Estructura del repositorio

```
.
├── mapo/          → app Elixir + Phoenix (LiveView). Sesiones,
│                     autenticación, colaboración en tiempo real sobre
│                     el mismo mapa. La cara al usuario.
├── mapo_core/     → servicio Python. Datos y motor de decisión:
│                     fuentes de INEGI y SESNSP, VRP (logística de
│                     múltiples vehículos), isócronas, Voronoi.
├── design/        → logo y demos de los temas metro/elixir.
├── docs/          → documentación.
└── docker-compose.yml
```

`mapo` y `mapo_core` se comunican por HTTP y comparten la misma
Postgres con PostGIS. El código de descarga de datos viene de Gaiarda,
copiado y adaptado dentro de `mapo_core`: Mapo no depende de que
Gaiarda esté corriendo.

## Arranque rápido

```bash
docker compose up
```

Levanta la base de datos (Postgres con PostGIS), el servicio de datos
y decisión en Python, y la aplicación Elixir/Phoenix en
`http://localhost:1864`. Cómo cargar datos y correr los tests:
[`docs/desarrollo.md`](docs/desarrollo.md).

## Identidad visual

Dos temas, con el mismo lenguaje visual, pensados para partes
distintas del producto:

- **metro**: tema principal, usado en prácticamente toda la
  aplicación.
- **elixir** (sin relación con el lenguaje Elixir): reservado para el
  apartado de análisis de mapas y datos, y para cualquier dashboard.

Ambos incluyen modo claro/oscuro y animaciones de fondo, que se pueden
desactivar desde configuración. Ver `design/`.

## Licencia

MIT (ver [`LICENSE`](LICENSE)).
