import L from "../vendor/leaflet/leaflet"

// Marcas del equipo sobre el plano: las dibujan /sesiones/:id (CollabMap) y la
// capa "Tus marcas" de /mapa (MapaTecnico), y ambas escriben en la misma
// sesion. Al poner una marca solo se manda al servidor; el servidor la guarda
// y la transmite por PubSub a TODOS los que tengan la sesion abierta, incluido
// quien la puso. Nadie la dibuja "de una vez": todos la reciben por el mismo
// evento, asi el dibujo es uno solo y no hay que deduplicar entre "mi marca"
// y "la que me llega por broadcast".
//
// Van a mano y en lapiz rojo (--accent), nunca mezcladas con lo impreso. Una
// forma nueva (trazo libre, flecha) agrega su caso en _dibujar y en _clic, y
// su validacion en Mapo.Sesiones.Anotacion.

export const escapar = t => String(t ?? "").replace(/[&<>"']/g, c =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c])

const METROS_POR_GRADO = 111320

function iconoPunto(anotacion, nueva) {
  const texto = anotacion.texto ? `<span class="marca-texto">${escapar(anotacion.texto)}</span>` : ""
  return L.divIcon({
    className: "",
    html: `<span class="marca-mano${nueva ? " nueva" : ""}"><span class="marca-punto"></span>${texto}</span>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    popupAnchor: [0, -10],
  })
}

// La nota de un circulo va junto a su orilla derecha. Es tambien su asa: ahi
// se ancla la ficha y por ahi se llega con teclado (sin nota, queda un asa
// chica).
function iconoNota(anotacion) {
  return L.divIcon({
    className: "",
    html: anotacion.texto
      ? `<span class="marca-nota">${escapar(anotacion.texto)}</span>`
      : `<span class="marca-nota vacia"></span>`,
    iconSize: null,
    iconAnchor: [-8, 10],
  })
}

// Un circulo como trazado con lapiz: el radio ondula suave y siempre igual
// (la semilla sale del id), y el trazo se pasa del inicio y acaba un poco
// afuera, como cuando se cierra a mano. Se calcula en metros, no en pixeles,
// asi no hay que rehacerlo al hacer zoom.
function trazoCirculo(lat, lon, radio, semilla) {
  const k = Math.cos(lat * Math.PI / 180)
  const puntos = []
  const pasos = 80, vuelta = Math.PI * 2.15
  for (let i = 0; i <= pasos; i++) {
    const t = i / pasos
    const a = semilla + t * vuelta
    const r = radio * (1 + 0.035 * Math.sin(2 * a + semilla) + 0.02 * Math.sin(3 * a + 2 * semilla) + 0.06 * t * t)
    puntos.push([lat + Math.sin(a) * r / METROS_POR_GRADO, lon + Math.cos(a) * r / (METROS_POR_GRADO * k)])
  }
  return puntos
}

export class Marcas {
  // push: el pushEvent del hook. pane: donde van los trazos (sobre los acetatos).
  constructor(map, {push, pane}) {
    this.map = map
    this.push = push
    this.pane = pane
    this.renderer = L.svg({pane})
    this.datos = new Map()
    this.capas = new Map()
    this.herramienta = "punto"
    this.centro = null
    this.alTecla = e => { if (e.key === "Escape") this.cancelar() }
    this.alMover = e => this._previa(e.latlng)
    document.addEventListener("keydown", this.alTecla)
  }

  poner(anotaciones) {
    [...this.capas.keys()].forEach(id => this.quitar(id))
    anotaciones.forEach(a => this.agregar(a, false))
  }

  bordes() {
    const puntos = [...this.datos.values()].map(a => [a.lat, a.lon])
    return puntos.length ? L.latLngBounds(puntos) : null
  }

  agregar(anotacion, nueva) {
    this.datos.set(anotacion.id, anotacion)
    if (this.capas.has(anotacion.id)) return
    this._dibujar(anotacion, nueva)
  }

  actualizar(anotacion) {
    const abierta = this.capas.get(anotacion.id)?.getLayers().some(l => l.isPopupOpen?.())
    this.datos.set(anotacion.id, anotacion)
    this._borrarCapa(anotacion.id)
    this._dibujar(anotacion, false)
    if (abierta) this._principal(anotacion.id).openPopup()
  }

  quitar(id) {
    this._borrarCapa(id)
    this.datos.delete(id)
  }

  usar(herramienta) {
    this.cancelar()
    this.herramienta = herramienta
  }

  // Un clic en el plano. El punto pide uno; el circulo, centro y orilla.
  clic(latlng) {
    if (this.herramienta === "circulo") {
      if (!this.centro) {
        this.centro = latlng
        this.map.on("mousemove", this.alMover)
        this._previa(latlng)
        return
      }
      const centro = this.centro
      const radio = Math.round(this.map.distance(centro, latlng))
      this.cancelar()
      if (radio < 1) return
      this._previa(latlng, centro, radio)
      this._nueva(latlng, "Círculo nuevo", texto => ({lat: centro.lat, lon: centro.lng, forma: "circulo", radio_m: radio, texto}))
    } else {
      this._nueva(latlng, "Marca nueva", texto => ({lat: latlng.lat, lon: latlng.lng, forma: "punto", texto}))
    }
  }

  cancelar() {
    this.centro = null
    this.map.off("mousemove", this.alMover)
    if (this.guia) { this.map.removeLayer(this.guia); this.guia = null }
  }

  destruir() {
    this.cancelar()
    document.removeEventListener("keydown", this.alTecla)
    ;[...this.capas.keys()].forEach(id => this._borrarCapa(id))
  }

  // Mientras se elige la orilla: un circulo punteado que sigue al cursor.
  _previa(latlng, centro = this.centro, radio = null) {
    if (!centro) return
    const r = radio ?? this.map.distance(centro, latlng)
    if (!this.guia) {
      this.guia = L.circle(centro, {radius: r, pane: this.pane, renderer: this.renderer, className: "guia-marca", interactive: false, fill: false, weight: 1.5, dashArray: "4 4"}).addTo(this.map)
    } else {
      this.guia.setRadius(r)
    }
  }

  _dibujar(anotacion, nueva) {
    // La primera parte lleva la ficha.
    const partes = []
    if (anotacion.forma === "circulo") {
      const orilla = [anotacion.lat, anotacion.lon + anotacion.radio_m / (METROS_POR_GRADO * Math.cos(anotacion.lat * Math.PI / 180))]
      const asa = L.marker(orilla, {icon: iconoNota(anotacion), keyboard: true, title: anotacion.texto || "Círculo sin nota"})
      const trazo = L.polyline(trazoCirculo(anotacion.lat, anotacion.lon, anotacion.radio_m, anotacion.id % 7), {
        pane: this.pane, renderer: this.renderer, className: `trazo-marca${nueva ? " nueva" : ""}`,
        weight: 2.6, lineCap: "round", lineJoin: "round", bubblingMouseEvents: false,
      }).on("click", () => asa.openPopup())
      partes.push(asa, trazo)
    } else {
      partes.push(L.marker([anotacion.lat, anotacion.lon], {
        icon: iconoPunto(anotacion, nueva),
        keyboard: true,
        title: anotacion.texto || "Marca sin texto",
      }))
    }
    partes[0].bindPopup(() => this._ficha(anotacion.id), {className: "ficha-marca"})
    this.capas.set(anotacion.id, L.layerGroup(partes).addTo(this.map))
  }

  _principal(id) {
    return this.capas.get(id)?.getLayers()[0]
  }

  _borrarCapa(id) {
    const capa = this.capas.get(id)
    if (capa) {
      this.map.removeLayer(capa)
      this.capas.delete(id)
    }
  }

  // Una ficha para escribir la nota antes de mandar la marca. Cerrarla sin
  // guardar no deja marca.
  _nueva(latlng, titulo, armar) {
    const {forma, input} = this._forma("", "Poner marca", texto => {
      this.push("crear_anotacion", armar(texto))
      this.map.closePopup()
    })
    const cab = document.createElement("b")
    cab.textContent = titulo
    forma.prepend(cab)
    L.popup({className: "ficha-marca"}).setLatLng(latlng).setContent(forma)
      .on("remove", () => this.cancelar())
      .openOn(this.map)
    input.focus()
  }

  _ficha(id) {
    const anotacion = this.datos.get(id)
    if (!anotacion) return document.createElement("div")

    const {forma, botones} = this._forma(anotacion.texto, "Guardar", texto => {
      this.push("editar_anotacion", {id: anotacion.id, texto})
    })
    const autor = document.createElement("span")
    autor.className = "ficha-autor"
    autor.textContent = anotacion.forma === "circulo"
      ? `${anotacion.autor} · radio ${Math.round(anotacion.radio_m).toLocaleString("es-MX")} m`
      : anotacion.autor
    forma.prepend(autor)

    const borrar = document.createElement("button")
    borrar.type = "button"
    borrar.textContent = "Borrar"
    borrar.className = "chico borrar"
    borrar.addEventListener("click", () => {
      if (window.confirm("¿Borrar esta marca para todo el equipo?")) {
        this.push("borrar_anotacion", {id: anotacion.id})
      }
    })
    botones.appendChild(borrar)
    return forma
  }

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
  }
}
