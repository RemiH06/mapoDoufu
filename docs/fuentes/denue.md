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

## Rubros para el buscador (2026-11-03)

Las 918 clases de actividad de Jalisco quedaron clasificadas en sector
y rubro en `mapo_core/src/mapo_core/rubros/clases.csv` (detalle en
`../producto/buscador.md`). Al cargar otro estado, `cli denue` avisa
de las clases que todavía no están en la tabla.

## Descarga masiva en vez de la API (2026-11-17, sesión 18)

La carga dejó de paginar `BuscarEntidad`: **su paginación no es estable.** La
misma página pedida dos veces trae otro orden, y en una de tres pruebas, 5 de
1,000 negocios distintos. Al recargar Jalisco por la API llegaron 401,813
registros pero solo 395,704 ids distintos: 6,109 repetidos y 6,109 que nunca
llegaron. La carga de agosto había salido completa (401,813 distintos), así que
el problema no siempre se nota.

Ahora `cli denue --estado NN` baja
`https://www.inegi.org.mx/contenidos/masiva/denue/denue_NN_csv.zip` (40 MB
para Jalisco, 215 MB descomprimido), lee el CSV en Latin-1 sin cargarlo entero
en memoria y reemplaza los negocios del estado. Es la misma edición que sirve la
API (05/2026, 401,813 negocios en Jalisco, ningún id repetido), no pide token y
tarda unos 5 minutos en vez de media hora. `--archivo` usa un ZIP ya bajado.

- **Cada carga reemplaza el estado.** Es una transacción: si se corta, no queda
  nada a medias. Al terminar borra los negocios del estado que ya no vinieron,
  salvo que sean más del 10 %: eso huele a archivo cortado y se avisa sin
  borrar. Si un id viene dos veces, no carga nada.
- **Mismas columnas que antes**, con los nombres del CSV: `nom_estab`,
  `nombre_act` (mismo texto que `Clase_actividad` de la API: las 918 clases
  empatan con `clases.csv` sin cambios), `per_ocu`, `nom_vial`, `nomb_asent`,
  `tipoUniEco`. `ubicacion` se arma con localidad, municipio y estado.
- **`cve_mun` y `cve_ageb` siguen saliendo por geometría**, aunque el CSV traiga
  las claves: así `cve_ageb` solo existe donde hay AGEB urbana cargada. Si un
  negocio cambió de coordenadas, se recalculan.
- **El CSV trae más de lo que se guarda:** código SCIAN (`codigo_act`), manzana
  y `fecha_alta` (año y mes). La fecha sirve al estudio de sobrevivencia.
- `/buscador/zonas` y `/buscador/patron` guardan resultados en memoria: después
  de una carga, reiniciar `mapo_core`.

## CLEE y plaza o mercado (2026-11-17, sesión 18)

Columnas nuevas, que la carga por API tiraba:

| Columna | CSV masivo | `BuscarEntidad` | `Buscar` |
|---|---|---|---|
| `clee` | `clee` | `CLEE` | `CLEE` |
| `tipo_plaza` | `tipoCenCom` | `tipo_corredor_industrial` | `TipoCentroComercial` |
| `plaza` | `nom_CenCom` | `nom_corredor_industrial` | `CentroComercial` |
| `numero_local` | `num_local` | `numero_local` | `NumLocal` |

En la API los nombres engañan: no son corredores industriales sino la plaza,
mercado o edificio donde está el local. Vacío se guarda como `NULL`.

- **Cobertura en Jalisco:** 29,785 de 401,813 (7.4 %). Los más comunes: centro
  y plaza comercial (11,284), mercado público (10,492), edificio comercial y de
  servicios (4,423), hospital o clínica (996), pasaje y andador comercial.
  Sin marca no quiere decir que el local esté en la calle: las 29 dulcerías
  alrededor de Santa Tere vienen sin ella. La usa el patrón del rubro
  (`../producto/buscador.md`).
- **`CLEE`:** 28 caracteres, uno por negocio. Es la llave para empatar
  ediciones de DENUE en el estudio de sobrevivencia; falta verificar que sea
  estable entre ediciones.
