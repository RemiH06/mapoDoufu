# Finanzas públicas municipales (INEGI, EFIPEM)

Cuánto ingresa cada municipio y de dónde (impuestos, derechos, participaciones,
aportaciones, financiamiento), cuánto cobra de predial y en qué gasta, por año. En `/perfil`,
papel "Hacienda municipal".

- **Dónde:** https://www.inegi.org.mx/contenidos/programas/finanzas/datosabiertos/efipem_municipal_csv.zip
  (109 MB): un CSV largo por año de 1989 a 2023, con tema (ingresos o egresos), nivel
  (tema, capítulo, concepto, partida genérica, subpartida), concepto y valor en pesos.
- **Carga:** `python -m mapo_core.cli efipem efipem_municipal_csv.zip`
  (`mapo_core/efipem.py`). Guarda los últimos cinco años, solo tema y capítulo más la
  partida "Impuesto predial": `fuente_efipem_municipal`, unos 180 mil renglones.
  Reemplaza todo.
- **Ingresos propios:** impuestos, contribuciones de mejoras, derechos, productos y
  aprovechamientos. **Transferencias:** participaciones federales y aportaciones federales y
  estatales. Lo que falta para el 100 % es financiamiento (deuda) y otros.
- **Pesos corrientes** de cada año, sin ajustar por inflación; el perfil lo dice.
- **Municipios que no reportan:** no tienen renglones ese año. 2019: 2,121; 2020: 2,250;
  2021: 2,225; 2022: 2,386; 2023: 2,249 de 2,475. El perfil muestra el último año del
  municipio y avisa si no es el último publicado; si no reportó ninguno, lo dice. Por
  estado varía mucho: en 2023, Puebla 61 de 217 y Oaxaca 550 de 570. La Ciudad de México no
  está en ningún año (sus alcaldías no tienen hacienda propia) y el perfil lo dice así, no
  como "no reportó".
- INEGI escribe algunos conceptos con espacios duros (`Remuneraciones\xa0al\xa0personal`):
  se limpian al leer.

## Validación

- **Al cargar:** los capítulos de ingresos suman el total de ingresos al peso en todos los
  municipios y años; cero descuadres en 2019 a 2023.
- Guadalajara 2023: ingresos 11,358.7 millones (iguales a sus egresos), predial 1,548.4,
  propios 38.8 %, transferencias 60.5 %, más 0.7 % de financiamiento.
- Sin cifra externa todavía: la cuenta pública de cada municipio está en PDF y con otro
  clasificador.

## Pendiente

- A la comparación de ciudades (`../producto/comparacion-ciudades.md`), como pedía la 28.
- Predial por habitante o por cuenta (el CNGMD trae el padrón de predial).
