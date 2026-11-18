# Sobrevivencia de negocios

El patrón del rubro (`buscador.md`) dice si los negocios de un giro se juntan,
no si les va mejor juntos. Este estudio mide lo segundo con DENUE, en notebook y
aparte de Mapo: `estudios/sobrevivencia/sobrevivencia.ipynb`, con la lógica en
`estudios/sobrevivencia/sobrevivencia/`. Ninguna probabilidad por negocio o por
zona pasa a Mapo: sería un puntaje (RNF5).

Correrlo:

```bash
cd estudios/sobrevivencia
uv sync
uv run jupyter nbconvert --to notebook --execute --inplace sobrevivencia.ipynb   # ~9 min
```

Baja solas las ediciones que falten a `mapo_core/data/denue_ediciones/`
(gitignorada, unos 35 MB cada una) y usa `vivienda_gdl_v7.zip` para el
contexto por AGEB (`dataset-vivienda.md`).

## La etiqueta

**Un negocio de DENUE 2019_11 "sigue" si su `id` está en 2024_11.**

- **Por qué esas dos ediciones.** Entre ediciones normales sigue casi el 100 %:
  INEGI actualiza sobre todo a los grandes, y un negocio chico que cerró sigue
  apareciendo. Las bajas llegan de golpe con cada Censo Económico:

  | De | A | Siguen |
  |---|---|---|
  | 2017_11 | 2018_11 | 99.7 % |
  | 2018_11 | 2019_11 | **61.6 %** (Censos Económicos 2019) |
  | 2019_11 | 2020_11 | 98.6 % |
  | 2022_11 | 2023_11 | 99.0 % |
  | 2023_11 | 2024_11 | **71.3 %** (Censos Económicos 2024) |
  | 2025_05 | 2026_05 | 99.0 % |

  Medir de una edición normal a otra mediría el calendario de INEGI, no los
  cierres. La ventana con sentido va de un corte censal al siguiente.
- **La llave es `id`, no `CLEE`.** `clee` no existe antes de 2022_11, y aun
  después cambia aunque el negocio siga: de 2024_11 a 2026_05, 74 mil negocios
  conservan `id` y cambian de `clee`. El `id` sobrevive a las mudanzas: de
  2019_11 a 2026_05, 11,795 negocios conservan el `id` a más de 100 m de donde
  estaban.
- **Re-registros.** ¿Y si INEGI le dio otro `id` al mismo negocio? De los que
  desaparecen entre 2019_11 y 2024_11, solo el 2.5 % tiene un negocio nuevo a
  menos de 30 m con la misma rama SCIAN y el mismo nombre. `sigue_o_reregistrado`
  los cuenta como vivos; con esa etiqueta el resultado casi no cambia (abajo).

## Resultado (zona metropolitana de Guadalajara)

221,513 negocios con coordenadas en los diez municipios; **el 67.7 % sigue** en
2024 (68.5 % contando re-registros).

**¿Les va mejor a los que se juntan?** Probabilidad lineal con efecto fijo por
giro (cada negocio se compara solo contra los de su giro) y errores agrupados
por bloques de 2 km. En puntos porcentuales de probabilidad de seguir, con
intervalo al 95 %:

| Rasgo (en 2019) | Puntos | IC 95 % |
|---|---|---|
| Vecinos del mismo giro a 200 m (log) | +1.6 | 1.1 a 2.2 |
| Vecinos de cualquier giro a 200 m (log) | +1.7 | 1.1 a 2.3 |
| En plaza, mercado o edificio comercial | −2.6 | −4.6 a −0.6 |
| Semifijo | −2.9 | −5.1 a −0.7 |
| Cada mes en DENUE antes de 2019 | +0.18 | 0.17 a 0.19 |
| 6 a 10 personas (contra 0 a 5) | +7.4 | 6.6 a 8.3 |
| 11 a 30 personas | +9.5 | 8.2 a 10.7 |
| 101 a 250 personas | +15.9 | 13.2 a 18.6 |
| Escolaridad promedio de la AGEB (por año) | −1.6 | −2.2 a −0.9 |
| Viviendas con auto en la AGEB (por punto) | +0.14 | 0.07 a 0.21 |

- **Sí, y más en los giros que se agrupan.** Multiplicar por e (2.7) los vecinos
  del mismo giro suma 1.6 puntos. Con la taxonomía (`buscador.md`), en los giros
  que se agrupan (distancia al vecino del rubro menos del 80 % de la del azar)
  suma 2.1 (1.0 + 1.1 de la interacción, IC 0.3 a 1.8); en los demás, 1.0.
- **Contando re-registros**, los vecinos del mismo giro suman 1.8 (1.3 a 2.4):
  el efecto no viene de negocios que solo cambiaron de `id`.
- **Estar en plaza o mercado resta**, aunque estar rodeado de comercio suma: las
  plazas rotan más locales.
- **Lo que más pesa es el tamaño**: de 0 a 5 personas sigue el 66.1 %; de 101 a
  250, el 83.2 %.

**¿Qué tanto se puede predecir?** Poco. Con validación por bloques espaciales,
la logística y los árboles dan AUC 0.67 y Brier 0.202; predecir solo la tasa
del giro da AUC 0.61 y Brier 0.211 (en muestra, con ventaja). Otra razón para no
llevar una probabilidad a Mapo: casi todo lo que decide si un negocio sigue no
está en DENUE.

## Lo que no dice

- **Desaparecer de DENUE no es lo mismo que cerrar.** Un negocio que cambió de
  nombre y de giro, o que el censo no encontró, cuenta como baja.
- **Es asociación, no causa.** El efecto fijo quita las diferencias entre
  giros, no las de lugar: un corredor puede durar más por el corredor, no por
  los vecinos.
- **La pandemia está adentro.** Es la sobrevivencia de 2019 a 2024, no la de
  cualquier periodo.
- **`meses_alta` tiene piso.** La primera edición de DENUE es de 2010-07: "alta
  2010-07" quiere decir "ya estaba en 2010" (112 meses es el tope).
- **Solo la zona metropolitana de Guadalajara.** 12 negocios de 2019 traían
  coordenadas de otros estados y se quitaron.

## Siguiente

- Otras zonas: la misma tubería con otros municipios y otra taxonomía.
- Ventana 2019 → 2024 contra 2014 → 2019 (Censos 2014), si las ediciones de
  2014 y 2015 se pueden bajar: usan otro patrón de nombre de archivo.
- Censos Económicos 2024 por AGEB (ingresos y personal agregados): otra señal
  de éxito, que no depende de que el negocio aparezca o no.
