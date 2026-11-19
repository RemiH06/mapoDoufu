# Precio estimado de vivienda por AGEB (diseño)

Estado: diseño, sin construir (2026-11-19). Sesiones 23c (método y validación) y
23d (vista) de `steps.md`.

Ninguna fuente abierta da el precio de mercado por AGEB
(`dataset-vivienda.md`, "MEDV"). Esta vista lo aproxima con método propio y lo
muestra como **rango con su cobertura medida**, nunca como un número solo. Así
cabe en RNF5: lo que RNF5 prohíbe es un puntaje que esconda su método, no una
estimación que lo enseña.

## Qué se muestra

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

## Validación

Sin precios reales no hay forma de medir el error en pesos. Opciones legales,
por decidir en la 23c:

- **Datos de equipos:** avalúos o ventas que un equipo sube como datos propios,
  con permiso explícito para calibrar. Nunca se muestran.
- **Muestra a mano:** precios de oferta capturados a mano en algunas colonias,
  solo para validar, con el procedimiento publicado. Los portales prohíben la
  extracción automática.

Comprobaciones mínimas antes de abrir la vista: cobertura medida por municipio
cerca de la prometida, orden contra escolaridad y marginación, y que ninguna AGEB
tome valores de un municipio vecino.

## Dónde vivirá

- El modelo y su calibración se ajustan fuera de la app, en un notebook, sobre el
  dataset de vivienda. Mapo guarda el resultado por AGEB con su método, versión y
  cobertura medida.
- La vista sigue el patrón del acetato de vivienda (`vista-vivienda.md`):
  catálogo cerrado de claves, nada interpolado en el SQL.
