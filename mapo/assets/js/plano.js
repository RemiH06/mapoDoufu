// El plano de todas las vistas: MapLibre GL sobre el mapa base vectorial de
// Protomaps recortado a México (docs/fuentes/plano.md), servido por Mapo
// mismo: ni mosaicos ni letras de terceros. Aquí vive lo que antes repetía
// cada hook de Leaflet: límites de México, controles en español, mapa base
// claro u oscuro según el tema, y utilidades para capas GeoJSON y fichas.
//
// MapLibre pesa 1.1 MB: se baja solo en las páginas con mapa (import
// dinámico), y su worker sale de /plano para que la CSP siga en 'self'.

let cargando = null

export function cargar() {
  cargando ??= Promise.all([
    import("../vendor/maplibre/maplibre-gl.mjs"),
    import("../vendor/maplibre/pmtiles.js"),
    import("../vendor/maplibre/basemaps.js"),
    fetch("/plano/frontera.geojson").then(r => r.json()),
  ]).then(([ml, pm, base, frontera]) => {
    ml.setWorkerUrl(`${location.origin}/plano/maplibre-gl-worker.mjs`)
    ml.addProtocol("pmtiles", new pm.Protocol().tile)
    return {ml, base, frontera}
  })
  return cargando
}

const raiz = document.documentElement
export const css = nombre => getComputedStyle(raiz).getPropertyValue(nombre).trim()
export const oscuro = () => raiz.dataset.theme === "dark"

