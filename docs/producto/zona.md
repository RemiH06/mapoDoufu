# Zona común

Una sola forma de decir "dónde" en todas las vistas (sesión 29b): un estado, uno o
varios municipios, una metrópoli, una colonia, un código postal o un polígono dibujado
en el plano. El mismo selector está en la hoja de `/riesgos` y `/accesibilidad` y en el
membrete de `/mapa`. `/perfil` y `/buscador` todavía eligen por estado y municipio: se
pasan en la 29h y la 29c.

## Cómo se usa

- Se escribe en la caja y salen sugerencias de lo cargado en Mapo: estados, metrópolis,
  municipios y colonias; cinco dígitos es un código postal. Enter toma la primera.
- Con un municipio elegido, "Sumar un municipio" agrega otros (la competencia o la
  población del otro lado del límite ya no se pierden); cada uno se quita con su ×.
- "Dibujar en el plano": cada clic pone un vértice, clic en el primero o doble clic
  cierra, Retroceso borra el último, Enter cierra y Esc cancela. De 3 a 200 vértices,
  hasta 10,000 km², sin cruzarse.
- "Que sea mi zona" la guarda en la cuenta. Las vistas abren con ella cuando el enlace
  no trae zona, sin consultar solas. "Es tu zona · Dejar de usarla" la quita.
- En `/riesgos` y `/accesibilidad`, elegir una zona ya consulta; el botón vuelve a
  consultar con otra cercanía o modo. En `/riesgos` sigue también el círculo en el plano.
- En `/mapa`, al cambiar de zona se vuelven a pedir las capas puestas que dependen de ella
  (censo, área por negocio, transporte, municipios, vivienda): si no, el plano seguiría con
  la zona de antes y el enlace ya diría la nueva.

## La clave de zona

La zona viaja como texto corto en la URL, en la cuenta (`users.zona_operacion`) y de Mapo
a `mapo_core`. La lee `mapo_core/src/mapo_core/zona.py` (`validar`), sin tocar la base, y
nada del navegador se interpola en el SQL.

| Clave | Zona | Polígono |
|---|---|---|
| `ent:14` | Estado | Marco Geoestadístico de INEGI |
| `mun:14039,14120` | Uno o varios municipios, de uno o varios estados (hasta 100) | Unión de los municipios del Marco |
| `zm:14.1.01` | Metrópoli de *Metrópolis de México 2020* | Unión de sus municipios |
| `cp:45615` | Código postal | Polígono de SEPOMEX (falta cargarlo, ver abajo) |
| `col:14098_0135` | Colonia | Cartografía de colonias de CONAPO 2020 |
| `pol:-103.4,20.66;-103.33,20.66;...` | Polígono dibujado | El dibujo, vértices `lon,lat` con 5 decimales |
| `cir:-103.35,20.67,2500` | Círculo (centro y radio en metros, de 100 a 25,000) | Buffer en metros |

Los enlaces llevan la clave tal cual (`zona=mun:14039,14120`): los dos puntos, la coma y
el punto y coma son válidos en una query y Plug solo parte en `&`. Los enlaces de antes de
la 29b siguen abriendo porque ya hay citas con ellos: `ent` y `mun` se leen como
`mun:` (o `ent:` sin municipio) y `modo=circulo&lat&lon&radio` como `cir:`; al abrirlos,
la URL se reescribe con `zona=`.

## Lo que regresa `mapo_core`

- `GET /zona/buscar?q=` da `resultados` (clave, tipo, nombre, detalle) y `aviso`, que
  dice por qué no hay resultados cuando no es cosa de escribir otra cosa (un CP sin los
  polígonos de SEPOMEX cargados).
- `GET /zona/resolver?clave=` da nombre, detalle, el polígono simplificado según el tamaño
  (una colonia pide metros, un estado no), km², caja, municipios que toca, estados,
  `faltan` (municipios de la clave que no están cargados), fuente, método y aviso. 422 si
  la clave no es válida, 404 si no hay nada cargado con ella.
- Un municipio "toca" la zona si tiene al menos 5 % de su área: los polígonos de CONAPO y
  los de INEGI no coinciden al metro, y en Jalisco 81 colonias tienen de 1 a 5 % en un
  municipio que no es el suyo (López Cotilla, 1.6 % en Tlajomulco). Con 1 %, el vecino se
  colaba en los datos por municipio (sequía, defunciones, cultivos).

## Cómo calcula cada vista

- **`/riesgos`**: igual que antes con el municipio o el círculo, ahora con cualquier
  polígono. Los datos por municipio (sequía, cultivos, defunciones) usan los municipios
  que toca la zona por polígono; sin municipios cargados, los del ITER que caen dentro.
- **`/accesibilidad`**: los minutos ya estaban por lugar (AGEB o localidad), así que una
  zona es la suma de los lugares cuyo punto cae dentro. Los minutos son por estado: los
  lugares de un estado sin calcular se dicen aparte (`sin_calcular`), nunca como lejos.
- **Área por negocio (`/mapa`)**: el Voronoi usa los negocios de la zona y, marcados
  `fuera`, los de DENUE a 5 km o menos fuera de ella, y recorta todo a la zona. Antes solo
  veía el municipio: un negocio junto al límite se quedaba con todo el borde aunque del
  otro lado hubiera competencia. En Guadalajara, con farmacias, 1,106 de fuera compiten y
  76 se quedan con parte del municipio. Sus celdas van con un velo y su punto hueco. Si el
  margen toca un estado sin DENUE en Mapo, se dice.
- **Las demás capas de `/mapa`** (censo, vivienda, municipios, transporte) todavía piden
  un estado y, si se puede, un municipio: salen de la zona (su primer estado; su municipio
  si es uno solo). Se pasan en la 29d.

## Límites

- `/riesgos` y `/accesibilidad` calculan hasta 5,000 km² (`zona.MAX_KM2_CONSULTA`): cabe
  el municipio más grande cargado (Mezquitic, 3,364 km²) y la ZMG (2,487), no un estado,
  que tardaría minutos. Más grande, la vista dice por qué y qué elegir.
- Tiempos en Aerilate (Docker en Windows, más lento que Pixilate): una colonia, 1 a 2 s;
  Guadalajara en riesgos, 7 s; la ZMG, 15 s en accesibilidad (5.5 MB de plano) y 64 s en
  riesgos. Las consultas de `mapo_core` corren sin JIT de Postgres: con punto en polígono
  contra una zona estimaba costos enormes y compilaba 1.4 s una consulta de 0.1 s.

## Código postal

SEPOMEX (Correos de México) publica los polígonos de CP por estado en datos.gob.mx
(`CP_14.zip` y uno por estado), pero el sitio les niega la descarga a los programas (403
de Akamai, igual que su catálogo y su API) y el Internet Archive no los tiene. Se bajan a
mano desde el navegador y se cargan con `cli codigos_postales`, que al cargar mide cuántos
negocios de DENUE caen dentro del polígono del CP que declaran. Mientras no estén, el
selector no ofrece CP y lo dice.

No se usa el CP de CONAPO: un polígono de CONAPO junta varias colonias de SEPOMEX, y en
Jalisco da 673 CP contra los 1,631 que declara DENUE. El detalle está en
`../fuentes/zonas.md`.
