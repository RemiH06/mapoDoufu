# ENOE (laboral)

## Vendorización ENOE (laboral) (2026-09-22)

**Bug real de URL encontrado y corregido, sin el cual esta fuente
directamente no funcionaba**: la URL de descarga que usaba Gaiarda
(`enoe_n_{año}_{trimestre}_dbf.zip`, con el segmento `_n_`) devuelve
"página no encontrada" (200 con HTML, no el zip real) para cualquier
trimestre de 2023 en adelante. Confirmado contra descargas reales que
el patrón real hoy es `enoe_{año}_{trimestre}_dbf.zip` (sin el `_n_`);
coincide con el corte que documenta el propio INEGI (la ENOE retoma su
nombre después del periodo ENOEN de 2020-2022). Los trimestres 2022 y
anteriores siguen en el patrón viejo, pero quedan fuera de alcance
(Mapo solo necesita el trimestre más reciente, no una serie histórica).

Gaiarda nunca expuso un endpoint de *consulta* para ENOE (solo de
descarga de las 5 tablas crudas), así que aquí se construyó el
indicador desde cero, no se copió lógica existente:

- `mapo_core/enoe_downloader.py`: descarga el zip de un trimestre,
  extrae solo la tabla `SDEM` (Sociodemográfico, la única que hace
  falta: trae `CLASE1`/`CLASE2` con la clasificación PEA/PNEA/ocupada/
  desocupada, y `FAC_TRI` como factor de expansión), y calcula la
  **tasa de desocupación ponderada por entidad** ahí mismo. A
  diferencia de las demás fuentes, no se guardan los ~400 mil
  microdatos crudos del trimestre: solo el agregado por entidad (32
  filas por trimestre), porque nadie en Mapo va a consultar microdatos
  individuales de ENOE, sería guardar cientos de miles de filas para
  recalcular siempre el mismo numero
- Fórmula (confirmada contra la cifra oficial real, no inventada):
  de las filas con entrevista completa (`R_DEF == '00'`), la PEA es
  `CLASE1 == 1`; de esas, desocupadas son `CLASE2 == 2`. Tasa =
  desocupada_ponderada / pea_ponderada × 100
- La ENOE **no tiene representatividad a nivel municipio** (diseño
  muestral por entidad): `/perfil_zona` trae `laboral` a nivel estado
  completo aunque se consulte por municipio, con nota honesta de esto
  en la tarjeta de la interfaz
- `python -m mapo_core.cli enoe --anio 2025 --trimestre trim3`
- **Probado con datos reales de INEGI, trimestre 2025-T3**: tasa
  nacional 2.88%, Jalisco 2.49%, CDMX 3.89% (cifras consistentes con
  las tasas de desocupación oficiales conocidas de ese periodo).
  `/perfil_zona` de Guadalajara: `laboral: {anio: 2025, trimestre:
  "trim3", tasa_desocupacion: 2.49, pea_ponderada: 3975301}`,
  confirmado con `curl` directo, coincide exacto con el cálculo de
  validación hecho aparte
- 9 tests nuevos en `mapo_core` (131 en total, incluye un test que
  construye un `.dbf` real byte por byte, mismo patrón que ya usan los
  tests de Gaiarda para esta fuente, no un mock del formato), 229 en
  `mapo` (tarjeta de Laboral ya renderiza datos reales, ya no dice
  "no disponible")
