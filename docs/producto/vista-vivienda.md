# Vista de vivienda

Acetato "Vivienda" en `/mapa`. Pinta los municipios de un estado con un indicador
de **una sola fuente** y, al tocar un municipio, abre su ficha con las cuatro
fuentes de vivienda por separado. Un indicador, el valor de suelo, va por AGEB
(ver abajo). Es la primera vista temática del plan
(`plan-nacional.md`, "Vistas temáticas"), hecha como acetato y no como pantalla
aparte: así se cruza con el censo, el DENUE o los datos del equipo en la misma mesa.

## Por qué no hay "precio de la zona"

Ninguna de las fuentes cargadas da el precio de una vivienda en un lugar
(`../historial/2026-11-fuentes-vivienda.md`):

| Fuente | Qué es | Nivel |
|---|---|---|
| Índice SHF (`../fuentes/shf.md`) | Cambio de precio, 2018 = 100; no dice cuánto cuesta | 74 municipios del país (4 en Jalisco), 8 zonas metropolitanas, estados |
| SNIIV (`../fuentes/sniiv.md`) | Lo prestado o subsidiado, por segmento de valor | Municipio, anual |
| Intercensal 2025 (`../fuentes/eic2025.md`) | Tenencia y escrituras, por muestra, con su CV | Municipio |
| ENVI 2020 (`../fuentes/envi.md`) | Renta y valor estimado declarados | Estado |

Juntarlas en un número sería un puntaje (RNF5). Por eso el acetato pinta un
indicador a la vez y siempre dice su fuente, su unidad, su nivel y su método.

## Indicadores del acetato

| Clave | Indicador | Método que se muestra |
|---|---|---|
| `eic_alqui`, `eic_propia`, `eic_prest` | Viviendas rentadas, propias, prestadas (% de las habitadas) | Estimación por muestra; cada valor con su CV; `MI` queda sin dato |
| `eic_noescri`, `eic_propresi` | Propias sin escrituras, o escrituradas a nombre de quien vive ahí (% de las propias) | Igual |
| `sniiv_acciones` | Créditos y subsidios del año | Suma de todos los organismos y destinos; año y segmento elegibles; si el año está incompleto, dice cuántos meses trae |
| `sniiv_promedio` | Monto promedio por acción, en miles de pesos | Monto entre las acciones que traen monto, mismo filtro. Muchos mejoramientos llegan con monto 0: contarlos bajaba el promedio de un segmento de Tlaquepaque a $40 |
| `shf_anual` | Cambio del índice SHF en un año | Último trimestre contra el mismo un año antes; solo donde SHF publica |
| `suelo_ageb` | Valor de suelo por AGEB, $/m² del año de la tabla | Catastro donde la AGEB tiene etiquetas; rango conformal donde no (`precio-estimado.md`) |

Sin año, el SNIIV toma el último año completo (12 meses). Un municipio sin
registro en el SNIIV ese año queda sin dato, no en cero: el SNIIV no distingue
"nadie pidió crédito" de "no se reportó".

Los colores son quintiles de los municipios con dato; los que no tienen van
punteados y se cuentan aparte en la escala.

## Valor de suelo por AGEB

Sale de la tabla `fuente_precio_estimado` (`precio-estimado.md`), una fila por AGEB
urbana del dataset de vivienda:

- **Catastro:** la mediana de las etiquetas de la tabla de valores dentro de la
  AGEB, con el año de la tabla y cuántas etiquetas son.
- **Estimado:** un rango ("de $2,000 a $4,500/m²") y, al lado, en cuántas AGEB no
  vistas de ese municipio el catastro cayó dentro. Va sin color y con borde
  punteado: fuera de Guadalajara el alto llega a ser 20 veces el bajo, y pintar su
  punto medio lo haría pasar por dato. La escala cuenta estas AGEB como "sin dato"
  porque no tienen color, no porque no tengan rango.
- **Sin dato:** el municipio no tiene tabla de valores ubicada. No se rellena con
  vecinas ni con otro municipio.

Cada municipio está en pesos del año de su tabla (Guadalajara 2020; Zapopan,
Tonalá e Ixtlahuacán 2026); el método lo dice y pide no comparar colores entre
años distintos. Al tocar una AGEB se abre su ventana; la ficha del municipio no,
porque agranda la cinta y la tapaba.

## Ficha del municipio

- **SHF:** la serie del municipio si SHF la publica; si no, la del estado, y lo
  dice ("Del estado: SHF no lo publica para este municipio"). Último índice,
  cambio en un año y la serie trimestral como línea, con la base 2018 = 100
  punteada; cada trimestre trae su valor al pasar el cursor y la tabla completa
  va plegada en "Ver la serie". La zona metropolitana no se usa: ver Pendiente.
- **SNIIV:** último año completo, acciones y monto promedio por segmento (solo con
  las acciones que traen monto), y los cuatro destinos con más acciones.
- **Intercensal 2025:** viviendas habitadas, tenencia y escrituras, cada valor con
  su CV; `MI` como "sin dato (MI)".
- **ENVI 2020:** del estado, con su error estándar cuando la ENVI lo permite (las
  medianas no lo traen).

## Dónde vive

- `mapo_core/src/mapo_core/vivienda_vista.py`: catálogo, coropleta y ficha. El
  navegador solo manda claves de una lista cerrada; nada se interpola en el SQL.
- `GET /vivienda/catalogo`, `GET /vivienda/municipios?cve_ent&indicador[&anio&segmento]`,
  `GET /vivienda/ficha?cve_ent&cve_mun`.
- `mapo/lib/mapo_web/live/mapa_live/index.ex`: acetato `vivienda`, cinta y ficha.
  El catálogo se pide la primera vez que se abre la cinta.
- `mapo/assets/js/mapa_tecnico.js`: `_vivienda`; el clic manda `ficha_vivienda`.
  `valorSuelo` arma la ventana de una AGEB.
- `mapo_core/src/mapo_core/precio_estimado.py`: cargador de la tabla por AGEB
  (`python -m mapo_core.cli precio_estimado --archivo ...`).

## Pendiente

- Serie de la zona metropolitana cuando el municipio no tiene la suya. SHF no
  publica qué municipios forman cada una de sus 8 zonas: su nota metodológica
  (4 páginas, 2026) solo dice "zonas metropolitanas". La página de precios del
  SNIIV dice que la delimitación es la del Sistema Urbano Nacional 2018, pero su
  catálogo municipal solo está en PDF y no se pudo bajar. Usarlo sería suponer
  que el SNIIV describe bien al SHF. Decisión (2026-11-19): preguntarle a SHF por
  transparencia y no suponer la delimitación mientras tanto. Lo que se pregunta,
  en `../fuentes/shf.md`, "Zonas metropolitanas: pregunta a la SHF".
- Rezago habitacional municipal del SNIIV, si hace falta (`steps.md`, sesión 20).
- Escala de mercado del valor de suelo: ver `precio-estimado.md`, Pendiente.
