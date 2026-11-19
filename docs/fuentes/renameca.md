# Calidad del agua (Conagua, RENAMECA)

Sitios de la Red Nacional de Medición de la Calidad del Agua con lo que se midió
en cada uno y su calificación. Responde: **¿cómo está el agua de este río, presa o
pozo, en qué parámetro falla?** No responde si hay plaguicidas: la red no los mide.

```bash
docker compose exec mapo_core python -m mapo_core.cli ambiental --crudos /app/data/crudos-ambiental --fuente renameca
```

Unos 25 s. Reemplaza `fuente_renameca_sitios`.

## De dónde sale

Los dos Excel de `gob.mx/conagua` ("Calidad del agua superficial" y "subterránea",
2012 a 2025), primera hoja. Cada una trae además un diccionario y las escalas de
calificación, que se reproducen en `calidad_generalidades_2025.pdf` (en los crudos).
Licencia: datos abiertos del gobierno federal; citar "Conagua, RENAMECA".

## Qué se guarda

| Columna | Qué es |
|---|---|
| `tipo`, `clave` | `superficial` o `subterranea` y la clave del sitio |
| `cuenca` | En superficial, la cuenca; en subterránea, el acuífero |
| `cuerpo`, `subtipo` | Cuerpo de agua y tipo (río, presa, pozo, brote...) |
| `periodo` | `2012-2025`: **cada fila resume el periodo**, no es una medición |
| `semaforo` | Verde, amarillo o rojo, como lo publica Conagua |
| `parametros` | JSON: por medición, `valor` y `calidad` |

`valor` se guarda tal cual: `<2` quiere decir "bajo el límite de detección de 2",
no cero ni dos. Los sólidos disueltos subterráneos traen dos calificaciones (para
riego y por salinidad): la segunda va en `calidad_2`.

Superficial: DBO, DQO, SST, coliformes fecales, *E. coli*, enterococos, oxígeno
disuelto (superficie, medio y fondo) y toxicidad (*Daphnia* y *Vibrio*).
Subterránea: alcalinidad, conductividad, sólidos disueltos, fluoruros, dureza,
coliformes fecales, nitratos, arsénico, cadmio, cromo, mercurio, plomo, manganeso
y hierro.

## Validación (2026-11-19)

- 5,033 sitios superficiales y 2,875 subterráneos, los renglones de los dos Excel;
  todos con coordenada dentro de México.
- Las calificaciones quedan emparejadas con su medición: en los 3,367 sitios con
  DBO numérica, la calificación guardada es la que da la escala de Conagua para
  ese valor (DBO ≤ 3 excelente, ≤ 6 buena, ≤ 30 aceptable, ≤ 120 contaminada, más
  fuertemente contaminada) en el 100 %. Los 167 con `<` están todos en excelente.
- Semáforo: superficial 2,089 verde, 1,211 amarillo, 1,402 rojo, 331 sin; subterránea
  1,225, 502, 1,026 y 122. Conagua publica porcentajes por año (2023: 50.9 % de 450
  sitios superficiales en rojo); este archivo resume 2012 a 2025 y no se compara
  con un año.

## Límites

- **No es serie de tiempo.** Para ver cambio hacen falta los cortes por año
  (`calidad_5000_sitios_*` trae 2021).
- **No mide plaguicidas.** Ninguna fuente abierta los mide; entran como datos
  propios de un equipo.
- Un sitio en rojo dice que algún parámetro incumple, no cuál: para eso está
  `parametros`.
- Hay sitios del mismo cuerpo con claves distintas a lo largo de los años.
