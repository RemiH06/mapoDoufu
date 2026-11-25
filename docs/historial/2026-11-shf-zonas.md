# Zonas metropolitanas y avalúos del SHF (sesión 23b)

La SHF no publica qué municipios forman las 8 zonas de su índice, y Mapo prefirió
preguntar por transparencia antes que suponerlo. La respuesta (oficio del 2026-11-20, recibida el 2026-11-24) trajo la
delimitación, el SUN 2018, y los avalúos por año detrás de cada serie. Detalle en
`../fuentes/shf.md`.

## Qué se hizo

- `shf_zonas.csv` y `shf_avaluos.csv` en `mapo_core`, sacadas de la respuesta con
  `scripts/shf/extraer.py`. Son fijas y chicas: se leen del paquete, sin tabla ni
  carga.
- La ficha de vivienda muestra la serie de la zona cuando el municipio no tiene la
  suya. En Jalisco la ven seis: Acatlán de Juárez, El Salto, Ixtlahuacán de los
  Membrillos, Juanacatlán, Tonalá y Zapotlanejo, que antes veían la del estado.
- La ficha dice con cuántos avalúos se calcula la serie, en qué año hubo menos y, en
  una zona, cuántos salen de municipios sin índice propio.
- **De paso:** los enlaces permanentes con la ficha abierta no la abrían. Desde la 29d
  la URL la escribe con cinco dígitos (`ficha=14039`) y al leerla solo aceptaba tres.

## Decisiones

- **La zona antes que el estado.** Es más cercana y está documentada. Pero puede decir
  poco de un municipio chico, y por eso va la cuenta de avalúos al lado, no un umbral.
- **`shf_anual` no se rellena con la zona.** Pintar Tonalá con el valor de la zona la
  haría pasar por dato propio.
- **2026 fuera de los avalúos.** Está a medias y no dice hasta qué mes.

Producción en `72fc888` el 2026-11-24 (revertir: `deploy-20261124d`; sin migración ni
carga). Comprobado ahí: Tonalá con la zona, Guadalajara con la suya y Tamazula con la del
estado.

Capturas: `scripts/capturas/shf23b.js`.
