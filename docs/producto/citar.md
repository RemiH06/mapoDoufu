# Cómo citar y enlaces permanentes

Mapo quiere ser una referencia que se pueda citar. Cada capa ya trae fuente,
fecha y método en pantalla; esto agrega dos cosas: una URL que reconstruye lo
que se está viendo y un texto de cita listo para copiar. Hecho en la sesión 24
(`docs/historial/2026-11-citar.md`).

## Reglas

- **La fuente original va primero.** El autor de la cita es quien produjo el
  dato (INEGI, SEDATU, SHF, IIEG, Conagua...). Mapo aparece solo como "Procesado
  por Mapo", con lo que se vio y la versión de la tabla.
- **Nada inventado.** Si no se comprobó el año de publicación, va "s. f.";
  si no hay una liga estable de la fuente, se omite. El periodo de los datos va
  aparte ("Datos de 2025, segmento Media").
- **Lo de un equipo nunca va en el enlace de la cita.** "Tus datos" no tiene
  botón de cita. La sesión de marcas sigue en la barra de direcciones (ya iba,
  y la revisa el scope), pero el enlace permanente de la cita no la lleva.
- **Nada de la URL llega al SQL sin pasar por su catálogo.** Un valor fuera de
  catálogo se ignora sin error y la URL se corrige a lo que de verdad se ve.

## Qué guarda la URL

### `/mapa`

| Parámetro | Qué es | Se valida contra |
|---|---|---|
| `ent`, `mun` | Estado y municipio | La lista de estados y la de municipios del estado |
| `censo` | Indicador del acetato "Censo por AGEB" | `MapoCore.indicadores_censo/0` |
| `viv`, `anio`, `seg` | Indicador de vivienda, año y segmento del SNIIV | El catálogo de `/vivienda/catalogo` |
| `ficha` | Municipio con la ficha de vivienda abierta | Tres dígitos; mapo_core responde 404 si no existe |
| `negocios` | "Área por negocio" puesto, con su giro (vacío: todos) | Texto de hasta 60 caracteres; mapo_core lo pasa por la tabla de rubros o como parámetro |
| `municipios=1` | Acetato "Municipios" puesto | Solo `1` |
| `alcance` | Isócrona: `lat,lon,minutos` | Lat 14 a 33.5, lon −119 a −85, de 1 a 120 minutos |
| `ver` | Cinta abierta | Los acetatos de la pantalla, menos "Tus datos" |
| `piel` | Piel fijada | Las siete pieles |
| `sesion`, `capa` | Del equipo (ya existían) | El scope; no van en la cita |

El año del SNIIV se escribe aunque se haya pedido "último completo": el enlace
dice 2025 y sigue diciendo 2025 cuando salga 2026. La URL se reescribe con cada
cambio (`push_patch` con `replace`, sin llenar el historial) y se lee una sola
vez, al conectar. El orden de las capas en la pila no se guarda.

### `/riesgos`

`modo=municipio&ent=&mun=&cerca=` o `modo=circulo&lat=&lon=&radio=&cerca=`.
Se escribe al terminar una consulta. Al abrirlo se consulta igual que con el
botón, con el mismo límite de 30 por hora; un municipio que no está en la lista
del estado, un radio fuera de 0.1 a 25 km o una cercanía que no es de la lista
dejan la hoja vacía.

`/perfil` y `/buscador` ya guardaban su estado en la URL (`cve_ent`, `cve_mun`
y `q`); todavía no tienen botón de cita.

## El texto de la cita

Botón "Cómo citar" en la cinta de cada acetato público puesto y en cada bloque
de `/riesgos`. La cita se arma al tocarlo, así que la fecha de consulta y el
enlace son los de ese momento. Trae dos formatos con su botón de copiar:

```text
INEGI. (2021). Censo de Población y Vivienda 2020: principales resultados por AGEB
y manzana urbana [Conjunto de datos]. https://www.inegi.org.mx/programas/ccpv/2020/
Datos de 2020. Procesado por Mapo: Población total por AGEB, Jalisco; tabla cargada
en Mapo el 2026-08-28. Consultado el 21 de noviembre de 2026 en
https://mapo.remlam.dev/mapa?ent=14&censo=pobtot&ver=coropleta
```

