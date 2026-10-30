# Rediseño del núcleo, octubre 2026

Sesión 4 del plan, cerrada el 2026-10-30. Llevó la mesa de planeación
(sesión 3) a Phoenix en el layout base, `/mapa`, `/perfil` y
`/logistica`. Las decisiones viven en
[decisiones.md](../arquitectura/decisiones.md), sección "Concepto
visual", apartado "En Phoenix"; aquí queda qué se hizo y qué falló.

## Qué quedó

- **Base:** pieles en `pieles.css` (generado desde
  `design/mesa_planeacion/pieles.js`), `mesa.css` con papel, cinta,
  membrete y botones, daisyUI con los tokens de la piel. `Layouts.app`
  con membrete, esquina (modo y cuenta), `full_width?` para vistas de
  plano completo y `amplio?` para vistas con documentos.
- **`/mapa`:** charola de acetatos, cinta por capa, rótulo, piel
  automática o fijada, plano entintado.
- **`/perfil`:** cinco documentos, uno por enfoque y con su piel, sobre
  el plano de los AGEB del municipio. La consulta va en la URL y se pide
  con `start_async`.
- **`/logistica`:** prototipo primero (`design/mesa_planeacion/
  logistica.html`, con un VRP real de Guadalajara) y luego Phoenix. Una
  hoja de ruta en vez del panel lateral; paradas que se ponen, se
  arrastran y se editan sobre el plano; rutas con la tinta de cada
  vehículo; aviso cuando dejan de corresponder.
- **Compartido:** `MapoWeb.Cifras` (cifras con separador de miles),
  `plano_tinta.js` (entintado del plano) y `.plano-leaflet` (estilos de
  Leaflet de la mesa).

Revisado en Chrome real en escritorio, 390×844, 360×740 y 844×390, en
los dos modos, sin scroll lateral.

## Bugs reales

- **El botón de modo regresaba a decir "Modo"** cada vez que LiveView
  volvía a pintar el layout (al llegar el perfil asíncrono, por
  ejemplo): el parche reponía el texto del servidor sobre el que puso el
  script. Va con `phx-update="ignore"`.
- **`leaflet.css` sin capa le ganaba a la mesa.** Los estilos sin capa
  ganan a cualquier `@layer`, sin importar la especificidad: en `/mapa`
  el zoom quedaba detrás de "Cuenta/Salir" y los bordes de Leaflet no
  eran los nuestros. Meterlo como primera capa tampoco sirvió: entonces
  perdía contra el reset de Tailwind y los popups se quedaron sin
  margen. Quedó en su propia capa entre `base` y `components`, con el
  orden declarado al inicio de `app.css`.
- **El `display: grid` de `.fieldset` (daisyUI) va en `utilities`** y le
  gana a cualquier regla de `components`: cada select de ubicación
  ocupaba su renglón y el membrete se triplicaba en celular. La regla
  que lo corrige va fuera de capa, con su comentario.
- **Clases con el mismo nombre en dos vistas** (`.sello`, `.total`,
  `.aviso` en `/perfil` y `/logistica`): todo el CSS es global, así que
  cada vista acota las suyas.
- **El encuadre de `/logistica` al poner paradas nunca se activaba:** la
  condición esperaba pasar de 0 a 2 paradas en un evento y llegan de una
  en una. Se quitó; solo encuadra al llegar rutas, como ya decía el
  comentario original (reencuadrar a cada clic mueve el mapa bajo el
  cursor).

## Lo que se aprendió

- Con Tailwind 4 y daisyUI, antes de pelear especificidad hay que
  preguntar en qué capa vive la regla que gana.
- Probar con el servicio real encontró lo que los tests no: OSRM cae a
  línea recta con paradas lejanas (por eso el sello de "línea recta
  aproximada"), y en zonas rurales la ruta va a la calle más cercana,
  que puede quedar lejos de la marca.

## Fuera de esta sesión

- Capa "Tus marcas" y notas en los documentos de `/perfil`: sesión 6.
- Revisión contra `anti-vibecode.md`: sesión 7.
- Pasada final de diseño, al terminar todo.
