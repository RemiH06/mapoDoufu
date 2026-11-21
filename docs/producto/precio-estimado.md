# Precio estimado de vivienda por AGEB

Estado (2026-11-21): Mapo muestra el precio de oferta por vivienda por AGEB (la
mediana de los anuncios del IIEG) y, donde falta, un rango conformal de Lasso con
su cobertura medida (acetato "Vivienda", indicador "Precio de oferta por AGEB";
`vista-vivienda.md`). Del 2026-11-20 al 21 mostró el valor catastral de suelo
(tabla v1). Estudio en `estudios/precio_estimado/` (notebooks y módulos); historia
en `../historial/2026-11-precio-estimado.md`.

Ninguna fuente abierta da el precio de mercado por AGEB
(`dataset-vivienda.md`, "MEDV"). Esta vista lo aproxima con método propio y lo
muestra como **rango con su cobertura medida**, nunca como un número solo. Así
cabe en RNF5: lo que RNF5 prohíbe es un puntaje que esconda su método, no una
estimación que lo enseña.

## Qué se muestra

(Diseño completo. Lo que ya está en Mapo, en "Lo construido".)

- Un rango en $/m² por AGEB ("de 18,000 a 26,000, cobertura medida 80 %"), con el
  trimestre al que está llevado.
- Al tocar la AGEB: de qué salió (valor catastral, calibración municipal, modelo),
  cuántos datos tiene detrás y por qué el rango es ancho o angosto.
- Sin dato cuando no hay base: una AGEB sin valor catastral ni vecinas comparables
  queda vacía y dice por qué. No se rellena para que el mapa se vea completo.
- La palabra es "referencia". No es un avalúo: en México el avalúo lo firma un
  perito valuador.

## Método

Dos piezas, porque ninguna fuente sola da forma y escala a la vez.

1. **Forma, quién es más cara que quién:** el valor catastral de suelo (`medv`,
   `medv_2026`) del dataset de vivienda. Ya ordena las zonas como el mercado
   (Spearman 0.80 con escolaridad en Guadalajara, 0.60 en Zapopan). Donde falta,
   lo predice un modelo con las demás columnas del dataset.
2. **Escala, en pesos de mercado:** el monto de crédito del SNIIV por segmento y
   municipio, la ENVI por estado y el índice SHF para llevar todo al trimestre
   vigente.
3. **Unión, por cuantiles:** la AGEB en el percentil *p* del catastro de su
   municipio toma el percentil *p* de la distribución de valores del SNIIV de ese
   municipio. Respeta el orden ya validado y se explica en un párrafo.

Límite conocido: el SNIIV solo ve vivienda con crédito o subsidio, así que en
zonas de autoconstrucción la escala queda baja. Se dice en la ficha.

## Rango: conformal, no el tubo de la SVR

La regresión de vectores de soporte (SVR) tiene un tubo de ancho ε, la "calle"
de la SVM: los errores menores a ε no cuestan nada y los vectores de soporte son
los puntos en el borde o fuera. Sirve como modelo, pero **ε no es un intervalo**:
es un hiperparámetro del entrenamiento y nada garantiza que 80 % de los valores
reales caigan dentro de ±ε.

Para que el rango diga cuánto acierta, cualquiera que sea el modelo, se usa
**predicción conformal**:

- **Partida (split conformal):** se ajusta el modelo en una parte, se miden los
  residuos en otra (calibración) y el cuantil 1 − α de esos residuos da el ancho.
  Con datos intercambiables cubre al menos 1 − α.
- **Ancho local:** con residuos normalizados por una estimación de la dispersión,
  o con regresión cuantílica conformalizada (CQR), el rango se ensancha donde hay
  pocos datos y se angosta donde hay muchos. Un ancho parejo para toda la ciudad
  escondería eso.
- **Autocorrelación espacial:** AGEB vecinas se parecen, así que una partición al
  azar promete más cobertura de la real. La calibración se hace por bloques
  espaciales (como la validación cruzada del dataset), y la cobertura se reporta
  por municipio, no solo global.

**Qué cubre cada rango.** Conformal garantiza cobertura del objetivo con que se
calibra. Calibrado contra el valor catastral, cubre el error del modelo sobre el
catastro, no la distancia entre catastro y mercado. Para cubrir el precio de
mercado hace falta una muestra de precios reales (ver Validación). Mientras no
la haya, la ficha dice "orden confiable, escala aproximada" y la cobertura que
muestra es la del catastro.

## Lo construido (sesiones 23c y 23d)

Decisiones de Remi al arrancar (2026-11-20): cobertura nominal de 80 %,
trimestre de referencia 2026-II y, por ahora, calibrar contra el catastro; la
muestra de precios a mano viene después.

- **Objetivo:** `log(medv)` del dataset de vivienda v7, 892 AGEB con catastro en
  85 bloques de 3 km. Guadalajara con su tabla de 2020; Zapopan, Tonalá e
  Ixtlahuacán con la de 2026. Efecto fijo por municipio para los años distintos;
  44 rasgos de nivel AGEB (censo, DENUE, OSM, GHSL, relieve, NDVI, LST).
