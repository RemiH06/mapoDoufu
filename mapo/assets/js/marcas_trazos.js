// La geometría a mano de las marcas (marcas.js): cómo se traza cada forma, dónde
// va su nota y cuánto mide. Todo en grados, calculado en metros, así el trazo
// no se rehace al acercar el plano.

import {distancia} from "./plano"

const METROS_POR_GRADO = 111320
// Los mismos topes que valida Mapo.Sesiones.Anotacion.
const MAX_PUNTOS = 500

// Metros alrededor de un punto: ida y vuelta.
function local([lon0, lat0]) {
  const k = Math.cos(lat0 * Math.PI / 180)
  return {
    a: ([lon, lat]) => [(lon - lon0) * METROS_POR_GRADO * k, (lat - lat0) * METROS_POR_GRADO],
    de: ([x, y]) => [lon0 + x / (METROS_POR_GRADO * k), lat0 + y / METROS_POR_GRADO],
  }
}

// Un círculo como trazado con lápiz: el radio ondula suave y siempre igual
// (la semilla sale del id), y el trazo se pasa del inicio y acaba un poco
// afuera, como cuando se cierra a mano.
function trazoCirculo(centro, radio, semilla) {
  const {de} = local(centro)
  const puntos = []
  const pasos = 80, vuelta = Math.PI * 2.15
  for (let i = 0; i <= pasos; i++) {
    const t = i / pasos
    const a = semilla + t * vuelta
    const r = radio * (1 + 0.035 * Math.sin(2 * a + semilla) + 0.02 * Math.sin(3 * a + 2 * semilla) + 0.06 * t * t)
    puntos.push(de([Math.cos(a) * r, Math.sin(a) * r]))
  }
  return puntos
}

// Un lado a pulso: se comba apenas hacia un lado. `combo` es la panza, en
// fracción del largo.
function ladoAPulso([x1, y1], [x2, y2], combo, pasos = 10) {
  const nx = -(y2 - y1), ny = x2 - x1
  return Array.from({length: pasos + 1}, (_, i) => {
    const t = i / pasos, b = combo * 4 * t * (1 - t)
    return [x1 + (x2 - x1) * t + nx * b, y1 + (y2 - y1) * t + ny * b]
  })
}

// El asta se comba y la punta son dos rayas aparte, del quinto de su largo.
function trazosFlecha([cola, punta], semilla) {
  const {a, de} = local(cola)
  const p = a(punta)
  const asta = ladoAPulso([0, 0], p, semilla % 2 ? 0.06 : -0.06, 24)
  const [px, py] = asta[asta.length - 3]
  const rumbo = Math.atan2(p[1] - py, p[0] - px)
  const largo = Math.hypot(...p) * 0.2
  const pluma = giro => [p[0] - Math.cos(rumbo + giro) * largo, p[1] - Math.sin(rumbo + giro) * largo]
  return [asta, [pluma(0.5), p, pluma(-0.45)]].map(linea => linea.map(de))
}

function trazoPoligono(vertices, semilla) {
  const {a, de} = local(vertices[0])
  const v = vertices.map(a)
  const puntos = v.flatMap((p, i) =>
    ladoAPulso(p, v[(i + 1) % v.length], 0.012 * Math.sin(semilla + i * 2.4)))
  // El último lado se pasa un poco del primer vértice.
  const [ux, uy] = v[v.length - 1]
  puntos.push([-ux * 0.05, -uy * 0.05])
  return puntos.map(de)
}

// Esquinas redondeadas (Chaikin): de cerca, el trazo simplificado no se ve
// como línea quebrada.
function suavizar(puntos, vueltas = 2) {
  for (let v = 0; v < vueltas && puntos.length > 2; v++) {
    const s = [puntos[0]]
    for (let i = 0; i < puntos.length - 1; i++) {
      const [x1, y1] = puntos[i], [x2, y2] = puntos[i + 1]
      s.push([x1 * 0.75 + x2 * 0.25, y1 * 0.75 + y2 * 0.25], [x1 * 0.25 + x2 * 0.75, y1 * 0.25 + y2 * 0.75])
    }
    s.push(puntos[puntos.length - 1])
    puntos = s
  }
  return puntos
}

