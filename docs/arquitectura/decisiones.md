# Decisiones de producto

## Gaiarda se vendoriza, no se consume en vivo

Mapo copia y adapta el código de descarga y normalización de Gaiarda
dentro de `mapo_core`, hacia sus propias tablas en su propia Postgres.
Nunca depende de un proceso de Gaiarda corriendo: lo único que se
recicla es su código. Se corrigió el 2026-08-24, después de que
`mapo_core` se construyera por un rato como cliente HTTP de un Gaiarda
vivo (`gaiarda_client.py`, ya eliminado). Detalle en
`../fuentes/geo-censo.md`.

## Sin puntaje único

Ninguna pantalla resume una decisión en un número que esconda su
metodología (¿un homicidio pesa igual que un robo sin violencia?). Se
muestran los datos crudos lado a lado y quien usa Mapo decide. Viene
de Gaiarda (seguridad por tipo de delito, sin puntaje) y aplica a todo
lo nuevo: el perfil de zona junta las 5 secciones sin ponderarlas.

## Idioma de la interfaz (decidido): español únicamente, no bilingüe

Se evaluó explícitamente meter soporte bilingüe (español/inglés) y se
descartó. Phoenix ya trae `gettext` instalado (mecanismo maduro para
esto), así que no es difícil técnicamente, pero sí es trabajo real y
constante: envolver cada string nueva en `gettext(...)`, mantener
traducciones por pantalla, y propagar el locale también al socket de
LiveView (que reconecta aparte del request inicial). RNF1 pide español
mexicano específicamente, no "internacional", así que se descartó
bilingüe por ahora: doble mantenimiento sin necesidad concreta detrás.
Si en algún momento aparece una razón real (usuarios de fuera,
stakeholders que necesiten inglés), se reevalúa.

`config :gettext, :default_locale, "es"` en `config/config.exs`. Las
pantallas de `phx.gen.auth` y los mensajes de validación de Ecto
(`priv/gettext/es/LC_MESSAGES/`) ya están traducidos.

## Identidad visual

El favicon de Gaiarda son 4 anillos concéntricos tangentes en la
esquina superior izquierda (rojo/naranja/verde/azul, colores de acento
de Metro), sobre fondo beige (`#F5F0E8`).

Para Mapo: mismo lenguaje visual, con una **M cruzada** (los trazos
diagonales centrales se pasan de largo y se cruzan por debajo) sobre
5 anillos concéntricos como fondo. `design/favicon.svg` es la versión
**definitiva**, confirmada por el usuario tal cual quedó (no una
prueba descartada por saturación, como se anotó por error en una
vuelta anterior de este documento). Ya está en uso real: copiado a
`mapo/priv/static/images/mapo-logo.svg`, como logo del navbar
(`Layouts.app`) y como favicon (`<link rel="icon"
type="image/svg+xml">` en `root.html.heex`).

## Concepto visual: mesa de planeación

Mapo heredó el tema metro de Gaiarda, pensado para tableros de
sistemas en operación. Mapo es otra cosa: una mesa donde se decide.
Frase de concepto: **un plano urbano sobre la mesa, con acetatos
encima**. Cada fuente (censo, DENUE, isócronas) es una hoja
translúcida que se desliza sobre el plano.

Segunda versión. La primera (panel lateral de tarjetas con switches,
Overpass, papel gris) se descartó: el concepto solo vivía en el texto,
la pantalla era un dashboard genérico.

- **El mapa es la mesa entera.** Nada de panel lateral: membrete,
  rótulo y la cinta de la capa elegida son papeles pegados encima con
  cinta adhesiva.
- **Charola de acetatos:** las capas asoman como pestañas por el borde
  inferior. Tocar una la desliza sobre el plano (barrido con
  `clip-path`); su cinta muestra fuente, control, escala y orden en una
  sola tira, que en celular se recorre de lado. El orden de la charola
  es el orden en el mapa.
- **Impreso contra anotado:** los datos van en Barlow y Barlow
  Condensed, las cifras en IBM Plex Mono. Lo que decide el equipo va a
  mano (Architects Daughter) y en lápiz rojo: la capa "Tus marcas", el
  rótulo, la ubicación. Las marcas nunca se mezclan con lo impreso.
