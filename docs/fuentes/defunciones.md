# Defunciones registradas (INEGI)

Muertes por municipio de residencia, causa, sexo y grupo de edad, de 2020 a 2023.
Responde: **¿de qué muere la gente que vive aquí, y cuántos?** No dice que una causa
sea ambiental: es contexto para la vista de riesgos, nunca prueba.

```bash
docker compose exec mapo_core python -m mapo_core.cli ambiental --crudos /app/data/crudos-ambiental --fuente defunciones
```

Unos 10 minutos (lee 3.8 millones de certificados). Reemplaza
`fuente_defunciones_municipal`.

## De dónde sale

Los datos abiertos de las estadísticas de defunciones registradas
(`inegi.org.mx/programas/edr/`), un ZIP por año. El CSV cambia de carpeta según el
año (2023 no usa `conjunto_de_datos/`): se toma el miembro más grande. Licencia:
términos de uso libre de INEGI; citar "INEGI, Estadísticas de defunciones
registradas".

## Qué se guarda

**Solo agregados, ningún microdato.** Cada certificado trae fecha de nacimiento,
ocupación, localidad y causa: juntos identifican a una persona en un municipio
chico. Se cuenta por:

| Columna | Qué es |
|---|---|
| `anio_registro` | Año de registro (el del archivo); algunas muertes ocurrieron el año anterior |
| `cve_ent`, `cve_mun` | Residencia habitual. `99`/`999` es no especificado; claves de entidad 33 a 35 son el extranjero |
| `causa` | CIE-10 a tres caracteres (`C34` cáncer de pulmón, `N18` enfermedad renal crónica, `J18` neumonía) |
| `sexo` | 1 hombre, 2 mujer, 9 no especificado |
| `edad_grupo` | `edad_agru` de INEGI: 1 menores de un año, 2 a 5 un año cada uno, 6 a 29 quinquenios de 5 a 9 hasta 120 y más, 30 no especificada |

No se guarda la localidad: un conteo de una causa en una ranchería es una persona.

## Validación (2026-11-19)

Totales por año contra los boletines de INEGI: 2020, 1,086,743; 2021, 1,122,249;
2022, 847,716; 2023, 799,869 (el de 2023 es la cifra definitiva del [comunicado del
8 de noviembre de 2024](https://inegi.org.mx/contenidos/saladeprensa/boletines/2024/EDR/EDR2023_Dtivas.pdf)).
Los cuatro iguales. 1,874,283 filas.

## Límites

- Tasas sin ajustar por edad: un municipio viejo tiene más muertes por tumores
  aunque no haya nada en el ambiente. Comparar entre municipios pide ajustar.
- La causa es la básica del certificado; la calidad del llenado cambia entre lugares.
- Un conteo chico (menos de 10 al año) varía mucho de un año a otro: no leer
  tendencias en él.
