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
- [vista-riesgos.md](producto/vista-riesgos.md): `/riesgos`, cada peligro de una zona por separado con la gente dentro y cerca.
- [comparacion-ciudades.md](producto/comparacion-ciudades.md): calor, dosel, NDVI, censo y marginación (2020, y 2010 en tablas) por AGEB de la ZMG y seis metrópolis más, con la entrega para ArcGIS y Mapo y cómo comprobar cada número.
- [vista-vivienda.md](producto/vista-vivienda.md): acetato de vivienda en `/mapa`, un indicador de una sola fuente a la vez (por municipio, o el valor de suelo por AGEB) y la ficha con SHF, SNIIV, Intercensal y ENVI por separado.
- [precio-estimado.md](producto/precio-estimado.md): precio de vivienda estimado por AGEB como rango con cobertura medida; hecha la forma (catastro y rango conformal, validados por bloques), pendiente la escala de mercado.
- [citar.md](producto/citar.md): enlace permanente de `/mapa` y `/riesgos` (qué parámetros guarda y cómo se validan) y "Cómo citar" con la fuente original primero, en APA y BibTeX, con la versión de la tabla.
- [accesibilidad.md](producto/accesibilidad.md): `/accesibilidad`, cuánta gente vive a más de N minutos a pie o en auto de cada servicio (salud, escuelas por nivel, supermercado, transporte masivo), cada uno con su grupo de población; cómo se calcula por estado y por qué las escuelas solo desde AGEB.
- [transporte.md](producto/transporte.md): acetato "Transporte público" en `/mapa` (rutas del GTFS con cada cuánto pasan en hora pico, o de OSM sin horarios) y las paradas como servicio en `/accesibilidad`.
- [datos-propios.md](producto/datos-propios.md): archivos del equipo (tabla, vectorial, ráster) como acetato, su cruce con fuentes públicas, la distancia entre capas y el valor de un ráster: formatos, límites, ubicación, procedencia, permisos y qué se guarda.

## Arquitectura

- [stack.md](arquitectura/stack.md): por qué Elixir + Python + Postgres/PostGIS, OR-Tools para VRP, OSRM para isócronas, y lo que se descartó.
- [estructura.md](arquitectura/estructura.md): carpetas del repo y cómo se hablan `mapo`, `mapo_core` y la base.
- [decisiones.md](arquitectura/decisiones.md): Gaiarda vendorizado, sin puntaje único, solo español, identidad visual.

## Fuentes de datos

Una por fuente: de dónde sale, cómo se carga, sus problemas conocidos y las cifras reales con que se validó.

