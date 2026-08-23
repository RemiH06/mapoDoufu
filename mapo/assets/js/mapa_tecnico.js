import L from "../vendor/leaflet/leaflet"

// Mapa tecnico: varias capas independientes (coropleta, Voronoi,
// coloreado, isocrona) sobre el mismo mapa base, cada una se prende y
// apaga por separado desde el servidor via push_event. El contenedor
// tiene phx-update="ignore", asi que todo el estado de que capa esta
// prendida vive aqui del lado del cliente, nunca en atributos
// re-renderizados por LiveView.

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5
const ESCALA_COROPLETA = ["#f0e6f7", "#c9a8dd", "#a06bc0", "#7239a0", "#4A1A6B"]
const COLOR_SIN_DATO = "#9ca3af"
const ANGULO_DORADO = 137.508
const PALETA_COLOREADO = ["#f2b632", "#4A1A6B", "#2f9e44", "#c0392b", "#2980b9", "#e67e22", "#16a085", "#8e44ad"]

function colorCoropleta(valor, min, max) {
  if (valor === null || valor === undefined) return COLOR_SIN_DATO
  if (max === min) return ESCALA_COROPLETA[ESCALA_COROPLETA.length - 1]
  const t = (valor - min) / (max - min)
  return ESCALA_COROPLETA[Math.min(ESCALA_COROPLETA.length - 1, Math.floor(t * ESCALA_COROPLETA.length))]
}

function colorVoronoi(indice) {
  return `hsl(${(indice * ANGULO_DORADO) % 360}, 65%, 55%)`
}

function colorColoreado(indice) {
  if (indice === null || indice === undefined) return COLOR_SIN_DATO
  return PALETA_COLOREADO[indice % PALETA_COLOREADO.length]
}

export const MapaTecnico = {
  mounted() {
    this.map = L.map(this.el).setView(CENTRO_MEXICO, ZOOM_MEXICO)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    this.capas = {coropleta: null, voronoi: null, coloreado: null, isocrona: null}
    this.leyendaCoropleta = null
    this.modoIsocrona = false
    this.marcadorIsocrona = null

    this.map.on("click", e => {
      if (this.modoIsocrona) {
        this.pushEvent("click_mapa", {lat: e.latlng.lat, lon: e.latlng.lng})
      }
    })

    this.handleEvent("capa_coropleta", ({activa, geojson, etiqueta}) => this._coropleta(activa, geojson, etiqueta))
    this.handleEvent("capa_voronoi", ({activa, geojson}) => this._voronoi(activa, geojson))
    this.handleEvent("capa_coloreado", ({activa, geojson}) => this._coloreado(activa, geojson))
    this.handleEvent("capa_isocrona", ({activa, poligono, metodo}) => this._isocrona(activa, poligono, metodo))
    this.handleEvent("modo_isocrona", ({activo}) => {
      this.modoIsocrona = activo
      this.el.style.cursor = activo ? "crosshair" : ""
    })
  },

  _quitar(nombre) {
    if (this.capas[nombre]) {
      this.map.removeLayer(this.capas[nombre])
      this.capas[nombre] = null
    }
  },

  _coropleta(activa, geojson, etiqueta) {
    this._quitar("coropleta")
    if (this.leyendaCoropleta) {
      this.map.removeControl(this.leyendaCoropleta)
      this.leyendaCoropleta = null
    }
    if (!activa || !geojson) return

    const valores = geojson.features.map(f => f.properties.valor_choropleth).filter(v => v !== null && v !== undefined)
    const min = valores.length ? Math.min(...valores) : 0
    const max = valores.length ? Math.max(...valores) : 0

    this.capas.coropleta = L.geoJSON(geojson, {
      style: f => ({color: "#3a3a3a", weight: 1, fillColor: colorCoropleta(f.properties.valor_choropleth, min, max), fillOpacity: 0.6}),
      onEachFeature: (f, capa) => {
        const valor = f.properties.valor_choropleth
        capa.bindPopup(`<strong>${etiqueta}</strong><br>${valor === null || valor === undefined ? "sin dato" : valor}`)
      },
    }).addTo(this.map)

    if (this.capas.coropleta.getBounds().isValid()) this.map.fitBounds(this.capas.coropleta.getBounds())
  },

  _voronoi(activa, geojson) {
    this._quitar("voronoi")
    if (!activa || !geojson) return

    const colorDe = new Map()
    geojson.features.forEach((f, i) => colorDe.set(f.properties.id, colorVoronoi(i)))

    this.capas.voronoi = L.geoJSON(geojson, {
      style: f => ({color: "#3a3a3a", weight: 1, fillColor: colorDe.get(f.properties.id), fillOpacity: 0.4}),
      onEachFeature: (f, capa) => capa.bindPopup(f.properties.nombre || `Negocio ${f.properties.id}`),
    }).addTo(this.map)

    if (this.capas.voronoi.getBounds().isValid()) this.map.fitBounds(this.capas.voronoi.getBounds())
  },

  _coloreado(activa, geojson) {
    this._quitar("coloreado")
    if (!activa || !geojson) return

    this.capas.coloreado = L.geoJSON(geojson, {
      style: f => ({color: "#3a3a3a", weight: 1, fillColor: colorColoreado(f.properties.color_indice), fillOpacity: 0.55}),
      onEachFeature: (f, capa) => capa.bindPopup(f.properties.nomgeo || f.properties.cvegeo),
    }).addTo(this.map)

    if (this.capas.coloreado.getBounds().isValid()) this.map.fitBounds(this.capas.coloreado.getBounds())
  },

  _isocrona(activa, poligono, metodo) {
    this._quitar("isocrona")
    if (this.marcadorIsocrona) {
      this.map.removeLayer(this.marcadorIsocrona)
      this.marcadorIsocrona = null
    }
    if (!activa || !poligono) return

    this.capas.isocrona = L.geoJSON(
      {type: "Feature", properties: {}, geometry: poligono},
      {style: {color: "#4A1A6B", weight: 2, fillColor: "#4A1A6B", fillOpacity: 0.25}}
    ).addTo(this.map)
    this.capas.isocrona.bindPopup(metodo === "osrm_real" ? "Carretera real" : "Círculo aproximado")

    if (this.capas.isocrona.getBounds().isValid()) this.map.fitBounds(this.capas.isocrona.getBounds())
  },

  destroyed() {
    this.map.remove()
  },
}