```bibtex
@misc{inegi_censo2020_mapo_20261121,
  author = {{Instituto Nacional de Estadística y Geografía}},
  title = {{Censo de Población y Vivienda 2020: principales resultados por AGEB y manzana urbana}},
  year = {2021},
  note = {Datos de 2020. Procesado por Mapo: ... Fuente original: https://...},
  url = {https://mapo.remlam.dev/mapa?ent=14&censo=pobtot&ver=coropleta},
  urldate = {2026-11-21}
}
```

En el BibTeX se escapan `\ { } & % $ # _ ^ ~` del texto (un giro escrito puede
traer cualquier cosa); el `url` va tal cual, como lo lee biblatex.

La ficha de vivienda de un municipio junta cuatro fuentes: su cita trae una
referencia por cada una (SHF, SNIIV, Intercensal y ENVI) además del indicador
puesto.

## Versión de lo citado

- **Precio de oferta por AGEB:** la versión de la tabla del estudio (`v2`,
  columna `version` de `fuente_precio_estimado`), que mapo_core manda en el
  `meta` de `/vivienda/municipios`.
- **Lo demás:** la fecha de la última carga de la tabla en Mapo, por estado si
  la tabla es por estado. La da `GET /fuentes/carga?tabla=&cve_ent=` de
  mapo_core (`max(actualizado)`, en UTC), con un catálogo cerrado de tablas:
  `censo`, `denue`, `municipios`, `eic2025`, `sniiv`, `shf`, `envi`, `precio`.
  DENUE cambia cada semestre con el mismo nombre: su cita dice "edición vigente
  en INEGI al cargarla en Mapo el ...".
- **`/riesgos`:** el periodo que trae cada bloque (`fecha_dato`), que ya dice de
  qué corte es cada fuente.

## Catálogo de referencias

En `mapo/lib/mapo_web/cita.ex`. Una entrada por fuente con autor corto (para el
texto), autor largo (para BibTeX), año comprobado o `nil`, título y liga.

| Clave | Autor | Año | Liga |
|---|---|---|---|
| `censo` | INEGI | 2021 | Programa del Censo 2020 |
| `marco` | INEGI | s. f. | Servicio `wscatgeo/v2` |
| `denue` | INEGI | s. f. | Descarga masiva |
| `eic2025` | INEGI | 2026 | Zip de datos abiertos |
| `envi` | INEGI | s. f. | Zip de datos abiertos |
| `sniiv` | SEDATU | s. f. | Datos abiertos del SNIIV |
| `shf` | Sociedad Hipotecaria Federal | s. f. | API del SNIIV |
| `iieg` | IIEG | 2024 | Página del sector inmobiliario |
| `osm` | Colaboradores de OpenStreetMap | s. f. | Página de derechos (ODbL) |
| `renameca`, `repda`, `acuiferos` | Conagua | s. f.; 2023 los acuíferos (DOF) | sin liga |
| `retc` | SEMARNAT | s. f. | sin liga |
| `firms` | NASA FIRMS | s. f. | Sitio de FIRMS |
| `sequia` | SMN, Conagua | s. f. | Monitor de Sequía |
| `anp`, `uso_suelo` | CONANP, INEGI (copias de CONABIO) | s. f. | Geoportal de CONABIO |
| `siap` | SIAP, SADER | s. f. | Cierre agrícola |
| `defunciones` | INEGI | s. f. | Programa EDR |

Las ligas "sin liga" son de crudos bajados a mano (`docs/fuentes/`): ponerlas
cuando se confirme la página estable de cada una.

## Límites

- **El enlace pide cuenta.** Todas las pantallas con datos piden iniciar
  sesión; quien abre una cita sin cuenta pasa por el inicio de sesión y vuelve a
  la vista. Abrir `/mapa` sin cuenta es otra decisión (costo y abuso).
- **Reconstruye la vista, no los datos de ese día.** Si una tabla se recarga, el
  enlace muestra la versión nueva; la cita dice qué versión se consultó.
- **Sin página `/metodo/<indicador>`.** El método va en la cinta y en
  `docs/`; hacerla si alguien necesita enlazar el método largo.
