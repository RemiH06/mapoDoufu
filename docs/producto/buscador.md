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
`test_ningun_termino_lleva_a_dos_rubros` lo impide en la tabla).

## Tabla de rubros

Vive en `mapo_core/src/mapo_core/rubros/` y es dato revisado a mano,
no se genera en vivo:

- `sectores.csv`: 21 sectores. `industria`, `mayoreo` y
  `agro_mineria_y_energia` no se ofrecen en el buscador (siguen en el
  modo técnico) y no tienen rubros.
- `rubros.csv`: 183 rubros con nombre para mostrar y sinónimos. Los
  `otros_*` no llevan sinónimos: existen para que ninguna clase quede
  huérfana.
- `clases.csv`: las 918 clases de DENUE de Jalisco, cada una con su
  sector, rubro, `sector_publico` y `origen` (de dónde salió la
  asignación).

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
la tabla siga consistente.