- [plano.md](fuentes/plano.md): el mapa base de todas las vistas (Protomaps recortado a México, servido por Mapo), cómo se extrae y sus licencias.
- [geo-censo.md](fuentes/geo-censo.md): marco geoestadístico (estados, municipios, AGEBs) y censo de población.
- [denue.md](fuentes/denue.md): negocios (comercio), desde la descarga masiva por estado.
- [enigh.md](fuentes/enigh.md): ingreso y gasto de hogares (consumo).
- [enoe.md](fuentes/enoe.md): ocupación y empleo (laboral).
- [sesnsp.md](fuentes/sesnsp.md): incidencia delictiva (seguridad), carga manual.
- [osrm.md](fuentes/osrm.md): ruteo por carretera, demo público contra servidor propio, y el perfil a pie por estado.
- [ambientales.md](fuentes/ambientales.md): agua, acuíferos, descargas, emisiones, uso de suelo, incendios y más, en crudo, y cómo recortarlas a una zona como paquete para SIG.
- [localidades.md](fuentes/localidades.md): las 189,432 localidades del Censo 2020 (ITER) de todo el país, con su punto, validadas contra los totales; destino de la distancia en Mapo.
- [edificios.md](fuentes/edificios.md): huellas de edificios de Overture Maps (OSM, Microsoft y Google) recortadas a una caja, con su validación contra el censo por manzana.
- [iieg-oferta.md](fuentes/iieg-oferta.md): precios de oferta de vivienda del IIEG por anuncio y colonia, seis municipios de la ZMG; el MEDV del dataset de vivienda desde la v8.
- [shf.md](fuentes/shf.md): índice SHF de precios de la vivienda, trimestral desde 2005, por estado, 8 zonas metropolitanas y 74 municipios.
- [sniiv.md](fuentes/sniiv.md): créditos y subsidios para vivienda por municipio y año (SNIIV), por organismo, destino y segmento de valor.
- [eic2025.md](fuentes/eic2025.md): Intercensal 2025, bloque de vivienda por municipio (tenencia, escrituras, servicios) con su precisión.
- [acuiferos.md](fuentes/acuiferos.md), [renameca.md](fuentes/renameca.md), [repda.md](fuentes/repda.md), [retc.md](fuentes/retc.md), [siap.md](fuentes/siap.md), [firms.md](fuentes/firms.md), [uso-suelo.md](fuentes/uso-suelo.md), [anp.md](fuentes/anp.md), [sequia.md](fuentes/sequia.md), [defunciones.md](fuentes/defunciones.md): fuentes ambientales cargadas (sesión 22).
- [clues.md](fuentes/clues.md): establecimientos de salud de la DGIS con institución, tipo, estatus y coordenadas; qué es público y a quién atiende, y las coordenadas y claves mal capturadas.
- [imss.md](fuentes/imss.md): empleo formal del IMSS por municipio y grupo de actividad (puestos, salario de cotización), con la equivalencia de claves IMSS a INEGI; validado al puesto contra el IMSS y el IIEG.
- [envi.md](fuentes/envi.md): ENVI 2020, renta mensual y valor estimado de la vivienda por estado.
- [gtfs.md](fuentes/gtfs.md): los 17 GTFS abiertos de México (dónde se buscaron, productor y licencia de cada uno), cómo se cuenta la frecuencia en hora pico, la frecuencia de relleno, y las rutas de OSM de todo el país como respaldo.
- [censos-economicos.md](fuentes/censos-economicos.md): Censos Económicos 2024 por municipio y sector (unidades, personal, remuneraciones, ingresos, valor agregado de 2023), validados contra la monografía de INEGI.
- [efipem.md](fuentes/efipem.md): finanzas públicas municipales de INEGI, ingresos y egresos por capítulo y predial, 2019 a 2023.
- [rezago-social.md](fuentes/rezago-social.md): Grado de Rezago Social por AGEB urbana 2020 de CONEVAL, validado contra su comunicado.
- [cngmd.md](fuentes/cngmd.md): Censo Nacional de Gobiernos Municipales 2025, por ahora los instrumentos de planeación territorial de cada municipio.
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
- [Fuentes ambientales y vista de riesgos, noviembre 2026](historial/2026-11-fuentes-ambientales-riesgos.md)
- [Patrones por rubro, noviembre 2026](historial/2026-11-patrones-rubro.md)
- [Distancia entre capas, noviembre 2026](historial/2026-11-distancia-capas.md)
- [Frontera agrícola y ráster con valor por píxel, noviembre 2026](historial/2026-11-raster-valores.md)
- [Fechas, marginación y colonias, noviembre 2026](historial/2026-11-fechas.md)
- [Fuentes de vivienda, noviembre 2026](historial/2026-11-fuentes-vivienda.md)
- [Vista de vivienda y especies nativas, noviembre 2026](historial/2026-11-vista-vivienda-especies.md)
- [Precio estimado: forma y rango, noviembre 2026](historial/2026-11-precio-estimado.md)
- [Cómo citar y enlaces permanentes, noviembre 2026](historial/2026-11-citar.md)
- [Empleo formal del IMSS, noviembre 2026](historial/2026-11-empleo-imss.md)
- [Accesibilidad a servicios, noviembre 2026](historial/2026-11-accesibilidad.md)
- [Transporte público, noviembre 2026](historial/2026-11-transporte.md)
- [Fuentes económicas y municipales, noviembre 2026](historial/2026-11-fuentes-municipales.md)
- [Plano común con MapLibre y mapa base propio, noviembre 2026](historial/2026-11-plano-maplibre.md)

## Gaiarda

- [referencia.md](gaiarda/referencia.md): resumen de Gaiarda 0.3.0, sus fuentes y lecciones.
- [rutas.md](gaiarda/rutas.md): cómo calcula rutas de turismo (TSP), base de la logística de Mapo.
