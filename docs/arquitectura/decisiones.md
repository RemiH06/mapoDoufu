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
