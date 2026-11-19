# Acuíferos (Conagua)

Los 653 acuíferos del país con su disponibilidad de agua subterránea, las vedas y
ordenamientos que los rigen, y la red piezométrica (profundidad al agua por pozo y
año). Responde: **¿se puede sacar más agua de aquí?, ¿qué decreto lo limita?, ¿qué
tan hondo está el agua y cómo ha cambiado?**

```bash
docker compose exec mapo_core python -m mapo_core.cli ambiental --crudos /app/data/crudos-ambiental --fuente acuiferos
```

Unos 25 s. Reemplaza `fuente_acuiferos`, `fuente_acuiferos_ordenamientos` y
`fuente_piezometria`, cada una en su transacción.

## De dónde sale

Datos abiertos de Conagua (`datos.conagua.gob.mx/docs/DatosAbiertos/`), bajados
con `scripts/crudos-ambientales.sh` el 2026-11-13:

| Archivo | Qué trae |
|---|---|
| `Acuiferos_Disponibilidad_09-11-2023.zip` | Polígonos con la disponibilidad publicada en el DOF el 2023-11-09 (corte al 2022-12-30). NAD27 geográficas: se pasan a WGS84 al leer |
| `Relacion_acuiferos_ordenamiento_indicando_tipo_vedas.zip` | Tres capas: vedas (147), suspensión de libre alumbramiento (331) y reglamentos o reservas (11), con su decreto y la liga al DOF |
| `Red_piezometrica_2023.zip` | 17,819 pozos con la profundidad al nivel estático (PNE) de 1996 a 2023 |

Licencia: datos abiertos del gobierno federal; citar "Conagua". La descarga no
trae licencia propia.

## Qué se guarda

`fuente_acuiferos`, una fila por acuífero, volúmenes en hm³ al año:

| Columna | Qué es |
|---|---|
| `recarga` | Recarga total media anual (R) |
| `descarga_natural` | Descarga natural comprometida (DNC): lo que tiene que seguir saliendo a ríos y manantiales |
| `vcas`, `veala`, `vaptyr`, `vaprh` | Concesionado o asignado en el REPDA, en libre alumbramiento, pendiente de título y registro, y por reservas |
| `veas` | Extracción total: la suma de los cuatro |
| `disponibilidad` | DMA = R − DNC − VEAS. Negativa es déficit. Conagua la publica partida en dos columnas (positiva y negativa); aquí es una |

`fuente_acuiferos_ordenamientos`: `tipo` (`veda`, `suspension`, `reglamento`),
nombre corto y oficial, fecha del DOF, clave del acuífero cuando aplica (las vedas
viejas cubren regiones, no acuíferos), clasificación y `url_dof`.

`fuente_piezometria`: `pne` es un JSON `{"1996": 83.05, ...}` con solo los años
medidos; `elev_brocal` en metros sobre el nivel del mar.

## Validación (2026-11-19)

- 653 acuíferos; 286 sin disponibilidad. El Acuerdo Nacional por el Derecho Humano
  al Agua (DOF, 2024) cita "286 de los 653 acuíferos" con problemas de
  disponibilidad, y la suma de lo que reporta [Excélsior](https://www.excelsior.com.mx/nacional/sobreexplotacion-seca-los-acuiferos-aumento-256-en-los-ultimos-50-anos/1642501)
  (107 sobreexplotados sin disponibilidad más 179 sin disponibilidad sin
  sobreexplotar) da lo mismo.
- R − DNC − VEAS reproduce la disponibilidad publicada en los 653, con error
  máximo de 0.000001 hm³ (redondeo).
- 489 ordenamientos = 147 + 331 + 11.

## Límites

- La disponibilidad es un balance administrativo con corte a 2022, no una
  medición: un acuífero "con disponibilidad" puede tener pozos que bajan.
- Sobreexplotación (extracción mayor que la recarga) no viene en el archivo y no
  es lo mismo que "sin disponibilidad": no se deduce aquí.
- La red piezométrica no es pareja: muchos pozos tienen pocos años, y en zonas
  enteras no hay pozos (el valle de Autlán, por ejemplo).
- No hay mapa nacional de vulnerabilidad de acuíferos. DRASTIC sería un puntaje:
  si se arma, con sus insumos por separado (`ambientales.md`).