- **Dos modos:** claro (papel) y oscuro (en urbanismo, una cianotipia
  profunda `#0F2444`, ya no el azul medio de la segunda versión). El mapa
  base de OSM se reimprime con las tintas de la piel activa mediante un
  filtro SVG de duotono (la idea del retinte por filtro viene de tanGo),
  así no hace falta servidor de teselas.
- **Pieles por enfoque, como los biomas de tarot.** La mesa (membrete,
  rótulo, charola, impreso contra anotado) es la base; cada enfoque trae
  su documento, sus tintas de día y de noche, su motivo de papel, su letra
  a mano y el nombre de sus dos modos. El color de cada piel es también el
  de sus capas en el mapa.

  | Piel | Documento | Motivo del papel | Letra a mano | Película |
  |---|---|---|---|---|
  | Urbanismo (base) | plano | cuadrícula | Architects Daughter | azul |
  | Demografía | cédula censal | renglones y casilla | Architects Daughter | guinda |
  | Comercio | libro mayor | renglones y doble margen rojo | Caveat | verde |
  | Consumo | ticket de caja | puntos de impresora térmica | Caveat | ocre |
  | Seguridad | expediente | perforación y doble raya | Special Elite | morado |
  | Laboral | tarjeta de checador | columnas y franja | Caveat | verde azulado |
  | Movilidad | hoja de ruta | franja de precaución | Architects Daughter | naranja |

  Guinda, verde, naranja, azul y morado son los anillos del logo; ocre y
  verde azulado se agregaron para consumo y laboral. En seguridad el modo
  oscuro es manila oscuro y no violeta, para no caer en morado sobre
  negro. Las 14 combinaciones (7 pieles por 2 modos) pasan: texto 7:1,
  secundario y anotaciones 4.5:1, bordes y películas 3:1.
- **La piel sigue al análisis:** la toma la capa de arriba de la pila
  (población pone demografía, DENUE pone comercio, una isócrona pone
  movilidad); sin capas, urbanismo. Un selector permite fijarla.
- **Acetatos:** se multiplican sobre el papel (`mix-blend-mode:
  multiply`); en el modo oscuro van normales, porque `screen` aplanaba
  las clases de la coropleta.
- **Vistas sin capas:** la raíz lleva urbanismo y cada bloque que
  pertenece a un enfoque lleva su propia piel. En `/perfil` eso son cinco
  documentos sobre el plano del municipio: cédula censal con casillas,
  libro mayor con el total doblemente subrayado y "las demás clases"
  explícitas, ticket con la advertencia de que la ENIGH no es municipal,
  expediente con los 40 tipos de delito (también los que tienen cero) y
  tarjeta de checador con la tasa sellada y la advertencia de que la ENOE
  es estatal. La portada muestra las siete pieles como una mano de
  cartas (el abanico de tarot): pasar encima viste la mesa con esa piel y
  tocar la deja puesta (patrón de la galería de iroFactory).
- **Prototipo:** `design/mesa_planeacion/`, se abre directo sin
  servidor. `index.html` es `/mapa`, `perfil.html`, `logistica.html` y `portada.html`. Lo
  común está aparte, como lo leerá Phoenix: `pieles.js` (fuente de
  verdad de las pieles; genera las reglas `[data-piel]`), `mesa.css`
  (papel, cinta, motivos, membrete, botones) y `plano.js` (el plano de
  fondo). Datos reales de Guadalajara: 442 AGEB del censo 2020, Voronoi
  de 1,858 negocios de DENUE con "papel" en el giro, una isócrona de 10
  minutos por OSRM y el perfil de zona de `mapo_core`.

**En Phoenix** (sesión 4, cerrada el 2026-10-30; historial en
[2026-10-rediseno-nucleo.md](../historial/2026-10-rediseno-nucleo.md)):

- Los colores de las pieles van en `mapo/assets/css/pieles.css`, un CSS
  estático generado desde `design/mesa_planeacion/pieles.js` (la fuente
  de verdad): así no parpadean al cargar. Si cambia una piel, se cambia
  en `pieles.js` y se regenera el CSS.
- `mesa.css` (papel, cinta, motivos, membrete, botones) y `mapa.css` van
  en `@layer components` e importados después de Tailwind, para que las
  utilidades sigan ganando y la capa no quede debajo de los estilos base.
- Los temas de daisyUI apuntan a los tokens de la piel: las vistas que
  todavía no se rehacen ya usan la paleta nueva.
