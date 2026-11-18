# Frontera agrícola y ráster con valor por píxel (noviembre 2026, sesión 19, segunda parte)

La primera parte dejó la distancia entre capas, pero el caso de prueba enseñó dos
huecos: la capa agrícola disponible (uso de suelo, 1:250 000) era demasiado
gruesa para hablar de cientos de metros, y los rásteres que sube un equipo
(Sentinel-2, temperatura de superficie, WorldCover) solo se podían ver.

## Qué se hizo

- **Frontera agrícola del SIAP, serie II** (1:10 000, SPOT 5 de 2010 y 2011) en el
  recorte ambiental. Su sitio de descarga ya no existe: se baja la copia del
  Internet Archive y se lee el KMZ de ArcGIS a mano. Validada polígono por
  polígono contra la superficie oficial. Detalle en
  `../fuentes/ambientales.md`, "Frontera agrícola".
- **Valores de un ráster:** `mapo_core` arma teselas WKB de PostGIS raster
  (`POST /datos/raster_valores`) y Mapo las guarda en `capa_raster_teselas`
  con la extensión `postgis_raster`. Clic en el ráster en `/mapa` da el valor
  del píxel.
- **Valor de un ráster en cada renglón** (`Mapo.Capas.Muestreo`, pantalla
  `/teams/:id/datos/:capa_id/raster`): el píxel en el punto, o promedio, mínimo,
  máximo, píxeles y parte con ciertos valores dentro de un polígono o un radio.
- **Cuota de un ráster:** cuenta lo que ocupan sus valores ya guardados, o el
  archivo si pesa más.
- `para_mapo.py` escribe en el GeoTIFF qué es la banda ("LST °C × 100"), y Mapo
  lo muestra junto al valor.
- `Mapo.Capas.Derivadas` y `MapoWeb.DatosLive.Derivada`: lo que comparten la
  distancia y el muestreo (filtros, nombres de columna, guardar contra la cuota).

## Por qué así

- **Teselas en PostGIS y no el GeoTIFF en `mapo_core`:** el muestreo junta
  renglones y píxeles en una consulta, como la distancia, y `mapo_core` sigue sin
  guardar datos de los equipos.
- **WKB armado en `mapo_core` y no `ST_FromGDALRaster`:** habría que prender GDAL
  dentro de Postgres para leer archivos de usuarios. El formato WKB de PostGIS es
  simple y Postgres lo valida sin GDAL.
- **En grados y reducido por vecino más cercano:** consultar con la geometría de
  las capas sin transformar, y no inventar valores intermedios en un ráster de
  clases.
- **Cuota por lo guardado:** las teselas van sin comprimir en el WKB, pero
  Postgres las comprime al guardarlas. WorldCover baja de 16 MB a 1.9 MB y la
  temperatura casi no baja; cobrar los bytes crudos castigaba ocho veces de más a
  los rásteres de clases.

## Lo que salió con datos reales

La frontera agrícola fina cambió poco la cuenta respecto a uso de suelo, pero
ahora la escala sí permite hablar de cientos de metros (con la salvedad de que
es de 2011). La temperatura de superficie en secas de 2025 salió en el punto de
113 escuelas en 0.3 s, y la parte de cultivo de WorldCover en círculos de 300 m,
en 4 s. Al principio tardaba 47 s y la página se caía esperando: `ST_Intersects`
contra un ráster revisa píxel por píxel cada tesela, y la zona se recalculaba en
cada una.
