import L from "../vendor/leaflet/leaflet"
import {entintar} from "./plano_tinta"

// Mapa tecnico: cada capa (coropleta, Voronoi, coloreado, isocrona) es un
// acetato sobre el plano. El servidor las prende y apaga por push_event y
// dice el orden de la pila y la piel de la mesa; aqui se pintan con la
// pelicula de su enfoque y el mapa base se reentinta con la piel activa
// (docs/arquitectura/decisiones.md, "Concepto visual"). El contenedor tiene
// phx-update="ignore": lo dibujado vive aqui, nunca en el DOM de LiveView.
//
// Canvas en vez de SVG: una coropleta de estado son ~5 mil poligonos y en
// SVG arrastrar el mapa baja a 30 o 40 fps. Cada acetato tiene su propio
// canvas, para que se mezcle con el plano (mix-blend-mode) por separado.

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5
const ENFOQUE = {coropleta: "demografia", voronoi: "comercio", coloreado: "urbanismo", isocrona: "movilidad"}
// Opacidad de la pelicula por clase: mas valor, mas tinta.
const TINTA_QUINTIL = [0.12, 0.26, 0.42, 0.6, 0.8]
const TINTA_COLOREADO = [0.14, 0.32, 0.5, 0.68]
const ZOOM_PUNTOS = 14

const raiz = document.documentElement
const tinta = nombre => getComputedStyle(raiz).getPropertyValue(nombre).trim()
const oscuro = () => raiz.dataset.theme === "dark"

function clase(valor, cortes) {
  if (valor === null || valor === undefined) return -1
  return cortes.filter(c => valor > c).length
}

