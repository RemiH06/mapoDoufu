# Distancia entre capas (noviembre 2026, sesión 19, primera parte)

La sesión 19 prueba si un equipo con datos propios puede hacer una
investigación completa en Mapo. El caso de prueba pedía saber qué escuelas
tienen parcelas agrícolas cerca, y el cruce solo agregaba por zona: no había
forma de medir de una capa a otra. Ahora la hay, y cada renglón puede decir de
dónde sale.

## Qué se hizo

- **Distancia entre capas** (`Mapo.Capas.Distancias`, pantalla
  `/teams/:id/datos/:capa_id/distancia`): de cada renglón de una capa de puntos
  o geometrías al más cercano de otra del mismo equipo, en metros, con hasta
  dos condiciones de texto por capa y un radio opcional para contar. El
  resultado se guarda como capa. Detalle en `../producto/datos-propios.md`,
  "Distancia entre capas".
- **Índice GiST en `capa_filas.geom`** y la extensión `unaccent`, para que el
  filtro ignore acentos.
- **Procedencia por renglón:** las columnas reservadas `fuente`, `url`,
  `fecha_dato`, `fecha_consulta`, `nivel` y `verificado` salen aparte en la
  ficha de `/mapa`. `scripts/para_mapo.py` las llena en cada capa de un paquete
  con lo que anotó `recorte.py`.
- **CSV de capas de puntos** con latitud y longitud.
- **Codificación de shapefiles:** Mapo y `recorte.py` decidían si un `.dbf` era
  UTF-8 decodificando el archivo completo, encabezado binario incluido, y casi
  siempre caían a Latin-1. Uso de suelo series VI y VII y las ANP de CONABIO
  salían como "MESÃ“FILO". Ahora se prueba solo la parte de registros.

## Por qué así

- **En PostGIS de Mapo, no en `mapo_core`:** las dos capas ya están en
  `capa_filas`, así que no hay que mandar renglones por la red, y el resultado
  se inserta con la geometría completa en la misma consulta.
- **Elipsoide, no grados ni una proyección:** una distancia en grados confunde
  el orden (un grado de longitud mide 94 % de uno de latitud a 20°), y una
  proyección cónica como la 6372 deforma según la zona. `geography` da metros
  sobre el elipsoide en todo el país. El índice trabaja en grados, así que da
  un candidato y su distancia en metros acota la búsqueda del bueno.
- **Filtro de texto y no una capa ya filtrada:** el equipo sube el archivo tal
  como lo bajó. Pedirle que lo recorte en un SIG antes es justo lo que Mapo
  quiere evitar.
- **Barra para alternativas, no coma:** las comas aparecen en los datos
  ("Comercio al por mayor de semillas y granos alimenticios, especias y chiles
  secos", en DENUE) y la barra casi nunca.

## Lo que salió con datos reales

Medido con escuelas de DENUE de dos cabeceras municipales contra los polígonos
agrícolas de uso de suelo serie VII, el cálculo tarda segundos y da lo que debe,
pero la capa es demasiado gruesa para la pregunta: casi todas las escuelas caen
en "asentamientos humanos", y las que salen a 0 m de una parcela están en la
orilla de la mancha urbana, que a 1:250 000 está generalizada. Para hablar de
300 m hace falta la frontera agrícola del SIAP o WorldCover a 10 m.
