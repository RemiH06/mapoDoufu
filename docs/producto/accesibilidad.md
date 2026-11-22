# Accesibilidad a servicios

`/accesibilidad` (en el menú, "Servicios"): se elige un municipio, cómo se llega (a pie
o en auto) y a partir de cuántos minutos se cuenta como lejos, y se ve, servicio por
servicio, cuánta gente de su grupo vive a más de esos minutos del más cercano. Es lo que
un municipio necesita saber y no puede calcular sin un SIG. Nunca un índice: cada
servicio va por separado, con su grupo de población, su fuente y su método.

## Servicios

| Servicio | Destinos | Grupo | Modos |
|---|---|---|---|
| Centro de salud | CLUES: consulta externa en operación, fija, de Secretaría de Salud, IMSS-Bienestar (`IMB`, `IMO`), servicios estatales o municipales; sin UNEME | Personas (`POBTOT`) | pie, auto |
| Clínica del IMSS | CLUES: consulta externa del IMSS ordinario (`IMS`) | Personas afiliadas al IMSS (`PDER_IMSS`) | pie, auto |
| Hospital público | CLUES: hospitalización de las instituciones anteriores, IMSS e ISSSTE | Personas | pie, auto |
| Preescolar, primaria, secundaria y bachillerato públicos | DENUE: escuelas del sector público de cada nivel (secundaria general y técnica; media superior y técnica terminal) | Personas de 3 a 5, 6 a 11, 12 a 14 y 15 a 17 años | pie, auto; solo AGEB |
| Supermercado | DENUE: "Comercio al por menor en supermercados" | Personas | pie, auto |
| Estación de transporte masivo | OSM: Mi Tren y Mi Macro (`transporte_masivo_zmg.csv`, de `scripts/vivienda/transporte_masivo.py`) | Personas | solo a pie |
| Parada de transporte público | GTFS: toda parada con rutas (sesión 27, `transporte.md`) | Personas | solo a pie; solo municipios con GTFS |
| Parada con paso cada 15 minutos o menos | GTFS: alguna ruta pasa 8 veces o más de 7 a 9 de un día hábil | Personas | solo a pie; solo municipios con GTFS |

La clínica del IMSS cuenta solo a sus afiliados porque solo a ellos atiende; el centro de
salud cuenta a todos porque atiende a quien llegue. Sedena, Marina, Pemex, forenses y la
consulta privada no entran (`docs/fuentes/clues.md`).

## Escuelas: solo desde AGEB urbanos

DENUE trae casi todas las escuelas públicas de las ciudades y casi ninguna del campo.
Contra "Principales cifras" de la SEP (ciclo 2025-2026, escuelas públicas de básica,
escolarizada; `scripts/vivienda/sep_cifras.py`) y las de DENUE con el mismo filtro:

| Municipio | SEP | DENUE |
|---|---|---|
| Guadalajara | 873 | 801 |
| Zapopan | 779 | 649 |
| Puerto Vallarta | 246 | 217 |
| Arandas | 171 | 46 |
| Bolaños | 80 | 3 |
| Mezquitic | 218 | 5 |

