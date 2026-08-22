import L from "../vendor/leaflet/leaflet"

// Mapa de coropletas: recibe un FeatureCollection de AGEBs con
// `properties.valor_choropleth` (puede venir null, si Gaiarda no tiene
// el dato de censo para ese AGEB) y lo pinta con una escala de color
// simple (5 franjas por rango, no cuantiles). Sin dato se pinta gris,
// nunca se le inventa un color de "cero".

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5
const ESCALA = ["#f0e6f7", "#c9a8dd", "#a06bc0", "#7239a0", "#4A1A6B"]
const COLOR_SIN_DATO = "#9ca3af"

function color(valor, min, max) {
  if (valor === null || valor === undefined) return COLOR_SIN_DATO
  if (max === min) return ESCALA[ESCALA.length - 1]
  const t = (valor - min) / (max - min)
  const indice = Math.min(ESCALA.length - 1, Math.floor(t * ESCALA.length))
  return ESCALA[indice]
}

export const CoropletaMap = {
  mounted() {
    this.map = L.map(this.el).setView(CENTRO_MEXICO, ZOOM_MEXICO)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    this.capa = null
    this.leyenda = null

    this.handleEvent("coropleta", ({geojson, etiqueta}) => this.pintar(geojson, etiqueta))
  },

  pintar(geojson, etiqueta) {
    if (this.capa) {
      this.map.removeLayer(this.capa)
      this.capa = null
    }
    if (this.leyenda) {
      this.map.removeControl(this.leyenda)
      this.leyenda = null
    }

    const valores = geojson.features
      .map(f => f.properties.valor_choropleth)
      .filter(v => v !== null && v !== undefined)

    const min = valores.length ? Math.min(...valores) : 0
    const max = valores.length ? Math.max(...valores) : 0

    this.capa = L.geoJSON(geojson, {
      style: feature => ({
        color: "#3a3a3a",
        weight: 1,
        fillColor: color(feature.properties.valor_choropleth, min, max),
        fillOpacity: 0.75,
      }),
      onEachFeature: (feature, capa) => {
        const valor = feature.properties.valor_choropleth
        const texto = valor === null || valor === undefined ? "sin dato" : valor
        capa.bindPopup(`<strong>${etiqueta}</strong><br>${texto}`)
      },
    }).addTo(this.map)

    if (this.capa.getBounds().isValid()) {
      this.map.fitBounds(this.capa.getBounds())
    }

    this.leyenda = this._crearLeyenda(etiqueta, min, max, valores.length > 0)
    this.leyenda.addTo(this.map)
  },

  _crearLeyenda(etiqueta, min, max, hayValores) {
    const control = L.control({position: "bottomright"})
    control.onAdd = () => {
      const div = L.DomUtil.create("div", "bg-base-100 p-2 rounded-box border border-base-300 text-xs")
      const titulo = document.createElement("div")
      titulo.className = "font-semibold mb-1"
      titulo.textContent = etiqueta
      div.appendChild(titulo)

      if (hayValores) {
        const fila = document.createElement("div")
        fila.className = "flex items-center gap-1"
        ESCALA.forEach(c => {
          const cuadro = document.createElement("span")
          cuadro.style.display = "inline-block"
          cuadro.style.width = "14px"
          cuadro.style.height = "14px"
          cuadro.style.backgroundColor = c
          fila.appendChild(cuadro)
        })
        div.appendChild(fila)

        const rango = document.createElement("div")
        rango.className = "flex justify-between mt-1"
        rango.innerHTML = `<span>${min}</span><span>${max}</span>`
        div.appendChild(rango)
      }

      const sinDato = document.createElement("div")
      sinDato.className = "flex items-center gap-1 mt-1"
      const cuadroGris = document.createElement("span")
      cuadroGris.style.display = "inline-block"
      cuadroGris.style.width = "14px"
      cuadroGris.style.height = "14px"
      cuadroGris.style.backgroundColor = COLOR_SIN_DATO
      sinDato.appendChild(cuadroGris)
      const etiquetaSinDato = document.createElement("span")
      etiquetaSinDato.textContent = "sin dato"
      sinDato.appendChild(etiquetaSinDato)
      div.appendChild(sinDato)

      return div
    }
    return control
  },

  destroyed() {
    this.map.remove()
  },
}
