# Escalas y dos indicadores (sesión 29e)

Quinta sesión del bloque 29a a 29m. Cada capa por clases tiene su escala (paleta,
método, clases, invertir), el censo por AGEB se lee como conteo en círculos, tasa o
combinado con su fórmula, dos indicadores van juntos por canales distintos, la
confianza de vivienda se ve como transparencia, y las coropletas ya no tienen huecos
entre AGEB al acercar. Cómo funciona: `docs/producto/escalas.md`.

## Qué se hizo

- **Escala** (`MapoWeb.Escala`): ocho paletas aptas para daltonismo más la tinta de la
  capa; cuantiles, cortes naturales (ckmeans exacto), intervalos iguales o manual; de 3
  a 7 clases; invertir. Se voltea con el tema. Se repinta sin pedir datos.
- **Lecturas del censo** (`MapoWeb.LecturaCenso`): conteo en círculos, % de su
  denominador natural, por 1,000 habitantes, por km², A ÷ B, A − B y cambio %, con la
  fórmula y la unidad en la cinta y en la cita. `mapo_core` manda el área, el punto de
  dentro y las columnas extra (`/censo/choropleth?extra=`).
- **Dos indicadores:** tasa en color con conteo en círculos, 3x3 con dos tasas, o la
  segunda tasa como altura (el plano se inclina). Dos conteos no se leen juntos.
- **Confianza:** la Intercensal más tenue con más CV; el precio estimado por AGEB se
  pinta tenue cuando su rango entero cae en una clase.
- **El buscador** pinta personas por km² en vez de personas por AGEB.
- **Sin huecos entre AGEB:** `geom_mapa` en `agebs` y `municipios`, simplificado como
  cobertura (`ST_CoverageSimplify`) una vez por estado; `cli cobertura` para lo ya
  cargado.
- **Leyendas** (`MapoWeb.Leyenda`): clases con su rango al pasar el cursor, círculos de
  referencia, rejilla 3x3 con sus cortes, altura y confianza.
- **Capturas:** `scripts/capturas/mapa29e.js`.

## Decisiones

- **El canal lo decide el tipo de dato, no la persona.** Elegir "conteo" ya es elegir
  círculos; no hay manera de pintar un conteo como coropleta. Los enlaces viejos
  (`censo=pobtot`) ahora abren en círculos.
- **Los combinados son una operación entre dos columnas del mismo censo y nivel.**
  Nada de sumas ponderadas, y por eso no se combinan capas distintas (vivienda es por
  municipio, el censo por AGEB).
- **La escala se aplica al cambiarla; la lectura, con el botón.** La lectura pide datos
  nuevos (0.8 a 1.6 s con la ZMG); la escala solo reclasifica lo que ya está.
- **Los círculos se encogen al alejar.** Con tamaño fijo la ZMG era una mancha; la
  leyenda dice el tamaño de cerca y que de lejos se encogen todos igual.
- **El precio estimado sigue sin punto medio.** Se pinta solo cuando el rango entero
  cabe en una clase: es honesto decir "esta AGEB está en la clase más cara" sin
  inventar un número. Cambia lo que decía la 23d ("va sin color") para ese caso.
- **La escala va plegada** ("Escala: viridis, cortes naturales, 5 clases"): abierta, la
  cinta medía 530 px y el encuadre dejaba los datos detrás de ella.
- **El 3x3 tiene su paleta fija** (Stevens) y no acepta cortes manuales.
- **Los datos propios** se quedan con la escala de omisión por ahora (pendiente).

## Bugs reales

- **`VIVPAR_HAB` no es el denominador de los `VPH_*`.** Con él, 209 AGEB de Jalisco
  tenían más del 100 % de viviendas con internet. Con `TVIVPARHAB`, ninguna.
- **`ST_Simplify` por polígono abría huecos entre vecinas** (Douglas-Peucker se queda con
  vértices distintos del mismo borde en cada anillo). Simplificar la cobertura entera
  en cada pedido tardaba 3.8 s con Jalisco; guardarla una vez, nada al leer.
- **Una sola clase dividía entre cero** al repartir colores y opacidades.
- **La prueba de focos del buscador fallaba a veces:** buscaba "C6" en todo el HTML y el
  token de la sesión de LiveView (base64) a veces lo trae. Ahora busca la etiqueta del
  botón.
