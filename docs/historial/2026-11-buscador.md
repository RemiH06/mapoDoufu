# Fase 6b: buscador (noviembre 2026)

Segunda mitad del modo buscador (RF6). La especificación vigente está en
`../producto/buscador.md`; aquí queda qué se hizo y qué se aprendió.

## Qué quedó

- Pantalla `/buscador`, primera sección del membrete. Se puede escribir
  la pregunta o llenar la plantilla a mano, y las dos llevan a lo mismo.
- `mapo_core/buscador.py`: analizador determinista (función pura, se
  prueba sin base) y resolución de las cinco intenciones.
- `mapo_core/consultas.py`: las consultas que antes vivían en `server.py`,
  generalizadas a varios municipios y a una lista exacta de clases. El
  modo técnico y el buscador usan las mismas.
- `cuantos_cerca`, la única consulta nueva: negocios dentro de la
  isócrona (`negocios_en_poligono`).
- El hook `MapaTecnico` ganó una capa de puntos, la ubicación del
  navegador, `centrar` y márgenes para encuadrar entre papeles fijos.
- `escala_quintiles` se movió a `MapoWeb.Cifras`, porque ya la usan dos
  pantallas.

## Decisiones

- **El analizador vive en `mapo_core`**, junto a la tabla de rubros que
  consulta. Phoenix solo dibuja; hasta los huecos de cada intención
  vienen del catálogo.
- **Un Voronoi recortado a la unión de los municipios**, no uno por
  municipio (estaba abierto desde la 6a; razón en `buscador.md`).
- **La pregunta va en la URL, las ediciones a mano no.** Basta para
  compartir una pregunta; serializar la plantilla entera no se justificó
  todavía.

## Cifras reales

Con los datos de Jalisco (2026-11-03):

| Pregunta | Resultado | Tiempo |
|---|---|---|
| Florerías en Zapopan | 305 negocios, 1,476,491 habitantes, 4,841 por negocio | 2.4 s |
| Florerías en Guadalajara, Zapopan y Tlaquepaque | 916 negocios | 1.1 s |
| Supermercados en Guadalajara y Tlaquepaque | 44 y 21 | 0.1 s |
| Sector salud en Guadalajara | 7,843: pasa de `MAX_PUNTOS`, solo cifras | 0.3 s |
| Hospitales públicos en Zapopan | 8 | menos de 0.1 s |
| Farmacias a 10 minutos del centro de Guadalajara | 453, con OSRM real | 1.1 s |
| Gente de 18 a 24 años en Zapopan | 179,405 | 0.1 s |

## Lo que se aprendió

- **El test de sinónimos volvió a pagar.** Al agregar sinónimos de sector
  encontró tres choques con rubros: "accesorios", "gobierno" y
  "construcción".
- **Las clases CSS sin acotar chocan en silencio.** `.ficha` y `.frase`
  ya existían en `logistica.css`: las fichas salieron como cajas y la
  frase se partía palabra por palabra por un `display: flex` ajeno. Se
  vio solo en el navegador. Las reglas de `buscador.css` van acotadas a
  `.pregunta` y `.respuesta`.
- **Un clic a escala de país no sirve de punto de partida.** El plano
  abre en México entero; ahora se acerca al punto elegido para poder
  corregirlo.
- **Dos papeles fijos tapaban el plano en celular.** Por eso la plantilla
  se pliega al resolver.
