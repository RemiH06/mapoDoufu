import L from "../vendor/leaflet/leaflet"
import {entintar} from "./plano_tinta"

// Plano de /accesibilidad. El LiveView manda "zona" (el contorno del municipio,
// sus AGEB y localidades con los minutos a cada servicio, y los destinos) y
// "estilo" (qué servicio pintar y con qué umbral). Más lejos, más tinta; sin
// dato, solo el borde punteado. Un solo servicio a la vez: nunca se suman.

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5
// Clases por fracción del umbral: hasta la mitad, hasta el umbral, hasta el
// doble y más del doble.
const CORTES = [0.5, 1, 2]
const TINTA = [0.06, 0.2, 0.5, 0.78]

const raiz = document.documentElement
const css = nombre => getComputedStyle(raiz).getPropertyValue(nombre).trim()

const escapar = t =>
  String(t ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c])

const cifra = n => (n ?? 0).toLocaleString("es-MX")

function clase(minutos, umbral) {
  if (minutos === null || minutos === undefined) return -1
  return CORTES.filter(c => minutos > c * umbral).length
}

function leyenda(umbral) {
  const mitad = (umbral / 2).toLocaleString("es-MX")
  return [
    `${mitad} min o menos`,
    `${mitad} a ${umbral} min`,
    `${umbral} a ${umbral * 2} min`,
    `más de ${umbral * 2} min`,
  ]
}

export const AccesibilidadMapa = {
  mounted() {
    raiz.dataset.piel = "laboral"
    entintar()
    this.map = L.map(this.el, {zoomControl: false}).setView(CENTRO_MEXICO, ZOOM_MEXICO)
    L.control.zoom({position: "topright"}).addTo(this.map)
    L.control.scale({imperial: false, position: "bottomright"}).addTo(this.map)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    this.leyenda = L.control({position: "bottomleft"})
    this.leyenda.onAdd = () => {
      this.cajaLeyenda = L.DomUtil.create("div", "leyenda-acc")
      return this.cajaLeyenda
    }

    this.handleEvent("zona", datos => this._dibujar(datos))
    this.handleEvent("estilo", ({servicio, umbral}) => {
      this.servicio = servicio
      this.umbral = umbral
      this._pintar()
    })
  },

  _dibujar({zona, plano, destinos, titulos, servicio, umbral}) {
    this.contorno?.remove()
    this.lugares?.remove()
    this.capaDestinos?.remove()
    this.titulos = titulos
    this.destinos = destinos
    this.servicio = servicio
    this.umbral = umbral

    this.contorno = L.geoJSON(zona, {style: {color: css("--text"), weight: 2.5, fill: false}, interactive: false})
      .addTo(this.map)
    this.lugares = L.geoJSON(plano, {
      pointToLayer: (_f, latlng) => L.circleMarker(latlng, {radius: 5}),
      onEachFeature: (f, capa) => capa.bindPopup(() => this._ficha(f.properties)),
    }).addTo(this.map)
    this.leyenda.addTo(this.map)
    this._pintar()

    this.map.fitBounds(this.contorno.getBounds(), this._margen())
  },

  // El municipio se encuadra en lo que la hoja deja libre: a la izquierda en
  // escritorio, a la derecha con el celular acostado y abajo con el celular parado.
  _margen() {
    const hoja = document.getElementById("hoja")?.getBoundingClientRect()
    const ancho = window.innerWidth
    if (!hoja || hoja.width === 0) return {padding: [30, 30]}
    if (hoja.width > ancho * 0.6) return {paddingTopLeft: [20, 40], paddingBottomRight: [20, 260]}
    if (hoja.left < ancho / 2) return {paddingTopLeft: [hoja.right + 20, 40], paddingBottomRight: [40, 40]}
    return {paddingTopLeft: [20, 40], paddingBottomRight: [ancho - hoja.left + 20, 20]}
  },

  _pintar() {
    if (!this.lugares) return
    const tinta = css("--f-movilidad")
    const linea = css("--line")
    this.lugares.setStyle(f => {
      const k = clase(f.properties.m?.[this.servicio], this.umbral)
      const punto = f.geometry.type === "Point"
      if (k < 0) return {color: linea, weight: punto ? 1 : 0.6, dashArray: "3 3", fillOpacity: 0}
      return {color: tinta, weight: punto ? 1.2 : 0.5, opacity: punto ? 0.9 : 0.6, fillColor: tinta, fillOpacity: TINTA[k]}
    })

    this.capaDestinos?.remove()
    const puntos = {...this.destinos, features: this.destinos.features.filter(f => f.properties.s === this.servicio)}
    this.capaDestinos = L.geoJSON(puntos, {
      pointToLayer: (_f, latlng) => L.circleMarker(latlng, {
        radius: 4.5, color: css("--bg"), weight: 1.5, fillColor: css("--text"), fillOpacity: 1,
      }),
      onEachFeature: (f, capa) => capa.bindPopup(`<b>${escapar(f.properties.n || "Sin nombre")}</b>`),
    }).addTo(this.map)

    if (this.cajaLeyenda) {
      const titulo = this.titulos?.[this.servicio] || ""
      const filas = leyenda(this.umbral).map((t, i) =>
        `<li><span class="muestra" style="background:${tinta};opacity:${Math.max(TINTA[i], 0.25)}"></span>${escapar(t)}</li>`)
      filas.push(`<li><span class="muestra vacia"></span>sin dato</li>`, `<li><span class="muestra punto"></span>${escapar(titulo)}</li>`)
      this.cajaLeyenda.innerHTML = `<p>Minutos a: ${escapar(titulo)}</p><ul>${filas.join("")}</ul>`
    }
  },

  _ficha(p) {
    const m = p.m?.[this.servicio]
    const tipo = p.t === "ageb" ? `AGEB ${escapar(p.c.slice(-4))}` : `Localidad ${escapar(p.c)}`
    const minutos = m === null || m === undefined ? "sin dato" : `${cifra(Math.round(m))} min`
    return `<b>${tipo}</b><br>${cifra(p.p)} personas<br>${escapar(this.titulos?.[this.servicio] || "")}: ${minutos}`
  },
}
