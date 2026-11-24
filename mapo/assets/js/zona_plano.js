import {css, fuente, quitar, bordes, margenHoja} from "./plano"

// La zona común en el plano (sesión 29b, docs/producto/zona.md). El selector de
// zona (MapoWeb.ZonaSelector) manda dos eventos que cualquier hook atiende con
// `conZona`:
//   "zona_elegida"  el contorno de la zona recién elegida, para verla antes de
//                   que la vista calcule; la vista lo quita al pintar el suyo.
//   "dibujar_zona"  pasa el plano a modo dibujo: cada clic pone un vértice, clic
//                   en el primero o doble clic cierra, Retroceso borra el último
//                   y Esc cancela. Al cerrar, el polígono va al selector.
// Mientras se dibuja, los clics del plano no llegan a la vista (`clics` en
// plano.js mira `map._dibujandoZona`).

const MAX_VERTICES = 200
// A cuántos pixeles del primer vértice un clic lo toma como cierre.
const CIERRE_PX = 12

export function conZona(hook, cuando, {margen = margenHoja} = {}) {
  let contorno = null
  let dibujo = null

  const pintarContorno = () => {
    const map = hook.map
    quitar(map, "zsel")
    if (!contorno) return
    fuente(map, "zsel-f", contorno)
    map.addLayer({id: "zsel", type: "line", source: "zsel-f",
      paint: {"line-color": css("--text"), "line-width": 2.5, "line-dasharray": [2, 1.5]}})
  }

  hook.handleEvent("zona_elegida", cuando(({geojson}) => {
    dibujo?.cancelar()
    contorno = geojson
    pintarContorno()
    const caja = bordes(geojson)
    if (caja) hook.map.fitBounds(caja, {padding: margen(caja), maxZoom: 15})
  }))

  hook.handleEvent("dibujar_zona", cuando(({destino}) => {
    dibujo?.cancelar()
    dibujo = dibujar(hook.map, {
      alTerminar: vertices => { dibujo = null; hook.pushEventTo(destino, "poligono", {vertices}) },
      alCancelar: () => { dibujo = null; hook.pushEventTo(destino, "cancelar_dibujo", {}) },
    })
  }))

  hook.handleEvent("cancelar_dibujo_zona", cuando(() => dibujo?.cancelar(true)))

  return {
    // Para el cambio de tema: el estilo nuevo tira las capas.
    repintar: () => { if (hook.map) { pintarContorno(); dibujo?.pintar() } },
    // La vista ya pintó su propia zona: el contorno provisional sobra.
    limpiar: () => { contorno = null; if (hook.map) quitar(hook.map, "zsel") },
  }
}

function dibujar(map, {alTerminar, alCancelar}) {
  const vertices = []
  let cursor = null
  let terminado = false
  let pendiente = null
  map._dibujandoZona = true
  map.doubleClickZoom.disable()
  const lienzo = map.getCanvas()
  lienzo.style.cursor = "crosshair"
  const aviso = document.createElement("div")
  aviso.className = "aviso-dibujo"
  aviso.setAttribute("role", "status")
  map.getContainer().appendChild(aviso)

  const texto = () => {
    aviso.textContent = vertices.length < 3
      ? `Toca el plano para poner vértices (${vertices.length} de al menos 3). Esc cancela.`
      : "Toca el primer vértice o haz doble clic para cerrar. Retroceso borra el último; Esc cancela."
  }

  const pintar = () => {
    if (terminado) return
    quitar(map, "zdib")
    const linea = cursor && vertices.length ? [...vertices, cursor] : [...vertices]
    const datos = {type: "FeatureCollection", features: [
      ...(linea.length >= 2 ? [{type: "Feature", properties: {}, geometry: {type: "LineString", coordinates: linea}}] : []),
      ...(vertices.length >= 3 ? [{type: "Feature", properties: {},
        geometry: {type: "Polygon", coordinates: [[...vertices, vertices[0]]]}}] : []),
      ...vertices.map((v, i) => ({type: "Feature", properties: {primero: i === 0}, geometry: {type: "Point", coordinates: v}})),
    ]}
    fuente(map, "zdib-f", datos)
    const acento = css("--accent")
    map.addLayer({id: "zdib-relleno", type: "fill", source: "zdib-f", filter: ["==", ["geometry-type"], "Polygon"],
      paint: {"fill-color": acento, "fill-opacity": 0.12}})
    map.addLayer({id: "zdib-linea", type: "line", source: "zdib-f", filter: ["==", ["geometry-type"], "LineString"],
      paint: {"line-color": acento, "line-width": 2, "line-dasharray": [2, 2]}})
    map.addLayer({id: "zdib-vertices", type: "circle", source: "zdib-f", filter: ["==", ["geometry-type"], "Point"],
      paint: {"circle-radius": ["case", ["get", "primero"], 6, 4], "circle-color": css("--bg"),
        "circle-stroke-color": acento, "circle-stroke-width": 2}})
    texto()
  }

  const terminar = cerrar => {
    // Un cuadro de mousemove pendiente volvería a pintar el dibujo ya cerrado.
    terminado = true
    if (pendiente) cancelAnimationFrame(pendiente)
    map.off("click", alClic)
    map.off("dblclick", alDoble)
    map.off("mousemove", alMover)
    document.removeEventListener("keydown", alTecla, true)
    aviso.remove()
    quitar(map, "zdib")
    lienzo.style.cursor = ""
    // El doble clic que cierra también dispara dos clics: se suelta después.
    setTimeout(() => { map._dibujandoZona = false; map.doubleClickZoom.enable() }, 300)
    if (cerrar) alTerminar(vertices.map(([lon, lat]) => [+lon.toFixed(5), +lat.toFixed(5)]))
  }

  const cerca = (a, b) => {
    const pa = map.project(a), pb = map.project(b)
    return Math.hypot(pa.x - pb.x, pa.y - pb.y) <= CIERRE_PX
  }

  function alClic(e) {
    const v = [e.lngLat.lng, e.lngLat.lat]
    if (vertices.length >= 3 && cerca(v, vertices[0])) return terminar(true)
    if (vertices.length && cerca(v, vertices[vertices.length - 1])) return
    if (vertices.length >= MAX_VERTICES) return
    vertices.push(v)
    pintar()
  }
  function alDoble(e) {
    e.preventDefault()
    if (vertices.length >= 3) terminar(true)
  }
  function alMover(e) {
    cursor = [e.lngLat.lng, e.lngLat.lat]
    if (pendiente || !vertices.length) return
    pendiente = requestAnimationFrame(() => { pendiente = null; pintar() })
  }
  function alTecla(e) {
    if (e.key === "Escape") {
      e.stopPropagation()
      terminar(false)
      alCancelar()
    } else if (e.key === "Backspace" && !e.target.closest?.("input, textarea")) {
      e.preventDefault()
      vertices.pop()
      pintar()
    } else if (e.key === "Enter" && vertices.length >= 3 && !e.target.closest?.("input, textarea")) {
      e.preventDefault()
      terminar(true)
    }
  }

  map.on("click", alClic)
  map.on("dblclick", alDoble)
  map.on("mousemove", alMover)
  document.addEventListener("keydown", alTecla, true)
  pintar()

  return {
    pintar,
    // `silencio`: lo canceló el servidor, no hace falta avisarle.
    cancelar: (silencio = false) => { terminar(false); if (!silencio) alCancelar() },
  }
}
