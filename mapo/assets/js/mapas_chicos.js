import {css, bordes} from "./plano"
import {esPuntos, puntoChico, colorPoligono, opacidadPoligono} from "./peligros"
import {claseMinutos, TINTA} from "./servicios_capa"

// Mapas chicos lado a lado (/riesgos y /accesibilidad): uno por peligro o servicio,
// todos con el mismo recuadro, dibujados en lienzos 2D con lo mismo que el LiveView
// manda al plano grande ("zona" y, al mover los minutos, "estilo"). Sin mapa base:
// el contorno y los límites municipales bastan para ubicarse. Cada uno es un botón
// del servidor; aquí solo se dibuja.

const MARGEN = 6

// Grados a pixeles, con la longitud encogida a la latitud del centro.
function proyeccion([[o, s], [e, n]], ancho, alto) {
  const k = Math.cos((s + n) / 2 * Math.PI / 180)
  const escala = Math.min((ancho - 2 * MARGEN) / ((e - o) * k), (alto - 2 * MARGEN) / (n - s))
  const x0 = (ancho - (e - o) * k * escala) / 2, y0 = (alto - (n - s) * escala) / 2
  return ([lon, lat]) => [x0 + (lon - o) * k * escala, y0 + (n - lat) * escala]
}

const anillos = g => g.type === "Polygon" ? g.coordinates : g.type === "MultiPolygon" ? g.coordinates.flat() : []

function trazar(c, geometria, xy) {
  c.beginPath()
  for (const anillo of anillos(geometria)) {
    anillo.forEach((p, i) => {
      const [x, y] = xy(p)
      if (i) c.lineTo(x, y)
      else c.moveTo(x, y)
    })
    c.closePath()
  }
}

export const MapasChicos = {
  mounted() {
    this.handleEvent("zona", datos => { this.datos = datos; this._pedir() })
    this.handleEvent("estilo", ({umbral}) => { if (this.datos) { this.datos.umbral = umbral; this._pedir() } })
    // Al mostrarse (la vista cambia) o cambiar de ancho, y con el tema.
    this.tamano = new ResizeObserver(() => this._pedir())
    this.tamano.observe(this.el)
    this.tema = new MutationObserver(() => this._pedir())
    this.tema.observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]})
  },

  destroyed() {
    this.tamano.disconnect()
    this.tema.disconnect()
    cancelAnimationFrame(this.cuadro)
  },

  _pedir() {
    cancelAnimationFrame(this.cuadro)
    this.cuadro = requestAnimationFrame(() => this._dibujar())
  },

  _dibujar() {
    if (!this.datos || this.el.hidden || this.el.clientWidth === 0) return
    const caja = bordes(this.datos.zona)
    if (!caja) return
    for (const lienzo of this.el.querySelectorAll("canvas")) {
      const ancho = lienzo.parentElement.clientWidth
      if (!ancho) continue
      const alto = Math.round(ancho * 0.82), dpr = Math.min(window.devicePixelRatio || 1, 2)
      lienzo.width = ancho * dpr
      lienzo.height = alto * dpr
      lienzo.style.height = `${alto}px`
      const c = lienzo.getContext("2d")
      c.scale(dpr, dpr)
      const xy = proyeccion(caja, ancho, alto)
      if (this.el.dataset.tipo === "servicios") this._servicio(c, lienzo.dataset.clave, xy)
      else this._peligro(c, lienzo.dataset.clave, xy, false)
      c.lineJoin = "round"
      c.strokeStyle = css("--line")
      c.lineWidth = 0.6
      for (const f of this.datos.limites?.features || []) { trazar(c, f.geometry, xy); c.stroke() }
      c.strokeStyle = css("--text")
      c.lineWidth = 1.3
      trazar(c, this.datos.zona, xy)
      c.stroke()
      if (this.el.dataset.tipo !== "servicios") this._peligro(c, lienzo.dataset.clave, xy, true)
    }
  },

  // Las áreas debajo de los límites; los puntos, encima.
  _peligro(c, clave, xy, puntos) {
    const capa = this.datos.capas.find(x => x.clave === clave)
    if (!capa || esPuntos(clave) !== puntos) return
    for (const f of capa.datos.features) {
      if (puntos) {
        const [x, y] = xy(f.geometry.coordinates)
        puntoChico(c, clave, f.properties, x, y, capa.datos.features.length > 200 ? 2 : 3)
      } else {
        c.globalAlpha = opacidadPoligono(clave, f.properties)
        c.fillStyle = colorPoligono(clave, f.properties)
        trazar(c, f.geometry, xy)
        c.fill("evenodd")
        c.globalAlpha = 1
      }
    }
  },

  _servicio(c, clave, xy) {
    c.fillStyle = css("--f-movilidad")
    for (const f of this.datos.plano.features) {
      const k = claseMinutos(f.properties.m?.[clave], this.datos.umbral)
      if (k < 0) continue
      c.globalAlpha = TINTA[k]
      if (f.geometry.type === "Point") {
        const [x, y] = xy(f.geometry.coordinates)
        c.beginPath()
        c.arc(x, y, 1.5, 0, Math.PI * 2)
      } else trazar(c, f.geometry, xy)
      c.fill("evenodd")
    }
    c.globalAlpha = 1
  },
}
