# Requisitos de Mapo

Formaliza lo decidido en `vision.md` y `../arquitectura/` en dos
listas. No inventa alcance nuevo, solo lo ordena. Se actualiza cuando
una decisión de producto cambie.

**Estado**: Listo = construido y funcionando. Parcial = construido en
parte, ver la nota. Vigente = no es un entregable único, es un
principio que se aplica de forma continua. Pendiente = no empezado. El
detalle de lo ya construido vive en `../historial/`.

## Requerimientos funcionales

| ID | Requerimiento | Estado |
|---|---|---|
| RF1 | Autenticación de cuentas personales (registro, login, recuperación de contraseña) | Listo (la recuperación es vía magic link por correo, no un flujo de "reset password" aparte). En producción depende de un adapter de correo real, que todavía no existe (falta dominio) |
| RF2 | Sesiones de equipo: varias personas autenticadas comparten una misma sesión de trabajo | Listo |
| RF3 | Colaboración en tiempo real: anotaciones sobre el mismo mapa visibles para todo el equipo sin recargar la página | Listo |
| RF4 | Modo técnico: mapas personalizables, con múltiples capas y estadísticas cruzadas de los enfoques disponibles | Listo (capas múltiples en `/mapa`, estadísticas cruzadas en `/perfil`, confirmado con datos reales de Jalisco) |
| RF5 | Capacidad de isócronas y otras vistas espaciales derivadas de tiempo/distancia de traslado | Listo (isócronas como capa en `/mapa`) |
| RF6 | Modo buscador: preguntas en lenguaje natural acotado (intención + parámetros fijos), resueltas por un sistema experto contra la misma data del modo técnico, sin generar texto libre ni inventar respuestas | Pendiente (Fase 6) |
| RF7 | Motor de logística (VRP): múltiples vehículos, capacidad de carga, ventanas de tiempo de entrega, paradas comerciales con restricciones propias | Parcial: motor completo en `mapo_core` (OR-Tools, `POST /vrp/calcular`) y pantalla `/logistica` con geometría real de cada ruta. La interfaz todavía no expone ventanas de tiempo ni capacidad distinta por vehículo (el backend sí las soporta) |
| RF8 | Vendorizar (no consumir en vivo) las fuentes de datos de Gaiarda: código de descarga/normalización propio, sin depender de un Gaiarda corriendo en ningún lado | Listo: geoestadístico, censo, DENUE, ENIGH, ENOE y SESNSP vendorizados y cargados con datos reales (ver `../fuentes/`). SESNSP se carga a mano (no hay descarga pública automatizable) |
| RF9 | Casos de ejemplo iniciales, probados en ambos modos: floristería, call center, supermercado, consultorio/hospital, estación de policía | Pendiente (Fase 7). La estación de policía ya está confirmada como posible vía DENUE |

## Requerimientos no funcionales

| ID | Requerimiento | Estado |
|---|---|---|
| RNF1 | Interfaz completa en español mexicano | Listo |
| RNF2 | Modo claro/oscuro disponible en toda la aplicación | Listo |
| RNF3 | Animaciones de fondo en pantallas como login y configuración, con un toggle para desactivarlas | Listo (fondo persistente en toda la app salvo las pantallas de mapa) |
| RNF4 | Todo el stack corre en Docker; no depende de tener Elixir/Python instalados directo en la máquina de desarrollo | Listo |
| RNF5 | Transparencia metodológica: no reducir decisiones a un puntaje único que esconda su metodología (heredado de Gaiarda, ej. seguridad sin puntaje) | Vigente (VRP, isócronas, Voronoi, coloreado, perfil de zona) |
| RNF6 | Honestidad ante datos faltantes: no inventar clasificaciones ni fuentes que no existen; declarar explícitamente cuando un enfoque no tiene fuente o dato | Vigente (`valor_choropleth: null`, secciones `null` en `/perfil_zona` cuando no hay datos de ese municipio, campo `metodo` en todo lo que depende de OSRM, 503 honesto si la base no responde) |
| RNF7 | Estructura de datos escalable: agregar un enfoque o fuente nueva debe ser agregar un módulo, no reestructurar lo existente | Vigente (cada capacidad y cada fuente de `mapo_core` es su propio módulo) |
| RNF8 | Comunicación entre `mapo` (Elixir) y `mapo_core` (Python) por HTTP simple; sin colas de mensajes ni RPC binario en esta primera versión | Listo |
| RNF9 | Licencia MIT, repo público bajo el nombre "Mapo" | Listo |
| RNF10 | Mensajes de commit en formato conventional commits, lo más cortos posible; sin guión largo en ningún texto, código o commit | Vigente |
