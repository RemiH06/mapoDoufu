# Empleo formal (IMSS)

Puestos de trabajo y salario base de cotización registrados en el IMSS, por
municipio y grupo de actividad, de los datos abiertos de asegurados. Responde lo
que el conteo de DENUE no: **cuánta gente tiene empleo formal aquí, en qué, y
cuánto cotiza**. Con el mismo mes de dos años, también si crece o se encoge.

```bash
docker compose exec mapo_core python -m mapo_core.cli imss data/imss
```

Toma uno o varios `asg-AAAA-MM-DD.csv` (o `.csv.gz`), o una carpeta con ellos, y
reemplaza esos meses en `fuente_imss_asegurados`. Un mes tarda unos 3 minutos y deja
unos 41,600 renglones.

## De dónde sale

Portal de datos abiertos del IMSS, un archivo por mes:

```
http://datos.imss.gob.mx/sites/default/files/asg-AAAA-MM-DD.csv
```

Separado por `|`, en latin-1, con fin de línea CRLF; diciembre de 2024 pesa 1.56 GB
(52 MB comprimido) y trae 4.65 millones de renglones. El diccionario de datos
(`diccionario_de_datos_1.xlsx`, actualizado el 24 de mayo de 2019) trae el layout y
los catálogos.

**El portal no deja bajar con un programa** (2026-11-21): responde 503 con una
página de Incapsula a `curl`, a `httpx` y a Chromium sin ventana, desde Aerilate y
desde Pixilate. No se intenta saltar el filtro. Lo cargado salió de la copia íntegra
que guardó el Internet Archive del archivo oficial:

| Mes | Copia | Comprobado contra |
|---|---|---|
| enero de 2024 | `web.archive.org/web/20260331113520id_/http://datos.imss.gob.mx/sites/default/files/asg-2024-01-31.csv` | Boletín del IMSS: 22,133,407 puestos |
| diciembre de 2024 | `web.archive.org/web/20260331113306id_/http://datos.imss.gob.mx/sites/default/files/asg-2024-12-31.csv` | Boletín del IMSS y del IIEG (abajo) |

Las demás copias del Archive pesan menos de 1 MB: están truncas o son la página del
filtro. Los meses nuevos se bajan a mano en un navegador y se cargan igual.

## Qué se guarda

Se suma por mes, estado, clave de municipio del IMSS, división y grupo. Lo demás
(fracción, tamaño del patrón, sexo, edad, rango salarial) se queda fuera.

| Columna | Qué es |
|---|---|
| `periodo` | Último día del mes |
| `cve_ent`, `cve_mun` | `000`: sin municipio (ver abajo) |
| `clave_imss` | `cve_municipio` del IMSS, para rehacer la equivalencia sin volver a cargar |
| `division`, `grupo` | `sector_economico_1` y `_2` del catálogo del IMSS. Vacíos: asegurados sin empleo |
| `puestos` | `ta`, empleo asegurado (puestos de trabajo, no personas) |
| `permanentes`, `eventuales` | `tpu + tpc` y `teu + tec` (urbano más del campo) |
| `asegurados`, `sin_empleo` | Asegurados y los que no tienen empleo asociado (`no_trabajadores`) |
| `puestos_con_salario`, `masa_salarial` | `ta_sal` y `masa_sal_ta`, en pesos diarios. Salario promedio = masa entre puestos con salario |
| `puestos_rango_tope` | `ta` en el rango W25 de UMA (más de 24 y hasta 25 UMA, donde está el tope) |

## Municipios: clave del IMSS a INEGI

El IMSS usa su propio catálogo (`A01`, `Y45`, `Z29`...) y el diccionario solo da
estado y nombre, sin clave de INEGI. Un municipio puede tener varias claves (una por
subdelegación: Guadalajara tiene seis). `scripts/imss/equivalencia.py` empareja por
nombre dentro del estado contra el catálogo de INEGI y escribe
`mapo_core/src/mapo_core/imss_municipios.csv` (2,471 claves) con el método de cada una:

- 2,449 por nombre exacto (sin acentos ni mayúsculas).
- 18 por nombre corregido a mano: el nombre oficial es más largo (Cintalapa de
  Figueroa) o cambió (Rosario es Valle del Rosario; Solidaridad, Playa del Carmen).
- 2 localidades que el IMSS trata como municipio: Isla de Cedros (Ensenada) y Santa
  Ana Pacueco (Pénjamo).
