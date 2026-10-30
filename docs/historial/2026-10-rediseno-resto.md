# Rediseño del resto, octubre 2026

Sesión 5 del plan, cerrada el 2026-10-30. Llevó la mesa de planeación a
las pantallas que faltaban: portada, entrar, registro, confirmación,
cuenta, equipos, invitaciones y sesión colaborativa. Las decisiones viven
en [decisiones.md](../arquitectura/decisiones.md), sección "Concepto
visual", apartado "Resto de las pantallas"; aquí queda qué se hizo y qué
falló.

## Qué quedó

- **Portada nueva** ("la mesa se arma"). Se descartaron dos opciones: las
  curvas de nivel (más atmosféricas, sin mostrar el producto) y pulir el
  abanico de cartas del prototipo. La portada pone el plano real de
  Guadalajara y desliza encima censo, DENUE, isócrona y la marca del
  equipo, con anime.js; la piel de la mesa cambia con cada acetato.
- **Sin fondo animado.** Se borraron `metro_bg.js`,
  `bg_animation_toggle.js` y el interruptor de la cuenta.
- **Documentos pegados** para cuenta, acceso, equipos e invitación, con
  campos de renglón escritos a mano.
- **Sesión colaborativa** sobre el plano entintado, con marcas a mano,
  ficha propia para escribir la nota y encuadre de las marcas existentes
  en la primera visita.
- `core_components` (`<.input>`, `<.button>`, flash) ya usa las piezas
  de la mesa.

Revisado en Chrome real en escritorio, 390×844, 360×740 y 844×390, en
los dos modos y con movimiento reducido, sin scroll lateral. La sesión
colaborativa se probó con dos navegadores: la marca que pone uno le llega
al otro con su onda, y una nota con HTML se muestra como texto.

## Bugs reales

- **Una marca sin nota tronaba.** La columna `texto` es `NOT NULL` y
  `cast` convierte `""` en `nil`, así que un clic sin escribir nada daba
  un error de la base, no un changeset. El `prompt` viejo mandaba `""`
  cuando la persona no escribía nada, así que pasaba seguido. Ahora
  `""` se guarda tal cual y el texto tiene el tope de la columna (255);
  hay prueba para los dos casos.
- **Otra vez clases con el mismo nombre:** `.renglon` (de `perfil.css`)
  ensanchaba las filas de miembros y `.quitar` (de `logistica.css`)
  dejaba los botones de 32 px de ancho. Las de esta sesión se llaman
  `.lista-fila` y `.borrar`. Antes de nombrar una clase nueva, buscarla en
  `assets/css/`.
- **El rótulo de la portada en celular dejaba su cinta flotando** a media
  pantalla: `position: static` le quitaba el `relative` de `.pegado` y las
  tiras se iban al contenedor. En una vista angosta va `relative`.
- **Cambiar `config.exs` (las banderas de esbuild) tumba el recargador de
  dev** con "config files changed": hay que reiniciar el contenedor de
  `mapo`.

## Lo que se aprendió

- El texto dentro de un SVG que se escala no sirve en celular: en 360 px
  la cifra de la marca quedaba en 7 px. En el plano solo va "¿aquí?" y
  las cifras van en el rótulo, en HTML.
- `clip-path: inset()` sobre un `<g>` de SVG barre sobre la caja del
  grupo, así que el deslizado de la charola de `/mapa` sirve igual en la
  portada.

## Fuera de esta sesión

- Capa "Tus marcas" en `/mapa` y notas en `/perfil`: sesión 6.
- Revisión contra `anti-vibecode.md`: sesión 7.
