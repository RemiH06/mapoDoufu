# Zonas: metrópolis, colonias y códigos postales

Las fuentes de la zona común (`../producto/zona.md`) que no son el Marco Geoestadístico
(`geo-censo.md`): de qué metrópoli es cada municipio, el polígono de cada colonia y el de
cada código postal.

## Metrópolis de México 2020

SEDATU, CONAPO e INEGI, *Metrópolis de México 2020*, edición 2024
([PDF](https://www.gob.mx/cms/uploads/sedatu/MM2020_06022024.pdf)). Delimita 92
metrópolis: 48 zonas metropolitanas, 22 metrópolis municipales y 22 zonas conurbadas, con
sus municipios. Solo existe en PDF.

- Tabla: `mapo_core/src/mapo_core/metropolis_2020.csv` (clave, nombre, municipio),
  sacada de los cuadros del documento en la sesión 22 para la comparación de ciudades
  (`scripts/ambiental/metropolis_2020_municipios.csv`). La clave es estado, tipo (1 zona
  metropolitana, 2 metrópoli municipal, 3 zona conurbada) y número: `14.1.01` es la de
  Guadalajara.
- **Faltaba una:** al cruzar las claves de la tabla con las del PDF (con `pdftotext`)
  salió que no estaba Los Cabos (`03.2.02`, metrópoli municipal, municipio 03008). Se
  agregó en la sesión 29b; la tabla de la sesión 22 sigue sin ella, pero ninguna de las
  siete ciudades comparadas es esa.
- Carga: `python -m mapo_core.cli metropolis` (reemplaza todo; se niega si no son 92).
  Validado: 92 metrópolis, 423 municipios, 48, 22 y 22 por tipo, como el cuadro resumen.
- La ZMG oficial de 2020 son 7 municipios (Guadalajara, Zapopan, Tlaquepaque, Tonalá,
  Tlajomulco, El Salto y Juanacatlán). El dataset de vivienda usa 10 (con Ixtlahuacán de
  los Membrillos, Zapotlanejo y Acatlán de Juárez, de delimitaciones anteriores): no son
  la misma zona.
- Una metrópoli puede cruzar estados (Puerto Vallarta con Bahía de Banderas, en Nayarit):
  si un municipio no está cargado, la zona queda sin él y lo dice (`faltan`, `aviso`).

## Colonias de CONAPO

Cartografía del Índice de marginación urbana 2020 de CONAPO, la única fuente nacional
con polígono de colonia (`../producto/colonias.md`).

- URL: `https://conapo.segob.gob.mx/work/models/CONAPO/Datos_Abiertos/Colonia/imc2020_shp.zip`
  (38 MB, sha256 `69d73b5b…a278426`, bajado el 2026-11-22). En
  `mapo_core/data/colonias/` (gitignorada).
- Shapefile en Lambert ITRF 2008 (EPSG 6372), UTF-8: 74,226 colonias con clave
  (`CVE_COL`, como `14098_0135`), nombre, CP, municipio, localidad, población estimada,
  componentes e índice de marginación, y su clasificación (Colonia, Fraccionamiento,
  Barrio, Pueblo...; `-` en las localidades que cuenta enteras, que Mapo muestra como
  "Asentamiento").
- Carga: `python -m mapo_core.cli colonias /app/data/colonias/imc2020_shp.zip` (todo el
  país, reemplaza todo; unos 3 minutos en Aerilate). Se reproyecta a 4326 y se repara con
  `ST_MakeValid`: 74,226 cargadas, ninguna inválida. Se guarda el nombre sin acentos para
  buscar.
- Los nombres vienen sin acentos y a veces con mayúsculas raras ("Lopez Cotilla",
  "Guadalupana Ii Seccion"): se muestran tal cual.

### El CP de CONAPO no sirve como polígono de CP

Se probó armar el polígono de cada CP con las colonias de CONAPO que lo declaran, y se
midió contra DENUE, que trae el CP de cada negocio (Jalisco, 401,707 negocios con
coordenadas y CP):

- Solo 68.7 % de los negocios ubicados en una colonia cae en una con el mismo CP que
  declara. En 55,463 coincide hasta el nombre de la colonia y aun así el CP es otro.
- En las colonias con 5 negocios o más (3,392), el CP de CONAPO coincide con el de la
  mayoría de los negocios en 2,201 (65 %); en 941 una mayoría clara (60 % o más) dice
  otro.
- En los casos que se pueden comprobar, DENUE acierta: Americana es 44160 (CONAPO dice
  44100), Moderna 44190 (44150), Jardines del Bosque 44520 (44320), Chapalita de
  Guadalajara 44500 (45510).
- La causa de fondo: un polígono de CONAPO junta varias colonias de SEPOMEX. La
  "Americana" de CONAPO tiene 996 negocios con 44160, 219 con 44130 y 180 con 44600. En
  Jalisco salen 673 CP de CONAPO contra 1,631 que declara DENUE: 932 CP de DENUE no tienen
  ninguna colonia.
- Los CP de la Ciudad de México vienen sin el cero de la izquierda (`9700` es 09700, 1,340
  colonias) y 1,051 colonias traen CP `0`.

Por eso la tabla `colonias` no guarda el CP y el detalle de una colonia no lo muestra.

## Códigos postales de SEPOMEX

Correos de México publica en datos.gob.mx "Códigos postales por entidad federativa": un
shapefile por estado (`CP_14.zip` para Jalisco), que según quienes lo han usado trae
solo `d_cp` y el polígono, con licencia CC BY 4.0 (confirmarla en la ficha al bajarlo).

- **No se puede bajar con un programa:** `repodatos.atdt.gob.mx` y la API de
  datos.gob.mx responden 403 de Akamai (2026-11-22), y el Internet Archive no tiene copia
  de `CP_14.zip`. Se baja a mano desde el navegador a `mapo_core/data/colonias/`.
- Carga: `python -m mapo_core.cli codigos_postales /app/data/colonias/CP_14.zip [...]`.
  Reemplaza el estado del nombre del archivo; un CP partido en varios polígonos se une;
  acepta WGS84 o la Lambert ITRF 2008 y se niega con otra proyección; rellena el cero de
  la izquierda. Al terminar dice cuántos negocios de DENUE del estado caen dentro del
  polígono del CP que declaran: esa es la prueba con datos reales antes de dar la fuente
  por buena.
- Probado con un shapefile sintético (`tests/test_zona.py`); falta la prueba con el archivo
  real.
