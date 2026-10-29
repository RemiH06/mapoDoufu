# ENIGH (consumo)

## Vendorización ENIGH (consumo) y SESNSP (seguridad) (2026-09-22)

**ENIGH quedó vendorizado completo, automático**, solo la tabla
`concentradohogar` (no las 17 de Gaiarda: es la única que Mapo
necesita, tiene ingreso/gasto ya agregados por hogar):

- `mapo_core/enigh_downloader.py`, vendorizado de
  `gaiarda/src/gaiarda/fuentes/enigh/{api,downloader}.py`. Descarga un
  solo zip nacional (`inegi.org.mx`, sin paginación), checkpoint unico
  (`enigh:concentradohogar`)
- `mapo_core/enigh_resumen.py`, vendorizado de `enigh/resumen.py`:
  resumen ponderado por municipio (cada hogar pesa `factor` hogares
  reales), con la misma advertencia que ya traía Gaiarda:
  ENIGH es representativa a nivel estado/dominio rural-urbano, NO a
  nivel municipio, por eso `n_hogares_muestra` siempre viene en la
  respuesta
- **Bug real encontrado y corregido antes de cerrar la pasada**: el
  esquema usaba `folioviv TEXT PRIMARY KEY`, pero un mismo domicilio
  puede tener varios hogares economicamente independientes
  (`foliohog` distinto). La primera descarga real guardó 90,324 filas
  en vez de las 91,414 reales (1,090 perdidas por colisión silenciosa
  de llave). Corregido a llave compuesta `(folioviv, foliohog)`; se
  tuvo que borrar la tabla ya creada con el esquema viejo y también el
  checkpoint (mismo síntoma que el bug de checkpoint desincronizado
  que ya documenta Gaiarda: la tabla vacía pero el checkpoint seguía
  diciendo "hecho"). Confirmado despues del fix: 91,414 filas exactas
- **Probado con datos reales de INEGI**: descarga nacional completa
  (91,414 hogares). `/perfil_zona` de Guadalajara:
  `consumo: {n_hogares_muestra: 335, periodo: "diario",
  promedio_ponderado: 632.06, mediana: 531.57}` (gasto diario
  promedio ponderado por hogar, en pesos), confirmado con `curl`
  directo

**Ambas fuentes ya no marcan `consumo_disponible`/`seguridad_disponible`
en `/perfil_zona`**: ahora son `consumo`/`seguridad`, `null` cuando no
hay datos para ese municipio (nunca un falso "no disponible", que es
un mensaje distinto). 23 tests nuevos en `mapo_core` (122 en total),
229 en `mapo` (fixture de `perfil_live/index_test.exs` actualizado,
tarjetas de Consumo y Seguridad ya renderizan datos reales)
