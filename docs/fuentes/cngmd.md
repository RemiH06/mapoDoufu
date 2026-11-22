# Censo Nacional de Gobiernos Municipales 2025 (INEGI)

Lo que cada municipio declara de su propio gobierno en 2024. De sus decenas de tablas, Mapo
carga por ahora una: los instrumentos de planeación territorial. En `/perfil`, al pie del
papel "Hacienda municipal".

- **Dónde:** datos abiertos por tema; la tabla de instrumentos de planeación es
  `https://www.inegi.org.mx/contenidos/programas/cngmd/2025/datosabiertos/conjunto_de_datos_ins_plan_ord_jur_cngmd2025_csv.zip`
  (módulo 2, sección XIV, pregunta 10). Los nombres salen de la API de descarga masiva de
  INEGI (`idBiinegi=3430`), como en los Censos Económicos.
- **Carga:** `python -m mapo_core.cli cngmd conjunto_de_datos_ins_plan_ord_jur_cngmd2025_csv.zip`
  (`mapo_core/cngmd.py`), a `fuente_cngmd_planeacion`: 17 tipos de instrumento por
  municipio (catálogo `instmun_a`), si existió, si se publicó y la vigencia, que cada
  municipio escribe a mano ("2045", "INDEFINIDA", "NO APLICA").
- **Respuestas tal cual:** sí, no, no se sabe, no aplica, sin elementos para responder,
  información no disponible. "No se sabe" nunca se vuelve "no".
- **En el perfil:** plan de desarrollo urbano, atlas de riesgos, programa de movilidad,
  ordenamiento ecológico y territorial y acción climática siempre; los demás, solo los que
  existían.

## Cifras

2,465 municipios y demarcaciones, 41,905 renglones. Con plan o programa de desarrollo
urbano del municipio: 942 (12 no saben); atlas de riesgos: 570 (31 no saben); programa de
movilidad: 167; acción climática: 94.

Sin comprobar todavía contra una cifra publicada (los tabulados del CNGMD 2025 traen
estos conteos por estado): pendiente abajo. Lo que sí se revisó es que el perfil de
Guadalajara y Autlán muestre lo mismo que la tabla cruda.

## Pendiente

- Comparar los conteos por instrumento contra los tabulados del CNGMD 2025.
- Catastro y predial (padrón, cuentas pagadas, actualización catastral) y protección civil
  (personal), que pedía la 28: cada tabla con su cuestionario a la mano.
