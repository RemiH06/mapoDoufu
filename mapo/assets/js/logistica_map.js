import L from "../vendor/leaflet/leaflet"

// Mapa de logistica (VRP): cada clic agrega una parada (la primera es
// el deposito). Al calcular, el servidor manda las rutas resueltas;
// si vinieron con geometria real (carretera_real via OSRM) se pinta
// esa polyline tal cual; si no (linea_recta_aproximada, o esa llamada
// en particular no respondio), se traza una linea recta punteada
// entre las paradas en el orden resuelto, para que se note a simple
// vista que es una aproximacion, no una ruta confirmada.

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5
const ANGULO_DORADO = 137.508

function colorPorVehiculo(id) {
  const tono = (id * ANGULO_DORADO) % 360
  return `hsl(${tono}, 70%, 45%)`
}

export const LogisticaMap = {
  mounted() {
    this.map = L.map(this.el).setView(CENTRO_MEXICO, ZOOM_MEXICO)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    this.marcadoresParadas = L.layerGroup().addTo(this.map)
    this.capasRutas = L.layerGroup().addTo(this.map)

    this.map.on("click", e => {
      this.pushEvent("click_mapa", {lat: e.latlng.lat, lon: e.latlng.lng})
    })

    this.handleEvent("paradas", ({paradas}) => this.pintarParadas(paradas))
    this.handleEvent("rutas_vrp", ({rutas, paradas}) => this.pintarRutas(rutas, paradas))
    this.handleEvent("limpiar_rutas", () => this.capasRutas.clearLayers())
  },

  pintarParadas(paradas) {
    this.marcadoresParadas.clearLayers()

    paradas.forEach((parada, indice) => {
      const esDeposito = indice === 0
      const marcador = L.circleMarker([parada.lat, parada.lon], {
        radius: esDeposito ? 9 : 7,
        color: "#1a1a1a",
        weight: 2,
        fillColor: esDeposito ? "#C89030" : "#4A1A6B",
        fillOpacity: 0.85,
      }).addTo(this.marcadoresParadas)

      marcador.bindPopup(esDeposito ? "Depósito" : `Parada ${indice} (demanda: ${parada.demanda})`)
    })

    if (paradas.length > 0) {
      const grupo = L.featureGroup(this.marcadoresParadas.getLayers())
      this.map.fitBounds(grupo.getBounds(), {maxZoom: 12})
    }
  },

  pintarRutas(rutas, paradas) {
    this.capasRutas.clearLayers()

    rutas.forEach(ruta => {
      const color = colorPorVehiculo(ruta.vehiculo_id)

      if (ruta.geometria) {
        L.geoJSON(
          {type: "Feature", properties: {}, geometry: ruta.geometria},
          {style: {color, weight: 4, opacity: 0.85}}
        )
          .bindPopup(`Vehículo ${ruta.vehiculo_id}: ${ruta.distancia_km.toFixed(1)} km (carretera real)`)
          .addTo(this.capasRutas)
      } else {
        const puntos = ruta.orden_paradas.map(i => [paradas[i].lat, paradas[i].lon])
        L.polyline(puntos, {color, weight: 4, opacity: 0.85, dashArray: "8 6"})
          .bindPopup(`Vehículo ${ruta.vehiculo_id}: ${ruta.distancia_km.toFixed(1)} km (línea recta aproximada)`)
          .addTo(this.capasRutas)
      }
    })

    if (this.capasRutas.getLayers().length > 0) {
      this.map.fitBounds(this.capasRutas.getBounds(), {maxZoom: 12})
    }
  },

  destroyed() {
    this.map.remove()
  },
}
