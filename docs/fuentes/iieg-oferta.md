# Precios de oferta de vivienda (IIEG)

Anuncios de venta de casas y departamentos que el Instituto de Información
Estadística y Geográfica de Jalisco junta de los portales inmobiliarios, en los
seis municipios principales de la zona metropolitana de Guadalajara. Responde:
**cuánto piden por una vivienda aquí**. Es el MEDV del dataset de vivienda
desde la v8 (`../producto/dataset-vivienda.md`).

No hay cargador a la base: el dataset lee los archivos directo.

```bash
MSYS_NO_PATHCONV=1 docker compose exec mapo_core python -m mapo_core.cli dataset_vivienda ... \
  --oferta /app/data/iieg/BD_SECTOR_INMOBILIARIO_07_2024.xlsx \
  --oferta-colonias /app/data/iieg/mapa_venta.shp --oferta-periodo 2024-07
```

## De dónde sale

Página del sector inmobiliario del IIEG, `https://iieg.gob.mx/ns/?page_id=11967`.
Se bajan a mano a `mapo_core/data/iieg/`:

| Archivo | Qué trae |
|---|---|
| `BD_SECTOR_INMOBILIARIO_07_2024.xlsx` (`wp-content/uploads/2024/12/`) | Hoja `Venta`: un renglón por anuncio con tipo (casa o departamento), municipio, colonia, precio y metros de terreno y de construcción. Hoja `Renta`: lo mismo sin metros |
| `conjunto_datos_vectoriales.zip` (`wp-content/uploads/2024/12/`) | `mapa_venta.shp` y `mapa_renta.shp`: polígonos de colonia en WGS84 con el promedio, la mediana y el número de anuncios de cada una |

Hay ediciones trimestrales desde octubre de 2019. Al 2026-11-20, la última es la
de julio de 2024 (publicada en diciembre de 2024).

## Cómo se usa

`mapo_core/src/mapo_core/iieg_oferta.py`:

- **Duplicados:** el IIEG avisa que los portales repiten anuncios. Se quitan los
  exactos (mismo tipo, municipio, colonia, precio y metros): 7,144 de 49,122.
  Dos departamentos iguales del mismo edificio también caen aquí; se prefiere
  eso a que un desarrollo anunciado veinte veces decida la mediana.
- **Ubicación:** los anuncios no traen coordenadas, solo colonia. Se empatan con
  los polígonos por municipio y nombre, sin acentos ni signos (el XLSX y el
  shapefile no escriben la Ñ igual). Las colonias homónimas de un municipio se
  unen en un polígono.
- **Reparto a la AGEB:** un anuncio de la colonia c cuenta en la AGEB a con peso
  área(c ∩ a) / área(c). Si los anuncios se reparten parejo dentro de la colonia,
  es cuántos caen en a. Solo cuentan colonias del mismo municipio que la AGEB.
- **`medv`:** mediana ponderada de los precios, con 3 anuncios efectivos como
  mínimo. `medv_m2` hace lo mismo con precio entre metros construidos (de 20 a
  3,000 m²).
- **`mercado_municipal.csv`:** media, mediana y cuartiles por municipio con todos
  los anuncios, también los que no traen colonia. Es la cifra contra la que se
  calibra en `estudios/precio_estimado/modelos.ipynb`.

## Límites

- Es precio **pedido**, no de venta: suele estar por arriba del de cierre.
- Solo lo que se anuncia en portales: deja fuera la venta entre conocidos, la
  informal y casi toda la vivienda económica. Zapopan pone más de la mitad de los
  anuncios.
- Cerca de 43 % de los anuncios no trae colonia: cuentan para el municipio, no
  para la AGEB.
- La colonia del anuncio la escribe quien anuncia; el IIEG la valida contra su
  catálogo, pero un anuncio en la colonia equivocada se queda ahí.
- Pocos anuncios fuera de Guadalajara, Zapopan y Tlajomulco: Tonalá tiene 886
  y El Salto 231 en todo el municipio. En Tonalá el orden de las AGEB sale al
  revés de la escolaridad (`../producto/dataset-vivienda.md`).
- Seis municipios. Los otros cuatro de la zona metropolitana (Acatlán,
  Ixtlahuacán de los Membrillos, Juanacatlán y Zapotlanejo) quedan sin `medv`.
- El IIEG no publica licencia. Citar como "IIEG con información de sitios web de
  venta y renta de propiedades". Mapo no redistribuye los anuncios, solo la
  mediana por AGEB y el resumen municipal.

## No sirve la SHF para el nivel

La SHF da la media y los cuartiles del precio por estado (`shf.md`): Jalisco,
primer trimestre de 2026, media de $2.21 millones y mediana de $1.28 millones.
La mediana de los anuncios de la zona metropolitana en julio de 2024 es de $4.95
millones. Miden poblaciones distintas (avalúos de crédito en todo el estado
contra precios pedidos en portales), así que una no calibra a la otra.
