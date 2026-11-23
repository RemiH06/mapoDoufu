# Alcances en auto apilados

El acetato "Alcance en auto" de `/mapa` dibuja hasta dónde se llega en auto desde un
punto en N minutos (la isócrona; cómo se calcula con OSRM, en
`../historial/fase-4-isocronas.md`). Desde la sesión 29d se apilan hasta cinco y cada uno
dice cuánta gente vive dentro.

## Uso

1. En la cinta, los minutos (de 1 a 120) y "Poner" (o "Agregar otro"). El plano espera
   el clic del punto de salida; "Cancelar" lo suelta.
2. Cada alcance sale con su número en el punto de salida y su tinta, en este orden:
   movilidad, urbanismo, comercio, seguridad y demografía. La cinta los lista con sus
   minutos, su punto y la gente dentro; "Quitar" quita uno y "Quitar todos", todos.
3. Con dos o más, la cinta dice cuánta gente vive **en todos** (la intersección) y **en
   alguno** (la unión), y el plano marca con un contorno grueso, del color del texto, la
   parte que comparten todos. Si no comparten nada, se dice.

Sirve para comparar: el mismo punto a 10 y 20 minutos, dos sucursales posibles, o
dónde se juntan los alcances de varios lugares.

## Cómo se cuenta la gente

`POST /isocronas/poblacion` de mapo_core (`isocronas.poblacion`) recibe los polígonos y
usa la misma regla que `/riesgos` y `/accesibilidad`:

- Cada AGEB urbana con censo cuenta **entera** donde cae su punto de dentro
  (`ST_PointOnSurface`); cada localidad del ITER sin AGEB cargada, donde cae su punto.
- No se reparte por área: una AGEB partida por el borde cuenta de un solo lado. Con
  alcances de varios kilómetros el error es chico; con uno de 1 o 2 minutos, no tanto, y
  la cinta lo dice en el método.
- La población reservada por INEGI (lugares con muy pocas viviendas) no se cuenta como
  cero: se dice cuántos lugares faltan ("sin 2 lugares con dato reservado").
- "En todos" son los lugares cuyo punto cae dentro de todos los alcances; "en alguno",
  dentro de al menos uno. La intersección dibujada se calcula aparte con Shapely y es
  solo para verla.
- Si mapo_core no responde al contar, los alcances se dibujan igual y la cinta dice que no
  se pudo contar.

Comprobado en dev el 2026-11-23 con dos alcances en la ZMG: desde el centro de
Guadalajara, 10 minutos (473,991 personas), y desde Zapopan, 15 minutos (578,722); en
los dos, 138,608, y en alguno, 914,105 (= 473,991 + 578,722 − 138,608).

## Enlace y cita

- `alcance=lat,lon,min;lat,lon,min` (hasta cinco, en el orden de la pila). Uno con un
  punto fuera de México o minutos fuera de 1 a 120 se salta. Los enlaces de antes, con un
  solo alcance, siguen abriendo.
- "Cómo citar" cita OSM (el ruteo) con cada alcance y su método y, si se contó la gente,
  el Censo 2020 con la fecha de carga.
