# Comparación de ciudades: calor, arbolado y marginación

Para el proyecto de arborización (sesión del 2026-11-19): la zona metropolitana de
Guadalajara completa, con la colonia López Cotilla como objetivo, comparada por AGEB
urbano con seis metrópolis parecidas y distintas. Temperatura de superficie, dosel, NDVI,
censo 2020 y marginación de CONAPO, cada una por separado (sin índice), con la
procedencia de cada dato y una guía para recalcular cualquier número en ArcGIS.

No lleva agua, emisiones, fuego ni defunciones: eso era del caso de Autlán.

**Entrega vigente desde el 2026-11-24:** solo 2020 y solo Guadalajara, Monterrey y Querétaro,
en shapefile (sección "Entrega 2020"). Lo demás de este documento describe la de siete
ciudades, que se conserva.

## Entrega 2020

Hipótesis del equipo: hay correlación entre marginación y temperatura de superficie.
`scripts/ambiental/ciudades_2020.py` (pasos `base`, `lst` y `entrega`), con
`LEEME_ciudades_2020.txt`. Sin base de Mapo: todo del productor.

| Dato | Fuente |
|---|---|
| Polígonos de AGEB y municipios | INEGI, Marco Geoestadístico del censo 2020 (`889463807469`, `EEa.shp` y `EEmun.shp`) |
| Población | INEGI, censo 2020 por AGEB (igual a la de CONAPO en los 4,378 AGEB) |
| Marginación | CONAPO, IMU 2020 |
| Temperatura | Landsat 8 de 2020, `ST_B10`, Planetary Computer |

**Por qué no la mediana de marzo a mayo.** En 2020 solo estaba Landsat 8. En Monterrey cada
AGEB tenía unas 2 fechas despejadas, distintas según la nube, con medianas de 28 a 48 °C: la
mediana por píxel pintaba la nubosidad. La correlación con marginación daba 0.06, contra 0.16
en las dos fechas más despejadas de ese periodo. Regla: fechas de marzo a junio con 98 % o más
de la mancha urbana despejada (QA_PIXEL bits 1 a 4), una sola órbita por ciudad, promedio solo
donde el píxel está limpio en todas. Quedan 7 fechas en Guadalajara, 2 en Monterrey y 5 en
Querétaro. La entrega de 2025 sí usa la mediana por píxel (con dos satélites); no se revisó
si Monterrey tiene ahí el mismo defecto.

**Shapefile y vacíos.** El DBF no guarda nulos y ArcGIS los lee como 0: los AGEB sin índice
van en `AGEB_<ciudad>_sin_dato.shp`.

| Ciudad | AGEB | Temperatura mediana (°C) | Spearman marginación y temperatura | n efectivo | p ajustada | Quinto más marginado menos el menos (°C) |
|---|---|---|---|---|---|---|
| Guadalajara | 1,790 | 45.5 | 0.10 | 124 | 0.28 | +0.42 |
| Monterrey | 2,008 | 42.4 | 0.06 | 160 | 0.47 | +0.37 |
| Querétaro | 580 | 40.8 | −0.17 | 364 | 0.0015 | −0.76 |

La p se ajusta por autocorrelación espacial (Clifford, Richardson y Hémon; Dutilleul). Con
campos suaves simulados sin relación rechaza 5 % al 5 % (sin ajustar, 54 %). Por fecha,
Guadalajara va de −0.39 (31 de julio) a +0.21 (28 de mayo); Querétaro es negativa en todas.

Comprobado: 0 AGEB de CONAPO sin polígono, promedios y celdas iguales a los de QGIS
(`native:zonalstatisticsfb`) en las tres ciudades, shapefiles sin nulos ni geometrías
inválidas. Zip en `mapo_core/data/entrega_ciudades_2020_2026-11-24/` (32 MB).

## Ciudades

