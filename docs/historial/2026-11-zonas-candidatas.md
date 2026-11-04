# Recomendaciones: zonas candidatas (noviembre 2026)

Pidieron recomendaciones, y un puntaje chocaba con RNF5. La respuesta fue
filtrar en vez de calificar. La especificación vigente está en
`../producto/buscador.md`; aquí queda qué se hizo y qué se aprendió.

## Qué quedó

- `mapo_core/zonas.py` y `POST /buscador/zonas`: AGEB que cumplen dos criterios
  a la vista, con lo que descartó cada uno.
- `OSRMClient.duraciones_matriz`: orígenes contra destinos, y un tramo sin ruta
  se queda en su celda en vez de tirar la matriz.
- Sección "Zonas candidatas" en la respuesta de `donde_poner`, con los criterios
  editables, la lista y el botón para ver cada zona.
- Capa `zonas` en `MapaTecnico`: resalta AGEB de la coropleta que ya está en el
  navegador, así que solo viaja la lista de claves.
- Isócronas con las muestras en escala geométrica.

## Decisiones

- **Filtros, no pesos.** Razón en `../arquitectura/decisiones.md`.
- **Dentro de `donde_poner`.** La pregunta ya existía; una sexta intención se
  traslaparía con ella.
- **Matriz, no isócronas por negocio.** Las isócronas entran después, para
  revisar una zona.
- **Un solo indicador a elegir.** Varios criterios del censo son fáciles de
  agregar si hacen falta; empezar con uno mantiene clara la lectura.
- **Los minutos se guardan en memoria**, no en una tabla: 32 consultas bastan
  para mover criterios, y no hay nada que migrar.

## Cifras reales

Con los datos de Jalisco y OSRM v26.7.3 en Docker (2026-11-04), en la laptop de desarrollo:

| Consulta | AGEB | Candidatas por defecto | Primera vez | Mover un criterio |
|---|---|---|---|---|
| Florería, Zapopan | 540 | 94 | 4 a 6 s | menos de 50 ms |
| Supermercado, Zapopan | 540 | 86 | 3 a 5 s | menos de 50 ms |
| Florería, Guadalajara, Zapopan y Tlaquepaque | 1,219 | 169 | 13 a 18 s | menos de 50 ms |
| Farmacia, zona metropolitana (5 municipios) | 1,840 | 124 | 22 a 26 s | 20 a 40 ms |

En producción, con OSRM en el disco de WSL, las candidatas son las mismas y la
primera consulta tarda mucho menos: 2.4 s con tres municipios y 3.3 s con la zona
metropolitana. Mover un criterio, 10 ms.

La última vuelta de Florería en Zapopan pone el criterio en 5 minutos y deja 13
AGEB; con el indicador de 60 años o más, 15. 327,602 celdas de matriz sin un solo
tramo sin ruta.

## Lo que se aprendió

- **El más cercano en línea recta no es el más cercano por calle** en 4 de cada
  10 AGEB de Zapopan. Medirlo cambió el diseño de 1 vecino a 10.
- **`Req` corta a los 15 s.** La zona metropolitana tarda más: esa llamada lleva
  su propio `receive_timeout`.
- **Las capturas vieron lo que los tests no:** el borde rojo no se leía sobre la
  tinta vino, y la isócrona de 5 minutos salía como un triángulo porque casi
  ninguna muestra alcanzaba a estar cerca del origen.
- **Una zona rara es un dato.** La isócrona de araña de la AGEB 1193 no era un
  error de dibujo: el punto cae en un coto. El mismo efecto infla sus minutos, y
  por eso se documentó como límite.
- **Medir desde Windows con `localhost` engaña.** El refiltrado parecía tardar
  2.3 s y eran 2 s de IPv6; contra `127.0.0.1`, 30 ms.
