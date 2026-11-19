import L from "../vendor/leaflet/leaflet"
import {entintar} from "./plano_tinta"

// Plano de /riesgos. El LiveView decide la zona y manda lo que hay que dibujar:
// "previa" (el círculo antes de consultar) y "zona" (el contorno y una capa por
// peligro con puntos). Un clic en el plano propone el centro de un círculo.
// Cada capa se prende y apaga sola en el control de capas: nunca se suman.

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5

const raiz = document.documentElement
const css = nombre => getComputedStyle(raiz).getPropertyValue(nombre).trim()

const SEMAFORO = {ROJO: "--r-rojo", AMARILLO: "--r-amarillo", VERDE: "--r-verde"}
const COLOR_CAPA = {
  descargas: "--f-urbanismo",
  retc: "--f-seguridad",
  fuego: "--f-movilidad",
}

const escapar = t =>
  String(t ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c])

function color(clave, props) {
  if (clave.startsWith("agua_")) return css(SEMAFORO[props.semaforo] || "--text2")
  return css(COLOR_CAPA[clave] || "--text")
}

function ficha(clave, p) {
  const filas = []
  if (clave.startsWith("agua_")) {
    filas.push(`<b>${escapar(p.nombre || p.clave)}</b>`, escapar(p.cuerpo), `Semáforo: ${escapar(p.semaforo || "sin")}`)
    if (p.incumple?.length) filas.push(`Incumple: ${p.incumple.map(escapar).join(", ")}`)
  } else if (clave === "descargas") {
    filas.push(`<b>Descarga con permiso</b>`, `Uso: ${escapar(p.uso)}`,
      `${escapar(Math.round(p.volumen_anual || 0).toLocaleString("es-MX"))} m³ al año`,
      `Recibe: ${escapar(p.cuerpo_receptor)}`)
  } else if (clave === "retc") {
    filas.push(`<b>${escapar(p.actividad || "Establecimiento")}</b>`, `Último reporte: ${escapar(p.anio)}`)
  } else if (clave === "fuego") {
    filas.push(`<b>Foco de calor</b>`, escapar(p.fecha), `Confianza: ${escapar(p.confianza)}`)
  }
  return filas.filter(Boolean).join("<br>")
}

export const RiesgosMapa = {
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

    this.control = L.control.layers(null, null, {position: "topright", collapsed: false})
    this.capas = []
    this.previo = null
    this.contorno = null

    this.map.on("click", e => this.pushEvent("punto", {lat: e.latlng.lat, lon: e.latlng.lng}))

    this.handleEvent("previa", ({lat, lon, radio_m}) => {
      this.previo?.remove()
      this.previo = L.circle([lat, lon], {radius: radio_m, color: css("--accent"), weight: 2, dashArray: "6 6", fill: false})
        .addTo(this.map)
    })

    this.handleEvent("zona", ({zona, capas}) => this._dibujar(zona, capas))
  },

  _dibujar(zona, capas) {
    this.previo?.remove()
    this.previo = null
    this.contorno?.remove()
    for (const c of this.capas) {
      this.control.removeLayer(c)
      c.remove()
    }
    this.capas = []

    this.contorno = L.geoJSON(zona, {style: {color: css("--text"), weight: 2.5, fill: false}}).addTo(this.map)
    for (const {clave, titulo, datos} of capas) {
      const capa = L.geoJSON(datos, {
        pointToLayer: (f, latlng) => L.circleMarker(latlng, {
          radius: clave === "fuego" ? 4 : 7,
          color: css("--bg"),
          weight: 1.5,
          fillColor: color(clave, f.properties),
          fillOpacity: 0.9,
        }),
        onEachFeature: (f, l) => l.bindPopup(ficha(clave, f.properties)),
      }).addTo(this.map)
      this.control.addOverlay(capa, `${escapar(titulo)} (${datos.features.length})`)
      this.capas.push(capa)
    }
    if (this.capas.length) this.control.addTo(this.map)
    else this.control.remove()
    const ancho = window.innerWidth > 760
    this.map.fitBounds(this.contorno.getBounds(), {paddingTopLeft: [ancho ? 460 : 20, 40], paddingBottomRight: [40, ancho ? 40 : 260]})
  },
}
