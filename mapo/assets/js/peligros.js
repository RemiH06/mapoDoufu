import {css, escapar, fuente, oscuro} from "./plano"

// Los peligros en el plano (/riesgos y el acetato "Riesgos" de /mapa): cada uno
// con su figura, su color y su ícono, siempre los mismos (docs/producto/vista-riesgos.md).
// De lejos, la figura sola; de cerca, la figura con su ícono. La figura basta
// para distinguirlos sin color: círculo, agua; cuadro, descarga; rombo,
// establecimiento; triángulo, foco. El agua en verde es un círculo hueco.

const ZOOM_ICONO = 12

// Íconos, tintas y colores vienen del servidor (MapoWeb.Cotejo.plano_json): son
// los mismos de la hoja y de la cinta.
let ICONOS = {}, TINTAS = {}, COLORES = {}
export function cargarPeligros(el) {
  if (el.dataset.peligros) ({iconos: ICONOS, tintas: TINTAS, colores: COLORES} = JSON.parse(el.dataset.peligros))
}

export const FIGURA = {agua_superficial: "circulo", agua_subterranea: "circulo", descargas: "cuadro", retc: "rombo", fuego: "triangulo"}
const SEMAFORO = {ROJO: "--r-rojo", AMARILLO: "--r-amarillo", VERDE: "--r-verde"}

export const esPuntos = clave => clave in FIGURA

// El tono de un punto: el semáforo en el agua, su tinta en los demás.
const tonos = clave => clave.startsWith("agua_") ? [...Object.keys(SEMAFORO), "SIN"] : ["U"]
const tonoDe = (clave, p) => clave.startsWith("agua_") ? (p.semaforo in SEMAFORO ? p.semaforo : "SIN") : "U"
const colorDe = (clave, tono) => css(clave.startsWith("agua_") ? SEMAFORO[tono] || "--text2" : TINTAS[clave])

export function trazarFigura(c, figura, x, y, r) {
  c.beginPath()
  if (figura === "circulo") c.arc(x, y, r, 0, Math.PI * 2)
  else if (figura === "cuadro") c.rect(x - r * 0.88, y - r * 0.88, r * 1.76, r * 1.76)
  else if (figura === "rombo") {
    c.moveTo(x, y - r * 1.18); c.lineTo(x + r * 1.18, y); c.lineTo(x, y + r * 1.18); c.lineTo(x - r * 1.18, y); c.closePath()
  } else {
    c.moveTo(x, y - r * 1.15); c.lineTo(x + r * 1.12, y + r * 0.85); c.lineTo(x - r * 1.12, y + r * 0.85); c.closePath()
  }
}

// Una figura con su color y su borde; con `trazos`, su ícono adentro.
function imagen(clave, tono, r, trazos) {
  const escala = 2, lado = Math.ceil(r * 2.6 + 4)
  const lienzo = document.createElement("canvas")
  lienzo.width = lienzo.height = lado * escala
  const c = lienzo.getContext("2d")
  c.scale(escala, escala)
  const color = colorDe(clave, tono), m = lado / 2, hueco = tono === "VERDE"
  trazarFigura(c, FIGURA[clave], m, m, r)
  // Halo del color del fondo, para que se vea encima de calles y de otro punto.
  c.lineWidth = hueco ? 5 : 3
  c.strokeStyle = css("--bg")
  c.stroke()
  c.fillStyle = hueco ? css("--bg") : color
  c.fill()
  if (hueco) {
    c.lineWidth = 2
    c.strokeStyle = color
    c.stroke()
  }
  if (trazos) {
    // El ícono cabe en la figura; en el triángulo, un poco más abajo.
    const ancho = r * (FIGURA[clave] === "triangulo" ? 1.05 : FIGURA[clave] === "rombo" ? 1.15 : 1.25)
    c.translate(m - ancho / 2, m - ancho / 2 + (FIGURA[clave] === "triangulo" ? r * 0.18 : 0))
    c.scale(ancho / 15, ancho / 15)
    c.fillStyle = hueco ? color : css("--bg")
    for (const d of trazos) c.fill(new Path2D(d))
  }
  return c.getImageData(0, 0, lienzo.width, lienzo.height)
}

// Las imágenes se vuelven a hacer con el tema: cambiar el estilo las tira.
function ponerImagenes(map, clave) {
  for (const tono of tonos(clave)) {
    for (const [sufijo, r, trazos] of [["s", 5, null], ["g", 11, ICONOS[clave]]]) {
      const id = `peligro-${clave}-${tono}-${sufijo}`
      if (map.hasImage(id)) map.removeImage(id)
      map.addImage(id, imagen(clave, tono, r, trazos), {pixelRatio: 2})
    }
  }
}

