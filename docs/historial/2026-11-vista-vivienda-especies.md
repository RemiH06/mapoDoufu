# Vista de vivienda y especies nativas (noviembre 2026, sesión 21)

Dos entregas en la misma sesión: las especies nativas que le faltaban al paquete de
arbolado de la colonia López Cotilla (fecha del equipo: 29 de noviembre) y la vista
de precios de vivienda que la sesión 20 dejó preparada.

## Qué se hizo

- **Especies** (`../fuentes/especies.md`): `scripts/ambiental/especies.py` junta los
  registros de plantas vasculares de GBIF en 30 km alrededor de una zona, el
  estatus de cada especie en Enciclovida (nativa, endémica, exótica, invasora),
  su forma de crecimiento, hábitat, riesgo y usos, y el cruce con GRIIS México.
  Deja `especies.csv`, `arboles_nativos.csv`, los registros en GeoPackage y su
  procedencia. Ya va en `arbolado_cp45615.zip`, carpeta `especies/`.
- **Vista de vivienda** (`../producto/vista-vivienda.md`): acetato "Vivienda por
  municipio" en `/mapa`, con ocho indicadores de cuatro fuentes, uno a la vez, y la
  ficha de un municipio con SHF, SNIIV, Intercensal 2025 y ENVI por separado.
  Endpoints `/vivienda/catalogo`, `/vivienda/municipios` y `/vivienda/ficha`.
  La ficha trae la serie del SHF como línea en SVG, sin JavaScript: el valor de
  cada trimestre en su `<title>` y la tabla completa plegada.

## Por qué así

- **Especies sin puntaje de idoneidad.** Ninguna fuente dice qué especie aguanta
  una banqueta; lo que sí hay (nativa o no, árbol o no, registros de herbario
  cerca, hábitat, usos) va en columnas. `arboles_nativos.csv` es un filtro, no un
  ranking: va por familia y nombre.
- **Herbario aparte de observación.** Nativa de México no es nativa del valle: la
  parota es de tierras bajas. Que haya ejemplares de herbario en la región es la
  señal de que crece silvestre cerca, y se cuenta aparte.
- **Vivienda como acetato y no como pantalla.** Así se cruza en la misma mesa con
  el censo por AGEB, el DENUE o los datos del equipo, que es lo que pide el plan
  de vistas temáticas.
- **Un indicador a la vez, con su método a la vista.** Las cuatro fuentes miden
  cosas distintas (cambio, préstamo, tenencia, renta declarada) a niveles
  distintos. Juntarlas sería un puntaje.

## Bugs y sorpresas

- **GBIF se vuelve lentísimo con desplazamientos grandes:** una página en el
  registro 30,000 tardó más de 2 minutos y la primera corrida no terminó en 20.
  Partir la región en cuadros de a lo más 3,000 registros la bajó a unos minutos.
- **Enciclovida escribe subgéneros** (`Quercus (Quercus) rugosa`): la búsqueda por
  nombre completo no encontraba ningún encino. Se busca por género y se compara
  sin el paréntesis.
- **Las taxonomías no coinciden:** 246 de 3,191 especies no estaban con el nombre
  de GBIF, entre ellas el huizache (`Acacia farnesiana` en CONABIO) y el mezquite
  (`Neltuma laevigata`). Se resuelven con los sinónimos de GBIF, y el método dice
  cuál; 41 quedan marcadas para revisar porque el sinónimo cambia de epíteto.
- **La columna de "riesgo" traía usos.** Al revisar el resultado salió "Leña",
  "Maderable" y "Ornamental" como riesgo: las características de Enciclovida
  vienen en niveles (riesgo es el 4, usos el 11, hábitat el 2). Cada nivel tiene
  ahora su columna.
- **Un promedio de $40 por crédito** en un segmento de Tlaquepaque: 1,000
  mejoramientos del INFONAVIT con monto 0. Ya estaba en `../fuentes/sniiv.md`; el
  promedio ahora usa solo las acciones con monto.
- **En la ficha de vivienda las cifras quedaban de un carácter de ancho** junto a
  etiquetas largas, y la cinta crecía hasta tapar el membrete. Se vio solo en el
  navegador; las pruebas pasaban.

## Lo que salió con datos reales

- 39,865 registros y 3,191 especies en 30 km alrededor del CP 45615; 579 con forma
  árbol, de ellas 516 nativas o endémicas (178 endémicas) y 404 con ejemplares de
  herbario en la región. La mitad de los registros son CC BY-NC.
- Especies conocidas en su lugar: encinos, ahuehuete, palo bobo, tepame, parota,
  mezquite y huizache como nativas; jacaranda, eucalipto, casuarina y tulipán
  africano como exóticas o invasoras. El ficus benjamina, muy plantado en
  banquetas del AMG, no aparece: lo plantado casi no llega a GBIF.
- Vivienda: cambio anual del SHF de Guadalajara 9.64 % y Zapopan 9.15 %, igual que
  la validación de la sesión 20; Intercensal 2025 en los 125 municipios de Jalisco;
  SNIIV 2025 en 110 (15 sin registro, que quedan sin dato y no en cero).
