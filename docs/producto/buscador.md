# Modo buscador

Capa de conveniencia sobre el modo técnico (RF6). Quien pregunta escribe
en español común; un sistema experto lo traduce a una **intención** con
**parámetros** de un conjunto cerrado y lo resuelve con la misma lógica
del modo técnico. No genera texto libre ni adivina: lo que no reconoce
lo dice.

## Intenciones

| Intención | Ejemplo | Parámetros | Se resuelve con |
|---|---|---|---|
| `donde_poner` | "¿Dónde pongo una floristería en Zapopan?" | rubro, municipios | Voronoi de la competencia del rubro (`/voronoi/denue`) y coropleta de población por AGEB (`/censo/choropleth`, `pobtot`). Cifras por municipio: negocios del rubro, población y habitantes por negocio (población ÷ negocios, con la fórmula a la vista) |
| `cuantos` | "¿Cuántos supermercados hay en Guadalajara y Tlaquepaque?" | rubro o sector, municipios | Conteo de DENUE por municipio y los puntos en el mapa |
| `cuantos_cerca` | "¿Cuántas farmacias hay a 10 minutos de aquí?" | rubro o sector, punto, minutos | Isócrona desde el punto (`/isocronas/calcular`, con su `metodo`) y negocios del rubro dentro de ella. Es la única consulta nueva: isócrona y negocios ya existen por separado |
| `donde_contratar` | "¿Dónde busco gente de 18 a 24 años en Zapopan?" | rango de edad, municipios | Coropleta del censo del rango (`/censo/choropleth`) y desocupación de la ENOE, que es estatal y así se dice |
| `perfil` | "¿Cómo es Tlaquepaque?" | un municipio | La pantalla `/perfil` |

"¿Dónde faltan servicios públicos?" es `donde_poner` con un rubro de
gobierno, salud o educación y el filtro `solo_publicos`.

Ninguna intención regresa un puntaje único (RNF5). "Habitantes por
negocio" es una razón con su fórmula, no una calificación: se muestra
junto a las capas y quien pregunta decide.

## Parámetros

- **Rubro**: uno de `mapo_core/src/mapo_core/rubros/rubros.csv`,
  reconocido por su nombre o sus sinónimos. También se puede preguntar
  por un **sector** completo ("¿cuántos negocios de salud...?").
- **Municipios**: uno o varios, del catálogo de la base (multiselección).
- **Punto**: la ubicación del navegador o un clic en el mapa.
- **Minutos**: entero positivo; las isócronas no tienen tope propio.
- **Rango de edad**: solo los grupos que trae el censo por AGEB: 0 a 2,
  3 a 5, 6 a 11, 12 a 14, 15 a 17, 18 a 24 y 60 o más. Un rango que no
  coincide (por ejemplo 25 a 40) no se aproxima: se avisa.
- **`solo_publicos`**: se queda con las clases cuyo nombre dice "del
  sector público" (más las de gobierno), columna `sector_publico`.

## Entrada

Las dos formas desde el inicio, y llevan a lo mismo:

1. **Texto libre.** Un analizador determinista (sin modelo de lenguaje):
   normaliza acentos y mayúsculas, busca nombres y sinónimos de rubro,
   nombres de municipio, números con "minutos" o "años", y palabras de
   intención ("dónde pongo/abro/conviene", "cuántos", "cerca de",
   "contratar", "cómo es"). Muestra la plantilla que entendió con los
   huecos editables antes de resolver.
2. **Plantillas con huecos.** "¿Dónde pongo un [rubro] en [municipios]?"
   con selects, para quien prefiera elegir.

Si falta un parámetro, el hueco queda vacío y se pide; si un término
coincide con dos rubros, no se elige uno en silencio (el test
`test_ningun_termino_lleva_a_dos_rubros` lo impide en la tabla). Si la
pregunta nombra dos rubros distintos, tampoco: se avisa y el hueco queda
vacío.

Reglas del analizador (`mapo_core/src/mapo_core/buscador.py`):

- **Gana el término más largo sin traslape.** "Tienda de mascotas" le
  gana al municipio Mascota y "San Juan de los Lagos" a "Lagos".
- **Cada palabra admite plural** ("consultorios médicos").
- **Rubro le gana a sector.** Si aparecen los dos y son de sectores
  distintos, se usa el rubro y se avisa.
- **Lo ya reconocido no cuenta para lo demás.** "Baños públicos" es un
  rubro, no el filtro `solo_publicos`.
- **Sin palabra de intención**, los minutos implican `cuantos_cerca` y la
  edad implica `donde_contratar`, las únicas intenciones que los usan.
- **`donde_contratar` y `perfil` no usan rubro.** Si la pregunta nombra
  uno, se quita y se avisa.
- **"Centro de salud" implica `solo_publicos`.**

## Pantalla

`/buscador` usa el mismo plano y el mismo hook de `/mapa` (`MapaTecnico`),
con la piel del enfoque de la respuesta. A la izquierda va la pregunta y
su plantilla, escrita como frase con los huecos; a la derecha, la
respuesta con sus cifras, su fórmula, sus avisos y sus fuentes. En
celular la plantilla se pliega al resolver para dejar ver el plano.

