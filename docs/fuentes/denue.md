# DENUE (comercio)

## Vendorización DENUE, comercio (2026-08-28)

Mismo patrón que geoestadístico + censo, un jalón más de la corrección
de arquitectura de arriba:

- `mapo_core/denue_downloader.py`, vendorizado de
  `gaiarda/src/gaiarda/fuentes/denue/{api,downloader}.py`. Solo usa
  `BuscarEntidad` (no `BuscarAreaAct`, cuyos nombres de campo de
  AGEB/manzana Gaiarda nunca confirmó). Paginación de 1000 en 1000,
  checkpoint por entidad completa (`denue:{cve_ent}`, mismo grano que
  Gaiarda). Requiere token gratuito de INEGI
  (`GAIARDA_DENUE_TOKEN`, ya en `mapo_core/.env`, gitignored)
- El geocódigo (`cve_mun`/`cve_ageb`) no viene en la respuesta de
  INEGI: se rellena con un `UPDATE ... FROM municipios/agebs WHERE
  ST_Contains(...)` directo en SQL (reemplaza el `IndiceEspacial`/
  `STRtree` en memoria que usaba Gaiarda, ya no hace falta porque los
  polígonos viven en Postgres)
- `/voronoi/denue` ya no regresa 501: usa negocios reales de la tabla
  `fuente_denue_negocios`, filtrables por `clase_actividad`. 404 si el
  municipio no existe, 422 si hay menos de 3 negocios con esos filtros
  o más de 5,000 (Guadalajara sin filtro son 97,128). Los negocios en
  la misma coordenada comparten celda y la celda trae `num_puntos`
  (`docs/historial/2026-10-rendimiento.md`)
- `/perfil_zona` ahora trae `comercio: {total_negocios,
  top_clases_actividad}` real (antes `comercio_disponible: false`)
- **Probado con datos reales de INEGI, estado 14 (Jalisco)**:
  401,813 negocios descargados, 401,812 con `cve_mun` asignado (el que
  falta es un punto justo en el borde de un municipio). `/voronoi/denue`
  con `clase_actividad=farmacia` en Guadalajara: 1,148 farmacias
  reales, polígonos de Voronoi recortados al polígono real del
  municipio. `/perfil_zona` de Guadalajara: 97,128 negocios,
  encabezados por "tiendas de abarrotes, ultramarinos y misceláneas"
  (6,339): confirmado con `curl` directo, acentos correctos en la
  respuesta (UTF-8 de punta a punta, se descartó un falso positivo de
  doble-decodificación que resultó ser solo un artefacto del `python -m
  json.tool` del lado del host en Windows, no un bug real)
- **Confirmado: DENUE sí cubre seguridad pública**, no hizo falta otra
  fuente. La clase de actividad real
  `Mantenimiento de la seguridad y el orden público` (556 negocios en
  Jalisco) trae Guardia Nacional, Policía Federal, agencias del
  Ministerio Público y Protección Civil y Bomberos: filtrando
  `/voronoi/denue?clase_actividad=` con ese texto ya da estaciones de
  seguridad pública reales, sin vendorizar SESNSP para esto
- 8 tests nuevos en `mapo_core` (99 en total), 229 en `mapo` (fixture
  de `perfil_live/index_test.exs` actualizado al nuevo formato de
  `comercio`)