// Pone una capa con el prefijo `p` y regresa el id de la que toma clics.
export function pintarPeligro(map, p, {clave, datos}, visible = true) {
  const id = `${p}${clave}`, layout = {visibility: visible ? "visible" : "none"}
  if (esPuntos(clave)) {
    ponerImagenes(map, clave)
    fuente(map, `${id}-f`, {type: "FeatureCollection", features: datos.features.map((f, i) => ({
      type: "Feature", geometry: f.geometry, properties: {_i: i, t: tonoDe(clave, f.properties)}}))})
    const base = ["concat", `peligro-${clave}-`, ["get", "t"]]
    map.addLayer({id, type: "symbol", source: `${id}-f`, layout: {
      ...layout,
      "icon-image": ["step", ["zoom"], ["concat", base, "-s"], ZOOM_ICONO, ["concat", base, "-g"]],
      // Los focos son muchos: de lejos, más chicos.
      "icon-size": clave === "fuego" ? ["interpolate", ["linear"], ["zoom"], 8, 0.55, ZOOM_ICONO, 1] : 1,
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      "symbol-z-order": "source",
    }})
    return id
  }
  fuente(map, `${id}-f`, {type: "FeatureCollection", features: datos.features.map((f, i) => ({
    type: "Feature", geometry: f.geometry, properties: {_i: i, c: colorPoligono(clave, f.properties), o: opacidadPoligono(clave, f.properties)}}))})
  map.addLayer({id, type: "fill", source: `${id}-f`, layout, paint: {"fill-color": ["get", "c"], "fill-opacity": ["get", "o"]}})
  map.addLayer({id: `${id}-borde`, type: "line", source: `${id}-f`, layout,
    paint: {"line-color": clave === "sequia" ? css("--text2") : ["get", "c"], "line-width": 1.2}})
  return id
}

export const colorPoligono = (clave, p) =>
  clave === "acuifero" ? css(p.disponibilidad > 0 ? "--p-agua-con" : "--p-agua-sin")
    : clave === "sequia" ? css(`--msm-${String(p.categoria).toLowerCase()}`)
      : css("--p-anp")

export const opacidadPoligono = (clave, p) =>
  clave === "sequia" ? (p.categoria === "sin" ? 0.15 : oscuro() ? 0.85 : 0.7) : clave === "anp" ? 0.3 : 0.28

// El punto en un mapa chico.
export function puntoChico(c, clave, p, x, y, r) {
  const tono = tonoDe(clave, p)
  trazarFigura(c, FIGURA[clave], x, y, r)
  c.fillStyle = colorDe(clave, tono)
  if (tono === "VERDE") {
    c.lineWidth = 1.2
    c.strokeStyle = c.fillStyle
    c.stroke()
  } else c.fill()
}

const cifra = n => Math.round(n || 0).toLocaleString("es-MX")

export function textoPeligro(clave, p) {
  const filas = []
  if (clave.startsWith("agua_")) {
    filas.push(`<b>${escapar(p.nombre || p.clave)}</b>`, escapar(p.cuerpo),
      `Semáforo: ${escapar((p.semaforo || "sin").toLowerCase())}`)
    if (p.incumple?.length) filas.push(`Incumple: ${p.incumple.map(escapar).join(", ")}`)
  } else if (clave === "descargas") {
    filas.push(`<b>Descarga con permiso</b>`, `Uso: ${escapar(p.uso)}`, `${cifra(p.volumen_anual)} m³ al año`,
      `Recibe: ${escapar(p.cuerpo_receptor)}`)
  } else if (clave === "retc") {
    filas.push(`<b>${escapar(p.actividad || "Establecimiento")}</b>`, `Último reporte: ${escapar(p.anio)}`)
  } else if (clave === "fuego") {
    filas.push(`<b>Foco de calor</b>`, escapar(p.fecha), `Confianza: ${escapar(p.confianza)}`,
      p.fija ? "Fuente fija, según FIRMS" : "")
  } else if (clave === "acuifero") {
    filas.push(`<b>Acuífero ${escapar(p.nombre)}</b>`,
      p.disponibilidad > 0 ? "Con agua disponible" : "Sin agua disponible",
      `${Number(p.disponibilidad).toLocaleString("es-MX", {maximumFractionDigits: 1})} hm³ al año`)
  } else if (clave === "sequia") {
    filas.push(`<b>${escapar(p.nombre)}</b>`, `${escapar(p.texto)}${p.categoria === "sin" ? "" : ` (${escapar(p.categoria)})`}`,
      `Corte del ${escapar(p.fecha)}`)
  } else if (clave === "anp") {
    filas.push(`<b>${escapar(p.nombre)}</b>`, escapar(p.categoria))
  }
  return filas.filter(Boolean).join("<br>")
}

// El ícono de un peligro o servicio, para las leyendas del plano.
export const iconoHtml = (clave, color = "currentColor") =>
  `<svg class="icono-tema" viewBox="0 0 15 15" width="16" height="16" fill="currentColor" style="color:${color}" aria-hidden="true">${
    (ICONOS[clave] || []).map(d => `<path d="${d}"/>`).join("")}</svg>`

export const tintaDe = clave => `var(${TINTAS[clave] || "--text2"})`

// Qué dice cada color de los peligros a la vista, sin repetir: [variable, texto, hueco].
export function coloresDe(claves) {
  const todos = claves.flatMap(c => COLORES[c] || [])
  return todos.filter(([v, t], i) => todos.findIndex(([w, u]) => v === w && t === u) === i)
}
