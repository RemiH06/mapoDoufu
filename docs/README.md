# Documentación de Mapo

## Producto

- [vision.md](producto/vision.md): qué es Mapo, su relación con Gaiarda, modos de uso y preguntas que debe poder responder.
- [rubros.md](producto/rubros.md): enfoques temáticos con su fuente y los casos de ejemplo por rubro.
- [requisitos.md](producto/requisitos.md): requerimientos funcionales y no funcionales, con su estado.
- [buscador.md](producto/buscador.md): intenciones y parámetros del modo buscador, zonas candidatas y la tabla de rubros de DENUE.
- [pipeline-datos.md](producto/pipeline-datos.md): dónde se rompe la obtención y lectura de cada fuente, cómo detectarlo sin una persona y qué hacer; base para automatizar.
- [dataset-vivienda.md](producto/dataset-vivienda.md): tabla tipo Boston Housing por AGEB de una zona metropolitana, equivalencias, método de cada columna y el pipeline de valor catastral.
- [sobrevivencia.md](producto/sobrevivencia.md): qué negocios de DENUE 2019 siguen en 2024 y si les va mejor juntos, en la ZMG y en los 32 estados; estudio en notebook, aparte de Mapo.
- [colonias.md](producto/colonias.md): cómo armar el polígono de una colonia en cualquier municipio (oficial, OSM, votación de direcciones sobre manzanas o dibujo del equipo), con el prototipo de López Cotilla.
- [plan-nacional.md](producto/plan-nacional.md): qué falta para tener el paquete ambiental y el dataset de vivienda en todo el país, y en qué orden.
- [vista-vivienda.md](producto/vista-vivienda.md): acetato de vivienda por municipio en `/mapa`, un indicador de una sola fuente a la vez y la ficha con SHF, SNIIV, Intercensal y ENVI por separado.
- [datos-propios.md](producto/datos-propios.md): archivos del equipo (tabla, vectorial, ráster) como acetato, su cruce con fuentes públicas, la distancia entre capas y el valor de un ráster: formatos, límites, ubicación, procedencia, permisos y qué se guarda.

## Arquitectura

- [stack.md](arquitectura/stack.md): por qué Elixir + Python + Postgres/PostGIS, OR-Tools para VRP, OSRM para isócronas, y lo que se descartó.
- [estructura.md](arquitectura/estructura.md): carpetas del repo y cómo se hablan `mapo`, `mapo_core` y la base.
- [decisiones.md](arquitectura/decisiones.md): Gaiarda vendorizado, sin puntaje único, solo español, identidad visual.

## Fuentes de datos

Una por fuente: de dónde sale, cómo se carga, sus problemas conocidos y las cifras reales con que se validó.

- [geo-censo.md](fuentes/geo-censo.md): marco geoestadístico (estados, municipios, AGEBs) y censo de población.
- [denue.md](fuentes/denue.md): negocios (comercio), desde la descarga masiva por estado.
- [enigh.md](fuentes/enigh.md): ingreso y gasto de hogares (consumo).
- [enoe.md](fuentes/enoe.md): ocupación y empleo (laboral).
- [sesnsp.md](fuentes/sesnsp.md): incidencia delictiva (seguridad), carga manual.
- [osrm.md](fuentes/osrm.md): ruteo por carretera, demo público contra servidor propio.
- [ambientales.md](fuentes/ambientales.md): agua, acuíferos, descargas, emisiones, uso de suelo, incendios y más, en crudo, y cómo recortarlas a una zona como paquete para SIG.
- [localidades.md](fuentes/localidades.md): las 189,432 localidades del Censo 2020 (ITER) de todo el país, con su punto, validadas contra los totales; destino de la distancia en Mapo.
- [edificios.md](fuentes/edificios.md): huellas de edificios de Overture Maps (OSM, Microsoft y Google) recortadas a una caja, con su validación contra el censo por manzana.
- [shf.md](fuentes/shf.md): índice SHF de precios de la vivienda, trimestral desde 2005, por estado, 8 zonas metropolitanas y 74 municipios.
- [sniiv.md](fuentes/sniiv.md): créditos y subsidios para vivienda por municipio y año (SNIIV), por organismo, destino y segmento de valor.
- [eic2025.md](fuentes/eic2025.md): Intercensal 2025, bloque de vivienda por municipio (tenencia, escrituras, servicios) con su precisión.
- [envi.md](fuentes/envi.md): ENVI 2020, renta mensual y valor estimado de la vivienda por estado.
- [especies.md](fuentes/especies.md): plantas vasculares registradas en GBIF alrededor de una zona, con su estatus en México (Enciclovida) y el cruce con GRIIS, para elegir árboles nativos.
- [imagenes.md](fuentes/imagenes.md): compuestos de Sentinel-2 y Landsat y WorldCover por zona, desde el STAC de Planetary Computer.

