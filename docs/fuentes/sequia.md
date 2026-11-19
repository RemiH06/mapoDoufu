# Sequía por municipio (SMN, Monitor de Sequía)

La categoría de sequía de cada municipio en cada corte del Monitor de Sequía de
México, de enero de 2003 a octubre de 2026. Responde: **¿cuánto tiempo ha pasado
este municipio en sequía, y qué tan fuerte?**

```bash
docker compose exec mapo_core python -m mapo_core.cli ambiental --crudos /app/data/crudos-ambiental --fuente sequia
```

Unos 50 s. Reemplaza `fuente_sequia_municipal`.

## De dónde sale

`MunicipiosSequia.xlsx` del SMN (`smn.conagua.gob.mx`, Monitor de Sequía en
México), hoja `MUNICIPIOS`: un renglón por municipio y una columna por fecha de
corte. Mensual hasta 2014 y quincenal después. Licencia: datos abiertos del gobierno
federal; citar "SMN, Conagua".

## Qué se guarda

Una fila por municipio y corte, con `categoria`:

| Valor | Qué es |
|---|---|
| `D0` | Anormalmente seco (no es sequía todavía) |
| `D1` a `D4` | Sequía moderada, severa, extrema y excepcional |
| `sin` | Sin anomalía. En el Excel es la celda vacía: no es dato faltante |

Una categoría que no sea esas detiene la carga.

## Validación (2026-11-19)

- 438 cortes de 2003-01-31 a 2026-10-31 para 2,478 municipios: 1,085,364 filas.
- 2024-04-30: 1,970 municipios de D1 a D4. Con datos del Monitor a esa fecha,
  [Grupo Animal](https://grupoanimal.mx/estados/municipios-sequia-mexico) reporta
  1,961. La diferencia de 9 (0.5 %) puede ser el número de municipios: la tabla
  usa el marco actual (2,478).

## Límites

- La categoría se asigna al municipio entero aunque la sequía cubra parte.
- Un municipio creado después de 2003 aparece como `sin` en los cortes anteriores a
  que existiera.
- Es sequía meteorológica con impactos; no dice cuánta agua hay en las presas ni en
  el acuífero (para eso, `acuiferos.md`).
