# Huellas de edificios

Polígonos del techo de cada edificio, de Overture Maps (tema `buildings`). Sirven
para saber dónde hay construcción a escala de lote: sombra, superficie de techo,
qué tan apretada está una manzana. No los carga la base de Mapo: salen en el
paquete de una zona.

```bash
uv run --script scripts/ambiental/edificios.py --salida SALIDA --caja=O,S,E,N [--version 2026-11-18.0]
```

## De dónde

Overture junta OpenStreetMap, Microsoft ML Buildings y Google Open Buildings en
una sola capa sin duplicados, y dice de cuál viene cada edificio (`fuente`). Se
lee directo de los GeoParquet públicos en S3 con DuckDB, sin cuenta: solo bajan
los grupos de renglones cuya caja toca la pedida. Una caja de 11 km tarda 19 s.

Licencia ODbL, por lo que viene de OSM: el paquete lo dice y quien publique un
mapa con ellos debe atribuir a Overture y a OpenStreetMap.

| Columna | Qué es |
|---|---|
| `id` | Id de Overture, estable entre versiones mientras el edificio no cambie |
| `fuente`, `id_fuente` | De dónde salió y su id allá |
| `altura_m`, `pisos` | Solo si la fuente los trae: casi nunca fuera de OSM |
| `clase` | Uso, si lo trae (casi siempre vacío) |
| `area_m2` | Área del techo, calculada en EPSG:6372 |
| `version_overture` | La versión leída, para repetir la consulta |

Un edificio entra si su caja toca la caja pedida: los de la orilla salen completos.

## Validación (2026-11-18)

Caja del CP 45615, Tlaquepaque (-103.40, 20.52, -103.29, 20.62), versión
2026-11-18.0, contra las 7,949 manzanas del censo 2020:

- 195,590 edificios: 119,805 de Microsoft, 74,944 de Google y 841 de OSM. Solo 19
  traen altura: para alturas está el dosel y, en la ZMG, la capa de altura de
  edificios del dataset de vivienda.
- 87 % cae dentro de una manzana; el resto, en zonas sin manzanas del marco
  (orillas rurales, predios grandes) o sobre la calle por desfase de la imagen.
- Mediana de 52 m² de techo (percentil 1, 11 m²; 99, 903 m²). 19 pasan de
  2 ha: naves industriales y centros comerciales.
- 0.8 edificios por vivienda (mediana por manzana), Spearman 0.42 con las
  viviendas de la manzana. En vivienda adosada el modelo junta techos contiguos
  en un solo polígono: **contar edificios no es contar casas**.
- 58 de 6,879 manzanas con viviendas no tienen ningún edificio: huecos del
  modelo o construcción posterior a la imagen.

## Límites

- La fecha de la imagen de cada fuente no viene por edificio: Microsoft y Google
  usan imágenes de 2018 a 2023 según la zona.
- En Mapo no caben como capa de un equipo en zonas urbanas (10,000 polígonos por
  capa): `para_mapo.py` lo marca y quedan solo en el paquete.
