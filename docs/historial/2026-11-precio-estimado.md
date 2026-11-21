# Precio estimado, primera parte: forma y rango (noviembre 2026)

Sesiones 23c y 23d, 2026-11-20. Diseño y cifras en
`../producto/precio-estimado.md`; la vista, en `../producto/vista-vivienda.md`.

## Qué se hizo

- **Estudio** `estudios/precio_estimado/` (entorno propio de `uv`): notebook que
  compara cuatro modelos de la forma, prueba la transferencia a un municipio sin
  tabla, mide la cobertura de tres maneras de dar el rango y escribe la tabla por
  AGEB. Corre de arriba abajo en unos 15 minutos.
- **Cargador** `cli precio_estimado` y tabla `fuente_precio_estimado` (la crea
  `mapo_core`, sin migración de Ecto).
- **Indicador** "Valor de suelo por AGEB" en el acetato de vivienda, que deja de
  llamarse "Vivienda por municipio". El catastro lleva color; las estimadas, borde
  punteado y su rango en la ventana; los municipios sin tabla, sin dato.
- **Capturas** `scripts/capturas/suelo.js`: plano, vista cerca y la ventana de una
  AGEB estimada, en tres tamaños y dos modos.

## Por qué así

- **Validación por bloques de 3 km y anidada.** Con particiones al azar la
  calibración tiene vecinas de las AGEB evaluadas: el rango sale 14 % más angosto
  y promete de más. Afuera, cinco particiones por bloques; adentro, ajuste y
  calibración también por bloques.
- **Normalizado y no CQR.** CQR cubrió 67 % en Zapopan, lejos del 80 %.
- **Bosque y no SVR.** Empatan en forma; la SVR normalizada cubrió 75 % en
  Zapopan. La SVR sigue en el notebook como comparación (proyecto de AEM).
- **Solo el catastro pinta.** Fuera de Guadalajara el rango de las AGEB estimadas
  llega a 20 veces de alto a bajo: pintar su punto medio lo haría pasar por dato.
- **La ventana de una AGEB no abre la ficha del municipio.** La ficha agranda la
  cinta y tapaba la ventana (se vio en las capturas).

## Lo que apareció

- **Valores menores a $1,000 del OCR.** 51 AGEB de Zapopan, 25 de Tonalá y 7 de
  Ixtlahuacán. Son la mayor parte del ancho: sin ellas, el rango baja a la mitad.
  Mezclan números de manzana con periferia real, así que no se quitaron a ciegas
  (pendiente en el diseño).
- **El plano es canvas.** Las capturas no pueden esperar ni tocar un `path`: la
  AGEB se ubica con la posición de un mosaico del mapa base.

## Modelos interpretables (2026-11-20)

`modelos.ipynb`: once modelos con la misma validación por bloques. Lasso queda
primero (RMSE log 0.619, Spearman 0.738) por delante del bosque (0.622, 0.720);
la red chica, último (0.698). Con Lasso el rango conformal es más angosto pero
cubre 77.8 %: producción sigue con el bosque. Detalle en
`docs/producto/precio-estimado.md`, "Modelos interpretables".

## MEDV a precio de oferta (2026-11-21)

Remi decidió pasar el MEDV a pesos por vivienda con los anuncios del IIEG
(julio de 2024, seis municipios). Dataset v8: 787 AGEB con precio; el catastro
queda en `suelo_*`. En `modelos.ipynb`, Lasso sigue primero (RMSE log 0.398,
Spearman 0.828) y el rango cubre 82 %. Calibrar con la mediana municipal de
anuncios empeora o deja igual el error por AGEB: mide otra población.

## La vista pasa al precio de oferta (2026-11-21)

El indicador `suelo_ageb` del acetato de vivienda se reemplazó por `precio_ageb`
(tabla v2, `modelos.ipynb` sección 12): la mediana de anuncios donde la AGEB tiene
al menos tres (787), un rango de Lasso con ancho lineal donde no (801) y sin dato
en el resto, con el motivo en la ventana. Antes de publicar salió que el modelo
lineal extrapolaba en la periferia sin anuncios (rangos de $0 a infinito en 8
AGEB) aunque la cobertura medida fuera de 82 %: se recortan los rasgos, se topa el
ancho y quedan sin dato las AGEB que se parecen poco a las de anuncios (227).
El Salto queda sin rangos: 5 AGEB con anuncios no alcanzan para medir cobertura.

De paso, todas las simplificaciones de geometría para pintar o medir usan
`ST_Simplify(geom, tol, true)`: la coropleta del censo, el buscador y
`/geo/agebs` ya no pierden las 24 AGEB chicas de la ZMG
(`mapo_core/tests/test_simplificar.py`). Capturas: `scripts/capturas/precio_ageb.js`.
