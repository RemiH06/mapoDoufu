import L from "../vendor/leaflet/leaflet"

// Mapa coloreado tipo "teorema de las 4 colores": recibe un
// FeatureCollection de municipios con `properties.color_indice` ya
// calculado en mapo_core (dos municipios vecinos nunca traen el mismo
// indice). Paleta chica y fija, a diferencia del ciclo de color de
// Voronoi: aqui el numero de colores es genuinamente pequeño (casi
// siempre 4, a veces unos pocos mas), no uno distinto por elemento.

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5
const PALETA = ["#f2b632", "#4A1A6B", "#2f9e44", "#c0392b", "#2980b9", "#e67e22", "#16a085", "#8e44ad"]

function colorDe(indice) {
  if (indice === null || indice === undefined) return "#9ca3af"
  return PALETA[indice % PALETA.length]
}

export const ColoreadoMap = {
  mounted() {
    this.map = L.map(this.el).setView(CENTRO_MEXICO, ZOOM_MEXICO)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    this.capa = null

    this.handleEvent("coloreado", ({geojson}) => this.pintar(geojson))
  },

  pintar(geojson) {
    if (this.capa) {
      this.map.removeLayer(this.capa)
      this.capa = null
    }

    this.capa = L.geoJSON(geojson, {
      style: feature => ({
        color: "#3a3a3a",
        weight: 1,
        fillColor: colorDe(feature.properties.color_indice),
        fillOpacity: 0.7,
      }),
      onEachFeature: (feature, capa) => {
        capa.bindPopup(feature.properties.nomgeo || feature.properties.cvegeo)
      },
    }).addTo(this.map)

    if (this.capa.getBounds().isValid()) {
      this.map.fitBounds(this.capa.getBounds())
    }
  },

  destroyed() {
    this.map.remove()
  },
}
