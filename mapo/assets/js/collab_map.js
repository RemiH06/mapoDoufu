import L from "../vendor/leaflet/leaflet"
import {entintar} from "./plano_tinta"
import {Marcas} from "./marcas"

// Mapa colaborativo de una sesion: el plano entintado con las marcas del
// equipo encima. El dibujo y la ficha de cada marca viven en marcas.js, que
// comparte con la capa "Tus marcas" de /mapa.

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5

export const CollabMap = {
  mounted() {
    const anotacionesIniciales = JSON.parse(this.el.dataset.anotaciones || "[]")
    this.claveVista = `mapo:sesion:${this.el.dataset.sesionId}:vista`

    entintar()
    const vistaGuardada = this._leerVistaGuardada()

    this.map = L.map(this.el, {zoomControl: false}).setView(
      vistaGuardada ? [vistaGuardada.lat, vistaGuardada.lon] : CENTRO_MEXICO,
      vistaGuardada ? vistaGuardada.zoom : ZOOM_MEXICO
    )
    L.control.zoom({position: "topright"}).addTo(this.map)
    L.control.scale({imperial: false, position: "bottomright"}).addTo(this.map)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    this.map.createPane("p-marcas").style.zIndex = 450
    this.marcas = new Marcas(this.map, {push: (e, p) => this.pushEvent(e, p), pane: "p-marcas"})
    this.marcas.poner(anotacionesIniciales)
    // Primera visita a la sesión: encuadra las marcas que ya puso el equipo.
    const bordes = this.marcas.bordes()
    if (!vistaGuardada && bordes) this.map.fitBounds(bordes, {padding: [80, 80], maxZoom: 15})

    this.map.on("click", e => this.marcas.clic(e.latlng))
    this.map.on("moveend zoomend", () => this._guardarVista())

    this.handleEvent("nueva_anotacion", anotacion => this.marcas.agregar(anotacion, true))
    this.handleEvent("anotacion_actualizada", anotacion => this.marcas.actualizar(anotacion))
    this.handleEvent("anotacion_borrada", ({id}) => this.marcas.quitar(id))
    this.handleEvent("herramienta", ({herramienta}) => this.marcas.usar(herramienta))

    this.alCambiarTema = () => entintar()
    window.addEventListener("mapo:tema", this.alCambiarTema)
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
    window.removeEventListener("mapo:tema", this.alCambiarTema)
    this.marcas.destruir()
    this.map.remove()
  },
}