Delimitación oficial: SEDATU, CONAPO e INEGI, *Metrópolis de México 2020* (edición
2024, [PDF](https://www.gob.mx/cms/uploads/sedatu/MM2020_06022024.pdf), sha256
`1d8e7b90…`). Solo existe en PDF: los municipios de cada metrópoli salieron de sus
cuadros A a `scripts/ambiental/metropolis_2020_municipios.csv` (91 de las 92; la de la
Ciudad de México, partida entre páginas, se sacó aparte). Los conteos de las siete usadas
coinciden con el cuadro resumen del documento.

| Clave | Metrópoli | Municipios | Grupo | UTM |
|---|---|---|---|---|
| `zmg` | Guadalajara | 7 | objetivo | 13N |
| `mty` | Monterrey | 16 | parecida | 14N |
| `pue` | Puebla-Tlaxcala | 28 | parecida | 14N |
| `leo` | León | 3 | parecida | 14N |
| `mer` | Mérida | 13 | distinta (cálida húmeda) | 16N |
| `hmo` | Hermosillo | 1 | distinta (desierto) | 12N |
| `cdmx` | Ciudad de México | 63 | distinta (mucho más grande) | 14N |

La ZMG oficial de 2020 son 7 municipios. `taxonomia` y el dataset de vivienda usan 10
(con Ixtlahuacán de los Membrillos, Zapotlanejo y Acatlán de Juárez, de delimitaciones
anteriores): no son la misma zona.

## Cómo se hace

```bash
# En Pixilate (necesita la base de Mapo con los estados cargados: cli municipios, agebs
# y censo_poblacion de 09 11 13 14 15 19 21 26 29 31)
scripts/ambiental/ciudades.sh BASE [zmg mty ...]
# En Aerilate, con el Python de QGIS
"C:\Program Files\QGIS 4.2.3\bin\python-qgis.bat" scripts/ambiental/empaquetar_ciudades.py \
    --entrada BASE --salida comparacion_ciudades \
    --leeme scripts/ambiental/LEEME_comparacion_ciudades.txt --guia scripts/ambiental/GUIA_VERIFICACION_ArcGIS.txt
```

| Paso | Qué hace |
|---|---|
| `agebs` | AGEB urbanos de los municipios de la metrópoli desde la base de Mapo, con 15 variables del censo 2020 y la marginación de CONAPO por AGEB (`IMU_2020`) |
| `imagenes.py` | Temperatura de superficie de Landsat (mediana de marzo a mayo de 2025, 30 m) y NDVI de Sentinel-2 (compuestos mensuales de marzo, abril y mayo de 2025, 10 m) |
| `reales` | Pasa la temperatura a °C y saca la mediana de los tres NDVI mensuales |
| `dosel` | Lee los mosaicos de ~1 m de Meta y WRI por franjas y deja dos rásteres a 10 m: % del área con árboles de 3 m o más y su altura media. Sin guardar el de 1 m (en la Ciudad de México serían decenas de GB) |
| `zonal` | Promedio de cada ráster por AGEB, con las celdas cuyo centro cae dentro (la regla de Zonal Statistics de ArcGIS), y cuántas celdas fueron |
| `colonias` | Solo la ZMG: lo mismo por colonia de CONAPO |
| `resumen` | Tabla por ciudad: medianas, ponderados por población, rango p90 menos p10, Spearman entre pares y diferencia entre el quintil más y el menos marginado |

Cada paso se salta si su salida ya existe. Los promedios salen de los mismos rásteres que
se entregan: eso es lo que permite al equipo comprobarlos.

## Validación

- **Dosel:** en la caja del CP 45615, el ráster de 10 m da 3.64 % de cobertura, lo mismo
  que el de 1 m del paquete de arborización (3.64 %).
- **Promedios por AGEB contra otro programa:** la estadística zonal de QGIS
  (`native:zonalstatisticsfb`) sobre los 1,987 AGEB de la ZMG y la temperatura da el mismo
  promedio: mismas celdas en el 99.9 %, diferencia máxima de 0.04 °C.
- **Población:** los AGEB urbanos suman 4,999,609 en la ZMG (la metrópoli completa,
  5,110,617; el resto es rural) y 20,838,648 en la Ciudad de México (21,436,911).

- **Índice de CONAPO al revés de lo intuitivo:** en el IMU 2020 un valor más alto es
  menos marginación (en la ZMG, grado "Muy bajo" ronda 124.8 y "Muy alto" 113.0; con
  `SBASC`, sin educación básica, la correlación es −0.93). La primera tabla comparativa
  salió con las correlaciones de marginación al revés y el "quintil más marginado" era el
  menos marginado. Ahora `resumen` invierte el signo y el alias del campo lo dice.

## Resultados (2026-11-19)

| Ciudad | AGEB con población | Temperatura mediana (°C) | Dosel mediano (%) | Spearman dosel y temperatura | Quintil más marginado contra el menos (°C; puntos de dosel) |
|---|---|---|---|---|---|
| Guadalajara | 1,921 | 42.6 | 3.9 | −0.39 | +0.85; −2.2 |
| Monterrey | 2,079 | 39.5 | 6.1 | −0.30 | +0.66; +0.6 |
| Puebla-Tlaxcala | 866 | 39.7 | 2.2 | −0.37 | +0.22; +0.4 |
| León | 760 | 41.0 | 1.9 | −0.12 | +1.11; −0.4 |
| Mérida | 692 | 42.1 | 17.0 | −0.37 | +0.38; +13.7 |
| Hermosillo | 622 | 44.3 | 3.8 | −0.18 | +0.04; +2.7 |
| Ciudad de México | 5,664 | 40.1 | 3.3 | −0.47 | +0.67; −7.5 |

La colonia López Cotilla: 44.2 °C de superficie (más caliente que el 85 % de las 1,919
colonias de la ZMG) con 9.4 % de dosel (más que el 87 %).

La temperatura absoluta depende de las fechas de las escenas de cada ciudad; para
comparar dentro de cada una está `lst_vs_mediana_ciudad_c`.

## Marginación 2010

Complemento solo en tablas (2026-11-19), sin rehacer el paquete:
`scripts/ambiental/marginacion_2010.py` con la base de CONAPO por AGEB urbano 2000 a 2010
([`Base_marginacion_AGEB_00-10.csv`](https://conapo.segob.gob.mx/work/models/CONAPO/Datos_Abiertos/AGEB_Urbana/Base_marginacion_AGEB_00-10.csv),
sha256 `ac31daf7…`, enlazada desde
[Índices de marginación 1990-2010](https://www.gob.mx/conapo/documentos/indices-de-marginacion-1990-2010))
y el IMU 2020 de siempre. Mismos municipios de 2020 en los dos años. Sale
`4_marginacion_2010.zip` junto a la entrega, con `LEEME.txt`
(`scripts/ambiental/LEEME_marginacion_2010.txt`).

- `marginacion_ageb_2010.csv`: los AGEB de 2010 con sus 10 indicadores, índice y grado, tal cual.
- `comparacion_ageb_2010_2020.csv`: unión por `cvegeo`; `presencia` dice si la clave existe
  en los dos años (`en_ambos`) o en uno.
- `resumen_ciudad_2010_2020.csv`: por ciudad.

Qué se compara y qué no, según las metodologías de CONAPO (2010: cuadro 1.1 y anexo C del
*Índice de marginación urbana 2010*; 2020: nota técnica del IMU 2020):

- **Índices en sentidos opuestos y con métodos distintos.** 2010 es de componentes
  principales y más alto es más marginado; 2020 al revés. El script lo comprueba con los
  datos (Spearman contra sin educación básica: +0.91 en 2010, −0.91 en 2020) y no los resta.
- **Posición:** el grado (orientativo, los cortes también cambiaron) y el percentil del AGEB
  dentro de su ciudad en cada año, que es lo más sólido.
- **Tres indicadores con la misma fórmula y unidad:** no asistencia de 6 a 14 años, sin
  educación básica de 15 o más y sin derechohabiencia.
- **No se restan:** en 2010 los de vivienda son % de viviendas y en 2020 % de ocupantes;
  drenaje, agua y hacinamiento además cambiaron de definición. Piso de tierra y refrigerador
  van lado a lado solo como referencia.

La no asistencia de 6 a 14 sube en las siete ciudades; también en todo el país (3.9 % a
5.5 %, ponderado por población), con la misma fórmula. Es de los censos, no del cruce.

| Ciudad | AGEB 2010 | Misma clave en 2020 | Población 2020 en esos AGEB | Población en grado Alto o Muy alto, 2010 y 2020 | Sin educación básica, mediana 2010 y 2020 |
|---|---|---|---|---|---|
| Guadalajara | 1,510 | 1,490 | 90.1 % | 15.7 %; 13.0 % | 35.0 %; 23.5 % |
| Monterrey | 1,586 | 1,580 | 82.5 % | 4.5 %; 2.3 % | 25.0 %; 15.7 % |
| Puebla-Tlaxcala | 788 | 772 | 95.2 % | 45.3 %; 26.2 % | 35.5 %; 23.8 % |
| León | 517 | 462 | 83.2 % | 22.8 %; 19.9 % | 47.3 %; 32.5 % |
| Mérida | 533 | 525 | 87.8 % | 18.3 %; 13.7 % | 33.5 %; 21.2 % |
| Hermosillo | 418 | 411 | 90.4 % | 9.8 %; 5.6 % | 23.9 %; 14.9 % |
| Ciudad de México | 5,301 | 5,224 | 96.5 % | 25.3 %; 13.2 % | 29.5 %; 20.2 % |

Que la clave se repita no garantiza los mismos límites. Los AGEB que solo existen en un año
quedan sin columnas de cambio; repartirlos por superficie no se hizo (pediría el marco
geoestadístico de 2010).

## Límites

- Una temporada (secas de 2025). Censo y marginación de 2020 (la de 2010, aparte y solo en
  tablas); dosel de imágenes de 2017 a 2020.
- Solo AGEB urbanos.
- Ciudades de otros países: temperatura, NDVI y dosel existen en todo el mundo, pero no
  hay censo ni marginación comparables. Si se agregan, sería en cuadrícula y solo con
  variables de satélite.
