# Buscador sin mapa (sesión 29c)

Tercera sesión del bloque 29a a 29m. `/buscador` deja de ser un plano con una pregunta
encima: primero es la pregunta sola, con autocompletado, y el plano entra con la
respuesta. Cómo funciona: `docs/producto/buscador.md` ("Entrada", "Pantalla" y "Menú de
rubros").

## Qué se hizo

- **Enter resuelve.** Si la pregunta se entiende completa, `interpretar` la resuelve sin
  pasar por "Resolver" (también al abrir un enlace con `?q=`). Si falta un hueco, se
  queda marcado y no se consulta nada. Un perfil completo navega a `/perfil` con
  `replace`, para que "atrás" no caiga en una pregunta que se vuelve a resolver sola.
- **Autocompletado, `POST /buscador/sugerir`** (`buscador.sugerir` en `mapo_core`).
  Completa el pedazo final con inicios de pregunta, rubros (nombre y sinónimos), sectores
  (sinónimos) y municipios (nombre y apodos de `municipios_alias.csv`). Pedazos de hasta
  cuatro palabras, el más largo primero ("tienda de masc" da "tienda de mascotas" antes
  que Mascota); uno por rubro o municipio con su nombre primero; sin marcas; nada con menos
  de tres letras. En Phoenix, el hook colocado `.Sugerencias` lleva las flechas, Enter, Tab
  y Esc, y completa el texto en el navegador (LiveView no toca el valor de una caja con
  foco). Las respuestas que llegan tarde se descartan comparando el texto.
- **Sin plano hasta la respuesta.** La pregunta va al centro y el plano se queda oculto
  con `visibility: hidden` (no `display: none`: MapLibre necesita su tamaño real para
  encuadrar las capas que llegan con la respuesta). Excepción: "cuántos cerca", que pide
  el punto con un clic en el plano.
- **Menú de rubros.** El `<select>` de 183 rubros en 21 grupos pasó a un popover con los
  sectores plegados y un filtro que usa el campo nuevo `buscar` del catálogo (nombre y
  sinónimos normalizados). El hook `.MenuRubros` normaliza igual que
  `rubros.normalizar`. No depende de la plantilla, así LiveView no lo vuelve a pintar y no
  borra el filtro.
- **Arrastre de la 16: la respuesta en celular.** Sigue abriendo en un papel de 30 dvh
  para que se vea el plano, pero ahora "Ver todo" lo sube hasta la pregunta y "Ver el
  plano" lo regresa.
- **Capturas:** `scripts/capturas/buscador.js`. `comun.js` toma `NAVEGAR_MS` (180 s por
  omisión) para las páginas de dev cuando el montaje de Docker va lento.

## Decisiones

- **El vocabulario se queda en `mapo_core`.** Las sugerencias salen del mismo lugar que el
  analizador, para no tener dos listas de sinónimos. El filtro del menú sí corre en el
  navegador (183 renglones, sin ida y vuelta por tecla), pero con los términos que manda
  el catálogo.
- **Sin "los más pedidos".** Mapo no guarda qué se pregunta; guardarlo solo para ordenar
  el menú no vale lo que cuesta en privacidad.
- **Tomar una sugerencia no pregunta.** Completa la palabra y deja seguir escribiendo; la
  pregunta se hace con Enter sin sugerencia marcada.

## Bugs reales

- **Esc no cerraba el menú.** En una caja `type="search"`, Chrome usa el primer Esc para
  borrar el texto y el popover no recibe la petición de cierre. Se cambió a
  `type="text"`.
- **Dev tardaba de 30 a 90 s por página.** No era Mapo: con 1.3 de 20 GB libres en la
  máquina de desarrollo, el montaje 9p de Docker Desktop se volvió lentísimo (un `ls -lR lib/` tardó
  8 s) y el code reloader revisa esos archivos en cada petición. Los `curl` que se
  cortaban por tiempo se quedaban formados detrás del reloader y lo empeoraban; reiniciar
  el contenedor `mapo` vació la fila.

## Queda

- Las mejoras al menú de rubros no llegaron al campo "Giro" de `/mapa`, que sigue siendo
  texto libre (entiende los mismos sinónimos, sin lista).
- `/buscador` sigue eligiendo por estado, sin el selector de zona común (29b); queda para
  cuando el buscador acepte zonas que no sean municipios.
