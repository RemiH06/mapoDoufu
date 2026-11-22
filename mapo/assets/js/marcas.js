import {css, escapar, fuente, quitar, distancia, circulo, recuadroDePuntos} from "./plano"

export {escapar}

// Marcas del equipo sobre el plano: las dibujan /sesiones/:id (CollabMap) y la
// capa "Tus marcas" de /mapa (MapaTecnico), y ambas escriben en la misma
// sesion. Al poner una marca solo se manda al servidor; el servidor la guarda
// y la transmite por PubSub a TODOS los que tengan la sesion abierta, incluido
// quien la puso. Nadie la dibuja "de una vez": todos la reciben por el mismo
// evento, asi el dibujo es uno solo y no hay que deduplicar entre "mi marca"
// y "la que me llega por broadcast".
//
// Van a mano y en lapiz rojo (--accent), nunca mezcladas con lo impreso. Los
// puntos y las notas son marcas del DOM (MapLibre las pone encima del lienzo);
// el trazo de los circulos es una capa de lineas, siempre arriba de los
// acetatos (alFrente). Una forma nueva (trazo libre, flecha) agrega su caso en
// _dibujar y en clic, y su validacion en Mapo.Sesiones.Anotacion.

const METROS_POR_GRADO = 111320
const TRAZO = "marcas-trazo"
const GUIA = "marcas-guia"

function elementoPunto(anotacion, nueva) {
  const el = document.createElement("div")
  const texto = anotacion.texto ? `<span class="marca-texto">${escapar(anotacion.texto)}</span>` : ""
  el.innerHTML = `<span class="marca-mano${nueva ? " nueva" : ""}"><span class="marca-punto"></span>${texto}</span>`
  return el
}

// La nota de un circulo va junto a su orilla derecha. Es tambien su asa: ahi
// se ancla la ficha y por ahi se llega con teclado (sin nota, queda un asa
// chica).
function elementoNota(anotacion) {
  const el = document.createElement("div")
  el.innerHTML = anotacion.texto
    ? `<span class="marca-nota">${escapar(anotacion.texto)}</span>`
    : `<span class="marca-nota vacia"></span>`
  return el
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
    puntos.push([lon + Math.cos(a) * r / (METROS_POR_GRADO * k), lat + Math.sin(a) * r / METROS_POR_GRADO])
  }
  return puntos
}

export class Marcas {
  // push: el pushEvent del hook. clic: el registro de clics del plano (plano.js).
  constructor(map, ml, {push, clic}) {
    this.map = map
    this.ml = ml
    this.push = push
    this.datos = new Map()
    this.capas = new Map()
    this.herramienta = "punto"
    this.centro = null
    this.alTecla = e => { if (e.key === "Escape") this.cancelar() }
    this.alMover = e => this._previa(e.lngLat)
    document.addEventListener("keydown", this.alTecla)
    clic.en(TRAZO, f => this.capas.get(f.properties.id)?.principal.togglePopup())
    this.repintar()
  }

  poner(anotaciones) {
    [...this.capas.keys()].forEach(id => this._borrarCapa(id))
    this.datos.clear()
    anotaciones.forEach(a => this.agregar(a, false))
  }

  bordes() {
    const puntos = [...this.datos.values()].map(a => [a.lon, a.lat])
    return puntos.length ? recuadroDePuntos(puntos) : null
  }

  agregar(anotacion, nueva) {
    this.datos.set(anotacion.id, anotacion)
    if (this.capas.has(anotacion.id)) return
    this._dibujar(anotacion, nueva)
    this._trazos()
  }

  actualizar(anotacion) {
    const abierta = this.capas.get(anotacion.id)?.principal.getPopup()?.isOpen()
    this.datos.set(anotacion.id, anotacion)
    this._borrarCapa(anotacion.id)
    this._dibujar(anotacion, false)
    this._trazos()
    if (abierta) this.capas.get(anotacion.id).principal.togglePopup()
  }

  quitar(id) {
    this._borrarCapa(id)
    this.datos.delete(id)
    this._trazos()
  }

  usar(herramienta) {
    this.cancelar()
    this.herramienta = herramienta
  }

  // Un clic en el plano ({lng, lat}). El punto pide uno; el circulo, centro y orilla.
  clic(lugar) {
    if (this.herramienta === "circulo") {
      if (!this.centro) {
        this.centro = lugar
        this.map.on("mousemove", this.alMover)
        this._previa(lugar)
        return
      }
      const centro = this.centro
      const radio = Math.round(distancia([centro.lng, centro.lat], [lugar.lng, lugar.lat]))
      this.cancelar()
      if (radio < 1) return
      this._previa(lugar, centro, radio)
      this._nueva(lugar, "Círculo nuevo", texto => ({lat: centro.lat, lon: centro.lng, forma: "circulo", radio_m: radio, texto}))
    } else {
      this._nueva(lugar, "Marca nueva", texto => ({lat: lugar.lat, lon: lugar.lng, forma: "punto", texto}))
    }
  }

