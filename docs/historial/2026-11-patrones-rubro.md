# Patrones por rubro (noviembre 2026, sesión 18)

`donde_poner` asumía que la competencia estorba: el filtro "sin florería a
menos de N minutos" nunca proponía Mezquitán. Ahora el buscador dice qué hace
el rubro (si se agrupa, en qué plazas, junto a qué y dónde) y el filtro de
zonas candidatas se puede invertir. En el camino, la carga de DENUE pasó de la
API a la descarga masiva, porque la paginación de la API pierde negocios.

## Qué se hizo

- **`patrones.py` y `POST /buscador/patron`** para `donde_poner` y `cuantos`:
  prueba de agrupación por vecino más cercano contra 199 sorteos de etiquetas,
  parte en plazas con la misma prueba, cociente de colocación de Leslie y
  Kronenfeld y focos con `ST_ClusterDBSCAN`. Detalle y límites en
  `../producto/buscador.md`, "Patrón del rubro".
- **Zonas candidatas con sentido:** `sentido` lejos (antes, el único) o cerca;
  por minutos se ordena primero lo que más cumple.
- **Pantalla:** sección "Patrón del rubro" en la respuesta, capa de focos con
  contorno punteado en el plano, los 5 mayores en lista con botón para
  centrarlos, y selector "más cercano: lejos o cerca" en los criterios.
- **DENUE:** columnas `clee`, `tipo_plaza`, `plaza` y `numero_local`; la carga
  baja el CSV masivo del estado y lo reemplaza en una transacción
  (`../fuentes/denue.md`).

## Por qué así

- **Contra sorteos de etiquetas, no contra puntos uniformes.** El comercio ya se
  junta siguiendo calles y gente; la pregunta útil es si el rubro se junta más
  que el comercio en general. Sortear etiquetas conserva las ubicaciones. La
  semilla es fija para que la misma pregunta dé la misma respuesta.
- **DBSCAN y no k-means**, como decía el plan: no pide cuántos focos, deja fuera
  lo suelto y no parte corredores. El radio sale del azar (la mitad de la
  distancia media de los sorteos), así que se adapta a rubros densos y ralos sin
  una constante por rubro. Solo se buscan focos si el rubro se agrupa: si no, lo
  que saliera sería casualidad.
- **Colocación con umbral estricto.** Con 183 rubros probados a la vez, a 0.05
  saldrían varios por azar; se pide p < 0.01 y al menos 10 casos.
- **Sin puntaje ni "conviene" (RNF5).** Se dice "se agrupa" y quien pregunta
  elige el sentido de las zonas. Que se junten no dice que les vaya mejor: eso
  es el estudio de sobrevivencia, que sigue pendiente.
- **Descarga masiva y no la API.** Ver abajo.

## Bugs reales

| Síntoma | Causa | Arreglo |
|---|---|---|
| Al recargar Jalisco por la API llegaron 401,813 registros pero solo 395,704 ids, y se borraron 6,109 negocios "que ya no venían" | La paginación de `BuscarEntidad` no es estable: la misma página pedida dos veces trae otro orden y hasta 5 de 1,000 negocios distintos. Los 6,109 no cerraron: la paginación se los saltó | La carga usa el CSV masivo (401,813 negocios, ningún id repetido) y se niega a cargar si un id se repite. La base de dev se recuperó con él |
| "Ver" en un foco no movía el plano | El parseo de números de la pantalla rechaza negativos (es para criterios), y la longitud en México es negativa | Parseo propio para coordenadas; lo atrapó el test |
| La pantalla decía "9 focos, con borde en el plano" y se dibujaban 8 | Se mandaban solo los que se listaban | Al plano van hasta 50; se listan 5 y se dice cuántos más hay |
| Un test esperaba cociente mayor que 5 y dio 4.6 | El umbral del test estaba mal: con 30 de 30 junto a dulcería entre 255 dulcerías de 1,184 vecinos, lo esperado es 4.64 | Test con el valor calculado a mano y un caso que sí prueba la asimetría |

## Validación con datos reales

- **Florerías en Guadalajara:** se agrupan (145 m al vecino del rubro contra
  240 m al azar, rango 224 a 255). Nueve focos; el mayor, Mezquitán con 117,
  igual que la API contó a 500 m del panteón. En plazas, 14.2 % contra 13.3 %
  de todos: lo mismo que al azar.
- **Dulcerías en la zona metropolitana** (10 municipios, 233 mil negocios):
  se agrupan en Abastos, San Juan de Dios, el Centro y Santa Teresita; su vecino
  más cercano es, más de lo esperado, primaria (1.8 veces) y papelería (1.7).
- **Tiempos:** Guadalajara 9 s y la zona metropolitana 12 s la primera vez; luego
  se sirve de memoria. La carga masiva de Jalisco tarda 4 min 21 s (la paginada,
  27 min 46 s).
- **Navegador real** (escritorio y celular, claro y oscuro, sin errores de
  consola): la sección se lee, los focos se ven punteados sobre la coropleta, el
  botón centra el foco y "cerca" deja 179 de 442 AGEB a 2 minutos o menos.

## Pruebas

`test_patrones.py` (11, con datos hechos a mano y DBSCAN contra la base de
test), `test_denue_downloader.py` (8, ZIP armado en el test), un caso de
`sentido` en `test_zonas.py` y 6 en el buscador de Phoenix. `pytest` 336 y
`mix precommit` 347.

## Pendiente

- **Producción:** recargar DENUE con la descarga masiva (crea las columnas
  nuevas; sin eso, `/buscador/patron` falla porque consulta `tipo_plaza`).
- **Sobrevivencia** (notebook, aparte): el CSV masivo trae `fecha_alta` y
  `clee`; falta bajar ediciones viejas y ver si `clee` es estable.
- **Taxonomía de rubros** con k-means sobre rasgos de rubro (agrupación, parte
  en plazas, colocación): opcional, no se hizo.