- **Forma:** ridge, SVR (RBF), bosque aleatorio y boosting, validados fuera de
  muestra por bloques con hiperparámetros elegidos dentro de cada partición.
  Empatan casi (RMSE en log de 0.62 a 0.68). Por municipio, el bosque:

  | Municipio | AGEB | RMSE log | Spearman |
  |---|---|---|---|
  | Guadalajara | 415 | 0.20 | 0.82 |
  | Zapopan | 302 | 0.87 | 0.63 |
  | Tonalá | 152 | 0.73 | 0.45 |
  | Ixtlahuacán | 23 | 0.86 | 0.12 |

- **Transferencia:** con un municipio entero fuera, el orden aguanta en
  Guadalajara (Spearman 0.79) y Zapopan (0.62), poco en Tonalá (0.42) y nada en
  Ixtlahuacán. Sin tabla tampoco hay nivel, así que los seis municipios sin tabla
  quedan sin dato.
- **Rango:** conformal partido normalizado (σ̂ de un bosque sobre el error fuera
  de muestra), calibrado por bloques. Cobertura medida en AGEB que ni el ajuste
  ni la calibración vieron:

  | Municipio | Normalizado, bosque | CQR | Alto entre bajo (mediana) |
  |---|---|---|---|
  | Todos | 79.6 % | 78.9 % | 3.1 |
  | Guadalajara | 78.6 % | 88.0 % | 1.5 |
  | Zapopan | 78.8 % | 67.2 % | 5.2 |
  | Tonalá | 83.6 % | 79.6 % | 5.2 |
  | Ixtlahuacán | 82.6 % | 65.2 % | 10.3 |

  CQR falla en Zapopan e Ixtlahuacán. Partir al azar en vez de por bloques da
  rangos 14 % más angostos (26 % en Tonalá): lo que se promete de más cuando la
  calibración tiene vecinas de lo evaluado.
- **Ruido del OCR:** sin las AGEB con valor menor a $1,000 de los municipios con
  OCR, el ancho baja a la mitad (Zapopan 2.7, Tonalá 2.3) con la misma cobertura.
  No se quitaron: en Zapopan esas AGEB tienen escolaridad mediana de 8.7 años
  contra 12.5, así que muchas son periferia de verdad.
- **Tabla:** 892 AGEB con catastro, 344 con rango (27 de Guadalajara, 227 de
  Zapopan, 76 de Tonalá, 14 de Ixtlahuacán) y 832 sin tabla. Las que se estiman
  están en la periferia, y su rango es ancho: mediana de alto entre bajo de 1.6
  en Guadalajara y de 17 a 50 en los otros tres. Por eso en el mapa solo el
  catastro lleva color.

**Límites:** la cobertura se mide en AGEB con catastro, y las estimadas están más
en la orilla, donde se ubicaron menos hojas: nada garantiza que se parezcan. El
rango cubre el catastro, no el mercado.

## Modelos interpretables (2026-11-20)

`estudios/precio_estimado/modelos.ipynb` repite la forma con modelos que se
pueden leer, en el orden de un curso de estadística multivariada: OLS, selección
por pasos con BIC, Lasso, regresión sobre componentes principales, tipos de zona
con k-medias, ANOVA y ANCOVA por municipio y regresión logística. Fuera de ese
temario: un modelo aditivo con splines, un árbol corto y un modelo mixto con
intercepto aleatorio por municipio. Una red chica (32 y 16 neuronas) y las
referencias de caja negra (SVR y bosque) se comparan con la misma validación por
bloques.

| Modelo | RMSE log | Spearman |
|---|---|---|
| Lasso | 0.619 | 0.738 |
| Bosque (referencia) | 0.622 | 0.720 |
| Aditivo con splines | 0.629 | 0.717 |
| Pasos BIC (11 rasgos) | 0.634 | 0.722 |
| SVR (referencia) | 0.636 | 0.735 |
| PCR | 0.643 | 0.716 |
| Tipos k-medias | 0.653 | 0.615 |
| Mixto | 0.658 | 0.698 |
| OLS completa | 0.663 | 0.695 |
| Árbol | 0.689 | 0.614 |
| Red | 0.698 | 0.654 |

Lasso ordena mejor que el bosque y transfiere mejor a un municipio no visto, así
que la forma no necesita una caja negra. Lo que más pesa, estable entre modelos:
escolaridad (+10 a +13 % por desviación estándar), ocupantes por cuarto (−12 a
−13 %), pendiente (−6 a −10 %) y parques a 1 km (+7 a +10 %). Con las covariables,
el municipio deja de ser significativo en la ANCOVA (p = 0.27).