// Las líneas que dibujan una marca (el punto no lleva: es del DOM).
export function trazos(a) {
  const semilla = (a.id ?? 0) % 7
  switch (a.forma) {
    case "circulo": return [trazoCirculo([a.lon, a.lat], a.radio_m, semilla)]
    case "flecha": return trazosFlecha(a.coords, semilla)
    case "trazo": return [suavizar(a.coords)]
    case "poligono": return [trazoPoligono(a.coords, semilla)]
    default: return []
  }
}

const masAlEste = coords => coords.reduce((m, c) => c[0] > m[0] ? c : m)

function orilla(a, rumbo) {
  return local([a.lon, a.lat]).de([Math.cos(rumbo) * a.radio_m, Math.sin(rumbo) * a.radio_m])
}

// Dónde va la nota y de qué lado: en la orilla derecha de la forma, o detrás de
// la cola de la flecha, para no taparla.
export function ancla(a) {
  switch (a.forma) {
    case "circulo": return {lugar: orilla(a, 0), lado: "left"}
    case "flecha": return {lugar: a.coords[0], lado: a.coords[1][0] >= a.coords[0][0] ? "right" : "left"}
    default: return {lugar: masAlEste(a.coords), lado: "left"}
  }
}

// Los puntos que tiene que incluir un encuadre.
export function extremos(a) {
  if (a.coords) return a.coords
  if (a.forma !== "circulo") return [[a.lon, a.lat]]
  return [0, 1, 2, 3].map(i => orilla(a, i * Math.PI / 2))
}

const numero = (v, decimales) => v.toLocaleString("es-MX", {maximumFractionDigits: decimales})

function enMetros(m) {
  return m < 1000 ? `${numero(m, 0)} m` : `${numero(m / 1000, 1)} km`
}

function enArea(m2) {
  if (m2 < 10000) return `${numero(m2, 0)} m²`
  return m2 < 1e6 ? `${numero(m2 / 1e4, 1)} ha` : `${numero(m2 / 1e6, 1)} km²`
}

function cruza([p, q], [r, s]) {
  const giro = (a, b, c) => Math.sign((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
  return giro(p, q, r) * giro(p, q, s) < 0 && giro(r, s, p) * giro(r, s, q) < 0
}

// Metros cuadrados de un polígono, o `null` si se cruza consigo mismo (un "8"
// no tiene un área que decir).
export function area(vertices) {
  const {a} = local(vertices[0])
  const v = vertices.map(a)
  const lados = v.map((p, i) => [p, v[(i + 1) % v.length]])
  if (lados.some((l, i) => lados.slice(i + 1).some(m => cruza(l, m)))) return null
  return Math.abs(lados.reduce((s, [[x1, y1], [x2, y2]]) => s + x1 * y2 - x2 * y1, 0)) / 2
}

// Lo que mide, para la ficha.
export function medida(a) {
  switch (a.forma) {
    case "circulo": return `radio ${enMetros(a.radio_m)}`
    case "poligono": {
      const m2 = area(a.coords)
      return m2 == null ? "se cruza, sin área" : enArea(m2)
    }
    case "flecha":
    case "trazo":
      return enMetros(a.coords.slice(1).reduce((s, c, i) => s + distancia(a.coords[i], c), 0))
    default: return ""
  }
}

// Douglas-Peucker sobre los pixeles del trazo: `puntos` son {x, y, lugar}.
// La tolerancia sube hasta que cabe en el tope que acepta el servidor.
export function simplificar(puntos) {
  for (let tolerancia = 1.2; ; tolerancia *= 1.6) {
    const s = douglasPeucker(puntos, tolerancia)
    if (s.length <= MAX_PUNTOS) return s.map(p => p.lugar)
  }
}

function douglasPeucker(p, tolerancia) {
  if (p.length < 3) return p
  const a = p[0], b = p[p.length - 1]
  const largo = Math.hypot(b.x - a.x, b.y - a.y)
  let lejos = 0, cual = 0
  for (let i = 1; i < p.length - 1; i++) {
    // Un trazo cerrado empieza y acaba en el mismo lugar: cuenta la distancia a él.
    const d = largo
      ? Math.abs((b.x - a.x) * (a.y - p[i].y) - (a.x - p[i].x) * (b.y - a.y)) / largo
      : Math.hypot(p[i].x - a.x, p[i].y - a.y)
    if (d > lejos) { lejos = d; cual = i }
  }
  if (lejos <= tolerancia) return [a, b]
  return [...douglasPeucker(p.slice(0, cual + 1), tolerancia).slice(0, -1), ...douglasPeucker(p.slice(cual), tolerancia)]
}
