import {crearPlano, alListo, clics} from "./plano"
import {Marcas} from "./marcas"

// Mapa colaborativo de una sesion: el plano con las marcas del equipo
// encima. El dibujo y la ficha de cada marca viven en marcas.js, que
// comparte con la capa "Tus marcas" de /mapa.

export const CollabMap = {
  mounted() {
    const anotacionesIniciales = JSON.parse(this.el.dataset.anotaciones || "[]")
    // La clave cambió con MapLibre: su zoom va un nivel abajo del de Leaflet.
    this.claveVista = `mapo:sesion:${this.el.dataset.sesionId}:plano`
    const vistaGuardada = this._leerVistaGuardada()

    this.listo = crearPlano(this.el, {alTema: () => this.marcas.repintar()}).then(({map, ml}) => {
      this.map = map
      if (vistaGuardada) map.jumpTo({center: [vistaGuardada.lon, vistaGuardada.lat], zoom: vistaGuardada.zoom})
      const clic = clics(map, {vacio: lugar => this.marcas.clic(lugar), cursor: () => "crosshair"})
      clic.cursor()
      this.marcas = new Marcas(map, ml, {push: (e, p) => this.pushEvent(e, p), clic})
      this.marcas.poner(anotacionesIniciales)
      // Primera visita a la sesión: encuadra las marcas que ya puso el equipo.
      const bordes = this.marcas.bordes()
      if (!vistaGuardada && bordes) map.fitBounds(bordes, {padding: 80, maxZoom: 14})
      map.on("moveend", () => this._guardarVista())
    })
    const cuando = alListo(this, this.listo)

    this.handleEvent("nueva_anotacion", cuando(anotacion => this.marcas.agregar(anotacion, true)))
    this.handleEvent("anotacion_actualizada", cuando(anotacion => this.marcas.actualizar(anotacion)))
    this.handleEvent("anotacion_borrada", cuando(({id}) => this.marcas.quitar(id)))
    this.handleEvent("herramienta", cuando(({herramienta}) => this.marcas.usar(herramienta)))
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
    this.cerrado = true
    this.marcas?.destruir()
    this.map?.remove()
  },
}