Con Lasso al centro y una ridge sobre log|residuo| para el ancho
(`conformal.Normalizado(..., escala="lineal")`), el rango es más angosto (alto
entre bajo 2.5 contra 3.1) pero cubre 77.8 % en vez de 79.6 %, y Zapopan 71.5 %.
Producción sigue con el bosque hasta resolver esa falta de cobertura (pendiente).

### Con el precio de oferta (dataset v8, 2026-11-21)

Desde la v8, `modelos.ipynb` usa como objetivo la mediana del precio pedido por
vivienda del IIEG (`../fuentes/iieg-oferta.md`), 787 AGEB en seis municipios,
todas de julio de 2024. Lasso sigue primero (RMSE log 0.398, Spearman 0.828),
con el bosque en 0.403 y 0.820 y la red en 0.459 y 0.764. El rango conformal con
Lasso y ancho lineal cubre 82 % con alto entre bajo de 2.8, igual que el bosque:
con este objetivo, Lasso puede reemplazarlo.

**Extrapolación.** La cobertura se mide en AGEB con anuncios; las que reciben
rango son las que no tienen, muchas en la periferia. Ahí Lasso y el ancho lineal
extrapolaban: 8 AGEB salían con rangos de $0 a infinito y 45 con piso menor a
$100,000. Por eso los rasgos se recortan al rango de las AGEB con anuncios, el
ancho se topa en el percentil 99 del ajuste y queda sin dato la AGEB con tres
rasgos o más fuera de rango o donde el modelo extrapola (227 de 1,028). Con eso,
el rango típico va de un piso a 2.9 veces el piso y el más ancho a 12.

**Calibrar contra la mediana municipal no mejora.** Al dejar fuera un municipio
y mover su nivel para igualar la mediana de anuncios del IIEG, el error por AGEB
empeora si se pesa por viviendas (lo que habría sin datos) y queda igual si se
pesa por anuncios (el mejor caso). La mediana de anuncios describe dónde se
anuncia, no la vivienda típica; la SHF mide otra población todavía (avalúos de
crédito en todo el estado). Una cifra agregada solo calibra si mide la misma
población que lo que se predice.

## Validación

Sin precios reales no hay forma de medir el error en pesos. Opciones legales
(se empieza sin ninguna: decisión de Remi del 2026-11-20):

- **Datos de equipos:** avalúos o ventas que un equipo sube como datos propios,
  con permiso explícito para calibrar. Nunca se muestran.
- **Muestra a mano:** precios de oferta capturados a mano en algunas colonias,
  solo para validar, con el procedimiento publicado. Los portales prohíben la
  extracción automática.

Comprobaciones mínimas antes de abrir la vista: cobertura medida por municipio
cerca de la prometida, orden contra escolaridad y marginación, y que ninguna AGEB
tome valores de un municipio vecino.

## Dónde vive

- `estudios/precio_estimado/`: `modelos.ipynb` (modelos interpretables sobre el
  precio de oferta; su sección 12 escribe
  `mapo_core/data/precio_estimado/precio_ageb_v2.csv`, lo que está en producción) y
  `precio_estimado.ipynb` (el estudio del suelo catastral, tabla v1), con módulos
  `precio/` (datos, modelos, interpretables, conformal, calibracion, salida,
  gráficas).
- `mapo_core/src/mapo_core/precio_estimado.py`: valida y carga esa tabla en
  `fuente_precio_estimado` (`python -m mapo_core.cli precio_estimado --archivo
  /app/data/precio_estimado/precio_ageb_v2.csv`). Rechaza un valor observado
  (`anuncios` o `catastro`) sin valor o un rango sin cobertura.
- El indicador `precio_ageb` del acetato de vivienda (`vista-vivienda.md`):
  catálogo cerrado de claves, nada interpolado en el SQL.

## Pendiente

- **Ruido del OCR:** revisar a mano una muestra de valores menores a $1,000 en los
  escaneos de Zapopan y Tonalá. Si la mayoría son números de manzana, subir el
  filtro del pipeline a $1,000, rehacer el dataset y esta tabla.
- **Escala de mercado:** resuelta el 2026-11-20 (Remi): pesos por vivienda, con el
  precio de oferta del IIEG (dataset v8).
- **Años distintos y trimestre:** llevar Guadalajara 2020 a 2026 con su tabla de
  2026 (hay 288 AGEB con las dos; Spearman 0.85) en vez de dejar cada municipio en
  su año, y luego todo a 2026-II, el trimestre elegido, con el índice SHF. Hoy
  cada AGEB va en pesos del año de su tabla y lo dice.
- **Validación con precios reales** (arriba).
- **Cambiar a Lasso en producción:** solo si el rango vuelve a cubrir 80 % por
  municipio; probar conformal calibrado por municipio (Mondrian).
- **Vista con precio de mercado:** hecha el 2026-11-21 (Remi). Tonalá necesitaría
  más anuncios; El Salto, al menos 20 AGEB con anuncios para dar rangos.
- **Dónde aparecen los anuncios:** para usar una cifra municipal en un municipio
  sin anuncios por AGEB, primero habría que modelar dónde se anuncia.
