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

## Concepto visual: mesa de planeación (propuesta, sesión 3)

Mapo heredó el tema metro de Gaiarda, pensado para tableros de
sistemas en operación. Mapo es otra cosa: una mesa donde se decide.
Frase de concepto: **un plano urbano sobre la mesa, con acetatos
encima**. Cada fuente (censo, DENUE, isócronas) es una hoja
translúcida que se apila sobre el plano.

- **Firma:** las capas se mezclan como acetatos reales
  (`mix-blend-mode: multiply` de día, `screen` en la mesa de luz), así
  que dos o tres capas se leen a la vez. Cada hoja lleva una pestaña
  del color de su capa, el orden de la pila es el orden en el mapa, y
  la coropleta codifica el valor como cantidad de tinta. Un rótulo de
  lámina (municipio, capas, fuentes, fecha) queda en una esquina, como
  en un plano.
- **Modos:** papel albanene de día, mesa de luz de noche.
- **Color:** los 5 tonos del logo son los colores de capa (guinda,
  naranja, verde, azul, morado), con variantes más claras para la mesa
  de luz. Acento del modo claro: el morado de la M (tinta de copia
  heliográfica). Acento del modo oscuro: amarillo marcatextos, para no
  caer en morado sobre negro. Todo texto pasa 4.5:1 y los bordes de
  controles 3:1 en los dos modos; el naranja (3.4:1 sobre papel) solo
  va en pestañas y trazos, nunca como texto.
- **Tipografía:** Overpass y Overpass Mono (Bunny Fonts). Overpass
  viene de Highway Gothic, la rotulación vial; la mono va en cifras y
  fuentes. Sustituye a DM Sans y Space Mono (esta última es la fuente
  reservada de metro y hoy se carga de Google Fonts).
- **Mapa base:** OSM en escala de grises, invertido en la mesa de luz,
  para que el color quede solo en los acetatos.
- **Prototipo:** `design/mesa_planeacion/index.html` (se abre directo,
  sin servidor), con datos reales de Guadalajara: 442 AGEB del censo
  2020, Voronoi de 1,858 negocios de DENUE con "papel" en el giro, y
  una isócrona de 10 minutos por OSRM.

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
