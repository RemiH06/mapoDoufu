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

| Archivo | Contenido | Valores |
|---|---|---|
| `s2_bandas_<periodo>.tif` | 10 bandas de Sentinel-2 (B02 a B12 sin B01, B09 ni B10), mediana sin nubes | Reflectancia × 10 000, `uint16`, 0 sin dato |
| `s2_indices_<AAAA-MM>.tif` | NDVI, NDWI (McFeeters) y NBR, mediana del mes | × 10 000, `int16`, -32768 sin dato |
| `lst_secas_<AAAA>.tif` | Temperatura de superficie, mediana de marzo a mayo | °C × 100, `int16`, -32768 sin dato |
| `worldcover_2021.tif` | Clases de cobertura de ESA | 10 árboles, 20 matorral, 30 pastizal, 40 cultivo, 50 construido, 60 suelo desnudo, 80 agua, 90 humedal |

## Correcciones que hace

- **URL firmadas:** Planetary Computer firma cada URL con un token que caduca en
  cerca de una hora, y una mediana larga lee mucho después de buscar. Se firma
  al leer (`patch_url` de odc-stac), con reintentos de GDAL, y una escena que
  falla se salta. Firmando al buscar, la primera corrida murió a los 50 minutos.
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

## Lo que no hace

- **Quemas por zafra:** la caña se cosecha y se quema de noviembre a mayo, así
  que un dNBR entre antes y después de la zafra confunde quema con cosecha. Por
  eso se entrega el NBR mensual: la caída de un mes al siguiente, cruzada con
  los focos de FIRMS, separa una de otra.
- **Clasificación:** no se clasifica nada. Para entrenar hay uso de suelo VII
  (`recorte.py`) y WorldCover como referencia.

## Validación: Autlán y El Grullo (2026-11-15)

- WorldCover 2021: 5,564 × 7,355 píxeles, clases 10 a 90 presentes, sin huecos.
- Temperatura de secas 2024: 43 escenas de Landsat. p5 26 °C, mediana 40 °C,
  p95 49 °C, razonable para suelo en mayo en un valle a 900 m.
