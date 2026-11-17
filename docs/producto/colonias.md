# Colonias: polígonos para cualquier parte del país

La gente piensa su ciudad por colonias, pero ninguna fuente nacional abierta las
publica con polígono: INEGI llega a AGEB y manzana, el catálogo de asentamientos
de INEGI y el de SEPOMEX dan nombres y códigos postales sin coordenadas, y OSM
tiene pocas. Este pipeline arma el polígono de una colonia en cualquier municipio
y dice de dónde salió y qué tan seguro es. Estado: diseño y prototipo
(2026-11-17), sin implementar.

## Niveles

Se usa el mejor nivel disponible; la columna `metodo` dice cuál fue.

| Nivel | Fuente | Cobertura | Confianza |
|---|---|---|---|
| `oficial` | Plano de colonias del municipio o del instituto de planeación, cuando lo publica | Algunos municipios | La del municipio; puede estar desactualizado |
| `osm` | Límites de OpenStreetMap (`place=neighbourhood` o `suburb` con polígono) | Escasa en México | Variable; revisar |
| `direcciones` | Votación de direcciones con coordenadas sobre las manzanas de INEGI | Nacional | Medida por colonia (ver abajo) |
| `equipo` | Polígono que dibuja o corrige un equipo en Mapo | Donde un equipo trabaje | La del equipo; queda como dato propio |

Un polígono de nivel `equipo` nunca reemplaza a los demás para otros equipos: es
un dato propio, y su diferencia con el nivel `direcciones` sirve para medir el
error del método.

## Nivel `direcciones`

Insumos, todos nacionales:

- **Manzanas** del marco geoestadístico (API de INEGI, `geo/mza/{ent}/{mun}`).
- **Puntos con colonia escrita:** DENUE (`colonia` y `codigo_postal` de cada
  negocio, ya en la base de Mapo). Después, otros registros con coordenadas y
  colonia: escuelas (SEP) y unidades de salud (CLUES).
- **Nombres oficiales por código postal:** catálogo de SEPOMEX, para unificar
  variantes ("LOPEZ COTILLA", "MANUEL LOPEZ COTILLA", "COL. MANUEL LÓPEZ COTILLA
  TLAQ.").

Pasos:

1. **Normalizar nombres:** sin acentos ni prefijos (colonia, fraccionamiento, el,
   la...), y unir variantes dentro del mismo código postal por parecido de texto.
   Cuando exista el catálogo de SEPOMEX, el nombre canónico es el suyo.
2. **Votar por manzana:** cada punto vota por la manzana donde cae o a 25 m (los
   negocios se ubican sobre la banqueta). Gana la colonia con más votos; la
   pureza es la parte de votos que se llevó.
3. **Rellenar:** una manzana sin votos se asigna si 60 % o más de las manzanas
   votadas a 150 m son de una misma colonia.
4. **Unir** las manzanas de cada colonia en un polígono, con sus métricas:
   manzanas votadas y rellenadas, puntos, pureza mediana, población del censo.

### Prototipo: López Cotilla, Tlaquepaque (2026-11-17)

Con DENUE y las manzanas de la zona del CP 45615:

- Más de 220 negocios con alguna variante del nombre en Tlaquepaque; el grupo
  principal (207, "LOPEZ COTILLA", CP 45615)
  tiene su centro en 20.5736, -103.3591 con desviación de ~200 m.
- 37 manzanas contiguas con pureza mediana de 1.0, 55.6 ha y 2,240 habitantes.
- 74 % de las manzanas de la zona recibió algún voto.

Lo que el prototipo enseñó:

- **Las manzanas sin negocios no votan.** Una zona solo habitacional queda como
  hueco o se asigna por relleno; el relleno no recuperó ninguna en este caso.
- **Manzanas grandes:** un predio grande con pocos negocios en su orilla puede
  entrar completo. Pedir un mínimo de votos por hectárea o partirlas.
- **Negocios lejos del grupo:** algunos registros con el nombre caen a 1 o 2 km
  (error de captura o una calle homónima). Quitar los puntos a más de N
  desviaciones del grupo antes de votar.
- **Dos nombres para lo mismo:** "López Cotilla" y "Manuel López Cotilla" en el
  mismo CP; el umbral de parecido no los unió. El catálogo de SEPOMEX lo resuelve.

## Cómo saber si sirve

- **Contra planos oficiales:** en municipios que publican colonias, comparar con
  intersección sobre unión por colonia y reportar la distribución.
- **Contra equipos:** cada corrección de nivel `equipo` es un dato de validación.
- **Por colonia:** mostrar siempre puntos, pureza y manzanas rellenadas; con pocos
  puntos, decir que es aproximado en vez de dibujar un límite seguro.

## Lo que falta

- Implementarlo en `mapo_core` como fuente (manzanas en la base y tabla de
  colonias con `metodo`), con pruebas.
- Registro de planos oficiales por municipio, como el de catastro.
- Bajar el catálogo de SEPOMEX y los registros de escuelas y salud.
- En Mapo: buscar una colonia por nombre y abrirla como zona en el mapa.
