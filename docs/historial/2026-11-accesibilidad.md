# Accesibilidad a servicios (noviembre 2026, sesión 26)

Cuánta gente de un municipio vive a más de N minutos, a pie o en auto, de un centro de
salud, una clínica del IMSS, un hospital público, una escuela pública por nivel, un
supermercado y una estación de transporte masivo. Ficha en
`../producto/accesibilidad.md`; fuente nueva en `../fuentes/clues.md`.

## Qué se hizo

- **OSRM a pie** para Jalisco (`scripts/osrm/pie.sh`, `foot.lua`, OSM del 2026-11-20) y
  servicio `osrm_pie` en producción con perfil `calculo`, que solo corre al calcular.
- **CLUES** de la DGIS: `mapo_core/clues.py`, `cli clues`, tabla `fuente_clues`.
- **Cálculo por estado:** `mapo_core/accesibilidad.py` y `cli accesibilidad`. Tablas
  `accesibilidad_minutos`, `accesibilidad_destinos` y `accesibilidad_cargas`.
- **Reuso:** `zonas.minutos_por_calle` (antes privada) dice cuál destino quedó más cerca
  y reintenta lotes; `osrm_client.duraciones_matriz` suma el tramo al camino con
  `acercamiento_kmh`.
- **Consulta:** `GET /accesibilidad/zona` y la vista `/accesibilidad` ("Servicios" en el
  menú), con el plano por minutos al servicio elegido, enlace permanente y "Cómo citar"
  (referencia nueva `clues`).
- Pruebas: `test_accesibilidad.py` (8) y la de LiveView (9). Script de capturas
  `scripts/capturas/accesibilidad.js`.

## Por qué así

- **Vista propia, no acetato.** Son nueve servicios; la regla de la 23 pide vista nueva
  desde tres capas. Comparte la hoja y el estilo de `/riesgos`.
- **Calcular una vez, restar en pantalla.** Mapo guarda los minutos de cada lugar y
  manda la gente a cada minuto de 0 a 120. Mover el umbral no consulta: es una resta.
- **CLUES para salud, no DENUE.** DENUE no dice el tipo de unidad ni si opera, y junta
  instituciones que atienden a públicos distintos. El CLUES sí: la clínica del IMSS
  cuenta solo a la gente afiliada al IMSS.
- **Escuelas solo desde AGEB.** Contra la SEP 2025-2026, DENUE tiene 801 de 873 escuelas
  públicas de básica en Guadalajara pero 5 de 218 en Mezquitic. Calcular desde las
  rancherías inventaría lejanía; se dice cuánta gente queda fuera.
- **Un OSRM a pie por estado.** El país a pie pediría unos 18 GB al preparar; Jalisco
  pidió 2.4 GB y 34 s.
- **Nunca el demo público** para esto: el comando exige un OSRM propio para cada modo.

## Bugs reales

- **Geofabrik cambió la ruta de México** a `north-america/mexico/`, y `mexico-latest`
  redirige al archivo del día aunque todavía no exista (404). El script usa una fecha
  fija.
- **Coordenadas y claves mal capturadas en el CLUES:** la "UMF 55 Guadalajara" cae en
  Tuxcueca y la "UMF 82 Unión de Tula" trae la clave de otro municipio. Regla de 1 km
  con excepción por nombre.
- **"En el municipio" contaba destinos de fuera** que quedaron como el más cercano de
  algún lugar (Mezquitic: 18 centros de salud en vez de 14). Ahora se cuentan solo los
  que caen dentro; los de fuera siguen en el plano.
- **El encuadre del plano** suponía la hoja a la izquierda; con el celular acostado va a
  la derecha y el municipio quedaba tapado. Ahora se mide la hoja.
- **En dev, Phoenix dejó de responder HTML** tras un `mix compile` manual mientras el
  reloader recompilaba: lo estático salía y las páginas no. Un reinicio del contenedor
  lo resolvió.

## Despliegue

Producción en `e2aecec` el 2026-11-22 (revertir: `deploy-20261122`; sin migración, las
tablas las crea `mapo_core`). CLUES cargado y los 9 servicios calculados a pie y en auto
para Jalisco el mismo día.
