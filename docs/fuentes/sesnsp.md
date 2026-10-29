# SESNSP (seguridad)

**SESNSP NO se pudo vendorizar como downloader automático**: la URL
fija que usaba Gaiarda (`repodatos.atdt.gob.mx/.../IDM_NM_dic25.csv`)
ya no responde, el dominio completo da 403 (confirmado desde curl real
en la máquina del usuario, con headers de navegador real, no es un
problema de User-Agent). Investigado el reemplazo real: SESNSP ahora
distribuye este dataset vía un link de SharePoint
(`sspcgob-my.sharepoint.com`) que exige inicio de sesión incluso con
el truco de `&download=1`, no es un endpoint público automatizable con
un cliente HTTP simple. Decisión del usuario: tratarlo igual que
CAPUFE en Gaiarda (que tampoco tiene descarga automática por bloqueo
de `robots.txt`):

- `mapo_core/sesnsp_ingesta.py`, vendorizado de
  `gaiarda/src/gaiarda/fuentes/sesnsp/{api,downloader}.py` pero sin la
  parte de descarga HTTP: espera un CSV ya descargado a mano (el
  usuario inicia sesión en el navegador, descarga el archivo, y se lo
  pasa al CLI). Sin checkpoint (a diferencia de las fuentes
  automáticas): cada carga es una acción deliberada del usuario, el
  upsert ya es idempotente por sí solo
- `python -m mapo_core.cli sesnsp --archivo <ruta>` para cargarlo
- `/perfil_zona` ahora trae `seguridad: {anio, total_delitos,
  por_tipo}` del año más reciente disponible para ese municipio (o
  `null` si no hay nada cargado todavía, que es el caso actual: 0
  filas en `fuente_sesnsp_delitos_municipal`). A propósito NO se
  combina en un solo "puntaje de seguridad" (mismo criterio que ya usa
  Gaiarda en su feature de Rutas)
- Probado con las mismas filas reales que ya usan los tests de
  Gaiarda (pegadas por el usuario directo del CSV real), no inventadas

**SESNSP, cerrado con datos reales el 2026-09-27.** La carpeta real de
SharePoint resultó tener más de lo esperado: un PDF propio de SESNSP
(`1. PARA_EVITAR_ERRORES_ANTES_DE_SU_USO`) que explica que el dataset
se publica en 2 formatos equivalentes (XLSX por año, para hojas de
cálculo; y un CSV consolidado 2015-2025, para software con más
capacidad), más archivos de metodología anterior (2014 y antes) y el
sistema nuevo **RNID** para 2026 en adelante (cambio de nombre de
sistema, no solo de año). Mapo usó el **CSV consolidado**
(`Municipal-Delitos-2015-2025_ago2026.csv`), que trae exactamente las
mismas columnas que ya esperaba `sesnsp_ingesta.py`
(`Año, Clave_Ent, Entidad, Cve. Municipio, Municipio, Bien jurídico
afectado, Tipo de delito, Subtipo de delito, Modalidad, Enero..Diciembre`):
no hizo falta soportar XLSX ni tocar el parser.

- El archivo se guarda en `mapo_core/data/sesnsp/` (nuevo, gitignored,
  montado en el contenedor via `docker-compose.yml`:
  `./mapo_core/data:/app/data`). Mismo criterio que `.env` para el
  token de DENUE: datos/credenciales de fuentes manuales no se
  versionan, pero sí tienen un lugar fijo esperado
- **Bug real de memoria encontrado y corregido antes de poder cargar
  el archivo real**: el CSV consolidado pesa ~380 MB y expande a
  decenas de millones de filas en formato largo. La primera versión de
  `sesnsp_ingesta.py` leía el archivo completo a memoria y
  materializaba toda la expansión en una lista de Python antes de
  tocar la base: contra el archivo real, esto **tumbó el contenedor
  entero por falta de memoria** (`OOMKilled`, confirmado con `docker
  inspect`). Corregido a un pipeline en streaming: `parsear_archivo`
  ahora es un generador (nunca el archivo completo en memoria), y
  `cargar_archivo` manda las filas a Postgres via `COPY` (streaming
  nativo) hacia una tabla temporal, con un solo `INSERT ... ON
  CONFLICT` de fusión al final en vez de un INSERT por fila
- **Probado con el archivo real completo, no una muestra**: las
  **30,755,928 filas** (10 años × municipios × delito/subtipo/
  modalidad × 12 meses) se cargaron completas. `/perfil_zona` de
  Guadalajara: `seguridad: {anio: 2025, total_delitos: 28865,
  por_tipo: [["Robo", 10126], ["Otros delitos del Fuero Común", 4356],
  ...]}`, confirmado con `curl` directo
- Memoria del contenedor estable durante toda la carga (~135 MB, antes
  se quedaba sin memoria por completo), confirmado con `docker stats`
  en vivo durante la corrida real