- La raíz lleva `data-piel="urbanismo"`. En `/mapa` el servidor calcula
  la piel (la capa visible de más arriba, o la fijada en el rótulo) y se
  la manda al hook, que la pone en la raíz y la regresa a urbanismo al
  salir de la vista. Los cortes por quintil de la coropleta también los
  calcula el servidor, para que el mapa y la escala de la cinta usen los
  mismos números.
- `/perfil` sigue el prototipo: los cinco documentos con su piel sobre el
  plano de los AGEB del municipio, que el servidor arma como un solo
  trazo SVG (442 AGEB de Guadalajara son unos 30 KB). Si una fuente no
  cubre el municipio, su documento sigue en la mesa y lo dice. La
  consulta va en la URL (`/perfil?cve_ent=14&cve_mun=039`) para
  compartirla, y el perfil (unos 3 s) y el plano se piden con
  `start_async` para no congelar la vista. El botón "+ nota del equipo"
  del prototipo no entró: espera a que las anotaciones se guarden (capa
  "Tus marcas").
- `/logistica` tiene su prototipo en `design/mesa_planeacion/logistica.html`,
  con un VRP real de `mapo_core` sobre Guadalajara (`ruta.js`: 11 paradas,
  3 vehículos, 48.5 km por carretera). Piel de movilidad (hoja de ruta),
  plano a pantalla completa y una sola hoja pegada en vez del panel
  lateral. Las paradas son marcas del equipo: un clic pone una, se
  arrastran para moverlas y al tocarlas sale una ficha para cambiar la
  demanda, volverla depósito o quitarla. Cada vehículo lleva una tinta
  de los anillos del logo, con un halo del color del papel para leerse
  sobre el plano. Si se edita algo después de calcular, las rutas se
  quedan desvanecidas y la hoja pide recalcular: nunca se muestra una
  ruta que ya no corresponde como si fuera vigente. El número de cada
  parada es su nombre y no cambia al quitar otras. "Reordenar" se
  resolvió como "volverla depósito": el orden de visita lo decide el
  solver, no la persona. En celular la hoja baja al borde y se pliega;
  acostado, se va a la derecha.
- `/logistica` en Phoenix sigue su prototipo. El estado (paradas, flota,
  cálculo) vive en el LiveView y la hoja es HEEx; el hook solo dibuja y
  manda `poner`, `mover` (al soltar un arrastre) y las acciones de la
  ficha. Recalcular es `POST /vrp/calcular` con `start_async`; el
  resultado se guarda con la foto de las paradas con que se pidió, así
  que si la persona siguió editando, llega ya marcado como no vigente.
  Las rutas vacías que regresa el solver (un vehículo sin paradas) no se
  muestran. Hasta 50 paradas y 10 vehículos por cálculo.
- `leaflet.css` va en su propia capa CSS, declarada entre `base` y
  `components` al inicio de `app.css`. Sin capa le ganaba a todo lo de
  `@layer components` sin importar la especificidad: en `/mapa` el zoom
  quedaba detrás de la esquina y los bordes de Leaflet no eran los de la
  mesa. Como primera capa perdía contra el reset de Tailwind (los
  popups se quedaban sin margen). Los estilos de Leaflet de la mesa van
  en la clase `.plano-leaflet` y el entintado del plano en
  `assets/js/plano_tinta.js`, compartidos por `/mapa` y `/logistica`.
- El display grid de `.fieldset` (daisyUI) vive en `utilities` y le
  gana a `components`; la regla que deja los selects de ubicación en
  línea va fuera de capa al final de `mapa.css`.
- El botón de modo lleva `phx-update="ignore"`: su texto lo pone el
  script de la raíz y cualquier parche de LiveView lo regresaba a "Modo".
- El fondo animado de metro se quitó de la raíz: pintaba su propio fondo
  encima de la paleta. Qué fondo lleva Mapo se decide en la sesión 5.

Conceptos considerados y guardados para otras piezas (fondo de la home,
animaciones, un tema futuro):

- **Curvas de nivel:** la ciudad como terreno de datos, los anillos del
  logo como curvas. Se acerca a odysseus.
- **Onda de alcance:** los anillos como la onda de una piedra en el
  agua; un pulso al poner un pin o calcular una isócrona. Choca con
  shui y no cubre las capas que no son alcance.
- **Mapo doufu:** el nombre del repo literal (aceite de chile, tofu en
  cubos como AGEB). Demasiado juguetón para decisiones de negocio y
  gobierno, pero sirve para un detalle oculto.
