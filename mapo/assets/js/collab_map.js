import L from "../vendor/leaflet/leaflet"
import {entintar} from "./plano_tinta"

// Mapa colaborativo: al hacer clic, manda la anotacion al servidor.
// El servidor la guarda y la transmite por PubSub a TODOS los que
// esten viendo la misma sesion, incluido quien la creo (nadie la
// dibuja "de una vez" al hacer clic: todos, sin excepcion, la reciben
// por el mismo evento "nueva_anotacion"). Asi el codigo de dibujo es
// uno solo, no hay que deduplicar entre "mi propio marcador" y "el que
// me llega por broadcast". Editar/borrar siguen el mismo patron
// ("anotacion_actualizada"/"anotacion_borrada").
//
// Las anotaciones son marcas del equipo: van a mano y en lapiz rojo
// sobre el plano entintado, con su texto al lado.

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5

const escapar = t => String(t ?? "").replace(/[&<>"']/g, c =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c])

function icono(anotacion, nueva) {
  const texto = anotacion.texto ? `<span class="marca-texto">${escapar(anotacion.texto)}</span>` : ""
  return L.divIcon({
    className: "",
    html: `<span class="marca-mano${nueva ? " nueva" : ""}"><span class="marca-punto"></span>${texto}</span>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    popupAnchor: [0, -10],
  })
}

export const CollabMap = {
  mounted() {
    const anotacionesIniciales = JSON.parse(this.el.dataset.anotaciones || "[]")
    this.claveVista = `mapo:sesion:${this.el.dataset.sesionId}:vista`
    this.datos = new Map()
    this.marcadores = new Map()

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

    anotacionesIniciales.forEach(a => this.agregarMarcador(a, false))
    // Primera visita a la sesión: encuadra las marcas que ya puso el equipo.
    if (!vistaGuardada && anotacionesIniciales.length > 0) {
      this.map.fitBounds(anotacionesIniciales.map(x => [x.lat, x.lon]), {padding: [80, 80], maxZoom: 15})
    }

    this.map.on("click", e => this._nuevaEn(e.latlng))
    this.map.on("moveend zoomend", () => this._guardarVista())

    this.handleEvent("nueva_anotacion", anotacion => this.agregarMarcador(anotacion, true))
    this.handleEvent("anotacion_actualizada", anotacion => this.actualizarAnotacion(anotacion))
    this.handleEvent("anotacion_borrada", ({id}) => this.quitarAnotacion(id))

    this.alCambiarTema = () => entintar()
    window.addEventListener("mapo:tema", this.alCambiarTema)
  },

  agregarMarcador(anotacion, nueva) {
    this.datos.set(anotacion.id, anotacion)
    if (this.marcadores.has(anotacion.id)) return

    const marcador = L.marker([anotacion.lat, anotacion.lon], {
      icon: icono(anotacion, nueva),
      keyboard: true,
      title: anotacion.texto || "Marca sin texto",
    }).addTo(this.map)

    marcador.bindPopup(() => this._ficha(anotacion.id), {className: "ficha-marca"})
    this.marcadores.set(anotacion.id, marcador)
  },

  actualizarAnotacion(anotacion) {
    this.datos.set(anotacion.id, anotacion)
    const marcador = this.marcadores.get(anotacion.id)
    if (!marcador) return
    marcador.setIcon(icono(anotacion, false))
    if (marcador.isPopupOpen()) marcador.setPopupContent(this._ficha(anotacion.id))
  },

  quitarAnotacion(id) {
    const marcador = this.marcadores.get(id)
    if (marcador) {
      this.map.removeLayer(marcador)
      this.marcadores.delete(id)
    }
    this.datos.delete(id)
  },

  // Clic en el plano: una ficha en ese punto para escribir la nota antes de
  // mandarla. Cerrarla sin guardar no deja marca.
  _nuevaEn(latlng) {
    const {forma, input} = this._forma("", "Poner marca", texto => {
      this.pushEvent("crear_anotacion", {lat: latlng.lat, lon: latlng.lng, texto})
      this.map.closePopup()
    })
    const cab = document.createElement("b")
    cab.textContent = "Marca nueva"
    forma.prepend(cab)
    L.popup({className: "ficha-marca"}).setLatLng(latlng).setContent(forma).openOn(this.map)
    input.focus()
  },

  _ficha(id) {
    const anotacion = this.datos.get(id)
    if (!anotacion) return document.createElement("div")

    const {forma, botones} = this._forma(anotacion.texto, "Guardar", texto => {
      this.pushEvent("editar_anotacion", {id: anotacion.id, texto})
    })
    const autor = document.createElement("span")
    autor.className = "ficha-autor"
    autor.textContent = anotacion.autor
    forma.prepend(autor)

    const borrar = document.createElement("button")
    borrar.type = "button"
    borrar.textContent = "Borrar"
    borrar.className = "chico borrar"
    borrar.addEventListener("click", () => {
      if (window.confirm("¿Borrar esta marca para todo el equipo?")) {
        this.pushEvent("borrar_anotacion", {id: anotacion.id})
      }
    })
    botones.appendChild(borrar)
    return forma
  },

  _forma(texto, etiqueta, alMandar) {
    const forma = document.createElement("form")
    forma.className = "ficha"
    const input = document.createElement("input")
    input.type = "text"
    input.value = texto || ""
    input.maxLength = 255
    input.placeholder = "Nota (opcional)"
    input.setAttribute("aria-label", "Nota de la marca")
    input.className = "campo"
    const botones = document.createElement("div")
    botones.className = "acciones"
    const mandar = document.createElement("button")
    mandar.type = "submit"
    mandar.textContent = etiqueta
    mandar.className = "chico primario"
    botones.appendChild(mandar)
    forma.append(input, botones)
    // Leaflet no debe tomar el clic dentro de la ficha como un clic en el plano
    L.DomEvent.disableClickPropagation(forma)
    forma.addEventListener("submit", e => {
      e.preventDefault()
      alMandar(input.value.trim())
    })
    return {forma, input, botones}
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
    this.map.remove()
  },
}
