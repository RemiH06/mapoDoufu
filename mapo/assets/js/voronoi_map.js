import L from "../vendor/leaflet/leaflet"

// Mapa de Voronoi: recibe un FeatureCollection de poligonos (una
// celda por negocio de DENUE, ya recortada al municipio) con
// `properties.{id, nombre, lat, lon}`. Cada celda se pinta de un
// color distinto (ciclo por angulo dorado, se ve bien sin importar
// cuantos negocios haya) y se marca el punto real del negocio encima
// de su propia celda, para no confundir "el area de influencia" con
// "donde esta el negocio".

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5
const ANGULO_DORADO = 137.508

function colorPorIndice(indice) {
  const tono = (indice * ANGULO_DORADO) % 360
  return `hsl(${tono}, 65%, 55%)`
}

export const VoronoiMap = {
  mounted() {
    this.map = L.map(this.el).setView(CENTRO_MEXICO, ZOOM_MEXICO)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    this.capa = null
    this.marcadores = null

    this.handleEvent("voronoi", ({geojson}) => this.pintar(geojson))
  },

  pintar(geojson) {
    if (this.capa) {
      this.map.removeLayer(this.capa)
      this.capa = null
    }
    if (this.marcadores) {
      this.map.removeLayer(this.marcadores)
      this.marcadores = null
    }

    const colorDe = new Map()
    geojson.features.forEach((f, indice) => colorDe.set(f.properties.id, colorPorIndice(indice)))

    this.capa = L.geoJSON(geojson, {
      style: feature => ({
        color: "#3a3a3a",
        weight: 1,
        fillColor: colorDe.get(feature.properties.id),
        fillOpacity: 0.45,
      }),
      onEachFeature: (feature, capa) => {
        capa.bindPopup(feature.properties.nombre || `Negocio ${feature.properties.id}`)
      },
    }).addTo(this.map)

    this.marcadores = L.layerGroup(
      geojson.features.map(f =>
        L.circleMarker([f.properties.lat, f.properties.lon], {
          radius: 5,
          color: "#1a1a1a",
          weight: 1,
          fillColor: colorDe.get(f.properties.id),
          fillOpacity: 1,
        }).bindPopup(f.properties.nombre || `Negocio ${f.properties.id}`)
      )
    ).addTo(this.map)

    if (this.capa.getBounds().isValid()) {
      this.map.fitBounds(this.capa.getBounds())
    }
  },

  destroyed() {
    this.map.remove()
  },
}
