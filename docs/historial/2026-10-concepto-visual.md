# Concepto visual, octubre 2026

Sesión 3 del plan, cerrada el 2026-10-29. Las decisiones de diseño viven
en [decisiones.md](../arquitectura/decisiones.md), sección "Concepto
visual"; aquí queda cómo se llegó a ellas.

## Tres vueltas

1. **Panel lateral (descartada).** Papel gris frío, Overpass, tarjetas
   apiladas con interruptores a la izquierda del mapa. El concepto (mesa
   de planeación) solo existía en el texto: si se quitaba, la pantalla
   quedaba igual. Lo único que se salvó fue el mapa.
2. **Mapa protagonista.** El plano ocupa la pantalla entera; membrete,
   rótulo y cinta son papeles pegados con cinta adhesiva; las capas
   asoman como pestañas en una charola. El mapa base de OSM se reimprime
   en dos tintas con un filtro SVG. Lo impreso en sans técnica, lo
   anotado a mano.
3. **Pieles por enfoque.** Como los biomas de tarot: siete pieles
   (urbanismo, demografía, comercio, consumo, seguridad, laboral,
   movilidad), cada una con su documento, tintas de día y de noche,
   motivo de papel y letra a mano. La cianotipia de urbanismo se bajó a
   un azul noche para que el modo oscuro lo sea de verdad.

Después se prototiparon dos vistas sin mapa (portada y perfil) para
confirmar que el sistema sirve fuera de `/mapa`.

## Lo que se aprendió

- Revisar primero las piezas ya hechas en iroFactory
  (`component-catalog.md`) y los temas renderizados, no solo su índice.
  La primera vuelta falló por saltarse ese paso.
- Las tiras de cinta de un papel que va de orilla a orilla abrían 4 px de
  scroll lateral en celular. `overflow-x: clip` en `body` no lo arregla
  (se propaga al viewport y sigue dejando mover la página); la cura fue
  dar al contenido más margen lateral que lo que sobresale la cinta.
- Una carta que sube al pasar el cursor mueve también su zona de
  detección: el cursor queda fuera, la carta baja, vuelve a quedar dentro
  y sube otra vez. La zona de detección (el botón) se queda quieta y solo
  sube la cara de adentro.
- En una cuadrícula de una columna, `1fr` toma como mínimo el contenido
  más ancho (aquí, una fila de cartas con scroll propio) y saca de la
  pantalla todo lo demás. Va `minmax(0, 1fr)`.
- `screen` como modo de mezcla en el modo oscuro aplanaba las clases de
  la coropleta; los acetatos van normales de noche.

## Prototipo

`design/mesa_planeacion/`: `index.html` (`/mapa`), `perfil.html`,
`portada.html`, con `pieles.js`, `mesa.css` y `plano.js` comunes. Se
abre directo, sin servidor. La redacción de los textos se revisó contra
las skills de redacción del hub.
