import L from "../vendor/leaflet/leaflet"

// Mapa colaborativo: al hacer clic, manda la anotacion al servidor.
// El servidor la guarda y la transmite por PubSub a TODOS los que
// esten viendo la misma sesion, incluido quien la creo (nadie la
// dibuja "de una vez" al hacer clic: todos, sin excepcion, la reciben
// por el mismo evento "nueva_anotacion"). Asi el codigo de dibujo es
// uno solo, no hay que deduplicar entre "mi propio marcador" y "el que
// me llega por broadcast".

const CENTRO_MEXICO = [23.6345, -102.5528]

export const CollabMap = {
  mounted() {
    const anotacionesIniciales = JSON.parse(this.el.dataset.anotaciones || "[]")

    this.map = L.map(this.el).setView(CENTRO_MEXICO, 5)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    this.marcadores = new Map()
    anotacionesIniciales.forEach(a => this.agregarMarcador(a))

    this.map.on("click", e => {
      const texto = window.prompt("Nota para esta anotacion (opcional):") || ""
      this.pushEvent("crear_anotacion", {lat: e.latlng.lat, lon: e.latlng.lng, texto})
    })

    this.handleEvent("nueva_anotacion", anotacion => this.agregarMarcador(anotacion))
  },

  agregarMarcador(anotacion) {
    if (this.marcadores.has(anotacion.id)) return

    const marcador = L.circleMarker([anotacion.lat, anotacion.lon], {
      radius: 8,
      color: "#6b1a2a",
      weight: 2,
      fillColor: "#6b1a2a",
      fillOpacity: 0.6,
    }).addTo(this.map)

    const texto = anotacion.texto ? `<br>${anotacion.texto}` : ""
    marcador.bindPopup(`<strong>${anotacion.autor}</strong>${texto}`)

    this.marcadores.set(anotacion.id, marcador)
  },

  destroyed() {
    this.map.remove()
  },
}
