# Focos de calor (NASA FIRMS)

Puntos donde un satélite vio un píxel más caliente que su entorno: quemas agrícolas,
incendios forestales, basureros y algunas industrias. Responde: **¿cuánto se quema
aquí y en qué temporada?** Un foco no es un incendio confirmado.

```bash
docker compose exec mapo_core python -m mapo_core.cli ambiental --crudos /app/data/crudos-ambiental --fuente firms
```

Unos 15 minutos (5 millones de puntos). Reemplaza `fuente_firms_focos`.

## De dónde sale

Los archivos por país y año de FIRMS (`firms.modaps.eosdis.nasa.gov/data/country/`):
VIIRS S-NPP (375 m) de 2012 a 2025 y MODIS (1 km) de 2000 a 2025. Licencia: datos de
NASA sin restricciones de uso; citar "NASA FIRMS" (LANCE, EOSDIS).

## Qué se guarda

| Columna | Qué es |
|---|---|
| `sensor` | `VIIRS_SNPP` o `MODIS` |
| `fecha`, `hora` | Del paso del satélite; `hora` es HHMM en UTC (para hora de México, restar 6) |
| `confianza` | VIIRS: `l`, `n`, `h` (baja, nominal, alta); MODIS: 0 a 100 |
| `frp` | Potencia radiativa del fuego, en MW |
| `dia_noche` | `D` o `N` |
| `tipo` | 0 vegetación, 1 volcán, 2 otra fuente fija (industria, quema recurrente en el mismo lugar), 3 costa |

**MODIS solo de 2000 a 2011.** Desde 2012 VIIRS ve todo lo que ve MODIS y más fino;
cargar los dos contaría dos veces el mismo fuego. Para comparar con años de antes de
2012 se usa MODIS en los dos lados (los CSV siguen en los crudos).

## Validación (2026-11-19)

- 4,225,823 focos VIIRS y 723,048 MODIS; cada año de VIIRS da lo mismo que su CSV
  (2024: 330,134).
- Caja de Autlán y El Grullo (-104.65, 19.55, -103.95, 20.05), 2024: 653 focos VIIRS,
  lo mismo que la revisión a mano del 2026-11-13 y que `recorte.py`.

## Límites

- Un píxel de 375 m: el punto es el centro del píxel, no el lugar exacto del fuego.
- Nubes y humo esconden focos; un día nublado no es un día sin quema.
- Los de 2025 son de la versión NRT o estándar según la fecha de descarga
  (2026-11-13); 2026 todavía no se baja.
- Pesa: 755 MB en la base con su índice.
