# Perfil de zona

`/perfil` describe cualquier zona de la [zona común](zona.md): un estado, un municipio o
varios, una metrópoli, una colonia, un código postal, un dibujo o un círculo (sesión 29h; antes,
solo un municipio). Arriba, la zona con su plano y seis cifras; abajo, ocho documentos, uno por
enfoque; al final, las zonas que se le parecen. Ningún documento se resume en un puntaje.

## Qué dato es de quién

Cada documento dice su nivel. Si el dato no es de la zona, va en un recuadro punteado ("De
Guadalajara entero, no de la zona").

| Documento | Fuente | Nivel más fino |
|---|---|---|
| Población | Censo 2020, rezago social de CONEVAL | la zona |
| Vivienda | Censo 2020, precio de oferta del IIEG | la zona; propias y rentadas (Intercensal 2025), el municipio |
| Servicios a pie | Minutos de [accesibilidad.md](accesibilidad.md) | la zona |
| Negocios | DENUE | la zona; Censos Económicos, el municipio |
| Gasto de los hogares | ENIGH | el estado; la muestra del municipio, como referencia |
| Incidencia delictiva | SESNSP | el municipio |
| Empleo | IMSS; ENOE | el municipio; el estado |
| Hacienda | EFIPEM, CNGMD | el municipio |

- **Varios municipios se suman** (delitos, puestos, unidades). La hacienda va por municipio con
  su último año reportado, y la suma solo lleva a los que reportaron el último.
- **La ENOE no se suma entre estados:** si la zona toca varios, se dice.
- **Un año de SESNSP incompleto** va rayado y sin tasa por habitante.
- **Lo reservado por INEGI** no es cero: se dice en cuántos lugares. Las razones (viviendas con
  internet sobre habitadas) solo usan los lugares que traen las dos partes.
- **Los minutos a pie** separan hasta 15, de 15 a 30 y más de 30. Sin ruta y sin calcular van
  aparte. Si lo no calculado pasa de 5 % del grupo, se dice de cuánta gente es la cifra; con más
  de la mitad, no hay cifra.
- Un polígono de más de 5,000 km² no se calcula y se dice por qué. Un estado o una metrópoli sí:
  van por clave.

## Cómo se estima una colonia o un dibujo

Los municipios enteros usan el renglón de INEGI. Lo demás se estima: cada AGEB urbana reparte su
gente por área (si la zona tiene la mitad, se lleva la mitad) y cada localidad sin AGEB cuenta
entera si su punto cae dentro.

Se midió contra la población por manzana del censo 2020 (Marco Geoestadístico, API de INEGI):
42,472 manzanas y 3,517,964 personas de Guadalajara, Zapopan y Tlaquepaque.

| Zona | Error mediano por área | Error mediano contando la AGEB por su punto |
|---|---|---|
| Colonias (1,212) | 20 % | 100 % |
| de 100 a 500 habitantes | 43 % | 100 % |
| de 500 a 1,500 | 29 % | 100 % |
| de 1,500 a 5,000 | 13 % | 50 % |
| de 5,000 a 20,000 | 5 % | 17 % |
| de más de 20,000 | 3 % | 7 % |
| Círculos de 500 m (150) | 10 % | 25 % |
| Círculos de 1 km (150) | 4 % | 10 % |

- Por punto, la mayoría de las colonias se queda sin gente: son más chicas que una AGEB. Por eso
  el perfil no usa la regla de `/riesgos` y `/accesibilidad`, que sirve para zonas grandes.
- Es un error mediano: una de cada diez colonias falla por más de 88 %.
- **La población que publica CONAPO por colonia no sirve para validar:** sale del mismo reparto
  (coincide a decimales en 4,397 colonias de Jalisco).
- En pantalla la gente y las viviendas van con ≈ y dos cifras significativas, con el error de su
  tamaño. Bajo 100 personas (error de más de 200 %) se avisa que ninguna cifra es de fiar.
- Para mejorarlo: cargar las manzanas. No están en Mapo.

## Plano y figuras

- **Plano:** personas por km² por AGEB, con cortes fijos (2,500, 5,000, 10,000 y 20,000) para
  comparar entre zonas; por municipio si la zona pasa de 5,000 km² (10, 40, 100 y 500). Las
  localidades sin AGEB son puntos con área según su gente. En una zona chica salen tenues las
  AGEB vecinas. La rueda pide Ctrl y el dedo, dos: el plano está dentro de una página. Ahí se
  dibuja también una zona nueva.
- **Pirámide:** INEGI da por AGEB bandas que no miden lo mismo (de 6 a 35 años). El alto son los
  años y el largo la gente por año, así que el área es la gente. La última va abierta y se
  dibuja de 60 a 85.

## Zonas que se parecen

`GET /perfil_zona/similares` (`mapo_core/similares.py`). Un municipio se compara con municipios;
una colonia, un CP, un dibujo o un círculo, con colonias de 500 habitantes o más. Varios
municipios, una metrópoli o un estado no tienen con qué compararse todavía, y se dice. Solo entra
lo cargado con `cli similares` (hoy Jalisco: 125 municipios y 2,419 colonias).

- **Nada se junta en un puntaje.** Cada variable dice por su cuenta si la otra zona cae en la
  *banda* de esta. La lista va por cuántas variables caen; el empate lo decide la menor de las
  mayores diferencias, que no se muestra.
- **La banda** mide hacia cada lado una fracción del rango intercuartil de esa variable entre
  las comparadas: un cuarto ("muy cerca"), la mitad ("cerca") o entero ("con holgura"). Puesta en
  la mediana, la de "cerca" contiene a la mitad de las comparadas. Se da en sus unidades. La
  densidad, los habitantes, los negocios y los montos por habitante se comparan en proporción
  (logaritmo): el doble está tan lejos como la mitad.
- **Áreas:** población, vivienda, negocios, empleo y salud, servicios a pie, y solo por municipio
  seguridad (promedio de los tres últimos años completos) y hacienda. Sin elegir, todas.
- **Dónde** (colonias): en todo, en el mismo municipio o en otros. La banda no cambia con esto.
- **Un dato que falta** no cuenta como parecido ni como distinto; con menos de la mitad de los
  datos, la zona no sale.
- **Desglose:** por variable, las dos cifras, la banda y dónde cae cada una entre el 10 % más
  bajo y el 10 % más alto de las comparadas.
- **Comprobado a ojo:** Guadalajara se parece más a Zapopan (25 de 37), Autlán a El Grullo (28),
  y la Americana a Arcos Vallarta (18 de 26) y, en Puerto Vallarta, a Versalles (17).
- La hacienda de cada municipio es de su último año reportado, que no es el mismo para todos.

La tabla `similares_zonas` se calcula de las demás (`cli similares --estado 14`, 2.5 min en
Aerilate): se vuelve a correr al recargar el censo, DENUE, la accesibilidad, los Censos
Económicos, el IMSS, el SESNSP o EFIPEM. Un dibujo se calcula al vuelo con el mismo código.

## Enlace y notas

- `/perfil?zona=<clave>`; con parecidos, `&parecidas=<áreas o todas>&margen=...&donde=...`. Los
  enlaces con `cve_ent` y `cve_mun` siguen abriendo.
- Las notas del equipo cuelgan del equipo, la zona (su clave) y el documento.

## Tiempos

En Aerilate: una colonia 0.8 s, Guadalajara 1.7 s, la ZMG 5.6 s, Jalisco 21 s; los parecidos,
menos de 1 s.
