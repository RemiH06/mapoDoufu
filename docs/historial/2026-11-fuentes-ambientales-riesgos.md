# Fuentes ambientales y vista de riesgos (noviembre 2026, sesiones 22 y 23)

## Qué se hizo

- **22:** diez fuentes ambientales cargadas desde los crudos con `cli ambiental`, cada una
  con su ficha en `../fuentes/` y validada: acuíferos (286 de 653 sin disponibilidad, como
  el DOF), RENAMECA, REPDA, RETC, SIAP (maíz 2022 a 0.1 % del SIAP), FIRMS (653 focos en la
  caja de Autlán en 2024, igual que el recorte), uso de suelo VI y VII (195.09 millones de
  ha), ANP (182 y 90.84 millones de ha, como CONANP), sequía y defunciones (los cuatro
  totales de INEGI exactos). El relieve no entra a la base: `recorte.py` lo lee del STAC
  de Planetary Computer fuera de Jalisco. El ITER ya estaba.
- **23:** `/riesgos` (`../producto/vista-riesgos.md`).
- **Paquetes para el ITESO:** versión para ArcGIS del paquete de arbolado
  (`scripts/ambiental/para_arcgis.py`) y la comparación de calor y arbolado entre siete
  metrópolis (`../producto/comparacion-ciudades.md`).

## Por qué así

- **Solo agregados de personas.** Defunciones por municipio, nunca por certificado; RETC
  sin nombre de establecimiento. El paquete de arbolado traía los microdatos de
  defunciones (heredados del recorte de Autlán): se cambió a conteos el mismo día.
- **La zona se calcula una vez.** Las distancias en `geography` contra el contorno de un
  municipio tardaban 260 s; con la zona y su buffer precalculados, 1.3 s.
- **El paquete de arbolado no es el de Autlán.** Remi corrigió el alcance: arbolado lleva
  calor, dosel, demografía y marginación, no agua ni emisiones.

## Bugs y sorpresas

- **El índice de marginación de CONAPO 2020 va al revés:** más alto es menos marginado.
  La primera tabla comparativa tenía el signo de las correlaciones invertido.
- **`GetField` por nombre en GDAL** busca el campo cada vez: con 239 campos, la
  geodatabase no avanzaba. Por índice, segundos.
- **Referencias de GDAL en Python:** una capa o banda de un dataset temporal muere con él
  (`gdal.Open(x).GetRasterBand(1)` truena).
- **Geodatabase sin enteros de 64 bits:** GDAL los escribe como decimales; se usan de 32.
- **INEGI usa `N/D` además de `*`** en el censo por manzana.
- **Metrópolis de México 2020 solo existe en PDF;** la tabla de la Ciudad de México viene
  partida entre páginas.
- **Docker Desktop se cayó dos veces en Aerilate** a mitad de pruebas.
