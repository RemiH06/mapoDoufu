# Imágenes de satélite

Mapo no guarda imágenes en su base ni las procesa en el servidor: son pesadas y
cada estudio pide otro periodo. `scripts/ambiental/imagenes.py` arma compuestos
recortados a una zona y los deja como GeoTIFF para QGIS, junto al paquete de
`recorte.py` (`ambientales.md`).

## De dónde salen

El STAC público de Microsoft Planetary Computer: no pide cuenta, y firma las
URLs al vuelo (`planetary-computer`). Se lee solo la ventana de la caja de cada
escena (COG), así que no se baja la escena completa.

| Producto | Colección | Resolución | Desde | Licencia |
|---|---|---|---|---|
| Bandas y NDVI, NDWI, NBR | `sentinel-2-l2a` | 10 m | 2017 | Copernicus, uso libre con atribución |
| Temperatura de superficie | `landsat-c2-l2` (Landsat 8 y 9) | 30 m (banda térmica remuestreada por USGS de 100 m) | 2013 | USGS, dominio público |
| Cobertura del suelo | `esa-worldcover` | 10 m | 2020 y 2021 | CC BY 4.0 |

## Uso

```bash
uv run --script scripts/ambiental/imagenes.py --salida SALIDA/imagenes \
  --caja=-104.65,19.55,-103.95,20.05 --epsg 32613 \
  --worldcover --bandas 2025-02-01/2025-05-31 --lst 2014/2025 --indices 2024-11/2025-10
```

`--epsg`: la UTM de la zona (13N para Jalisco occidental, 14N del centro al
este). Cada producto se salta si ya existe y se escribe a `.tmp.tif` antes de
renombrar, así que un corte se reanuda relanzando el mismo comando. `--hilos`
(3 por omisión) limita la RAM: la mediana carga todas las fechas de un bloque.
En Pixilate se corre como trabajo de `job.ps1`.

Cada corrida anota en `procedencia_imagenes.csv` las escenas que usó (producto,
bloque, colección, ID de la escena en el STAC, fecha, nubosidad y mosaico).
`--solo-procedencia` repite las búsquedas sin bajar nada, para anotar productos
hechos con una versión anterior del script.

| Archivo | Contenido | Valores |
|---|---|---|
| `s2_bandas_<periodo>.tif` | 10 bandas de Sentinel-2 (B02 a B12 sin B01, B09 ni B10), mediana sin nubes | Reflectancia × 10 000, `uint16`, 0 sin dato |
| `s2_indices_<AAAA-MM>.tif` | NDVI, NDWI (McFeeters) y NBR, mediana del mes | × 10 000, `int16`, -32768 sin dato |
| `lst_secas_<AAAA>.tif` | Temperatura de superficie, mediana de marzo a mayo | °C × 100, `int16`, -32768 sin dato |
| `worldcover_2021.tif` | Clases de cobertura de ESA | 10 árboles, 20 matorral, 30 pastizal, 40 cultivo, 50 construido, 60 suelo desnudo, 80 agua, 90 humedal |

## Correcciones que hace

- **Por bloques, por las URL firmadas:** Planetary Computer firma cada URL con un
  token que caduca en cerca de una hora, y odc-stac aplica la firma (`patch_url`)
  al **armar** el cálculo, no al leer. El primer compuesto de Autlán tardó una
  hora: lo que se leyó al final (el 22 % sur de la caja) ya tenía el token
  vencido, falló, y `fail_on_error=False` lo saltó sin aviso. Se vio solo al
  mirar una vista en color. Ahora cada producto se arma en bloques de 0.25°
  (`--bloque`): cada bloque busca, firma, calcula y se guarda en minutos; al
  final se unen y se mide el porcentaje sin dato (avisa `¡HUECO!` arriba de 2 %).
  Un bloque que falla se reintenta tres veces y luego el producto no se escribe;
  relanzar retoma desde los bloques que faltan (`.bloques_<producto>/`).
- **Esquinas fuera de la caja:** la caja en grados, proyectada a UTM, es un
  cuadrilátero girado. Los bloques cubren la caja pero no todas las esquinas
  de su envolvente en UTM: en Autlán queda 0.5 % sin dato, todo fuera de la caja.
- **Menos escenas, las más despejadas:** el compuesto usa las 16 escenas con
  menos nubes (menos de 20 %) y los índices mensuales 8, repartidas por mosaico
  MGRS para que ninguna parte de la caja se quede sin datos. Con las 87 escenas
  de secas el compuesto tardaba horas en leer decenas de GB.
- **Nubes en Sentinel-2:** se conservan solo las clases 4 a 7 de la capa SCL
  (vegetación, suelo, agua, sin clasificar). Se tiran nubes, cirros, sombras y
  píxeles saturados, y luego se toma la mediana.
- **Desplazamiento de la línea base 04.00:** desde enero de 2022 ESA suma 1000 a
  cada valor de reflectancia. Sin restarlo, el NDVI de 2022 en adelante sale
  más bajo que el de antes sin que cambie nada en el suelo. Se resta por escena,
  según `s2:processing_baseline`.
