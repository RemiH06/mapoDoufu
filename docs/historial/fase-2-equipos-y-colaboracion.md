# Fase 2: Sesiones de equipo y colaboración


- Base de datos lista para esto: `db` cambió de `postgres:16-alpine` a
  `postgis/postgis:16-3.4-alpine`, extensión PostGIS habilitada en
  `mapo_dev` y `mapo_test` (decisión y por qué en
  `../arquitectura/stack.md`)
- Modelo de datos: `Mapo.Teams` (contexto), tablas `teams` y
  `team_memberships` (rol `owner`/`admin`/`member` vía `Ecto.Enum`,
  único por `[team_id, user_id]`). La propiedad de un equipo sale de
  la membresía (rol `owner`), **no** de una columna `user_id` directa
  en `teams` (el generador de Phoenix la agregó sola por el sistema de
  "scope" nuevo, se corrigió a mano: antes de generar un recurso
  compartido por varias personas, pasar `--no-scope` desde el
  principio). `list_teams`/`get_team!` filtran por membresía del
  usuario; `update_team`/`delete_team` exigen rol `owner`/`admin`
  según el caso. 130 tests pasando
- Pantallas: `/teams` (lista, solo los equipos del usuario),
  `/teams/new` (crear, el creador queda como `owner`), `/teams/:id`
  (detalle: miembros con su rol, agregar miembro existente por correo
  con rol member/admin, quitar miembro). Autorización real: solo
  owner/admin ven "Agregar miembro"; no se puede quitar al único
  owner del equipo (protegido en el contexto, no solo en la
  pantalla). Link "Mis equipos" agregado al navbar. 146 tests pasando
- **Invitar a alguien sin cuenta todavía**: contexto `Mapo.Teams`
  ampliado con `Invitacion` (tabla `invitaciones`: correo, rol
  `member`/`admin`, token único, estado `pendiente`/`aceptada`). En
  `/teams/:id`, si "Agregar miembro" no encuentra una cuenta con ese
  correo, ya no falla: crea (o reutiliza, si ya había una pendiente
  para ese correo) una invitación y manda un correo con el link
  `/invitaciones/:token` (`Mapo.Teams.TeamNotifier`, mismo patrón que
  `UserNotifier`, cae a `/dev/mailbox` en dev). Sección "Invitaciones
  pendientes" en la pantalla del equipo, visible solo para
  owner/admin, con botón para cancelar. `InvitacionLive.Show` (ruta
  pública `/invitaciones/:token`, sin requerir sesión previa) cubre
  los cinco estados: token inexistente, ya aceptada, visitante anónimo
  (CTA de iniciar sesión/crear cuenta), sesión con correo distinto al
  invitado (mensaje de error, no deja aceptar), y el flujo normal de
  aceptar (crea la membresía y marca la invitación como aceptada en
  una transacción). 185 tests pasando. Hueco conocido, no resuelto:
  no hay mecanismo de "volver a la invitación" después de iniciar
  sesión o registrarse desde el link (hay que volver a abrir el
  correo), ni se precarga el correo en los formularios de
  login/registro cuando se llega desde una invitación
- **LiveView colaborativo construido y probado de verdad**: contexto
  `Mapo.Sesiones` (`Sesion` pertenece a un `Team`, `Anotacion`
  pertenece a una `Sesion` y a un `User`, con `geom` como
  `Geo.PostGIS.Geometry` real, no lat/lon sueltos). Mapa con Leaflet
  (vendorizado a mano en `assets/vendor/leaflet/`, sin npm), hook
  `CollabMap`. Clic en el mapa -> `crear_anotacion` -> se guarda -> se
  transmite por `Phoenix.PubSub` a **todos** los que ven la misma
  sesión, incluido quien la creó (nadie dibuja su propio clic "de una
  vez", todos pasan por el mismo camino de broadcast). Sección de
  sesiones agregada a `/teams/:id`. 160 tests pasando, incluyendo uno
  con **dos procesos de LiveView reales viendo la misma sesión**: uno
  crea una anotación, se confirma que ambos la reciben, no solo
  mockeado
- Definición de qué se guarda de una sesión de equipo: `nombre` +
  `team_id`, cada anotación es `geom` (punto) + `texto` + quién y
  cuándo. Nada más, se agrega si hace falta, no antes
- **Presencia** (`MapoWeb.Presence`, agregado al árbol de
  supervisión): "Viendo ahora: ..." en `/sesiones/:id`, en vivo,
  excluyendo al propio usuario. Reusa el mismo tópico de PubSub que ya
  usaban las anotaciones (`Sesiones.topico_sesion/1`), no hace falta
  un canal aparte
- **Editar y borrar anotaciones**: `Sesiones.update_anotacion/4` y
  `delete_anotacion/3`, mismo patrón de autorización y broadcast que
  crear (cualquier miembro del equipo, no solo quien la creó: es un
  pizarrón compartido). El popup de cada marcador en el mapa trae un
  campo de texto editable y un botón de borrar
- **El mapa recuerda dónde lo dejaste**: centro y zoom en
  `localStorage`, por sesión (`mapo:sesion:{id}:vista`), preferencia
  de cliente pura, no se guarda en la base de datos
- 169 tests pasando en `mapo` en el cierre de esta fase (autorización
  de editar/borrar, rechazo de editar una anotación de *otra* sesión,
  presencia probada con dos procesos de LiveView reales)
- Nota permanente, no un pendiente: solo se vendorizó
  `leaflet.js`/`leaflet.css`, no los íconos default de marcador (no
  hacen falta, se usa `circleMarker`; si algún día se agrega el
  control de capas nativo de Leaflet, esos sí necesitarían íconos
  propios)
