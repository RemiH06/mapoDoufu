# Fase 1: Autenticación y sesiones personales


- `mix phx.gen.auth Accounts User users` (LiveView based, con
  `Scope`). Rutas `/users/register`, `/users/log-in`,
  `/users/settings` respondiendo 200. Migración corrida (tablas
  `users`, `users_tokens`). 111 tests pasando (`mix test` dentro del
  contenedor `mapo`)
- Tema **metro** aplicado a nivel de app entera vía retoken de los
  colores de daisyUI (`assets/css/app.css`), tipografías DM Sans +
  Space Mono, toggle claro/oscuro/sistema (ya lo trae Phoenix 1.8 de
  fábrica en `Layouts.theme_toggle`, no hubo que construirlo). Fondo
  animado (grafo de nodos, hook `MetroBg` en `assets/js/metro_bg.js`)
  agregado solo en `/users/log-in` por ahora, respeta
  `prefers-reduced-motion` y ya deja el gancho (`window` event
  `mapo:toggle-bg-animation` + localStorage `mapo:bg-animation`) para
  cuando exista el toggle real
- Toggle real de animación en `/users/settings` (checkbox + hook
  `BgAnimationToggle` en `assets/js/bg_animation_toggle.js`),
  sincronizado con `metro_bg.js` vía localStorage y el evento
  `mapo:toggle-bg-animation`. Canvas de fondo agregado también en
  settings, no solo en login. 130 tests pasando (12 nuevos de la suite
  de settings, verificados con sesión real)
- Fondo animado también en `/users/register` (mismo canvas que
  login/settings)
- **Español único, decidido y aplicado** (no bilingüe, ver
  `../arquitectura/decisiones.md`). Las pantallas de `phx.gen.auth` (login,
  registro, confirmación, settings), sus flashes, los correos
  (`user_notifier.ex`), y los mensajes de validación de Ecto ("no
  puede estar en blanco", etc. vía `priv/gettext/es/`) ya están en
  español. `default_locale` fijo en `"es"` (`config/gettext,
  :default_locale`), sin lógica de cambio de idioma (no hace falta, no
  es bilingüe). `<html lang="es">`. 130 tests actualizados y pasando
  (las aserciones de los tests generados comprobaban texto en inglés
  literal)
- **Home real de Mapo**, reemplazando la bienvenida genérica de
  Phoenix (`lib/mapo_web/controllers/page_html/home.html.heex`):
  logo, tagline "Mapo, powered by Gaiarda", la frase de una línea de
  qué es Mapo, y CTA que cambia según sesión ("Ir a mis equipos" si
  hay sesión, "Crear cuenta"/"Iniciar sesión" si no). Envuelta en
  `Layouts.app` (antes era la única pantalla sin el header con logo +
  toggle de tema que ya tiene el resto de la app). 161 tests pasando
- **Logo real de Mapo en el navbar y como favicon** (el favicon ya
  estaba resuelto: `design/favicon.svg`, la versión de 5 anillos + M
  cruzada, es la definitiva). Copiado a
  `priv/static/images/mapo-logo.svg` (reemplaza el placeholder
  `logo.svg` de Phoenix, que se borró). Favicon real vía `<link
  rel="icon" type="image/svg+xml">` en `root.html.heex` (cubre
  navegadores modernos; el `favicon.ico` viejo de Phoenix se quedó sin
  usar, como respaldo para navegadores muy antiguos, no vale la pena
  convertirlo a mano)
- Correo en producción: aplazado a propósito ("Future Feature"), no
  solo pendiente. No se puede configurar un adapter real todavía
  porque no hay dominio propio (SendGrid, Resend, Postmark, etc. todos
  piden un dominio verificado para enviar). Sigue cayendo a
  `/dev/mailbox`. Se retoma cuando haya dominio, no antes (**sigue sin
  resolverse**)
