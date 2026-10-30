# Capa "Tus marcas", octubre 2026

Sesión 6 del plan, cerrada el 2026-10-30. Las anotaciones a mano del
equipo salen de la sesión colaborativa: ahora se ponen también sobre
`/mapa`, encima de los acetatos, y cada documento de `/perfil` lleva sus
notas del equipo. Las decisiones viven en
[decisiones.md](../arquitectura/decisiones.md), apartado "Tus marcas".

## Qué quedó

- **Las marcas de `/mapa` son de una sesión.** La pestaña "Tus marcas" va
  primero en la charola, no se reordena y no pone piel. Su cinta elige la
  sesión (agrupadas por equipo) y la forma, y dice cuántas marcas tiene.
  La sesión va en la URL (`/mapa?sesion=ID`) y la hoja de la sesión
  colaborativa enlaza ahí ("Ver las marcas con las capas de datos"). Lo
  que se pone en un lado llega en vivo al otro: es el mismo tópico de
  PubSub.
- **Círculo además del punto.** Un clic en el centro y otro en la orilla;
  mientras tanto, una guía punteada sigue al cursor. Se dibuja como lápiz
  (radio que ondula y un trazo que se pasa del inicio) y su nota va en la
  orilla derecha, que es también el asa: ahí se ancla la ficha y por ahí
  se llega con teclado. Escape cancela.
- **Esquema listo para más formas.** `anotaciones` ganó `forma`
  (`punto` o `circulo`) y `radio_m`. `geom` ya era geometría genérica, así
  que un trazo libre guardaría un LineString sin otra migración.
- **Dibujo compartido.** `assets/js/marcas.js` dibuja, crea y edita marcas
  para `CollabMap` y `MapaTecnico`; `MapoWeb.Marcas` atiende sus eventos
  en las dos vistas. Antes todo vivía dentro de `collab_map.js` y
  `SesionLive`.
- **Notas en `/perfil`.** Tabla `notas_perfil` y contexto `Mapo.Notas`:
  cada nota cuelga de equipo, municipio y documento. Van al pie del
  documento, a mano y en el lápiz de su piel, con su autor; "+ nota del
  equipo" abre un renglón para escribirla. Con varios equipos, la consulta
  deja elegir de cuál son las notas; sin equipo, el pie invita a crear
  uno. También llegan en vivo.

## Por qué así

- **Sesión y no equipo** para las marcas de `/mapa`: la sesión ya es "el
  mapa del equipo", con su tabla, su autorización y su canal en vivo.
  Colgar marcas sueltas del equipo habría duplicado la sesión
  colaborativa con dos tipos de anotación.
- **Notas aparte de `anotaciones`:** no son geométricas ni pertenecen a
  una sesión; las ancla el municipio y el documento.
- **La marca le gana a la isócrona:** con la cinta de "Tus marcas" abierta
  el clic pone marca; cerrada, elige el punto de salida de la isócrona.
  Así no hace falta un modo aparte.
- **El círculo se guarda como centro y radio,** no como polígono: conserva
  el radio exacto (la ficha lo dice en metros) y el trazo a mano se
  calcula al dibujarlo, en metros, sin rehacerse al hacer zoom.

## Bugs reales

- En la primera prueba el círculo salía picudo, como polígono: el temblor
  dependía del índice del punto con frecuencia alta. Ahora ondula en
  función del ángulo con 80 puntos.
- La ficha del círculo se abría donde caía el clic sobre el trazo, y el
  círculo no se alcanzaba con teclado. Se resolvió con el asa en la
  orilla.

Revisado en Chrome real (Playwright) en escritorio, 390×844 y 844×390,
claro y oscuro, sin scroll lateral ni errores de consola: círculo
dibujado en `/mapa`, visto en `/sesiones/:id`, editado y borrado; nota
puesta y borrada en `/perfil`.

## Pendiente

- Flechas y trazo libre (el esquema ya los admite).
- En 844×390 el encuadre de las marcas deja alguna debajo de la cinta
  (pasada final de diseño).