## Guías

- [replicar.md](guias/replicar.md): rehacer el paquete ambiental o el dataset de vivienda para otra zona, con la procedencia de cada dato, y subirlos a Mapo.

## Desarrollo

- [desarrollo.md](desarrollo.md): levantar, probar, cargar datos y problemas de Docker/Phoenix ya resueltos.
- [despliegue.md](despliegue.md): compose de producción, secretos, acceso por Tailscale, correo a mano, migraciones, primera carga de datos, respaldos y OSRM propio.

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
- [Rendimiento, octubre 2026](historial/2026-10-rendimiento.md)
- [Concepto visual, octubre 2026](historial/2026-10-concepto-visual.md)
- [Rediseño del núcleo, octubre 2026](historial/2026-10-rediseno-nucleo.md)
- [Rediseño del resto, octubre 2026](historial/2026-10-rediseno-resto.md)
- [Capa "Tus marcas", octubre 2026](historial/2026-10-tus-marcas.md)
- [Revisión contra anti-vibecode, octubre 2026](historial/2026-10-anti-vibecode.md)
- [Preparar el hosteo, octubre 2026](historial/2026-10-hosteo.md)
- [Primer despliegue, octubre 2026](historial/2026-10-despliegue.md)
- [Fase 6a: intenciones y rubros, noviembre 2026](historial/2026-11-intenciones.md)
- [Fase 6b: buscador, noviembre 2026](historial/2026-11-buscador.md)
- [Fase 7: casos por rubro, noviembre 2026](historial/2026-11-casos-rubro.md)
- [Recomendaciones: zonas candidatas, noviembre 2026](historial/2026-11-zonas-candidatas.md)
- [Datos propios, noviembre 2026](historial/2026-11-datos-propios.md)
- [Cruce de datos propios, noviembre 2026](historial/2026-11-cruce.md)
- [Pasada final de diseño, noviembre 2026](historial/2026-11-diseno-final.md)
- [Pasada de seguridad, noviembre 2026](historial/2026-11-seguridad.md)
- [Patrones por rubro, noviembre 2026](historial/2026-11-patrones-rubro.md)
- [Distancia entre capas, noviembre 2026](historial/2026-11-distancia-capas.md)
- [Frontera agrícola y ráster con valor por píxel, noviembre 2026](historial/2026-11-raster-valores.md)
- [Fechas, marginación y colonias, noviembre 2026](historial/2026-11-fechas.md)
- [Fuentes de vivienda, noviembre 2026](historial/2026-11-fuentes-vivienda.md)
- [Vista de vivienda y especies nativas, noviembre 2026](historial/2026-11-vista-vivienda-especies.md)

## Gaiarda

- [referencia.md](gaiarda/referencia.md): resumen de Gaiarda 0.3.0, sus fuentes y lecciones.
- [rutas.md](gaiarda/rutas.md): cómo calcula rutas de turismo (TSP), base de la logística de Mapo.
