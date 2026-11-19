# Emisiones de establecimientos (SEMARNAT, RETC)

Establecimientos de jurisdicción federal que reportaron al Registro de Emisiones y
Transferencia de Contaminantes, de 2004 a 2022, y lo que reportaron por sustancia.
Responde: **¿qué industria reporta emisiones cerca de aquí, de qué y a qué medio
(aire, agua, suelo)?**

```bash
docker compose exec mapo_core python -m mapo_core.cli ambiental --crudos /app/data/crudos-ambiental --fuente retc
```

Unos 5 minutos (19 Excel). Reemplaza `fuente_retc_establecimientos` y
`fuente_retc_emisiones`.

## De dónde sale

`RETC_2004-2022.zip` de `sinat.semarnat.gob.mx/retc`: un Excel por año con dos hojas,
"Datos Generales" y "Emisiones y Transferencias". Licencia: datos abiertos del
gobierno federal; citar "SEMARNAT, RETC".

Lo que cambia entre años y se resuelve al leer:

- El encabezado no está en el primer renglón: abajo de los títulos de la dirección
  general. Se busca el renglón con `LATITUD` (generales) o la celda `NRA`
  (emisiones); en 2004 y 2005 hay encima un renglón de grupos que no es encabezado.
- Las columnas cambian de nombre y orden: se toman por nombre normalizado.
- Coordenadas en decimales o en texto `20°41'27"`; la longitud oeste casi siempre
  sin signo.
- Unidades: `ton/año` (2004 y 2005), `kg/año`, `Kg` o `g`. Todo se guarda en kg.
- Algunos Excel declaran un millón de renglones vacíos: se corta tras 500 vacíos
  seguidos.

## Qué se guarda

`fuente_retc_establecimientos` (`anio`, `nra`): SCIAN (desde que lo traen),
actividad, sector, estado y municipio como texto, y el punto. `NOMBRE` no se lee:
hay granjas y talleres a nombre de personas.

`fuente_retc_emisiones`: por año, establecimiento y sustancia, `aire_kg`, `agua_kg`,
`suelo_kg` y `transferencias` (JSON en kg: reutilización, reciclado, coprocesamiento,
tratamiento, disposición final, alcantarillado, incineración, otros).

## Validación (2026-11-19)

- 50,905 reportes de establecimiento (de 1,714 en 2004 a 3,016 en 2022) y 171,851
  renglones de sustancia. Un NRA repetido en el mismo año se cuenta una vez.
- Coordenadas: desde 2012 casi todos los reportes traen una válida (2022: 3,016 de
  3,016); en 2004, 1,548 de 1,714. El punto cae en el estado que dice el reporte en
  99.8 % de 2022 y en 90 % de 2004 y 2012.
- 2022: 141 millones de toneladas de CO₂ reportadas, la sustancia más grande, luego
  metano y óxido nitroso. No se encontró una cifra oficial del total para comparar.

## Límites

- Solo reportan los establecimientos obligados (jurisdicción federal y umbrales de
  la NOM-165): un ingenio o una granja chica pueden no estar.
- Es lo que el establecimiento reporta, sin verificación pública.
- El estado y municipio son texto; para cruzar, usar el punto.
