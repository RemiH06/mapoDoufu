# Marcas del equipo

Lo que un equipo anota a mano sobre el plano. Pertenecen a una sesión del equipo y se
ponen en `/sesiones/:id` o en la capa "Tus marcas" de `/mapa` (`?sesion=ID`): es la misma
marca en los dos lados y llega en vivo a quien tenga la sesión abierta. Cualquier miembro
las pone, edita y borra.

## Formas

| Forma | Cómo se dibuja | Qué se guarda | La ficha dice |
|---|---|---|---|
| Punto | Un clic | Punto | |
| Círculo | Centro y orilla | Centro y `radio_m` (hasta 50 km) | Radio |
| Flecha | De donde sale a lo que señala | Línea de dos puntos, cola primero | Largo |
| Trazo | Arrastrar (con un dedo en pantalla táctil; con dos se mueve el plano) | Línea de 2 a 500 puntos | Largo |
| Polígono | Un clic por vértice; el primero o doble clic cierra, Retroceso borra el último | Polígono de 3 a 200 vértices | Área, o que se cruza consigo mismo |

- Escape o cambiar de forma cancela lo que va a medias. Cerrar la ficha de la marca nueva
  sin guardar no deja marca.
- Con una figura elegida, el clic siempre dibuja, aunque caiga sobre la línea de otra
  marca. Cada marca se abre por su nota (o su asa, si no tiene), con clic, Enter o espacio.
- El trazo se simplifica en pixeles antes de mandarse (Douglas-Peucker; la tolerancia sube
  hasta caber en 500 puntos) y se dibuja con las esquinas redondeadas.
- El aspecto a mano (lados combados, círculo que no cierra) se calcula al dibujar, en
  metros, y no se guarda: lo guardado es lo que la persona marcó.

El servidor arma la geometría de lo que manda el plano (`Mapo.Sesiones.Anotacion.geom/1`)
y rechaza coordenadas fuera del mundo, puntos de menos o de más y polígonos sin tres
vértices distintos. Una marca ya puesta solo cambia sus notas, no su forma ni su lugar.

## Nota y nota larga

- `texto` (255 caracteres) es la etiqueta del plano.
- `detalle` (5,000) se lee en la ficha, con sus saltos de línea. La etiqueta termina en
  "…" si hay nota larga.
- La ficha abre en lectura; "Editar" la vuelve formulario. Si otra persona cambia la misma
  marca mientras tanto, el borrador se conserva y la ficha avisa; al guardar queda lo
  último que se guardó.

## Un lápiz por persona

Cada quien marca con un color fijo en cada equipo, el menos usado cuando entra
(`team_memberships.lapiz`, 1 a 6). No se elige: así el color dice de quién es. Con más de
seis personas se repite. Las marcas de quien ya no está en el equipo salen en grafito.

- Para no depender del color, la marca lleva **dos letras de quien la puso** (iniciales si
  el correo trae nombre y apellido). Solo salen si en la sesión hay marcas de más de una
  persona.
- La lista de lápices (en la hoja de la sesión y en la cinta) dice de quién es cada uno y
  cuántas marcas lleva.
- Los colores (`--lapiz-0` a `--lapiz-6`, `mesa.css`) son de la persona y no cambian con la
  piel. Contraste de 4.6:1 o más contra el papel blanco, el de la sesión, el negro y la
  cianotipia. Distancia entre cualquier par (CIE76): 29 con visión normal, 19 con
  deuteranopía y 18 con protanopía en claro; 36, 22 y 22 en oscuro.

## Límites

- Con el trazo elegido, el plano no se arrastra con el ratón: se acerca con la rueda y se
  recorre con las flechas del teclado, o se cambia de forma.
- Las marcas no van en la cita ni en el enlace público: son del equipo.
