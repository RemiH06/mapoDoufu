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

## :compass: ¿Qué es Mapo?

Gaiarda contesta "qué hay": descarga y organiza datos abiertos de
México en un dashboard explorable. **Mapo contesta "qué deberías hacer
con eso"**: cruza esos datos para responder preguntas con una decisión
implícita adentro (dónde poner un negocio, en qué colonias buscar
cierto perfil de gente, dónde le faltan servicios públicos al
gobierno).

**Mapo, powered by Gaiarda.**

Dos modos de uso:

- **Modo técnico**: mapas personalizables, capas y estadísticas
  cruzadas de múltiples fuentes, isócronas y otras vistas espaciales.
- **Modo buscador**: preguntas simples en lenguaje natural acotado
  ("¿dónde pongo una floristería?"), resueltas por un sistema experto
  contra la misma data del modo técnico, sin generar texto libre.

El detalle completo de producto vive en `MAPO_FUNDAMENTOS.md` (fuera
de este repo público, documento de trabajo interno).

## :building_construction: Estructura de este repositorio

```
.
├── mapo/          → app Elixir + Phoenix (LiveView). Sesiones,
│                     autenticación, colaboración en tiempo real sobre
│                     el mismo mapa. La cara al usuario.
├── mapo_core/     → servicio Python. Motor de decisión: VRP
│                     (logística de múltiples vehículos), isócronas,
│                     y cliente de la API de Gaiarda para los datos ya
│                     existentes.
├── design/        → sistema de diseño (temas metro/elixir, paletas
│                     claro/oscuro, logo). Ver design/README.md.
└── docker-compose.yml
```

`mapo` y `mapo_core` se hablan por HTTP. `mapo_core` no vuelve a
descargar ni normalizar nada que Gaiarda ya resuelve, solo agrega lo
que Gaiarda no necesita: el motor de logística comercial.

## :rocket: Arranque rápido

```bash
docker compose up
```

Levanta la base de datos (Postgres, para sesiones de Mapo), el
servicio de datos/decisión en Python y la app Elixir/Phoenix.

## :art: Identidad visual

Dos temas, mismo lenguaje visual, pensados para partes distintas del
producto:

- **metro**: tema principal, para prácticamente toda la app.
- **elixir** (sin relación con el lenguaje Elixir): para el apartado
  de análisis de mapas/datos y cualquier dashboard.

Ambos con modo claro/oscuro y animaciones de fondo, que se pueden
apagar desde configuración. Ver `design/`.

## Licencia

MIT (ver [`LICENSE`](LICENSE)).