# Visión de Mapo

## Qué es Mapo, en una frase

**Gaiarda contesta "qué hay". Mapo contesta "qué deberías hacer con eso".**

Mapo se construye encima de Gaiarda (la consume, no la reemplaza) para
responder preguntas que implican una decisión: dónde conviene poner un
negocio, en qué colonias buscar cierto perfil de gente para contratar,
qué zonas le faltan servicios públicos al gobierno.

**"Consumir" es código, no un servicio vivo.** Corregido el
2026-08-24 después de que `mapo_core` se construyera mal por un rato
como cliente HTTP hacia un Gaiarda corriendo aparte: la relación real
es que Mapo vendoriza (copia y adapta) el código de descarga/
normalización de Gaiarda hacia sus propias tablas, en su propia
Postgres. En tiempo de ejecución, ni en desarrollo ni en producción,
Mapo nunca depende de que haya un proceso de Gaiarda corriendo en
ningún lado: lo único que se recicla es su código, no un servicio.
El detalle de cada fuente ya vendorizada está en `../fuentes/`.

Tagline reservado para cuando arranque el repo de Mapo:
**"Mapo, powered by Gaiarda"**

## División de responsabilidades: Gaiarda vs. Mapo

| | Gaiarda | Mapo |
|---|---|---|
| Rol | Plomería: descarga, normaliza, sirve datos | Inteligencia: cruza datos, recomienda, decide |
| Usuarios manejados | Ninguno (sin cuentas) | **Sí tiene sesiones**, personales o de equipo |
| Rutas | **Turismo**: TSP entre municipios, presupuesto de viaje (gas, casetas, hospedaje), seguridad de la zona | **Logística de carga/pasajeros**: líneas de camión, transporte de bienes, distinto problema de optimización (capacidad, ventanas de tiempo, múltiples paradas comerciales) |
| Tema visual de rutas | Odysseus (Ulises, el viajero) | Pendiente de definir, pero debería sentirse distinto a Odysseus, ya que resuelve un problema distinto |

## Fuentes de datos disponibles en Gaiarda (para que Mapo las consuma)

7 fuentes, todas con checkpoint y tests: Marco Geoestadístico (INEGI),
DENUE (negocios), CRE (gasolineras), Censo de Población por AGEB,
SESNSP (incidencia delictiva), ENIGH (ingreso/gasto de hogares, 17
tablas), ENOE (empleo, 5 tablas trimestrales). Servidas vía API REST
(`gaiarda/src/gaiarda/server.py`) además de la base SQLite directa.

## Requisito nuevo que Gaiarda nunca tuvo: sesiones

Mapo va a necesitar, desde el diseño inicial:
- Autenticación de usuarios
- Sesiones **personales** y **de equipo** (varias personas en la misma sesión)
- Muy probablemente: anotaciones colaborativas en tiempo real sobre el
  mapa (ver siguiente sección)

Esto es una pieza de arquitectura que Gaiarda no resuelve ni necesita
resolver; hay que diseñarla desde cero para Mapo.

## Ejemplos de preguntas que Mapo debería poder responder

(Tal como se plantearon originalmente, para no perder la intención)

- Si hay una colonia sin papelerías, ¿por qué, y en qué parte exacta de
  la colonia conviene poner una (con mapas de calor a nivel AGEB)?
- Si una empresa necesita contratar personas de cierto rango de edad,
  ¿en qué colonias debería buscar?
- Si un comerciante quiere vender tacos, ¿dónde le conviene?
- Para el gobierno: ¿dónde faltan ciertos servicios públicos?
- Logística de transporte de bienes/pasajeros: líneas de camión,
  optimización de rutas comerciales (no confundir con las rutas de
  turismo, que se quedan en Gaiarda).

## Modos de uso

Mapo va a mostrar los datos y dejar que quien lo usa decida (hereda de
Gaiarda la honestidad de no esconder metodología detrás de un número
único, ej. seguridad sin puntaje). Dos modos, pensados para gente
distinta:

- **Modo técnico/analítico**: la herramienta de verdad. Mapas
  personalizables, capas y estadísticas múltiples cruzadas, variedad
  amplia de tipos de mapa (incluyendo isócronas, ver más abajo). Para
  quien ya sabe qué está buscando y quiere explorar.
- **Modo buscador**: una capa de conveniencia sobre el modo técnico,
  no un producto aparte. Preguntas acotadas en lenguaje natural simple
  ("¿dónde pongo una floristería?", "¿cuántos supermercados hay a 10
  minutos de mí?"), resueltas por un **sistema experto** (intención +
  parámetros fijos: rubro, radio o tiempo, ubicación) contra la misma
  data y lógica del modo técnico, sin generar texto libre ni inventar
  respuesta. A pesar de sentirse "más simple" para quien lo usa, es el
  modo más pesado de construir bien: tiene que entender la intención
  sin que se le deletree campo por campo, y traducirla exacto a lo que
  el modo técnico ya sabe resolver.
