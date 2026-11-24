# Organización de `/mapa` (sesión 29d)

Cuarta sesión del bloque 29a a 29m. `/mapa` pasa a una mesa neutra con el color solo en
los datos, la pila se ordena arrastrando, los alcances en auto se apilan con la gente
dentro, las rutas pueden llevar su color, y las cuatro capas que seguían pidiendo estado y
municipio usan la zona común.

## Qué se hizo

- **Mesa neutra.** `/mapa` ya no cambia de piel con la capa de arriba ni tiene el
  selector "Piel" del rótulo: la mesa es blanca en claro y negra en oscuro (piel `neutra`
  en `mesa.css`; texto 16:1 o más, secundario 7.4:1, acento 5.5:1, bordes 4:1, medidos
  contra los dos fondos). Cada acetato conserva su tinta en el plano y en su pestaña. La
  raíz sale con `data-piel="neutra"` desde el primer render (`piel_raiz` en el layout
  raíz) y el hook la pone al navegar dentro de LiveView. El parámetro `piel` de los
  enlaces viejos se ignora y la URL se corrige.
- **Pestañas arrastrables** (hook `Charola`, `charola.js`). Arrastrar una pestaña la
  mueve en la pila; al soltar se manda el orden entero (`ordenar`) y el servidor solo lo
  acepta si son las mismas capas. Con ratón empieza al moverse 6 px; con el dedo, después
  de dejarlo quieto 280 ms, para que deslizar siga recorriendo la lista. El clic que sigue
  al arrastre no abre la cinta. "Más arriba" y "Más abajo" se quedan para el teclado.
- **Alcances apilados** (`docs/producto/isocronas.md`). Hasta cinco, cada uno con su
  número y su tinta, y `POST /isocronas/poblacion` cuenta la gente dentro de cada uno, en
  todos y en alguno. El enlace guarda todos (`alcance=...;...`).
- **Rutas con color.** `transporte/zona` manda el `route_color` del GTFS (`col`) cuando es
  un hexadecimal válido. Con 20 rutas o menos y colores en el feed, cada ruta sale con el
  suyo; con más, una sola tinta con el grosor y la tinta por frecuencia. La cinta deja
  cambiarlo ("Color de las rutas"). Pasar el cursor por una ruta la dibuja encima con un
  halo de tinta de texto: con cientos encimadas en el centro es la forma de seguir una.
- **Zona común en censo, vivienda, municipios y transporte** (pendiente de la 29b). El
  censo y el precio por AGEB toman las AGEB con su punto de dentro en la zona; vivienda
  por municipio y "Municipios", todos los municipios de los estados que toca la zona (un
  municipio necesita a sus vecinos para leerse por quintiles); transporte, las rutas que
  cruzan la zona y sus paradas dentro, hasta 5,000 km² (la ZMG sí, Jalisco no: se dice
  por qué). La ficha de vivienda va por cvegeo (`ficha=14039`; la de tres dígitos sigue
  abriendo con el primer estado de la zona).
- **Arrastres de la 29a.** Las fichas se recorren para quedar fuera del membrete, la
  cinta y la charola (`ficha` en `plano.js`, con el margen de cada vista); vale para los
  cinco mapas. Los acetatos de `/mapa` y `/buscador` van debajo de los nombres del mapa
  base.
- **Capturas:** `scripts/capturas/mapa29d.js`.

Producción en `ff12be5` el 2026-11-23 (revertir: `deploy-20261123c`; sin migración). En
Pixilate, con la ZMG: censo 0.16 s (1,987 AGEB), transporte 0.8 s (332 rutas, 305 con
color propio), precio por AGEB 0.17 s, municipios 0.3 s y la gente de dos alcances 0.02 s.

## Decisiones

- **Sin animación de entrada del acetato.** En Leaflet era una transición de CSS sobre su
  capa; en MapLibre todo va en un lienzo y la opacidad de la coropleta depende del dato,
  y MapLibre no anima propiedades que dependen del dato. Animarla a mano es reescribir la
  pintura de miles de polígonos en cada cuadro. No vale lo que cuesta.
- **El orden de la pila no va en el enlace**, como antes: es cómo lo ve cada quien.
- **Vivienda y municipios por estado completo.** Recortarlos a una colonia dejaría un
  solo municipio, sin nada contra qué compararlo.
- **El color de las rutas no va en el enlace.** Al abrirlo se decide igual que al
  ponerlo (por cuántas rutas hay).

## Bugs reales

- **El censo de un estado por geometría tardaba 44 s.** Punto en polígono contra Jalisco
  entero, aun partido en pedazos. Un estado, municipios o una metrópoli son municipios
  enteros: van por clave (`zona.filtro_agebs`), 0.1 a 0.7 s. Solo colonia, CP, dibujo y
  círculo van por geometría.
- **`text = text[]` con la metrópoli.** `ANY((SELECT cvegeos ...))` necesita el
  `::text[]` explícito; sin él PostgreSQL toma la subconsulta como un conjunto de arreglos.
- **El arrastre no encontraba destino.** La charola se tomaba por columna cuando la
  primera pestaña estaba puesta: va levantada 8 px. Se compara el borde izquierdo.
