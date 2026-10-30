# Revisión contra anti-vibecode, octubre 2026

Sesión 7 del plan, cerrada el 2026-10-30. Se pasaron todas las pantallas
por la lista de señales de diseño "hecho por IA" de la skill
`frontend-design` (`references/anti-vibecode.md`), con la regla de
umbral: tres señales juntas son la marca de lo genérico, y una señal no
cuenta si se justifica en una frase ligada al contenido.

## Cómo se revisó

- Lectura del CSS y las plantillas buscando cada señal (mayúsculas con
  espaciado, sombras, radios, colores puros, degradados, hovers, franjas
  laterales, iconos, emojis, fuentes).
- Chrome sin ventana con Playwright sobre las 10 pantallas, en
  escritorio (1440×900), celular (390×844) y modo oscuro, midiendo en el
  DOM ya pintado: scroll lateral, botones que se parten en dos renglones,
  sombras, radios, mayúsculas, colores `#000`/`#fff` y fuentes usadas.

## Resultado: el diseño pasa

Ninguna señal visual sin justificar; el umbral no se acerca.

- Sin sombras, sin radios (solo los círculos de las marcas, que son
  trazos a mano), sin `#000` ni `#fff`, sin scroll lateral.
- Los degradados son los motivos de papel de cada piel (renglones,
  cuadrícula, perforación, franja de precaución).
- La única mayúscula es el sello de `/logistica`: un sello de goma.
- Los hovers cambian color o asoman una pestaña de la charola; no hay
  animación decorativa.
- Iconos: solo `x-mark` (cerrar un aviso) y `arrow-path` (reconectando).
- Las pestañas de la charola usan dos renglones a propósito (nombre y
  estado), no son botones partidos.

## Lo que sí salió, y se corrigió

- **Sin aviso de privacidad.** Mapo guarda correos (también los de las
  personas invitadas), marcas y notas, y el navegador habla con
  OpenStreetMap y Bunny Fonts; `mapo_core` manda puntos al demo público
  de OSRM. Ahora hay `/privacidad`, un documento de la mesa enlazado
  desde la portada, el registro y la cuenta. El contacto de quien
  administra la instalación sale de `MAPO_CONTACTO`; sin él, el aviso
  dice que falta en vez de inventar uno.
- **Lema de la portada.** "Gaiarda contesta qué hay. Mapo contesta qué
  deberías hacer con eso" es un contraste del tipo "no es X, es Y",
  nombra a Gaiarda (que quien llega no conoce) y promete decir qué hacer,
  cuando Mapo da evidencia y nunca un puntaje. En la portada quedó "Los
  datos abiertos de México sobre la mesa, para que tu equipo decida
  dónde". La frase original sigue en `vision.md` y el README como tesis
  del proyecto.
- **`/perfil` sin esqueleto.** Durante los ~3 s de consulta solo había
  un aviso y la mesa vacía. Ahora los cinco papeles ya están pegados en
  su lugar, con su piel, encabezado y renglones en blanco, y una altura
  parecida a la del documento lleno para que la mesa no salte. No usa
  los documentos reales sin datos: dirían "no hay datos de este
  municipio", que sería falso mientras se consulta.
- **Restos del generador.** `header`, `table` y `list` de
  `core_components` no se usaban y traían estilos de daisyUI; se
  borraron.
- **Zoom de Leaflet en Lucida Console.** Los botones de acercar y alejar ahora usan
  la mono de la mesa.
- **RNF3 desactualizado.** `requisitos.md` decía que el fondo animado
  seguía; se marcó como descartado en la sesión 5.

## Lo que se aprendió

- `wait_until="networkidle"` nunca llega en una vista con LiveView (el
  websocket y las teselas siguen hablando): hay que esperar a
  `[data-phx-main].phx-connected` y luego a un selector concreto.
- La pantalla de entrar tiene dos formularios con `user[email]`; llenar
  el primero manda un enlace en vez de iniciar sesión.
