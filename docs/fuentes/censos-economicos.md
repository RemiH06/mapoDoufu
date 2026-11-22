# Censos Económicos 2024 (INEGI)

Unidades económicas, personal ocupado, remuneraciones, ingresos, producción y valor
agregado del año 2023, por municipio y sector SCIAN. En `/perfil`, debajo del DENUE en el
libro mayor ("Tamaño de la economía, 2023").

- **Dónde:** datos abiertos por estado,
  `https://www.inegi.org.mx/contenidos/programas/ce/2024/datosabiertos/conjunto_de_datos_ce_{abr}_2024_csv.zip`
  (`jal`, `cdmx`, `mex`...; 1 a 6 MB). La página del programa arma sus enlaces con
  JavaScript; los nombres salieron de la API de descarga masiva de INEGI
  (`/app/api/descarga/componente/descargamasiva/lista/archivoscompaginacion?...&idBiinegi=3366`).
- **Nivel:** estado, municipio, sector a clase y estrato de personal. **No hay AGEB:**
  el producto por AGEB urbana de 2019 no se repitió en 2024 (2026-11-22).
- **Carga:** `python -m mapo_core.cli censos_economicos [--estados 14 ...] [--carpeta ...]`
  (`mapo_core/censos_economicos.py`). Guarda solo el nivel de sector sin estrato:
  `fuente_ce2024_municipal`, un renglón por municipio y sector más el total (`sector =
  'total'`). Reemplaza cada estado en una transacción.
- **Variables:** `UE`, `H001A` (personal ocupado total), `J000A` (remuneraciones),
  `M000A` (ingresos por suministro de bienes y servicios), `A111A` (producción bruta
  total) y `A131A` (valor agregado censal bruto), en millones de pesos de 2023.
- **Reservados:** INEGI deja vacía la celda que permitiría identificar a una empresa. Se
  guarda `null` y el perfil dice "INEGI reserva el personal de N sectores", nunca cero.
  En Jalisco, 580 de 1,994 renglones de sector.
- **Comprobación al cargar:** los municipios tienen que sumar las unidades del total del
  estado; si no, no se carga.

## Validación

Contra la monografía de Jalisco de INEGI (`mjal_ce24.pdf`): 365,421 unidades, 2,092,026
personas ocupadas, 249,897 millones de remuneraciones, 1,870,778 de producción y 939,970
de valor agregado; las cinco iguales. Guadalajara: 24.5 % de las unidades, 30.2 % del
personal, 29.9 % de las remuneraciones y 28.8 % del valor agregado del estado, iguales a la
tabla 2 de la monografía.

## Pendiente

- Al buscador (hoy solo en `/perfil`).
- Remuneración media por persona remunerada (`J000A` entre personal remunerado), que
  INEGI publica por estado: hace falta la columna del personal remunerado.
