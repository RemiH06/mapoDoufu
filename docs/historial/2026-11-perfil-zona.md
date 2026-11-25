# Perfil de cualquier zona y zonas que se parecen (sesión 29h)

Octava sesión del bloque 29a a 29m. `/perfil` deja de ser de un municipio: toma cualquier zona
de la zona común, gana plano, dos documentos y figuras, y busca zonas parecidas por área con su
desglose. Cómo funciona: [perfil.md](../producto/perfil.md).

## Qué se hizo

- **`mapo_core/perfil.py`**: `/perfil_zona?zona=` para todos los niveles. Municipios enteros por
  clave; colonias, CP y dibujos con el censo repartido por área. Documentos nuevos: Vivienda y
  Servicios a pie. DENUE por sector y tamaño, SESNSP por año, ENIGH del estado.
- **`mapo_core/similares.py`**, tabla `similares_zonas` y `cli similares`: 37 variables por
  municipio y 26 por colonia en siete áreas.
- **Vista** (`PerfilLive`, `MapoWeb.PerfilDocumentos`, `MapoWeb.PerfilSimilares`,
  `perfil_mapa.js`): selector común, dibujo en el plano, nivel de cada dato, pirámide, tiras y
  columnas, y el cotejo con reglas. Ligas desde `/riesgos` y `/accesibilidad` ("Su perfil") y de
  regreso.
- **Notas por zona:** `notas_perfil.zona`; `cve_ent` y `cve_mun` se quedan para poder regresar.
- **Capturas:** `scripts/capturas/perfil29h.js`.

Producción en `094672b` el 2026-11-25 (revertir: `deploy-20261125b`; con migración, la columna
`zona` puede quedarse; respaldo previo `mapo_prod-20261125-1135.dump`), con `cli similares`
corrido (31 s). En Pixilate: una colonia 0.25 s, Guadalajara 0.4, la ZMG 1.4, Jalisco 6.6; los
parecidos, 0.25 s o menos. Mismas cifras que dev.

## Decisiones

- **Reparto por área, no por punto.** `/riesgos` y `/accesibilidad` cuentan la AGEB entera donde
  cae su punto. Con colonias eso deja sin gente a 2,064 de 4,397. Se midió contra manzanas antes
  de decidir, y la cifra del error va en pantalla.
- **Contar variables, no distancia.** Una distancia entre vectores es un puntaje con pesos
  escondidos (las escalas). Contar cuántas caen en una banda declarada se puede revisar a mano.
- **Rango intercuartil y no percentiles.** Con percentiles, el agua entubada (casi todas entre
  98 y 99 %) haría distintas a zonas iguales, y la densidad de Guadalajara y la de Zapopan, las
  dos en lo más alto, saldrían parecidas siendo 9,179 y 1,274 hab/km².
- **Colonias contra colonias**, aunque se pregunte por un dibujo: es la unidad con nombre más
  cercana en tamaño.
- **Variables calculadas por estado y guardadas:** cruzar las AGEB con las colonias de Jalisco
  tarda más de un minuto.
- **`cve_ent` y `cve_mun` no se borran de las notas:** la versión anterior los exige.
- **La cabeza deja de ser un fondo:** el trazo de AGEB detrás de los papeles pasa a ser un plano
  de verdad, con calles, densidad y dibujo.

## Bugs reales

- **7.7 s por una colonia:** `cve_ent || cve_mun = ANY(...)` no usa el índice de los delitos (30
  millones de renglones). Por pares (`(cve_ent, cve_mun) IN unnest`), 0.06 s.
- **25 s los minutos de un estado:** filtrar por 13 mil claves costaba más que leerlas todas.
- **Densidad de colonias chicas:** `resolver` da el área redondeada a hectáreas.
- **Razones sesgadas por lo reservado:** sumar numerador y denominador por separado bajaba el
  porcentaje si INEGI reservaba solo el primero.
- **Precio "en 2 de 8 AGEB"** de una colonia con 3: las otras eran bordes de polígono de menos
  de 1 % de su área.
- **`.pista`** ya era la clase de las pistas escritas a mano: las barras salían 4 px abajo.
- **CONAPO como prueba habría sido circular:** su población por colonia sale del mismo reparto.

## Queda

- CP: falta que se carguen los polígonos de SEPOMEX.
- Similares solo con Jalisco; metrópolis y estados, sin con qué comparar.
- Cita en `/perfil` (pendiente desde la 24).
- Manzanas en la base bajarían el error de las colonias.
