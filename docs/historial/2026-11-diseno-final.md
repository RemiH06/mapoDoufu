# Pasada final de diseño, noviembre 2026

Sesión 16 del plan. No cambió el concepto (la mesa de planeación de
[decisiones.md](../arquitectura/decisiones.md)): reacomodó dónde va cada
cosa, sobre todo en celular y acostado.

## Cómo se revisó

Un script de Playwright recorrió 15 pantallas en tres tamaños (1280×800,
390×844 y 844×390) y en los dos modos: 90 capturas, más 21 de estados con
datos (tres capas propias abiertas, coropleta de Zapopan, consulta del
buscador resuelta). Mide el scroll lateral y junta los errores de consola.
Antes y después: sin scroll lateral ni errores. Los defectos de abajo no
los marcaba ninguna medición: salieron de mirar las capturas.

## Qué cambió

- **Membrete en celular.** Ocupaba unos 210 de 844 px: las secciones en
  dos renglones, los selects de ubicación en otros dos y una fila aparte
  para modo, Cuenta y Salir. Ahora es un renglón con la marca y la sección
  actual; tocarla despliega las secciones, el modo y la cuenta. Estado y
  municipio van en un renglón debajo, a todo lo ancho. Los controles de
  zoom de los cuatro planos usan una sola variable, `--alto-cabecera`,
  en vez de 150, 168 y 196 px sueltos.
- **Cuenta** es un desplegable con el correo, Configuración y Salir, en
  todos los tamaños y también en la portada.
- **Charola de `/mapa`.** Siete pestañas no cabían en ningún tamaño y la
  última quedaba fuera sin aviso. En escritorio, "en la charola" ya no se
  escribe (solo "encima") y caben las siete. En 900 px o menos la charola
  se pliega en un botón "Acetatos · N encima" que abre la lista; elegir
  una capa la vuelve a plegar.
- **Cinta en pantallas angostas.** Era una tira con scroll lateral: con
  tres capas propias se veía una y media, y acostado tapaba medio plano y
  cortaba "Más arriba / Más abajo". Ahora es un papel vertical con scroll
  propio y las capas apiladas; acostado va a la mitad izquierda.
- **Encuadre.** El buscador abre en el estado elegido, no en México
  entero (`estados_bbox.js`; en Colima y Baja California se quitaron las
  islas, que estiraban el recuadro al océano). Todo encuadre mide los
  papeles en pantalla: en el buscador, la pregunta y la respuesta; en
  `/mapa`, la cabecera, la cinta abierta y la charola. Antes el buscador
  usaba márgenes fijos que en celular no aplicaba, y `/mapa` encuadraba
  las marcas con 80 px fijos, así que alguna quedaba bajo la cinta.
- **Buscador.** "otro" en la plantilla pasó a "+ municipio". La fórmula y
  la leyenda van en el desplegable "Cómo se lee". Acostado, la plantilla
  se pliega al resolver y la pregunta plegada se apila sobre la respuesta.
- **Datos del equipo.** El input de archivo nativo decía "Choose File / No
  file chosen", en el idioma del navegador: ahora es una zona propia
  ("Arrastra un archivo aquí"), con el input oculto a la vista pero no al
  teclado. Los botones de cada capa van siempre debajo de su nombre: al
  lado solo cabían en las capas con menos botones.
- **Cruce.** Las 27 casillas del censo van en cuatro desplegables por
  tema, cada uno con cuántas lleva marcadas. El resultado sigue a todo lo
  ancho, debajo: la tabla necesita el espacio.
- **Equipo.** "Datos propios" tiene su propia tarjeta; estaba dentro de
  la de Sesiones.
- **Portada acostada.** El plano medía unos 160 px de ancho junto al
  rótulo; el rótulo bajó después de la charola y el plano toma la columna.

## Lo que falló en el camino

- Un `<details>` dentro de LiveView se cierra solo en el siguiente parche:
  morphdom quita el `open` que puso la persona. Se resolvió con
  `phx-mounted={JS.ignore_attributes(["open"])}` (LiveView 1.2).
- Con el margen lateral de la cabecera en 12 px, la cinta adhesiva del
  membrete se salía 2 px y daba scroll lateral en las páginas de documento.
  Quedó en 16 px, el mismo de `px-4` del contenido.
- Las reglas de acostado (`max-height: 500px`) también aplican a una
  pantalla ancha y baja; las que cambian anchos se limitaron a 900 px o
  menos.
