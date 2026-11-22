# Empleo formal del IMSS (noviembre 2026, sesión 25)

Puestos de trabajo y salario de cotización del IMSS por municipio y grupo de
actividad, para responder lo que el conteo de DENUE no: cuánta gente tiene empleo
formal en un municipio, en qué y cuánto cotiza. Ficha en `../fuentes/imss.md`.

## Qué se hizo

- **Cargador** `mapo_core/imss_asegurados.py` y `cli imss`: lee archivos mensuales
  ya bajados (`.csv` o `.csv.gz`) en flujo y guarda las sumas por municipio y grupo
  en `fuente_imss_asegurados` (41,600 renglones por mes, contra 4.6 millones del
  archivo).
- **Equivalencia de claves** IMSS a INEGI (`imss_municipios.csv`, generada por
  `scripts/imss/equivalencia.py`) y catálogo de grupos (`imss_grupos.csv`).
- **Puente con los rubros:** columna `grupos_imss` en `rubros/sectores.csv`.
- **`/perfil`:** la tarjeta de checador pasa de "Desocupación" a "Empleo": puestos del
  municipio, permanentes y eventuales, salario diario, reparto por división y la parte
  en el rango del tope; la desocupación de la ENOE queda como renglón del estado.
- **Buscador:** en `cuantos` y `donde_poner`, el empleo formal de los grupos del rubro
  por municipio, con su parte del total y su salario.
- Cargados enero y diciembre de 2024 en dev.

## Por qué así

- **Archivos locales, no descarga.** `datos.imss.gob.mx` responde 503 (Incapsula) a
  cualquier programa, desde Aerilate y desde Pixilate. No se salta el filtro. Remi
  eligió cargar solo lo que guardó íntegro el Internet Archive (enero y diciembre de
  2024) en vez de bajar meses nuevos a mano por ahora.
- **Sumar al cargar.** El archivo trae fracción, tamaño de patrón, sexo, edad y
  rango salarial; Mapo usa municipio y grupo. Guardar todo serían 4.6 millones de
  renglones por mes para nada que se muestre.
- **La clave del IMSS se guarda junto a la de INEGI**, para rehacer la equivalencia
  sin recargar cuando se compruebe una clave nueva.
- **Lo que no tiene municipio no se pierde:** va en `000`, suma en su estado y la
  pantalla dice cuántos puestos son (la Ciudad de México entera).
- **Variación anual solo contra el mismo mes del año anterior.** Enero contra
  diciembre mezcla la temporada (diciembre pierde empleo todos los años), así que
  con lo cargado no hay variación y la pantalla lo dice. Aparece sola al cargar el
  mismo mes de otro año.
- **Grupo y no división en el buscador.** Los 62 grupos del IMSS se parecen a los
  sectores de Mapo (87 preparación de alimentos, 92 servicios médicos); las 9
  divisiones mezclan demasiado (la 8 junta bancos, hoteles y restaurantes).

## Bugs y sorpresas

- **Claves que no están en el catálogo.** Zapopan y Guadalajara salían con 35,765 y
  5,546 puestos menos que el IIEG. Las diferencias eran exactas a dos claves nuevas
  (`Z60` y `Z62`) que no aparecen en el diccionario de 2019. Con ellas, siete
  municipios cuadran al puesto. Otras siete claves nuevas de cinco estados quedan sin
  asignar hasta tener con qué comprobarlas.
- **El diccionario y los archivos no coinciden:** el diccionario pone los grupos 20 a
  29 en la división 2; los archivos, en la 3.
- **Copias truncas en el Archive.** El CDX lista decenas de meses, pero solo dos
  pesan lo que deben (52 MB comprimidos); los demás son la página del filtro o
  pedazos.
- **Barras desalineadas en `/perfil`.** Cada renglón de `.barras` era su propia
  rejilla, así que las barras arrancaban donde terminaba cada etiqueta, y en celular
  una regla ponía columnas a cada renglón. Ahora el contenedor define las columnas y
  los renglones las heredan (`subgrid`); arregla también el expediente de seguridad.

## Pruebas

`pytest` (428) y `mix precommit` (408) verdes; revisión en navegador con
`scripts/capturas/empleo.js` (tarjeta de Zapopan y buscador, tres tamaños y dos
modos). La CDMX sin municipio no se puede ver mientras solo Jalisco tenga municipios
cargados: la cubre una prueba de LiveView. Cuadre de diciembre de 2024 en la ficha de
la fuente.
