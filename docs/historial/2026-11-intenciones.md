# Fase 6a: intenciones y rubros (noviembre 2026)

Primera mitad del modo buscador (RF6). La especificación vigente está en
`../producto/buscador.md`; aquí queda qué se hizo y qué se aprendió.

## Qué quedó

- Cinco intenciones cerradas: `donde_poner`, `cuantos`,
  `cuantos_cerca`, `donde_contratar` y `perfil`, todas sobre lógica que
  el modo técnico ya tiene. Los municipios son multiselección.
- Entrada por texto libre (analizador determinista) y por plantillas,
  las dos desde el inicio.
- Tabla curada `mapo_core/src/mapo_core/rubros/`: 21 sectores, 183
  rubros con sinónimos y las 918 clases de DENUE de Jalisco. Módulo
  `mapo_core.rubros` para leerla, 7 tests de consistencia y aviso en
  `cli denue` de clases sin clasificar.

## Decisiones

- **Sector, rubro y sinónimos; cada clase en un solo rubro.** Más fácil
  de revisar y de explicar que permitir una clase en varios rubros.
- **`sector_publico` sale del nombre de la clase**, no de un modelo:
  DENUE ya dice "del sector público" o "del sector privado".
- **Industria, mayoreo y agro no se ofrecen en el buscador.** Son 378
  clases que casi nadie pregunta en lenguaje común; siguen disponibles
  en el modo técnico.
- **El catálogo SCIAN completo se quedó fuera por ahora.** Su página en
  INEGI arma la lista con JavaScript y no se encontró una descarga
  directa. Con las clases de la base basta para Jalisco; el aviso de la
  CLI cubre los estados nuevos.

## Lo que se aprendió del Baker

El Baker `clasificador` (modelo local chico) acertó lo grueso: separó
bien consultorio de hospital, que es el caso de `rubros.md`. Pero en la
revisión completa salieron errores que ningún test hubiera atrapado:
paleterías en agua y hielo, educación media técnica terminal en
secundaria, telas en artesanías y laboratorios de pruebas industriales
en laboratorio clínico. Además, sus respuestas traen los índices
desglosados y leerlas cuesta casi lo mismo que clasificar; por eso los
12 sectores de nombres regulares se hicieron con reglas por palabra
clave. Para tablas que van a quedar como dato, la revisión humana
no es opcional: aquí se revisó completo lo del Baker, las reglas por
sus casos generales y Remi aprobó la tabla por muestreo. Los casos de
la Fase 7 son la siguiente revisión, ya con preguntas reales.

El test de sinónimos encontró dos choques reales al primer intento
(`computación` y `maquinaria` en dos rubros cada uno).