- 2 claves nuevas que no están en el catálogo de 2019, comprobadas con el IIEG:
  `Z60` es Zapopan y `Z62` es Guadalajara. Con ellas, los dos municipios dan al
  puesto lo que publica el IIEG; sin ellas faltaban exactamente 35,765 y 5,546.

Quedan en `000`, sumados en su estado y dichos en pantalla:

- **La Ciudad de México entera** (3,479,354 puestos en diciembre de 2024): el IMSS
  no la reparte por alcaldía.
- Claves nuevas sin comprobar: `Z45` en Michoacán (55,483), `Z40` y `Z61` en
  Quintana Roo (8,714 y 6,225), `Z63` en Coahuila (3,701), `Z64` en Aguascalientes
  (950), `Z47` y `Z48` en Baja California (884 y 78). Por el estado, las de Baja
  California y Quintana Roo pueden ser municipios nuevos (San Quintín y San Felipe;
  Puerto Morelos), pero no hay con qué comprobarlo. Se asignan cuando una cifra
  publicada por municipio las cuadre, como las de Jalisco.

El cargador imprime, por mes, cada clave que quedó en `000` con sus puestos.

## Grupos del IMSS y rubros de Mapo

El IMSS no clasifica con SCIAN sino con su catálogo de actividades (9 divisiones, 62
grupos en `imss_grupos.csv`). Cada sector de Mapo lleva en `rubros/sectores.csv`
(columna `grupos_imss`) los grupos más cercanos: comida preparada es el 87,
salud el 92, ropa el 62. Un rubro toma los de su sector. Es aproximado y se dice en
pantalla: los grupos de compraventa mezclan mayoreo y menudeo, y la reparación de
autos no tiene grupo propio.

El diccionario pone los grupos 20 a 29 en la división 2, pero los archivos los traen
en la 3 (Industrias de transformación); manda lo que traen los archivos.

## Validación (2026-11-21)

Diciembre de 2024, contra el
[boletín del IMSS](https://www.imss.gob.mx/prensa/archivo/202501/009) y el
[boletín económico del IIEG de enero de 2025](https://iieg.gob.mx/ns/wp-content/uploads/2025/02/boletin_economico_IIEG_enero_2025.pdf):

- Nacional: 22,238,379 puestos y salario diario promedio de $587.39; el IMSS publica
  22,238,379 y $587.4.
- Jalisco: 2,026,081; el IIEG, 2,026,081.
- Siete municipios, igual al puesto que el IIEG: Guadalajara 694,493, Zapopan
  481,851, San Pedro Tlaquepaque 138,822, Tlajomulco 115,410, Puerto Vallarta 81,535,
  El Salto 73,575 y Tonalá 36,475.
- Seis divisiones de Jalisco, igual que el IIEG: agropecuario 115,357, extractivas
  3,062, transformación 519,468, construcción 146,929, eléctrica y agua 10,411,
  comercio 429,181.
- Enero de 2024, nacional: 22,133,407, igual al boletín del IMSS.

## Límites

- **Solo empleo formal registrado.** Quien trabaja sin seguro social no aparece.
- **Municipio del registro patronal**, no donde vive ni donde trabaja la persona:
  una empresa registrada en Guadalajara puede tener gente en Zapopan.
- **Salario de cotización con tope de 25 UMA.** El promedio queda abajo del real
  donde hay muchos salarios altos; en Zapopan, 2.8 % de los puestos está en el último
  rango. Es salario diario.
- **Puestos, no personas:** quien tiene dos empleos cuenta dos veces.
- **Sin variación anual con lo cargado:** enero y diciembre no son el mismo mes, y
  comparar meses distintos mezcla la temporada (diciembre pierde empleo cada año).
  La variación aparece sola cuando se carga el mismo mes del año anterior.
- Los datos tienen casi un año: los meses de 2025 y 2026 esperan a que alguien los
  baje en un navegador.

## En Mapo

- `/perfil`: la tarjeta de checador ("Empleo") trae puestos, permanentes y
  eventuales, salario diario promedio, reparto por división y la parte en el rango
  del tope del municipio; la desocupación de la ENOE se queda, dicha como del estado.
- Buscador (`cuantos` y `donde_poner`): por municipio, los puestos de los grupos del
  IMSS del rubro, su parte del total del municipio y su salario diario.
- Cita: `GET /fuentes/carga?tabla=imss`.
