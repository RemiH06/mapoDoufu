# Mapa base (Protomaps recortado a México)

El plano de todas las vistas desde la sesión 29a. No es una fuente de
datos que Mapo analice: es el fondo sobre el que se pintan los acetatos.

## De dónde sale

- **Mosaicos:** la build diaria de [Protomaps](https://docs.protomaps.com/basemaps/downloads),
  un solo archivo PMTiles con todo el planeta (~140 GB) armado con
  Planetiler desde OpenStreetMap. Mapo baja solo los pedazos que caen
  dentro de México con 10 km de margen (`scripts/plano/mexico.geojson`)
  con `pmtiles extract`, que lee el archivo remoto por rangos.
- **Estilo:** `@protomaps/basemaps` 5.7.2 arma las capas en el navegador
  con los sabores `white` (claro) y `black` (oscuro), etiquetas en
  español (`lang: "es"`).
- **Letras e íconos:** los de [basemaps-assets](https://github.com/protomaps/basemaps-assets),
  copiados a `mapo/priv/static/plano/`. Solo los rangos de glifos que usa
  el español y las lenguas de México en alfabeto latino (0 a 1023, latín
  extendido adicional, puntuación, símbolos de letras y el saltillo
  `ꞌ`, U+A78C): 2.2 MB en vez de 60.
- **Frontera:** `mapo/priv/static/plano/frontera.geojson` es el mundo menos
  México (contorno de `entidades`, el marco geoestadístico de INEGI,
  simplificado a 0.01°): el velo que tapa lo que no es México.

## Licencias

| Pieza | Licencia | Qué pide |
|---|---|---|
| Datos del mapa (OSM) | ODbL | Atribución "© colaboradores de OpenStreetMap" visible: va en el control de créditos de cada plano |
| Mosaicos de Protomaps | ODbL (derivan de OSM) | La misma atribución; Protomaps se cita junto |
| Letras Noto Sans | SIL OFL 1.1 | Copia de la licencia junto a las letras (`fonts/OFL.txt`) |
| Íconos (sprites) | MIT (de tangrams/icons) | Aviso en el mismo `LICENCIAS.md` |
| MapLibre GL JS 6.19.0 | BSD-3 | Aviso en `assets/vendor/maplibre/LICENSE.txt` |
| pmtiles 4.5.0, @protomaps/basemaps 5.7.2 | BSD-3 (el diseño de los estilos, CC0) | Aviso en `assets/vendor/maplibre/LICENCIAS.md` |
| fflate 0.8.3 (lo usa pmtiles) | MIT | Aviso en el mismo `LICENCIAS.md` |

El mapa exportado (sesión 29l) también tiene que llevar la atribución de OSM.

## Cómo se carga

```bash
scripts/plano/extraer.sh ~/srv/mapo-plano            # build más nueva
scripts/plano/extraer.sh ~/srv/mapo-plano 20261122   # fecha fija
```

Baja ~1.3 GB de red y deja `mexico.pmtiles` (~1.2 GB) y `BUILD` (la
fecha) en la carpeta. Escribe primero un `.parcial` y lo renombra al
final: Mapo nunca sirve un archivo a medias. En Linux x86_64 baja solo el
CLI `pmtiles` (go-pmtiles 1.31.2) a `~/.local/bin`; en Windows hay que
bajarlo a mano de sus releases.

La carpeta se monta de lectura en `/plano` del contenedor `mapo`
(`MAPO_PLANO_DATOS`; en dev, `./plano` por omisión, gitignorada) y
Phoenix la sirve en `/mosaicos/mexico.pmtiles` con `Plug.Static`, que ya
atiende `Range`: el navegador pide pedazos de unos KB. Sin el archivo,
`/mosaicos/...` da 404 y el plano sale vacío, pero las capas encima
funcionan.

Refrescar no es urgente: el mapa base no es un dato que se analice. Una
vez al año, o si alguien reporta una calle o colonia nueva que no sale.

## Cifras de la extracción del 2026-11-22

| Recorte | Tamaño |
|---|---|
| Recuadro de México (-118.6, 14.3, -86.5, 32.8), zoom 0 a 15 | 2.7 GB |
| Contorno de México con 10 km de margen, zoom 0 a 15 (el que se usa) | 1.2 GB (2,294,530 mosaicos) |
| Contorno, hasta zoom 12 | 282 MB (sin calles menores de cerca) |
| Recuadro de Jalisco, zoom 0 a 15 | 144 MB |

Build de Protomaps `20261122` (Planetiler 0.10.2, esquema 4).
`curl -r 0-126` contra `/mosaicos/mexico.pmtiles` responde `206` con 127
bytes; un archivo que no está en la lista (`/mosaicos/otro.pmtiles`), 404.

## Problemas conocidos

- **De lejos se ven los vecinos.** Un mosaico de zoom bajo cubre medio
  continente: el recorte por contorno no lo parte. Lo resuelve el velo
  de `frontera.geojson`, no el recorte.
- **Lenguas con otros alfabetos.** Un nombre con glifos fuera de los
  rangos copiados sale sin esas letras (MapLibre avisa en consola). Si
  pasa, se copia el rango que falte de basemaps-assets.
- **Cloudflare no lo guarda en caché.** Medido el 2026-11-22: los pedazos
  responden `cf-cache-status: DYNAMIC` y tardan ~0.45 s desde fuera (el
  túnel hasta Pixilate y de regreso); cada uno llega hasta Phoenix, que lo
  lee del disco. La extensión `.pmtiles` no está en las que Cloudflare
  guarda por omisión, y el plan gratuito no guarda archivos de más de
  512 MB. Si el plano se siente lento, la salida es servir mosaicos
  sueltos (`/z/x/y.mvt`, unos KB cada uno) con una regla de caché, no
  partir el PMTiles.
