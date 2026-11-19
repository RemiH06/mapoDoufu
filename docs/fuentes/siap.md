# Producción agrícola municipal (SIAP)

Cierre agrícola por municipio de 2003 a 2025: qué se sembró, cuánto se cosechó y
perdió, y cuánto valió. Responde: **¿qué se cultiva aquí, con riego o de temporal,
y cuánto?** Sirve para saber qué cultivos (y por lo tanto qué agroquímicos
probables) hay alrededor de una zona.

```bash
docker compose exec mapo_core python -m mapo_core.cli ambiental --crudos /app/data/crudos-ambiental --fuente siap
```

Unos 80 s. Reemplaza `fuente_siap_agricola`.

## De dónde sale

Un CSV por año de `nube.agricultura.gob.mx` (cierre de la producción agrícola).
Licencia: datos abiertos del gobierno federal; citar "SIAP, SADER".

Lo que cambia entre años: la codificación (UTF-8 o Latin-1, se prueba UTF-8
primero), la columna del cultivo (`Nomcultivo Sin Um` de 2015 a 2020, `Nomcultivo`
el resto; los nombres de cultivo son los mismos) y la del precio (que no se usa).

## Qué se guarda

Llave: año, municipio, ciclo (otoño-invierno, primavera-verano, perennes), modalidad
(riego, temporal), cultivo y unidad del volumen. Valores: `sembrada`, `cosechada` y
`siniestrada` en hectáreas, `volumen` en su unidad y `valor` en pesos de cada año.

El SIAP publica por CADER y municipio; un municipio partido entre varios CADER se
suma. El rendimiento y el precio no se guardan: salen de `volumen / cosechada` y
`valor / volumen` con las sumas, nunca promediando los publicados.

## Validación (2026-11-19)

- 800,773 filas de 23 años.
- Maíz grano 2022: 26.55 millones de toneladas; el SIAP publicó 23,168,504 de blanco
  y 3,364,735 de amarillo (26.53 millones, [De nuestra cosecha, octubre
  2023](https://www.gob.mx/cms/uploads/attachment/file/861109/DE_NUESTRA_COSECHA_OCTUBRE_2023.pdf)).
  La diferencia de 0.1 % son los otros colores.
- Maíz grano 2023 y 2024: 27.55 y 24.33 millones; SADER pronosticó para 2024 una
  caída de 8.9 % frente a 2023, que desde 27.55 da 25.1, su cifra.
- Jalisco 2024: 1.60 millones de ha sembradas.

## Límites

- Es por municipio: no dice dónde están las parcelas. Para eso, la frontera agrícola
  (`ambientales.md`, sección "Frontera agrícola") o el uso de suelo.
- No dice qué agroquímicos se usaron.
- `valor` en pesos corrientes: para comparar años, deflactar.