La pregunta va en la URL (`?q=`) para poder compartirla. Las ediciones a
mano de la plantilla no viajan en la URL.

Qué huecos lleva cada intención lo dice `GET /buscador/catalogo`, que
también trae los rubros por sector y los grupos de edad. Nada de eso se
repite en Phoenix. `POST /buscador/interpretar` convierte el texto en
plantilla y `POST /buscador/resolver` da capas y cifras; si a la
plantilla le falta un hueco responde 422 con `faltan`.

## Resolución

Las consultas viven en `mapo_core/src/mapo_core/consultas.py` y las usan
por igual el modo técnico y el buscador. Criterios:

- **Varios municipios: un solo Voronoi recortado a su unión.** La
  competencia no se detiene en la frontera municipal: una florería de
  Zapopan compite con la de Guadalajara de enfrente. Dibujar uno por
  municipio cortaría esas celdas en una línea que nadie ve en la calle.
- **El rubro filtra por lista exacta de clases**, no por texto: el
  `ILIKE` del modo técnico mezclaría clases que la tabla ya separó.
- **La población es la del municipio**, no la suma de sus AGEB: esa suma
  deja fuera a la población rural.
- **Negocios sin coordenadas** cuentan en `cuantos` y `donde_poner`, pero
  no se dibujan, y se avisa cuántos son. En `cuantos_cerca` no pueden
  contar, porque no se sabe si caen en la isócrona, y también se dice.
- **Más de 5,000 negocios** no se dibujan uno por uno (`MAX_PUNTOS`): se
  dan las cifras y se avisa. En `donde_poner`, el Voronoi conserva el
  tope y el mínimo del modo técnico.
- **`perfil`** no resuelve nada: lleva a `/perfil` del municipio.
- **No todo es un negocio.** En gobierno y con `solo_publicos`, las cifras
  dicen "unidades" (`cifras.unidad`) y la leyenda habla de cobertura, no
  de competencia.

## Filtro "giro" del modo técnico

El campo "Giro" de `/mapa` entiende las mismas palabras que el buscador
(`buscador.giro_tecnico`). Si el texto es un término de la tabla, usa las
clases de ese rubro o sector; si no, las clases que lo contienen, sin
importar acentos. Si nada coincide, cae al `ILIKE`, para clases de un
estado que todavía no están en la tabla. `/voronoi/denue` regresa en
`filtro` lo que reconoció y la cinta lo muestra.

## Tabla de rubros

Vive en `mapo_core/src/mapo_core/rubros/` y es dato revisado a mano,
no se genera en vivo:

- `sectores.csv`: 21 sectores, con sinónimos propios para preguntar por
  un sector entero. El nombre del sector no cuenta como término: el de
  "Otros comercios" también es nombre de rubro. `industria`, `mayoreo` y
  `agro_mineria_y_energia` no se ofrecen en el buscador (siguen en el
  modo técnico) y no tienen rubros.
- `rubros.csv`: 183 rubros con nombre para mostrar y sinónimos. Los
  `otros_*` no llevan sinónimos: existen para que ninguna clase quede
  huérfana. Dos columnas más:
  - `marcas`: se reconocen ("oxxo", "walmart"), pero DENUE clasifica por
    giro: se resuelve el giro entero y se avisa.
  - `nota`: lo que hay que saber al leer la cifra de ese rubro. Sale en
    los avisos de la respuesta.
- `clases.csv`: las 918 clases de DENUE de Jalisco, cada una con su
  sector, rubro, `sector_publico` y `origen` (de dónde salió la
  asignación).
- `municipios_alias.csv`: cómo le dice la gente a municipios de nombre
  largo ("Tlaquepaque", "Ciudad Guzmán", "Vallarta"). Por estado.

La llave es el nombre exacto de la clase, porque `BuscarEntidad` de
DENUE no trae el código SCIAN.

### Cómo se armó (2026-11-03)

1. Las 918 clases distintas de `fuente_denue_negocios` (401,813
   negocios de Jalisco).
2. Un Baker local (`clasificador`) asignó cada clase a un sector.
3. El mismo Baker asignó rubro en 6 sectores (comida preparada,
   abarrotes, salud, educación, otros comercios, servicios
   profesionales). Los otros 12 sectores, de nombres muy regulares, se
   clasificaron con reglas por palabra clave.
4. Revisión a mano de todo lo del Baker: 54 asignaciones corregidas o
   puestas a mano (`origen = a_mano`), entre ellas paleterías que había
   puesto en agua y hielo, la educación media técnica terminal que había
   puesto en secundaria y los laboratorios de pruebas industriales que
   había puesto en laboratorio clínico.

Resultado: 201 clases por el Baker, 285 por regla, 54 a mano y 378 sin
rubro (sectores no buscables).

### Al cargar otro estado

`python -m mapo_core.cli denue --estado NN` avisa al final de las clases
que no están en `clases.csv`. Hay que agregarlas a mano con su sector y
rubro antes de usarlas en el buscador; `tests/test_rubros.py` revisa que
la tabla siga consistente. Los apodos de sus municipios se agregan a
`municipios_alias.csv`.