La SEP cuenta centros de trabajo (dos turnos en un edificio son dos escuelas), así que en
las ciudades la diferencia es en parte eso. En Mezquitic no: la SEP registra escuelas en
94 localidades y DENUE en 3. Calcular desde las rancherías diría que sus niñas y niños
están a horas de la escuela que tienen. Por eso las escuelas se calculan solo desde los
AGEB urbanos, y la gente de las localidades sin AGEB se dice aparte ("viven en 500
localidades sin AGEB: no se calculan"), nunca como lejos.

Para cubrir el campo hace falta la escuela por localidad de la SEP: su consulta da
escuelas por localidad (por nombre, sin clave) y por tipo educativo. Pendiente en
`steps.md`.

## Cómo se calcula

Una vez por estado, con `cli accesibilidad` (minutos guardados en
`accesibilidad_minutos`, destinos en `accesibilidad_destinos`, una fila por servicio y
modo en `accesibilidad_cargas`). Consultar es leer la base.

- **Lugares:** los mismos de `/riesgos`. Cada AGEB urbano con censo cuenta en
  `ST_PointOnSurface` (cae siempre dentro); donde no hay AGEB, el punto de la localidad
  del ITER (sin las de población cero). Jalisco: 14,948 lugares (4,891 AGEB con censo y 10,057
  localidades).
- **Destinos por lugar:** los 10 más cercanos en línea recta (árbol k-d), y de esos el
  menor tiempo por calle con el `table` de OSRM, en lotes de 25 lugares. Es la misma
  función que las zonas candidatas del buscador (`zonas.minutos_por_calle`), que ahora
  también dice cuál destino fue y reintenta un lote que falla (3 veces).
- **El tramo al camino:** OSRM mide desde el punto del camino más cercano a la
  coordenada. Ese tramo, de ida y de llegada, se suma a 5 km/h (`acercamiento_kmh` en
  `osrm_client.duraciones_matriz`): una ranchería a 2 km del camino no queda a cero
  minutos de él.
- **Red:** a pie, OSRM con `foot.lua` sobre Jalisco (OSM del 2026-11-20); en auto, el
  OSRM de producción con `car.lua` (OSM del 2026-08-01), sin tráfico. Detalle en
  `docs/fuentes/osrm.md`.
- **Sin ruta:** si ninguno de los 10 tiene ruta por calle, el lugar queda en `null`: no
  cuenta ni cerca ni lejos y se dice cuánta gente es. En Jalisco, a pie, son 21 a 42
  localidades según el servicio (Cihuatlán y La Huerta, en la costa: caminos que en OSM
  no se conectan con el resto); en auto, ninguna.
- **Nada a medias:** cada servicio y modo se guarda en su propia transacción; si OSRM no
  responde a un lote ni tras reintentar, el comando para y lo ya calculado antes se
  queda.
- **Destinos mal ubicados:** un destino fuera del estado se descarta. En el CLUES,
  además, uno a más de 1 km del municipio que declara, salvo que caiga en un municipio
  cuyo nombre lleve la unidad (ver `docs/fuentes/clues.md`). El comando lista los
  descartados.

## Qué manda mapo_core

`GET /accesibilidad/zona?cve_ent=&cve_mun=&modo=pie|auto`. Por servicio: `total`
(personas del grupo), `sin_ruta`, `reservados` (lugares con `*` de INEGI, no se cuentan
como cero), `sin_calcular` y `sin_calcular_lugares` (escuelas fuera de AGEB) y
`dentro`, la gente a m minutos o menos para cada m de 0 a 120. La pantalla resta: mover
el umbral no vuelve a consultar. También el plano (AGEB simplificados a 0.0001° y
localidades como punto, con los minutos a cada servicio) y los destinos dentro del
municipio o que quedaron como el más cercano de algún lugar.

## La pantalla

- La frase: "733,854 personas, el 49.7 % de 1,476,462 con ruta, viven a más de 15
  minutos a pie" (Zapopan, centro de salud). El porcentaje es sobre la gente con ruta.
- El plano pinta un servicio a la vez ("Ver en el plano"): más lejos, más tinta, en
  cuatro clases relativas al umbral (hasta la mitad, hasta el umbral, hasta el doble y
  más); sin dato, solo el borde punteado. Al tocar un lugar, su gente y sus minutos.
- Enlace permanente: `ent`, `mun`, `modo`, `umbral` (1 a 120) y `servicio`. Un modo o
  umbral raro cae al valor inicial (a pie, 15); un municipio que no está deja la hoja
  vacía. Límite de 60 consultas por hora por cuenta.
- "Cómo citar" en cada servicio: la fuente de los destinos (CLUES, DENUE u OSM), el
  censo y OSM como red, con la fecha del cálculo (`citar.md`).

## Cifras de Jalisco (2026-11-22)

Zapopan, 15 minutos, parte de la gente con ruta que vive a más:

| Servicio | A pie | En auto |
|---|---|---|
| Centro de salud | 49.7 % | 0.7 % |
| Clínica del IMSS (afiliados) | 92.5 % | 6.9 % |
| Hospital público | 92.4 % | 13.6 % |
| Primaria pública (6 a 11 años, en AGEB) | 15.6 % | 0.3 % |
| Bachillerato público (15 a 17, en AGEB) | 70.0 % | 0.4 % |
| Supermercado | 60.5 % | 0.6 % |
| Estación de transporte masivo | 78.3 % | no aplica |

Mezquitic, 30 minutos a pie: centro de salud 51.8 %, hospital público 100 %. Dev y
producción dan a pie las mismas cifras, al dígito.

Revisión con datos reales: ningún tiempo a pie es menor que la línea recta al más
cercano a 5 km/h (cinco casos quedan por debajo menos de 0.5 %, por el redondeo de los
minutos y la proyección plana del árbol); el rodeo mediano por calle es 1.33 a 1.40
veces la línea recta según el servicio.

## Costo

Jalisco completo (14,948 lugares; 4,891 para escuelas), en producción: los 9 servicios
a pie y los 8 en auto en 102 s, de 2 a 10 s cada uno. Desde Aerilate por túnel, solo a
pie, 2 min 34 s. Cargar el CLUES: 30 s en Pixilate. Preparar el OSRM a pie de
Jalisco: 34 s y 2.4 GB de pico en `osrm-extract`; servirlo, 934 MB. El país entero a pie
pediría unos 18 GB en `osrm-extract` (el pbf de Jalisco con margen es el 13 % del de
México), más de los 16 GB del WSL de Pixilate: por estado sí cabe, nacional no.

## Pendiente

- Escuelas del campo con la SEP por localidad (arriba).
- Otros estados: necesitan su OSRM a pie (`scripts/osrm/pie.sh` con otra caja), y DENUE,
  censo y AGEB cargados.
- Transporte: las paradas del GTFS ya entran (sesión 27, `transporte.md`), solo donde
  hay GTFS; las de OSM no, porque OSM no dice si la ruta opera.
- Destinos de otro estado: hoy solo cuentan los del mismo estado; en las orillas el
  más cercano puede estar del otro lado.