export const escapar = t => String(t ?? "").replace(/[&<>"']/g, c =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c])

export const MEXICO = [[-118.4, 14.5], [-86.7, 32.7]]
// Un poco más que México: se puede ver la frontera, no irse a otro país.
const LIMITES = [[-124, 11.5], [-82, 35]]

const ATRIBUCION =
  '<a href="https://protomaps.com" target="_blank" rel="noopener">Protomaps</a> · ' +
  '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">colaboradores de OpenStreetMap</a>'

const TEXTOS = {
  "NavigationControl.ZoomIn": "Acercar",
  "NavigationControl.ZoomOut": "Alejar",
  "NavigationControl.ResetBearing": "Norte arriba",
  "AttributionControl.ToggleAttribution": "Créditos del mapa",
  "AttributionControl.MapFeedback": "Corregir el mapa",
  "ScrollZoomBlocker.CtrlMessage": "Usa Ctrl + rueda para acercar",
  "ScrollZoomBlocker.CmdMessage": "Usa ⌘ + rueda para acercar",
  "TouchPanBlocker.Message": "Usa dos dedos para mover el mapa",
  "Map.Title": "Mapa",
  "Popup.Close": "Cerrar",
}

// Mapa base neutro, blanco o negro: el color es de los datos encima. Lo que
// no es México queda bajo un velo del color del fondo: de lejos los mosaicos
// traen el país vecino entero, y Mapo no tiene datos de allá.
function estilo({base, frontera}) {
  const sabor = oscuro() ? "black" : "white"
  const colores = base.namedFlavor(sabor)
  return {
    version: 8,
    glyphs: `${location.origin}/plano/fonts/{fontstack}/{range}.pbf`,
    sprite: `${location.origin}/plano/sprites/${sabor}`,
    sources: {
      protomaps: {
        type: "vector",
        url: `pmtiles://${location.origin}/mosaicos/mexico.pmtiles`,
        attribution: ATRIBUCION,
      },
      velo: {type: "geojson", data: frontera},
    },
    layers: [
      ...base.layers("protomaps", colores, {lang: "es"}),
      {id: "velo", type: "fill", source: "velo", paint: {"fill-color": colores.background, "fill-opacity": 0.78}},
    ],
  }
}

// Crea el plano en `el` y resuelve cuando ya se le pueden poner capas.
// `alTema` corre cuando el estilo nuevo (claro u oscuro) ya cargó: el cambio
// recarga el estilo entero y tira las capas del hook, que las vuelve a poner
// con las tintas nuevas desde los datos que guardó. Llevarse las capas al
// estilo nuevo (transformStyle) tronaba el render de MapLibre a medio cambio.
// `margen` da el relleno para encuadrar México al abrir (lo que tapa la hoja).
export async function crearPlano(el, {escala = "bottom-right", alTema, margen = () => 20} = {}) {
  const recursos = await cargar()
  const {ml} = recursos
  const map = new ml.Map({
    container: el,
    style: estilo(recursos),
    bounds: MEXICO,
    fitBoundsOptions: {padding: margen()},
    minZoom: 3,
    maxZoom: 19,
    maxBounds: LIMITES,
    renderWorldCopies: false,
    dragRotate: false,
    pitchWithRotate: false,
    touchPitch: false,
    attributionControl: {compact: true},
    locale: TEXTOS,
  })
  map.touchZoomRotate.disableRotation()
  map.keyboard.disableRotation()
  map.addControl(new ml.NavigationControl({showCompass: false}), "top-right")
  if (escala) map.addControl(new ml.ScaleControl({unit: "metric"}), escala)

  // El tema cambia con el botón, con otra pestaña o con el sistema: se
  // observa el atributo, no un evento.
  // Con `diff` MapLibre conserva la fuente de mosaicos (no los vuelve a
  // pedir) y solo cambia colores; las capas del hook salen del estilo nuevo
  // y `alTema` las vuelve a poner cuando el plano queda quieto: ni antes
  // (el cambio de estilo las borraba) ni a medio cambio (tronaba el render).
  const observador = new MutationObserver(() => {
    map.setStyle(estilo(recursos))
    if (alTema) map.once("idle", () => alTema())
  })
  observador.observe(raiz, {attributes: true, attributeFilter: ["data-theme"]})
  map.on("remove", () => observador.disconnect())

  if (!map.loaded()) await new Promise(r => map.once("load", r))
  // Los scripts de capturas (scripts/capturas/) ubican puntos con él.
  el.planoMapo = map
  return {map, ml}
}

// Los hooks registran sus eventos de inmediato (LiveView no espera a un
// mounted asíncrono) y los atienden cuando el plano ya cargó.
export function alListo(hook, promesa) {
  return f => (...args) => promesa.then(() => { if (!hook.cerrado) f(...args) })
}

// ---------------------------------------------------------------- capas

const VACIO = {type: "FeatureCollection", features: []}

// Pone (o reemplaza) los datos de una fuente GeoJSON.
export function fuente(map, id, datos = VACIO) {
  const f = map.getSource(id)
  if (f) f.setData(datos)
  else map.addSource(id, {type: "geojson", data: datos})
}

// Quita las capas y las fuentes cuyo id empieza con `prefijo`.
export function quitar(map, prefijo) {
  const estilo = map.getStyle()
  for (const l of estilo.layers) if (l.id.startsWith(prefijo)) map.removeLayer(l.id)
  for (const f of Object.keys(estilo.sources)) if (f.startsWith(prefijo)) map.removeSource(f)
}

// Copia de un GeoJSON con propiedades mínimas para MapLibre: el índice del
// original (`_i`, para armar la ficha con todo) más lo que pida `extra`.
// MapLibre convierte los objetos anidados en texto y copia todo al worker.
export function indexar(geojson, extra = () => ({})) {
  return {
    type: "FeatureCollection",
    features: geojson.features.map((f, i) => ({type: "Feature", geometry: f.geometry, properties: {_i: i, ...extra(f.properties || {}, f)}})),
  }
}

// Recuadro [[oeste, sur], [este, norte]] de un GeoJSON, o null si está vacío.
export function bordes(...geojsons) {
  let o = Infinity, s = Infinity, e = -Infinity, n = -Infinity
  const ver = c => {
    if (typeof c[0] === "number") {
      o = Math.min(o, c[0]); e = Math.max(e, c[0]); s = Math.min(s, c[1]); n = Math.max(n, c[1])
    } else c.forEach(ver)
  }
  const recorrer = g => {
    if (!g) return
    if (g.type === "FeatureCollection") g.features.forEach(recorrer)
    else if (g.type === "Feature") recorrer(g.geometry)
    else if (g.type === "GeometryCollection") g.geometries.forEach(recorrer)
    else if (g.coordinates) ver(g.coordinates)
  }
  geojsons.forEach(recorrer)
  return o === Infinity ? null : [[o, s], [e, n]]
}

export const recuadroDePuntos = puntos => bordes({type: "MultiPoint", coordinates: puntos})

// Relleno de encuadre al estilo de Leaflet ([x, y] arriba a la izquierda y
// abajo a la derecha) para fitBounds de MapLibre.
export const relleno = ([izq, arriba], [der, abajo]) => ({top: arriba, left: izq, right: der, bottom: abajo})

// Metros entre dos puntos [lon, lat] (haversine).
export function distancia([lon1, lat1], [lon2, lat2]) {
  const r = Math.PI / 180
  const a = Math.sin((lat2 - lat1) * r / 2) ** 2 +
    Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin((lon2 - lon1) * r / 2) ** 2
  return 2 * 6371008.8 * Math.asin(Math.sqrt(a))
}

const METROS_POR_GRADO = 111320

// Polígono de un círculo de `radio` metros (para previas y radios).
export function circulo([lon, lat], radio, pasos = 72) {
  const k = Math.cos(lat * Math.PI / 180)
  const anillo = Array.from({length: pasos + 1}, (_, i) => {
    const a = (i / pasos) * Math.PI * 2
    return [lon + Math.cos(a) * radio / (METROS_POR_GRADO * k), lat + Math.sin(a) * radio / METROS_POR_GRADO]
  })
  return {type: "Feature", properties: {}, geometry: {type: "Polygon", coordinates: [anillo]}}
}

// Ficha (popup) única del plano: abrir una cierra la anterior.
export function ficha(map, ml, lugar, contenido, opciones = {}) {
  map._fichaMapo?.remove()
  const popup = new ml.Popup({maxWidth: "320px", focusAfterOpen: false, ...opciones}).setLngLat(lugar)
  if (typeof contenido === "string") popup.setHTML(contenido)
  else popup.setDOMContent(contenido)
  map._fichaMapo = popup.addTo(map)
  return popup
}

// Un solo clic por plano: si cae sobre una capa con ficha, gana la de más
// arriba (como en Leaflet); si no, es un clic en el plano vacío (`vacio`).
// Mientras se dibuja (`activo()` falso) las capas no toman clics: todo va a
// `vacio`, para poner la marca o el origen encima de una coropleta.
export function clics(map, {vacio, activo = () => true, cursor = () => ""} = {}) {
  const manejadores = new Map()
  const vivas = () => [...manejadores.keys()].filter(id => map.getLayer(id))
  const encima = punto => {
    const ids = vivas()
    return activo() && ids.length ? map.queryRenderedFeatures(punto, {layers: ids})[0] : null
  }
  map.on("click", e => {
    // Las marcas (DOM) y las fichas tienen sus propios clics.
    if (e.originalEvent.target.closest?.(".maplibregl-marker, .maplibregl-popup")) return
    const f = encima(e.point)
    if (f) manejadores.get(f.layer.id)(f, e.lngLat, e)
    else vacio?.(e.lngLat, e)
  })
  let pendiente = null
  map.on("mousemove", e => {
    if (pendiente) return
    pendiente = requestAnimationFrame(() => {
      pendiente = null
      map.getCanvas().style.cursor = encima(e.point) ? "pointer" : cursor()
    })
  })
  return {
    en: (id, f) => manejadores.set(id, f),
    fuera: prefijo => [...manejadores.keys()].forEach(id => { if (id.startsWith(prefijo)) manejadores.delete(id) }),
    cursor: () => { map.getCanvas().style.cursor = cursor() },
  }
}

// Relleno para encuadrar en lo que deja libre la hoja (#hoja): a la derecha
// de ella en escritorio, a su izquierda con el celular acostado y arriba de
// ella con el celular parado.
export function margenHoja() {
  const hoja = document.getElementById("hoja")?.getBoundingClientRect()
  const ancho = window.innerWidth
  if (!hoja || hoja.width === 0) return 30
  if (hoja.width > ancho * 0.6) return relleno([20, 40], [20, 260])
  if (hoja.left < ancho / 2) return relleno([hoja.right + 20, 40], [40, 40])
  return relleno([20, 40], [ancho - hoja.left + 20, 20])
}
