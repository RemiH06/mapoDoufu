# Financiamientos para vivienda (SNIIV)

Créditos y subsidios para vivienda por municipio y año, del Sistema Nacional de
Información e Indicadores de Vivienda (SEDATU). Responde: **cuánto se presta aquí
para vivienda, quién presta y para qué segmento**. No es precio: el monto es lo
prestado, y el valor de la vivienda viene como categoría, no en pesos.

```bash
docker compose exec mapo_core python -m mapo_core.cli sniiv [--estado 14,01]
```

Sin `--estado` baja los 32 (330,878 filas, minuto y medio). Cada estado se
reemplaza en su propia transacción en `fuente_sniiv_financiamiento`.

## De dónde sale

API pública del cubo, documentada en `https://sniiv.sedatu.gob.mx/Reporte/Datos_abiertos`:

```
https://sniiv.sedatu.gob.mx/api/CuboAPI/GetFinanciamiento/{año inicio},{año fin}/{estado}/{municipio}/{dimensiones}
```

Con municipio `000` y la dimensión `municipio` regresa todos los municipios del
estado. El dominio viejo, `sniiv.conavi.gob.mx`, ya no resuelve (2026-11-18).

Se admiten hasta 5 dimensiones. Se usan `anio`, `municipio`, `organismo`,
`destino_credito` y `valor_vivienda`; el mes queda fuera. Otras disponibles:
`mes`, `zona`, `genero`, `grupo_organismo`, `modalidad`, `poblacion_indigena`,
`rango_edad`, `rango_salarial`, `tipo_credito`.

## Qué se guarda

| Columna | Qué es |
|---|---|
| `anio` | Año, de 2013 al actual |
| `meses` | Meses publicados de ese año, de una consulta nacional por mes. 12 salvo el último (2026: 8, de enero a agosto). Un año a medias no es una caída |
| `cve_ent`, `cve_mun` | `000` es "No distribuido": acciones que el organismo no asigna a un municipio |
| `organismo` | INFONAVIT, FOVISSSTE, BANCA (CNBV), CONAVI, SHF (FONDEO), BANJERCITO, ISSFAM, CFE, FONHAPO, INSUS, PEMEX... |
| `destino_credito` | Vivienda nueva, existente, mejoramientos, pago de pasivos, liquidez, adquisición de suelo, autoproducción, arrendamiento... |
| `valor_vivienda` | Económica, Popular, Tradicional, Media, Residencial, Residencial plus, No disponible |
| `acciones`, `monto` | Número de créditos o subsidios y pesos otorgados |

## Validación (2026-11-19)

Contra datos del SNIIV citados en prensa ([Líder Empresarial](https://www.liderempresarial.com/panorama-de-la-vivienda-en-mexico/)):

- Banca, 2023: 170,405 créditos; la nota dice "alrededor de 170 mil".
- Banca, crédito promedio de 2024: 2.29 millones; la nota dice 2.3 millones.
- La misma nota dice que en 2024 los créditos crecieron 5.6 %; aquí, sumando
  todos los organismos y destinos, crecen 15.6 %. La nota corta a noviembre y no
  dice qué cuenta: no se tomó como validación.
- La suma de los 32 estados en 2024 da 881,447 acciones; la consulta nacional,
  881,470. Hay 23 que la API no asigna a ningún estado.

## Límites

- Mezcla créditos y subsidios: sumar todo da "acciones de financiamiento", no
  "viviendas compradas". Un mejoramiento cuenta igual que una compra.
- El monto viene en cero en buena parte de los mejoramientos: 1.94 de 2.67
  millones de acciones de INFONAVIT y 0.79 de 1.07 millones del fondeo de la SHF
  (de 2013 a 2026). Un promedio por crédito que los incluya sale bajo: sacarlo
  solo de compra de vivienda, o solo de filas con monto.
- El segmento de valor no tiene rango en pesos en la API; ver el glosario del
  SNIIV antes de mostrarlo.
- Uso: "sin restricción, siempre y cuando se mencione la fuente" (metadatos del
  SNIIV). Citar "SNIIV, SEDATU".