  cancelar() {
    this.centro = null
    this.map.off("mousemove", this.alMover)
    if (this.map.getSource(GUIA)) fuente(this.map, GUIA)
  }

  destruir() {
    this.cancelar()
    document.removeEventListener("keydown", this.alTecla)
    ;[...this.capas.keys()].forEach(id => this._borrarCapa(id))
  }

  // El trazo de los circulos y la guia, con la tinta del tema en curso. Se
  // llama al crear y despues de cada cambio de tema (el estilo se recarga).
  repintar() {
    const map = this.map
    quitar(map, "marcas-")
    fuente(map, GUIA)
    map.addLayer({id: GUIA, type: "line", source: GUIA,
      paint: {"line-color": css("--accent"), "line-width": 1.5, "line-dasharray": [2.7, 2.7]}})
    this._trazos()
    map.addLayer({id: TRAZO, type: "line", source: TRAZO, layout: {"line-cap": "round", "line-join": "round"},
      paint: {"line-color": css("--accent"), "line-width": 2.6}})
  }

  // Las marcas van encima de todos los acetatos.
  alFrente() {
    for (const id of [GUIA, TRAZO]) if (this.map.getLayer(id)) this.map.moveLayer(id)
  }

  _trazos() {
    const features = [...this.datos.values()].filter(a => a.forma === "circulo").map(a => ({
      type: "Feature",
      properties: {id: a.id},
      geometry: {type: "LineString", coordinates: trazoCirculo(a.lat, a.lon, a.radio_m, a.id % 7)},
    }))
    fuente(this.map, TRAZO, {type: "FeatureCollection", features})
  }

  // Mientras se elige la orilla: un circulo punteado que sigue al cursor.
  _previa(lugar, centro = this.centro, radio = null) {
    if (!centro) return
    const r = radio ?? distancia([centro.lng, centro.lat], [lugar.lng, lugar.lat])
    fuente(this.map, GUIA, circulo([centro.lng, centro.lat], r))
  }

  _dibujar(anotacion, nueva) {
    const ml = this.ml
    const ficha = new ml.Popup({className: "ficha-marca", offset: 12, focusAfterOpen: false, maxWidth: "300px"})
    ficha.on("open", () => ficha.setDOMContent(this._ficha(anotacion.id)))
    let principal
    if (anotacion.forma === "circulo") {
      const orilla = [anotacion.lon + anotacion.radio_m / (METROS_POR_GRADO * Math.cos(anotacion.lat * Math.PI / 180)), anotacion.lat]
      principal = new ml.Marker({element: elementoNota(anotacion), anchor: "left", offset: [8, 0]}).setLngLat(orilla)
      principal.getElement().title = anotacion.texto || "Círculo sin nota"
    } else {
      principal = new ml.Marker({element: elementoPunto(anotacion, nueva)}).setLngLat([anotacion.lon, anotacion.lat])
      principal.getElement().title = anotacion.texto || "Marca sin texto"
    }
    const el = principal.getElement()
    el.tabIndex = 0
    el.setAttribute("role", "button")
    el.setAttribute("aria-label", el.title)
    principal.setPopup(ficha).addTo(this.map)
    this.capas.set(anotacion.id, {principal})
  }

  _borrarCapa(id) {
    const capa = this.capas.get(id)
    if (capa) {
      capa.principal.getPopup()?.remove()
      capa.principal.remove()
      this.capas.delete(id)
    }
  }

  // Una ficha para escribir la nota antes de mandar la marca. Cerrarla sin
  // guardar no deja marca.
  _nueva(lugar, titulo, armar) {
    const {forma, input} = this._forma("", "Poner marca", texto => {
      this.push("crear_anotacion", armar(texto))
      popup.remove()
    })
    const cab = document.createElement("b")
    cab.textContent = titulo
    forma.prepend(cab)
    const popup = new this.ml.Popup({className: "ficha-marca", focusAfterOpen: false, maxWidth: "300px"})
      .setLngLat(lugar).setDOMContent(forma)
    popup.on("close", () => this.cancelar())
    popup.addTo(this.map)
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
    forma.addEventListener("submit", e => {
      e.preventDefault()
      alMandar(input.value.trim())
    })
    return {forma, input, botones}
  }
}
