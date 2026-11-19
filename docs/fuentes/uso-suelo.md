# Uso de suelo y vegetación (INEGI, series VI y VII)

Qué cubre el suelo (agricultura de riego o temporal, bosque, selva, pastizal,
vegetación secundaria, asentamientos) a escala 1:250 000, en 2014 (serie VI) y
2018 (serie VII). Responde: **¿qué hay alrededor de esta zona y cómo cambió en
cuatro años?**

```bash
docker compose exec mapo_core python -m mapo_core.cli ambiental --crudos /app/data/crudos-ambiental --fuente uso_suelo
```

Unos 20 minutos (320 mil polígonos). Reemplaza cada serie de `fuente_uso_suelo` en
su propia transacción.

## De dónde sale

Las copias del geoportal de CONABIO del conjunto nacional de INEGI
(`usv250s7gw.zip` y `usv250s6gw.zip`), en WGS84 y UTF-8 sin `.cpg`. INEGI no da liga
fija a su descarga (`ambientales.md`).

**Licencia:** la copia de CONABIO es CC BY-NC 2.5 México ("no se permite utilizar
estos datos con fines lucrativos", metadatos del zip). El original de INEGI está bajo
sus términos de uso libre, que sí permiten uso comercial: antes de vender algo con
esta capa, cambiar la fuente a la de INEGI. Citar "INEGI, Uso del suelo y
vegetación, serie VII" y "CONABIO".

## Qué se guarda

`serie` (6 o 7), `descripcion` (la clase, como la escribe INEGI: "AGRICULTURA DE
TEMPORAL ANUAL", "BOSQUE DE ENCINO", "VEGETACIÓN SECUNDARIA ARBUSTIVA DE SELVA BAJA
CADUCIFOLIA"...), `codigo` y el polígono, válido y como MultiPolygon. La copia de
CONABIO no trae las demás columnas de INEGI.

## Validación (2026-11-19)

- Serie VII: 179,095 polígonos; serie VI: 142,754.
- Las dos suman 195.09 millones de hectáreas. El territorio continental de México
  mide unos 195.9 millones: 99.6 %, sin islas lejanas.
- Lo más extenso en la VII: matorral desértico micrófilo (18.47 millones de ha),
  agricultura de temporal anual (17.02) y pastizal cultivado (12.66). En la VI, los
  mismos tres (18.76, 17.53 y 13.32).

## Límites

- 1:250 000: la unidad mínima es de decenas de hectáreas y las orillas de los
  pueblos se generalizan. Para distancias de cientos de metros, la frontera
  agrícola 1:10 000 (`ambientales.md`).
- Entre series cambian también los criterios de interpretación: una diferencia
  chica entre la VI y la VII puede ser método, no cambio real.
