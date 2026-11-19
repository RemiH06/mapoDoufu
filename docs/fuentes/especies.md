# Especies de plantas y árboles nativos

Plantas vasculares registradas alrededor de una zona, cada especie con su estatus en
México. Sirve para elegir qué plantar en un proyecto de arborización: qué árboles
son nativos o endémicos y cuáles ya se han visto en la región. No la carga la base
de Mapo: sale en el paquete de una zona.

```bash
uv run --script scripts/ambiental/especies.py --salida SALIDA --caja=O,S,E,N [--radio-km 30]
```

## De dónde

| Fuente | Qué da | Licencia |
|---|---|---|
| GBIF, búsqueda de ocurrencias | Cada registro de Tracheophyta con coordenadas en un círculo alrededor del centro de la caja: ejemplares de herbario y observaciones (iNaturalist con grado de investigación, que no incluye lo cultivado) | La de cada registro, en la columna `licencia`: CC0, CC BY o CC BY-NC |
| Enciclovida (CONABIO), `especies/ID.json` | Tipo de distribución en México (nativa, endémica, exótica, exótica invasora, criptogénica) y sus características, cada nivel en su columna: forma de crecimiento (18), hábitat y tipo de vegetación (2), riesgo UICN, NOM-059 y CITES (4), usos (11), silvestre o cultivada (23), nectarífera (24) y pariente silvestre de cultivo (25). El nivel 1 ("Descripción del taxón") no es dato y se omite | Consulta pública de CONABIO |
| GRIIS México (GBIF, `7185a1d5-...`) | Si la especie está registrada como introducida en el país | CC BY 4.0 |

Cada fuente queda en sus propias columnas. No hay puntaje de "idoneidad": qué tan
bien le va a una especie en una banqueta (raíces, agua, sombra, poda) no está en
ninguna de estas fuentes, y lo decide quien diseña el proyecto.

### Cómo se cruzan

- **Nombres:** Enciclovida escribe el subgénero en algunos géneros (`Quercus
  (Quercus) rugosa`); se compara sin él. Si el nombre de GBIF no está, se prueban
  sus sinónimos binomiales del backbone de GBIF, prefiriendo el que conserva el
  epíteto: `Vachellia farnesiana` (huizache) es `Acacia farnesiana` en Enciclovida
  y `Prosopis laevigata` (mezquite) es `Neltuma laevigata`. La columna
  `metodo_enciclovida` dice si fue con el mismo nombre o por cuál sinónimo, y
  marca "(otro epíteto: revisar)" cuando el sinónimo encontrado no conserva el epíteto.
- **Árbol:** `es_arbol` es "si" cuando "Árbol" está entre las formas de
  crecimiento de Enciclovida (muchas especies son "Árbol; Arbusto"), "no" si hay
  formas pero no esa, y vacío si Enciclovida no la da.
- **Consultas:** la búsqueda de GBIF tarda minutos por página con desplazamientos
  grandes (más de 2 min en el registro 30,000). Se parte la región en cuadros de a
  lo más 3,000 registros y se pagina cada uno desde cero; los registros se juntan
  por su `gbif_id`. Enciclovida se consulta por género (una búsqueda trae todas sus
  especies) y por especie, con 4 hilos y caché en `enciclovida_cache.json`.

## Qué deja

| Archivo | Qué es |
|---|---|
| `especies.csv` | Una fila por especie: registros en la región, en la caja, de herbario y de observación, último año, columnas de Enciclovida y GRIIS |
| `arboles_nativos.csv` | Las mismas columnas, solo forma árbol y distribución nativa o endémica, por familia y nombre (sin orden de prioridad) |
| `registros_especies.gpkg` | Capa `registros`: cada registro con especie, año, tipo, incertidumbre, conjunto de datos, institución, licencia y si cae en la caja |
| `procedencia_especies.csv` | Fecha de consulta, centro, radio, consulta, cuadros, conteos por tipo, licencia y distribución |

## Validación (2026-11-19)

Caja del CP 45615, Tlaquepaque (-103.40, 20.52, -103.29, 20.62), 30 km alrededor
de su centro, en 40 cuadros:

- GBIF reportó 41,162 registros; quedan 39,865 con especie (los 1,297 restantes
  están identificados solo a género o más arriba). 21,008 observaciones, 17,645
  ejemplares de herbario. Licencias: 19,992 CC BY-NC, 17,464 CC BY, 2,409 CC0.
- 3,191 especies: 1,719 nativas, 1,010 endémicas, 231 exóticas, 77 exóticas
  invasoras, 153 sin dato en Enciclovida. 246 se encontraron por sinónimo de GBIF;
  41 de ellas cambian de epíteto y quedan marcadas para revisar.
- 579 con forma árbol; 516 nativas o endémicas (178 endémicas), 404 de ellas con
  ejemplares de herbario en la región y 46 con algún registro dentro de la caja.
- Contra especies conocidas: encinos (*Quercus resinosa*, *Q. castanea*),
  ahuehuete, palo bobo, tepame, parota, fresno, mezquite y huizache salen nativos;
  jacaranda, eucalipto, casuarina y tulipán africano, exóticos o invasores. Solo una
  especie nativa según Enciclovida está en GRIIS (*Senna polyantha*).
- *Ficus benjamina*, muy plantado en banquetas del AMG, no tiene registros: lo
  plantado casi no llega a GBIF.

## Límites

- **Nativa de México no es nativa del valle.** La parota y la rosa morada son
  nativas del país pero de tierras bajas. Los registros de herbario en la región
  (`registros_herbario`) son la mejor señal de que la especie crece silvestre
  cerca; las observaciones urbanas pueden ser árboles plantados.
- GBIF tiene sesgo de muestreo: más registros donde más se colecta (barrancas,
  La Primavera, campus), no donde la especie es más común.
- iNaturalist con grado de investigación excluye lo marcado como cultivado, así que
  casi no trae el arbolado urbano plantado (ficus, jacarandas en banqueta). Para eso
  hace falta el inventario del AMG (Imeplan, 2024), que no es público como datos.
- Los registros CC BY-NC (la mitad, sobre todo iNaturalist) no se pueden usar con
  fines comerciales.
- El catálogo de CONABIO y el backbone de GBIF no siempre coinciden; lo que quedó
  sin cruzar va con su `metodo_enciclovida` vacío de estatus.
