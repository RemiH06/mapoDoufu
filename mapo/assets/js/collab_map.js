import L from "../vendor/leaflet/leaflet"

// Mapa colaborativo: al hacer clic, manda la anotacion al servidor.
// El servidor la guarda y la transmite por PubSub a TODOS los que
// esten viendo la misma sesion, incluido quien la creo (nadie la
// dibuja "de una vez" al hacer clic: todos, sin excepcion, la reciben
// por el mismo evento "nueva_anotacion"). Asi el codigo de dibujo es
// uno solo, no hay que deduplicar entre "mi propio marcador" y "el que
// me llega por broadcast". Editar/borrar siguen el mismo patron
// ("anotacion_actualizada"/"anotacion_borrada").

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5

export const CollabMap = {
  mounted() {
    const anotacionesIniciales = JSON.parse(this.el.dataset.anotaciones || "[]")
    this.claveVista = `mapo:sesion:${this.el.dataset.sesionId}:vista`
    this.datos = new Map()
    this.marcadores = new Map()

    const vistaGuardada = this._leerVistaGuardada()

    this.map = L.map(this.el).setView(
      vistaGuardada ? [vistaGuardada.lat, vistaGuardada.lon] : CENTRO_MEXICO,
      vistaGuardada ? vistaGuardada.zoom : ZOOM_MEXICO
    )
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    anotacionesIniciales.forEach(a => this.agregarMarcador(a))

    this.map.on("click", e => {
      const texto = window.prompt("Nota para esta anotacion (opcional):") || ""
      this.pushEvent("crear_anotacion", {lat: e.latlng.lat, lon: e.latlng.lng, texto})
    })

    this.map.on("moveend zoomend", () => this._guardarVista())

    this.handleEvent("nueva_anotacion", anotacion => this.agregarMarcador(anotacion))
    this.handleEvent("anotacion_actualizada", anotacion => this.actualizarAnotacion(anotacion))
    this.handleEvent("anotacion_borrada", ({id}) => this.quitarAnotacion(id))
  },

  agregarMarcador(anotacion) {
    this.datos.set(anotacion.id, anotacion)
    if (this.marcadores.has(anotacion.id)) return

    const marcador = L.circleMarker([anotacion.lat, anotacion.lon], {
      radius: 8,
      color: "#6b1a2a",
      weight: 2,
      fillColor: "#6b1a2a",
      fillOpacity: 0.6,
    }).addTo(this.map)

    marcador.bindPopup(() => this._contenidoPopup(anotacion.id))
    this.marcadores.set(anotacion.id, marcador)
  },

  actualizarAnotacion(anotacion) {
    this.datos.set(anotacion.id, anotacion)
    const marcador = this.marcadores.get(anotacion.id)
    if (marcador && marcador.isPopupOpen()) {
      marcador.setPopupContent(this._contenidoPopup(anotacion.id))
    }
  },

  quitarAnotacion(id) {
    const marcador = this.marcadores.get(id)
    if (marcador) {
      this.map.removeLayer(marcador)
      this.marcadores.delete(id)
    }
    this.datos.delete(id)
  },

  _contenidoPopup(id) {
    const anotacion = this.datos.get(id)
    if (!anotacion) return document.createElement("div")

    const contenedor = document.createElement("div")
    contenedor.className = "flex flex-col gap-1"

    const autor = document.createElement("strong")
    autor.className = "text-xs"
    autor.textContent = anotacion.autor
    contenedor.appendChild(autor)

    const input = document.createElement("input")
    input.type = "text"
    input.value = anotacion.texto || ""
    input.className = "input input-sm w-full"
    contenedor.appendChild(input)

    const fila = document.createElement("div")
    fila.className = "flex gap-1"

    const guardar = document.createElement("button")
    guardar.type = "button"
    guardar.textContent = "Guardar"
    guardar.className = "btn btn-xs btn-primary"
    guardar.addEventListener("click", () => {
      this.pushEvent("editar_anotacion", {id: anotacion.id, texto: input.value})
    })

    const borrar = document.createElement("button")
    borrar.type = "button"
    borrar.textContent = "Borrar"
    borrar.className = "btn btn-xs btn-error"
    borrar.addEventListener("click", () => {
      if (window.confirm("¿Borrar esta anotacion?")) {
        this.pushEvent("borrar_anotacion", {id: anotacion.id})
      }
    })

    fila.appendChild(guardar)
    fila.appendChild(borrar)
    contenedor.appendChild(fila)

    return contenedor
  },

  _leerVistaGuardada() {
    try {
      return JSON.parse(localStorage.getItem(this.claveVista) || "null")
    } catch (e) {
      return null
    }
  },

  _guardarVista() {
    try {
      const centro = this.map.getCenter()
      localStorage.setItem(
        this.claveVista,
        JSON.stringify({lat: centro.lat, lon: centro.lng, zoom: this.map.getZoom()})
      )
    } catch (e) {
      // localStorage puede tronar en modo privado/con site data bloqueado;
      // recordar la vista es una comodidad, no algo critico.
    }
  },

  destroyed() {
    this.map.remove()
  },
}
