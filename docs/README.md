# Documentación de Mapo

## Producto

- [vision.md](producto/vision.md): qué es Mapo, su relación con Gaiarda, modos de uso y preguntas que debe poder responder.
- [rubros.md](producto/rubros.md): enfoques temáticos con su fuente y los casos de ejemplo por rubro.
- [requisitos.md](producto/requisitos.md): requerimientos funcionales y no funcionales, con su estado.

## Arquitectura

- [stack.md](arquitectura/stack.md): por qué Elixir + Python + Postgres/PostGIS, OR-Tools para VRP, OSRM para isócronas, y lo que se descartó.
- [estructura.md](arquitectura/estructura.md): carpetas del repo y cómo se hablan `mapo`, `mapo_core` y la base.
- [decisiones.md](arquitectura/decisiones.md): Gaiarda vendorizado, sin puntaje único, solo español, identidad visual.

## Fuentes de datos

Una por fuente: de dónde sale, cómo se carga, sus problemas conocidos y las cifras reales con que se validó.

- [geo-censo.md](fuentes/geo-censo.md): marco geoestadístico (estados, municipios, AGEBs) y censo de población.
- [denue.md](fuentes/denue.md): negocios (comercio).
- [enigh.md](fuentes/enigh.md): ingreso y gasto de hogares (consumo).
- [enoe.md](fuentes/enoe.md): ocupación y empleo (laboral).
- [sesnsp.md](fuentes/sesnsp.md): incidencia delictiva (seguridad), carga manual.
- [osrm.md](fuentes/osrm.md): ruteo por carretera, demo público contra servidor propio.

## Desarrollo

- [desarrollo.md](desarrollo.md): levantar, probar, cargar datos y problemas de Docker/Phoenix ya resueltos.

## Historial

Qué se construyó en cada etapa, por qué así y qué bugs reales aparecieron.

- [Fase 0: fundación](historial/fase-0-fundacion.md)
- [Fase 1: autenticación](historial/fase-1-autenticacion.md)
- [Fase 2: equipos y colaboración](historial/fase-2-equipos-y-colaboracion.md)
- [Fase 3: mapo_core, OSRM y VRP](historial/fase-3-mapo-core.md)
- [Fase 4: isócronas](historial/fase-4-isocronas.md)
- [Fase 5: modo técnico](historial/fase-5-modo-tecnico.md)
- [Pulido de interfaz, agosto 2026](historial/2026-08-pulido.md)
- [Pantalla de logística, septiembre 2026](historial/2026-09-logistica.md)
- [Limpieza de código, octubre 2026](historial/2026-10-limpieza.md)

## Gaiarda

- [referencia.md](gaiarda/referencia.md): resumen de Gaiarda 0.3.0, sus fuentes y lecciones.
- [rutas.md](gaiarda/rutas.md): cómo calcula rutas de turismo (TSP), base de la logística de Mapo.