- **Landsat:** temperatura con la escala de USGS (DN × 0.00341802 + 149.0, en
  kelvin), y nubes y sombras fuera con los bits 3 y 4 de `QA_PIXEL`.

## Altura de dosel a 1 m

`scripts/ambiental/dosel.py --salida SALIDA --caja=O,S,E,N --epsg 32613` recorta
el mapa de altura de dosel de Meta y WRI (Tolan et al. 2024, CC BY 4.0): un modelo
entrenado con lídar que estima la altura de los árboles en imágenes de Maxar de
~0.5 m. Ve árboles sueltos en banquetas y patios, que Sentinel-2 (10 m) mezcla con
el pavimento: es la capa base para arborización.

- **Origen:** bucket público `dataforgood-fb-data`, índice `tiles.geojson` (56,145
  mosaicos de nivel 9 en EPSG:3857) y un COG por mosaico (`chm/<quadkey>.tif`,
  ~600 MB, uint8 en metros, sin nodata declarado).
- **Lectura:** los COG están en franjas de una fila y sin vistas reducidas, así
  que una ventana baja filas completas (unos 80 MB por mosaico para 11 km). Para
  una zona metropolitana entera hay que partir en bloques como `imagenes.py`.
- **Salida:** `dosel_1m.tif` en la UTM pedida a 1 m (0 sin dosel, 255 fuera de
  cobertura), `dosel_fecha.tif` con la fecha de la imagen de origen y
  `procedencia_dosel.csv`. El archivo de fechas viene en grados y con celdas
  gruesas; su valor parece ser el año menos 2000 en decimales (20.33 ≈ abril de
  2020 en Tlaquepaque). No ve lo plantado o talado después de esa fecha.
- **Zona del CP 45615 (Tlaquepaque, 2026-11-17):** 2 mosaicos, 11,581 × 11,187 px,
  98 % con dato y 3.6 % de la caja con dosel de 3 m o más.
- **Límites:** subestima árboles altos y aislados y confunde algunas estructuras
  con dosel; validar contra unas cuantas calles conocidas antes de concluir.

## NO₂ de Sentinel-5P

`scripts/ambiental/no2_s5p.py`: NO₂ troposférico medio de un año en una
rejilla fina, para cualquier caja. Es NOX del dataset de vivienda y sirve como
capa ambiental.

- **Lectura parcial:** cada órbita es un NetCDF de cientos de MB. Con `fsspec` y
  `h5py` se leen por rangos HTTP la latitud y la longitud, y luego solo los
  renglones que tocan la caja: unos 15 a 30 s por órbita en lugar de bajarla.
- **Filtros:** modo de procesamiento OFFL (no mezclar con NRTI ni con
  reprocesos de otra colección, que tienen sesgos distintos), `qa_value > 0.75`
  (quita nubes, nieve y escenas malas) y valores de relleno (9.97e36) fuera.
- **Rejilla:** un píxel de TROPOMI mide unos 5.5 × 3.5 km. Se suma a cada celda
  cuyo centro cae dentro de su huella (las cuatro esquinas de
  `SUPPORT_DATA/GEOLOCATIONS`) y se promedia. La celda de 0.01° no agrega
  detalle: conserva la forma de la huella.
- **Reanudable:** guarda la suma, la cuenta y las órbitas hechas cada 10 órbitas.
- **Salida:** GeoTIFF de dos bandas en EPSG:4326: media en µmol/m² y número de
  observaciones.
- **Licencia:** datos de Copernicus Sentinel; al publicar, "contiene datos
  modificados de Copernicus Sentinel [año]".

## Validación: Autlán, índices mensuales (2026-11-15)

De noviembre de 2024 a mayo de 2025, de 0.5 a 1 % sin dato (las esquinas fuera
de la caja). De junio a octubre de 2025, de 2 a 7.8 %: es el temporal, con días
nublados sin escena limpia, no fallas de lectura. Para un mes de lluvias con
cobertura completa, ampliar el periodo.

## Lo que no hace

- **Quemas por zafra:** la caña se cosecha y se quema de noviembre a mayo, así
  que un dNBR entre antes y después de la zafra confunde quema con cosecha. Por
  eso se entrega el NBR mensual: la caída de un mes al siguiente, cruzada con
  los focos de FIRMS, separa una de otra.
- **Clasificación:** no se clasifica nada. Para entrenar hay uso de suelo VII
  (`recorte.py`) y WorldCover como referencia.

## Validación: Autlán y El Grullo (2026-11-15)

- WorldCover 2021: 5,564 × 7,355 píxeles, clases 10 a 90 presentes, sin huecos.
- WorldCover por bloques (6 de 0.25°): la misma rejilla de 5,564 × 7,355 que en
  una sola lectura, mismas clases, 0.5 % sin dato en las esquinas.
- Temperatura de secas de 2014 a 2025: 0 % sin dato cada año. Se hizo antes del
  cambio a bloques, pero cada año tardó menos de 10 minutos, dentro de la vida
  del token.
- Temperatura de secas 2024: 43 escenas de Landsat. p5 26 °C, mediana 40 °C,
  p95 49 °C, razonable para suelo en mayo en un valle a 900 m.
