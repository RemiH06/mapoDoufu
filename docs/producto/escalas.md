# Escalas y dos indicadores

Cómo se pinta un indicador en `/mapa` desde la sesión 29e: la escala de color de
cada capa por clases, qué se lee del censo por AGEB (conteo, tasa o combinado) y cómo
van dos indicadores juntos. El código: `MapoWeb.Escala` (clases y paletas),
`MapoWeb.LecturaCenso` (lecturas del censo), `MapoWeb.Leyenda` (leyendas) y el hook
`mapa_tecnico.js` (la pintura).

## Un conteo nunca va en color

Una AGEB grande tiene más personas, más viviendas y más de todo por ser grande. Pintar
un conteo en color hace que el área mande. Por eso, en el censo por AGEB:

- Un **conteo** (personas, hogares, viviendas) va en **círculos proporcionales**: el
  área del círculo va con el valor, en el punto de dentro de la AGEB
  (`ST_PointOnSurface`).
- Una **tasa** (porcentaje, densidad, promedio o razón) va en **color**.

El buscador también: su "población por AGEB" se pinta como personas por km².

Los círculos de la leyenda tienen el tamaño que se ve de cerca (zoom 12 o más). De
lejos el hook los encoge todos en la misma proporción (a 1/8 en zoom 8): con 22 px
fijos, la zona metropolitana de Guadalajara (1,987 AGEB) era una mancha. Lo que se
compara (un círculo contra otro) no cambia. Los grandes se dibujan abajo.

## Lecturas del censo

| Lectura | Fórmula | Unidad | Canal |
|---|---|---|---|
| Conteo | A | personas, hogares, viviendas | círculos |
| % de su denominador | A ÷ denominador × 100 | % de ... | color |
| Por cada 1,000 habitantes | A ÷ población total × 1,000 | ... por cada 1,000 habitantes | color |
| Por km² | A ÷ área de la AGEB en km² | ... por km² | color |
| Tal cual (promedios) | A | años, personas por vivienda | color |
| A ÷ B | A ÷ B | ... por cada B | color |
| A − B | A − B | la de A | círculos (hueco si es negativo) |
| Cambio % | (A − B) ÷ B × 100 | % más que B | color |

La fórmula y la unidad se ven en la cinta y van en la cita. No hay índices ponderados
ni puntajes: un combinado es una sola operación entre dos columnas del mismo censo y
del mismo nivel (AGEB). Lo que falta (un dato confidencial, un denominador cero) queda
sin dato, nunca en cero.

### Denominadores naturales

| Indicadores | Denominador |
|---|---|
| Población por sexo y edad, con servicios de salud | `POBTOT` |
| PEA, inactiva | `P_12YMAS` (por sexo, `P_12YMAS_F` y `P_12YMAS_M`) |
| Ocupada, desocupada | `PEA` |
| Viviendas habitadas | `VIVTOT` |
| Viviendas con internet, computadora, auto, celular, sin bienes | `TVIVPARHAB` |

Los `VPH_*` se cuentan sobre `TVIVPARHAB`, no sobre `VIVPAR_HAB`: en Jalisco, 209 de
4,579 AGEB tienen más viviendas con internet que `VIVPAR_HAB` y ninguna más que
`TVIVPARHAB`. Los demás denominadores se comprobaron igual (ninguna PEA sobre su
población de 12 años o más, ninguna desocupada sobre la PEA). Los que no son columna
propia salen de `datos_json` (el renglón completo del censo); el `*` de INEGI
(confidencial) llega como `null`.

`mapo_core` manda en cada AGEB su área en km² (del polígono sin simplificar), su punto
de dentro y, con `extra=`, las columnas que pida la lectura (hasta cuatro, de una
lista cerrada). Mapo calcula la tasa.

## Dos indicadores

El canal lo decide el tipo de cada lectura, no la persona:

- **Tasa y conteo:** la tasa en color, el conteo en círculos encima (tinta de texto,
  casi transparentes, para no tapar el color).
- **Dos tasas:** a elegir entre el **3x3** (tres clases de cada una, paleta de Joshua
  Stevens: una en verde azulado, otra en rosa, las dos altas en azul oscuro) o la
  **segunda como altura** (extrusión; el plano se inclina 50°, la más alta mide
  2.5 km, sin dato al ras y punteada).
- **Dos conteos:** no se leen juntos; la cinta pide pasar uno a tasa.

El 3x3 usa terciles (o cortes naturales o intervalos iguales, en 3); manual no aplica.

## Escala de color

En cada capa por clases (censo y vivienda; los datos propios usan la de omisión):

- **Paleta:** la tinta de la capa (opacidad por clase, la de antes), viridis, cividis,
  amarillo-verde-azul, naranja-rojo, y tres divergentes (naranja-morado,
  café-verde azulado, rojo-azul). Todas publicadas como aptas para daltonismo
  (viridis y cividis; ColorBrewer las marca así).
- **Clases por:** cuantiles (mismas zonas en cada clase), cortes naturales, intervalos
  iguales o manual (los cortes escritos, hasta seis).
- **Clases:** de 3 a 7.
- **Invertir:** voltea la paleta.

Los cortes naturales son el óptimo exacto de Jenks en una dimensión (la menor suma de
cuadrados dentro de cada grupo, como `ckmeans` de Wang y Song, 2011), por
programación dinámica con divide y vencerás: con las 4,932 AGEB de Jalisco tarda
milisegundos. Una prueba lo compara con la búsqueda exhaustiva en datos al azar.

Una clase va de su corte de abajo (sin incluirlo) al de arriba (incluido). Si el
método no alcanza las clases pedidas (muchos valores iguales), sale con las que hay y
la leyenda lo dice. En tema claro, más es más oscuro; en oscuro, más es más claro
(la paleta se voltea), para que más siempre sea más contraste contra la mesa. Las
divergentes no se voltean con el tema.

La escala se aplica al cambiarla, sin pedir datos a `mapo_core`: el servidor guarda los
valores de cada AGEB y manda solo los cortes y los colores nuevos (`escala_coropleta`,
`escala_vivienda`). Lo que se lee (indicador, lectura, segundo indicador) se aplica
con "Actualizar".

## Confianza como transparencia (vivienda)

- **Intercensal:** cada municipio trae su coeficiente de variación. Menor a 15 %, la
  tinta completa; de 15 a 30 %, al 55 %; 30 % o más, al 22 % (los niveles de
  precisión de INEGI).
- **Precio por AGEB estimado:** se pinta, tenue y con borde punteado, solo si su rango
  entero cae en una clase. Si cruza clases, va sin color: su punto medio pasaría por
  dato. Con los quintiles de omisión en la ZMG se pintan unas 180 de 801 estimadas,
  casi todas en la clase más baja o la más alta (`precio-estimado.md`).

## En el enlace

`censo`, `como`, `b`, `censo2`, `como2`, `modo2`, `esc` y `vesc` (`citar.md`). La
escala va en una sola clave: `paleta:metodo:clases`, más `:inv`; con manual, los
cortes en lugar de las clases (`esc=rdbu:manual:-5,0,12.5`). Lo de omisión no se
escribe.
