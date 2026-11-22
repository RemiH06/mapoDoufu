# CLUES: establecimientos de salud

Catálogo de Clave Única de Establecimientos de Salud de la Dirección General de
Información en Salud (DGIS, Secretaría de Salud): cada unidad pública y privada del país
con su institución, tipo, tipología, estatus de operación, nivel de atención y
coordenadas. Lo usa la accesibilidad a servicios (`../producto/accesibilidad.md`).

- **Dónde:** http://www.dgis.salud.gob.mx/contenidos/intercambio/clues_gobmx.html,
  que liga un Excel mensual (`ESTABLECIMIENTO_SALUD_AAAAMM.xlsx`, hojas `CLUES_`,
  `SUBCLUES_` y `HORARIOS_`). Se bajó sin cuenta el 2026-11-22 el de octubre de 2026
  (27.8 MB, sha256 `c4432363…f785`).
- **Carga:** `python -m mapo_core.cli clues ESTABLECIMIENTO_SALUD_202610.xlsx`
  (`mapo_core/clues.py`). Reemplaza el catálogo completo en `fuente_clues`; el mes sale
  del nombre del archivo y va en `corte`. Con openpyxl en modo lectura tarda unos 5
  minutos en Aerilate y 30 s en Pixilate. En producción el archivo vive en
  `~/srv/mapo-crudos/clues/`.
- **Qué guarda:** clave CLUES, institución (clave y nombre), entidad, municipio y
  localidad, tipo de establecimiento, tipología y subtipología, nombre, estatus, nivel de
  atención, estrato, unidad móvil, `publica` y el punto.

## Cifras del corte 2026-10

68,027 establecimientos; 41,701 en operación; 2,005 sin coordenadas (o fuera de la caja
de México, que se toma como error de captura). En Jalisco, en operación: 1,560 de
consulta externa, 305 de hospitalización, 233 de apoyo y 79 de asistencia social.

Por institución (país): Secretaría de Salud 20,437; privados (`SMP`) 19,193;
IMSS-Bienestar 13,959 (`IMB`) y 4,529 (`IMO`); IMSS 5,868; ISSSTE 1,320; DIF 885;
estatales 538; Sedena 319; municipales 214; Cruz Roja 193. Jalisco no tiene unidades de
IMSS-Bienestar en operación: sigue con su Secretaría de Salud.

## Qué es público y quién atiende

`publica` es falso solo para privados (`SMP`), Cruz Roja (`CRO`) y Centros de
Integración Juvenil (`CIJ`). Pero público no quiere decir que atienda a cualquiera: el
IMSS y el ISSSTE atienden a sus afiliados, y hay unidades de Sedena, Marina, Pemex,
fiscalías e institutos forenses. Por eso la accesibilidad elige instituciones, no solo
`publica`: el centro de salud es Secretaría de Salud, IMSS-Bienestar, estatales y
municipales; la clínica del IMSS cuenta a la población afiliada al IMSS.

Fuera del centro de salud quedan las tipologías "UNIDAD MÓVIL" y "UNIDAD DE
ESPECIALIDADES MÉDICAS (UNEMES)" y toda unidad con `unidad_movil`: no son un lugar fijo de
consulta general.

## Problemas conocidos

- **Coordenadas mal capturadas.** De las 936 unidades de consulta externa y
  hospitalización en operación de las instituciones públicas que usa Mapo en Jalisco,
  927 caen dentro del municipio que declaran, 2 a menos de 1 km y 7 más lejos. Entre
  ellas, la "UMF 55 Guadalajara" cae en Tuxcueca (20.17, −103.21, coordenadas
  redondeadas) y la "UMF 11 Amatitán" en Teuchitlán.
- **Claves de municipio mal capturadas.** La "UMF 82 Unión de Tula" cae en Unión de
  Tula, pero el catálogo le pone la clave de otro municipio (251 km de distancia).
- **Regla:** una unidad se descarta si cae a más de 1 km del municipio que declara,
  salvo que caiga en un municipio cuyo nombre aparezca en el nombre de la unidad (sin
  acentos). Con eso se quedan la UMF 82 y se van las demás; el comando de accesibilidad
  lista los descartados.
- **Comparado con DENUE**, que sí trae consultorios del sector público: 513 en Jalisco
  ("Clínicas de consultorios médicos", "Consultorios de medicina general" y "Otros
  consultorios" del sector público) contra 623 centros de salud del CLUES con la regla
  de arriba, más 106 clínicas del IMSS. El CLUES trae el tipo de unidad, la institución
  y si opera; DENUE no.