export const MapaTecnico = {
  mounted() {
    entintar()
    this.map = L.map(this.el, {zoomControl: false}).setView(CENTRO_MEXICO, ZOOM_MEXICO)
    L.control.zoom({position: "topright"}).addTo(this.map)
    L.control.scale({imperial: false, position: "bottomleft"}).addTo(this.map)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    this.renderers = {}
    Object.keys(ENFOQUE).forEach((id, i) => {
      const pane = this.map.createPane(`p-${id}`)
      pane.classList.add("acetato")
      pane.style.zIndex = 460 - i
      this.renderers[id] = L.canvas({pane: `p-${id}`})
    })
    this.capas = {coropleta: null, voronoi: null, coloreado: null, isocrona: null}
    this.datos = {coropleta: null, voronoi: null, coloreado: null, isocrona: null}
    this.modoIsocrona = false
    this.origen = null

    this.map.on("click", e => {
      if (this.modoIsocrona) {
        this.origen = e.latlng
        this.pushEvent("click_mapa", {lat: e.latlng.lat, lon: e.latlng.lng})
      }
    })
    this.map.on("zoomend", () => this._puntosVoronoi())

    this.handleEvent("capa_coropleta", datos => this._recibir("coropleta", datos))
    this.handleEvent("capa_voronoi", datos => this._recibir("voronoi", datos))
    this.handleEvent("capa_coloreado", datos => this._recibir("coloreado", datos))
    this.handleEvent("capa_isocrona", datos => this._recibir("isocrona", datos))
    this.handleEvent("modo_isocrona", ({activo}) => {
      this.modoIsocrona = activo
      this.el.style.cursor = activo ? "crosshair" : ""
    })
    this.handleEvent("orden_capas", ({orden}) => {
      orden.forEach((id, i) => { this.map.getPane(`p-${id}`).style.zIndex = 460 - i })
    })
    this.handleEvent("piel", ({piel}) => {
      raiz.dataset.piel = piel
      this._repintar()
    })
    this.alCambiarTema = () => this._repintar()
    window.addEventListener("mapo:tema", this.alCambiarTema)
  },

  _recibir(id, datos) {
    const nueva = !this.datos[id] && datos.activa
    this.datos[id] = datos.activa ? datos : null
    this._dibujar(id)
    if (nueva) this._deslizar(id)
    const capa = this.capas[id]
    const bordes = capa && capa.getBounds && capa.getBounds()
    if (bordes && bordes.isValid()) this.map.fitBounds(bordes)
  },

  // El acetato entra deslizandose sobre el plano.
  _deslizar(id) {
    const pane = this.map.getPane(`p-${id}`)
    pane.classList.remove("entra")
    void pane.offsetWidth
    pane.classList.add("entra")
  },

  _repintar() {
    entintar()
    Object.keys(this.datos).forEach(id => this._dibujar(id))
  },

  _quitar(id) {
    if (this.capas[id]) {
      this.map.removeLayer(this.capas[id])
      this.capas[id] = null
    }
    if (id === "voronoi" && this.puntos) {
      this.map.removeLayer(this.puntos)
      this.puntos = null
    }
  },

  _dibujar(id) {
    this._quitar(id)
    const datos = this.datos[id]
    if (!datos) return
    const color = tinta(`--f-${ENFOQUE[id]}`)
    const opciones = {pane: `p-${id}`, renderer: this.renderers[id]}
    this.capas[id] = this[`_${id}`](datos, color, opciones)
    this.capas[id].addTo(this.map)
    if (id === "voronoi") this._puntosVoronoi()
  },

  _coropleta({geojson, etiqueta, cortes}, color, opciones) {
    const factor = oscuro() ? 0.85 : 1
    return L.geoJSON(geojson, {
      ...opciones,
      style: f => {
        const k = clase(f.properties.valor_choropleth, cortes || [])
        return k < 0
          ? {color: tinta("--line"), weight: 0.6, dashArray: "3 3", fillOpacity: 0}
          : {color, weight: 0.5, opacity: 0.6, fillColor: color, fillOpacity: TINTA_QUINTIL[k] * factor}
      },
      onEachFeature: (f, capa) => {
        const valor = f.properties.valor_choropleth
        capa.bindPopup(`<strong>${etiqueta}</strong><br>${valor === null || valor === undefined ? "sin dato" : valor.toLocaleString("es-MX")}`)
      },
    })
  },

  _voronoi({geojson}, color, opciones) {
    this.datosPuntos = geojson.features
    return L.geoJSON(geojson, {
      ...opciones,
      style: {color, weight: 0.8, opacity: 0.9, fill: true, fillOpacity: 0},
      onEachFeature: (f, capa) => {
        const nombre = f.properties.nombre || `Negocio ${f.properties.id}`
        const otros = f.properties.num_puntos - 1
        capa.bindPopup(otros > 0 ? `${nombre}<br>y ${otros} más en el mismo punto` : nombre)
      },
    })
  },

  // De lejos solo las celdas: miles de puntos a escala de ciudad son una mancha.
  _puntosVoronoi() {
    const ver = this.capas.voronoi && this.map.getZoom() >= ZOOM_PUNTOS
    if (!ver) {
      if (this.puntos) { this.map.removeLayer(this.puntos); this.puntos = null }
      return
    }
    if (this.puntos) return
    const color = tinta("--f-comercio")
    this.puntos = L.layerGroup(this.datosPuntos
      .filter(f => f.properties.lat !== undefined)
      .map(f => L.circleMarker([f.properties.lat, f.properties.lon], {
        pane: "p-voronoi", renderer: this.renderers.voronoi, radius: 2.2, stroke: false, fillColor: color, fillOpacity: 1,
      }))).addTo(this.map)
  },

  _coloreado({geojson}, color, opciones) {
    return L.geoJSON(geojson, {
      ...opciones,
      style: f => ({
        color, weight: 0.8, opacity: 0.7, fillColor: color,
        fillOpacity: TINTA_COLOREADO[(f.properties.color_indice ?? 0) % TINTA_COLOREADO.length],
      }),
      onEachFeature: (f, capa) => capa.bindPopup(f.properties.nomgeo || f.properties.cvegeo),
    })
  },

  _isocrona({poligono, metodo}, color, opciones) {
    const area = L.geoJSON({type: "Feature", properties: {}, geometry: poligono}, {
      ...opciones,
      style: {color, weight: 2, dashArray: "6 4", fillColor: color, fillOpacity: 0.2},
    }).bindPopup(metodo === "osrm_real" ? "Por carretera real" : "Círculo aproximado: OSRM no respondió")
    const partes = [area]
    if (this.origen) {
      [4, 9, 14].forEach(r => partes.push(L.circleMarker(this.origen, {...opciones, radius: r, color, weight: 1.3, fill: false})))
    }
    const grupo = L.featureGroup(partes)
    return grupo
  },

  destroyed() {
    window.removeEventListener("mapo:tema", this.alCambiarTema)
    raiz.dataset.piel = "urbanismo"
    this.map.remove()
  },
}
