import {css, escapar, fuente, quitar, distancia, circulo, recuadroDePuntos, alcanzar} from "./plano"
import {dibujar} from "./zona_plano"
import {trazos, ancla, extremos, medida, simplificar} from "./marcas_trazos"

export {escapar}

// Marcas del equipo sobre el plano: las dibujan /sesiones/:id (CollabMap) y la
// capa "Tus marcas" de /mapa (MapaTecnico), y ambas escriben en la misma
// sesion. Al poner una marca solo se manda al servidor; el servidor la guarda
// y la transmite por PubSub a TODOS los que tengan la sesion abierta, incluido
// quien la puso. Nadie la dibuja "de una vez": todos la reciben por el mismo
// evento, asi el dibujo es uno solo y no hay que deduplicar entre "mi marca"
// y "la que me llega por broadcast".
//
// Van a mano y en el lapiz de quien las puso (--lapiz-N de mesa.css, fijo por
// persona y equipo), nunca mezcladas con lo impreso. Los puntos y las notas
// son marcas del DOM (MapLibre las pone encima del lienzo); lo demas es una
// capa de lineas, siempre arriba de los acetatos (alFrente). Una forma nueva
// agrega su caso en marcas_trazos.js y en clic, y su validacion en
// Mapo.Sesiones.Anotacion.

const TRAZO = "marcas-trazo"
const GUIA = "marcas-guia"
const GUIA_PUNTO = "marcas-guia-punto"
const NOMBRES = {punto: "Marca", circulo: "Círculo", flecha: "Flecha", trazo: "Trazo", poligono: "Polígono"}
const NUEVAS = {punto: "Marca nueva", circulo: "Círculo nuevo", flecha: "Flecha nueva", trazo: "Trazo nuevo", poligono: "Polígono nuevo"}
// Menos que esto no es un dibujo: es un clic que tembló.
const MINIMO_PX = 8
// El tope de Mapo.Sesiones.Anotacion: el círculo deja de crecer ahí.
const RADIO_MAXIMO_M = 50000

const redondo = ([lon, lat]) => [+lon.toFixed(6), +lat.toFixed(6)]
const tinta = lapiz => css(`--lapiz-${lapiz}`) || css("--accent")

// La etiqueta del plano: la nota, tres puntos si hay nota larga y la firma de
// quien la puso (solo se ve si hay marcas de mas de una persona).
function etiqueta(a) {
  const mas = a.detalle ? `<span class="marca-mas" aria-hidden="true">…</span>` : ""
  return `${escapar(a.texto)}${mas}<span class="marca-firma" aria-hidden="true">${escapar(a.firma)}</span>`
}

function elementoPunto(a, nueva) {
  const el = document.createElement("div")
  el.innerHTML = `<span class="marca-mano${nueva ? " nueva" : ""}"><span class="marca-punto"></span><span class="marca-texto">${etiqueta(a)}</span></span>`
  return el
}

// La nota de las demas formas es tambien su asa: ahi se ancla la ficha y por
// ahi se llega con teclado (sin nota, queda un asa chica).
function elementoNota(a) {
  const el = document.createElement("div")
  const asa = a.texto || a.detalle ? "" : `<span class="marca-asa"></span>`
  el.innerHTML = `<span class="marca-nota">${asa}${etiqueta(a)}</span>`
  return el
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
    this.lapiz = 1
    this.activa = true
    // Lo que se esta dibujando: el primer clic del circulo o la flecha, el
    // poligono abierto, el trazo bajo el dedo y la ficha de la marca nueva.
    this.inicio = null
    this.poligono = null
    this.trazo = null
    this.nueva = null
    // La ficha en edicion: si llega un cambio de otra persona no se pierde.
    this.borrador = null
    this.alTecla = e => { if (e.key === "Escape") this.cancelar() }
    this.alMover = e => this._seguir(e.lngLat)
    this.alBajar = e => this._bajar(e)
    this.alTrazar = e => this._trazar(e)
    this.alSoltar = () => this._soltar()
    document.addEventListener("keydown", this.alTecla)
    map.on("mousedown", this.alBajar)
    map.on("touchstart", this.alBajar)
    clic.en(TRAZO, f => this.capas.get(f.properties.id)?.togglePopup())
    this.repintar()
  }

  poner(anotaciones) {
    this.cancelar()
    ;[...this.capas.keys()].forEach(id => this._borrarCapa(id))
    this.datos.clear()
    anotaciones.forEach(a => {
      this.datos.set(a.id, a)
      this._dibujar(a, false)
    })
    this._trazos()
  }

  bordes() {
    const puntos = [...this.datos.values()].flatMap(extremos)
    return puntos.length ? recuadroDePuntos(puntos) : null
  }

  agregar(anotacion, nueva) {
    this.datos.set(anotacion.id, anotacion)
    if (this.capas.has(anotacion.id)) return
    this._dibujar(anotacion, nueva)
    this._trazos()
  }

  actualizar(anotacion) {
    const {id} = anotacion
    const abierta = this.capas.get(id)?.getPopup()?.isOpen()
    // Cerrar la ficha vieja tira el borrador: se aparta y se regresa.
    const borrador = this.borrador?.id === id ? {...this.borrador, ajeno: true} : null
    this.datos.set(id, anotacion)
    this._borrarCapa(id)
    this._dibujar(anotacion, false)
    this._trazos()
    if (borrador) this.borrador = borrador
    if (abierta) this.capas.get(id).togglePopup()
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

  // En /mapa solo se dibuja con la cinta de "Tus marcas" abierta.
  activar(activa) {
    this.activa = activa
    if (!activa) this.cancelar()
  }

  // Con una figura elegida, el clic es del dibujo aunque caiga sobre la línea de
  // otra marca (que se abre por su nota).
  dibujando() {
    return this.herramienta !== "punto"
  }

  // Un clic en el plano ({lng, lat}). El punto pide uno; el circulo y la flecha,
  // dos; el poligono, uno por vertice (zona_plano.js). El trazo se arrastra.
  clic(lugar) {
    this.nueva?.remove()
    const aqui = redondo([lugar.lng, lugar.lat])
    switch (this.herramienta) {
      case "trazo":
        return
      case "poligono":
        this.poligono = dibujar(this.map, {
          inicio: aqui,
          tinta: () => tinta(this.lapiz),
          alTerminar: coords => { this._cerrarPoligono(); this._proponer({forma: "poligono", coords}, coords[0]) },
          alCancelar: () => this._cerrarPoligono(),
        })
        return this._marcando()
      case "circulo":
      case "flecha": {
        if (!this.inicio) {
          this.inicio = aqui
          this.map.on("mousemove", this.alMover)
          this._seguir(lugar)
          return this._marcando()
        }
        const forma = this._forma(aqui)
        if (this._pixeles(this.inicio, aqui) < MINIMO_PX || forma.radio_m === 0) return
        this._dejar()
        return this._proponer(forma, aqui)
      }
      default:
        return this._proponer({forma: "punto", lon: aqui[0], lat: aqui[1]}, aqui)
    }
  }

  cancelar() {
    this._dejar()
    this.poligono?.cancelar(true)
    this._cerrarPoligono()
    this._dejarTrazo()
    this.nueva?.remove()
    this._guia([])
  }

  destruir() {
    this.cancelar()
    document.removeEventListener("keydown", this.alTecla)
    this.map.off("mousedown", this.alBajar)
    this.map.off("touchstart", this.alBajar)
    ;[...this.capas.keys()].forEach(id => this._borrarCapa(id))
  }

  // Las lineas y la guia, con las tintas del tema en curso. Se llama al crear y
  // despues de cada cambio de tema (el estilo se recarga).
  repintar() {
    const map = this.map
    quitar(map, "marcas-")
    fuente(map, GUIA)
    map.addLayer({id: GUIA, type: "line", source: GUIA, filter: ["!=", ["geometry-type"], "Point"],
      paint: {"line-color": tinta(this.lapiz), "line-width": 1.5, "line-dasharray": [2.7, 2.7]}})
    map.addLayer({id: GUIA_PUNTO, type: "circle", source: GUIA, filter: ["==", ["geometry-type"], "Point"],
      paint: {"circle-radius": 4, "circle-color": css("--bg"), "circle-stroke-color": tinta(this.lapiz), "circle-stroke-width": 2}})
    this._trazos()
    map.addLayer({id: TRAZO, type: "line", source: TRAZO, layout: {"line-cap": "round", "line-join": "round"},
      paint: {"line-color": ["get", "color"], "line-width": 2.6}})
    this.poligono?.pintar()
  }

  // Las marcas van encima de todos los acetatos.
  alFrente() {
    for (const id of [TRAZO, GUIA, GUIA_PUNTO]) if (this.map.getLayer(id)) this.map.moveLayer(id)
  }

  // ---------------------------------------------------------- a medio dibujar

  _pixeles(a, b) {
    const p = this.map.project(a), q = this.map.project(b)
    return Math.hypot(p.x - q.x, p.y - q.y)
  }

  _forma(aqui) {
    return this.herramienta === "circulo"
      ? {forma: "circulo", lon: this.inicio[0], lat: this.inicio[1], radio_m: Math.min(RADIO_MAXIMO_M, Math.round(distancia(this.inicio, aqui)))}
      : {forma: "flecha", coords: [this.inicio, aqui]}
  }

  _seguir(lugar) {
    if (!this.inicio) return
    const punto = {type: "Feature", properties: {}, geometry: {type: "Point", coordinates: this.inicio}}
    this._guia([punto, ...this._previa(this._forma([lugar.lng, lugar.lat]))])
  }

  // Lo que todavia no es marca, punteado.
  _previa(forma) {
    if (forma.forma === "circulo") return [circulo([forma.lon, forma.lat], forma.radio_m)]
    return trazos(forma).map(coordinates => ({type: "Feature", properties: {}, geometry: {type: "LineString", coordinates}}))
  }

  _guia(features) {
    if (!this.map.getSource(GUIA)) return
    const color = tinta(this.lapiz)
    this.map.setPaintProperty(GUIA, "line-color", color)
    this.map.setPaintProperty(GUIA_PUNTO, "circle-stroke-color", color)
    fuente(this.map, GUIA, {type: "FeatureCollection", features})
  }

  _dejar() {
    this.inicio = null
    this.map.off("mousemove", this.alMover)
    this._marcando()
  }

  _cerrarPoligono() {
    this.poligono = null
    this._marcando()
  }

  // Mientras se dibuja, las marcas ya puestas no atrapan el clic (sesion.css).
  _marcando() {
    this.map.getContainer().classList.toggle("marcando", !!(this.inicio || this.poligono || this.trazo))
  }

  // El trazo libre: se arrastra con el boton o con un dedo. Dos dedos son para
  // mover el plano: si llega el segundo, el trazo se suelta.
  _bajar(e) {
    if (!this.activa || this.herramienta !== "trazo" || this.map._dibujandoZona) return
    const o = e.originalEvent
    if (o.touches?.length > 1) return this._dejarTrazo()
    if (o.button || o.target.closest?.(".maplibregl-marker, .maplibregl-popup")) return
    e.preventDefault()
    this.nueva?.remove()
    this.trazo = [{x: e.point.x, y: e.point.y, lugar: redondo([e.lngLat.lng, e.lngLat.lat])}]
    this.map.on("mousemove", this.alTrazar)
    this.map.on("touchmove", this.alTrazar)
    // En la ventana: el boton puede soltarse fuera del plano.
    window.addEventListener("mouseup", this.alSoltar)
    window.addEventListener("touchend", this.alSoltar)
    window.addEventListener("touchcancel", this.alSoltar)
    this._marcando()
  }

  _trazar(e) {
    if (!this.trazo || e.originalEvent.touches?.length > 1) return
    this.trazo.push({x: e.point.x, y: e.point.y, lugar: redondo([e.lngLat.lng, e.lngLat.lat])})
    this._guia([{type: "Feature", properties: {}, geometry: {type: "LineString", coordinates: this.trazo.map(p => p.lugar)}}])
  }

  _soltar() {
    const trazo = this.trazo
    this._dejarTrazo()
    if (!trazo) return
    const largo = trazo.slice(1).reduce((s, p, i) => s + Math.hypot(p.x - trazo[i].x, p.y - trazo[i].y), 0)
    if (largo < MINIMO_PX) return
    const coords = simplificar(trazo)
    const fin = coords[coords.length - 1]
    // El clic que sigue al soltar cerraria la ficha recien abierta.
    setTimeout(() => this._proponer({forma: "trazo", coords}, fin), 0)
  }

  _dejarTrazo() {
    if (this.trazo) this._guia([])
    this.trazo = null
    this.map.off("mousemove", this.alTrazar)
    this.map.off("touchmove", this.alTrazar)
    window.removeEventListener("mouseup", this.alSoltar)
    window.removeEventListener("touchend", this.alSoltar)
    window.removeEventListener("touchcancel", this.alSoltar)
    this._marcando()
  }

  // ------------------------------------------------------------- marcas puestas

  _trazos() {
    const features = [...this.datos.values()].filter(a => a.forma !== "punto").map(a => ({
      type: "Feature",
      properties: {id: a.id, color: tinta(a.lapiz)},
      geometry: {type: "MultiLineString", coordinates: trazos(a)},
    }))
    fuente(this.map, TRAZO, {type: "FeatureCollection", features})
    // Con marcas de una sola persona la firma sobra.
    const autores = new Set([...this.datos.values()].map(a => a.autor))
    this.map.getContainer().classList.toggle("con-firmas", autores.size > 1)
  }

  _dibujar(a, nueva) {
    const ml = this.ml
    const ficha = new ml.Popup({className: "ficha-marca", offset: 12, focusAfterOpen: false, maxWidth: "320px"})
    ficha.on("open", () => this._abrirFicha(ficha, a.id))
    ficha.on("close", () => { if (this.borrador?.id === a.id) this.borrador = null })
    let marca
    if (a.forma === "punto") {
      marca = new ml.Marker({element: elementoPunto(a, nueva)}).setLngLat([a.lon, a.lat])
    } else {
      const {lugar, lado} = ancla(a)
      marca = new ml.Marker({element: elementoNota(a), anchor: lado, offset: [lado === "left" ? 8 : -8, 0]}).setLngLat(lugar)
    }
    const el = marca.getElement()
    el.style.setProperty("--lapiz", `var(--lapiz-${a.lapiz})`)
    el.title = `${a.texto || `${NOMBRES[a.forma]} sin nota`}${a.detalle ? ", con nota larga" : ""}, de ${a.autor}`
    el.tabIndex = 0
    el.setAttribute("role", "button")
    el.setAttribute("aria-label", el.title)
    // En este orden: `addTo` quita el oyente de Enter y espacio que pone `setPopup`.
    marca.addTo(this.map).setPopup(ficha)
    this.capas.set(a.id, marca)
  }

  _borrarCapa(id) {
    const marca = this.capas.get(id)
    if (!marca) return
    marca.getPopup()?.remove()
    marca.remove()
    this.capas.delete(id)
  }

  // ---------------------------------------------------------------- fichas

  // La ficha para escribir la nota antes de mandar la marca. Cerrarla sin
  // guardar no deja marca.
  _proponer(forma, lugar) {
    this.nueva?.remove()
    this._guia(forma.forma === "punto" ? [] : this._previa(forma))
    const {el, input} = this._formulario({texto: "", detalle: ""}, "Poner marca", notas => {
      this.push("crear_anotacion", {...forma, ...notas})
      popup.remove()
    })
    const cab = document.createElement("b")
    cab.textContent = NUEVAS[forma.forma]
    el.prepend(cab, this._medida(forma))
    const popup = new this.ml.Popup({className: "ficha-marca", focusAfterOpen: false, maxWidth: "320px"})
      .setLngLat(lugar).setDOMContent(el)
    popup.on("close", () => {
      if (this.nueva !== popup) return
      this.nueva = null
      this._guia([])
    })
    this.nueva = popup.addTo(this.map)
    input.focus({preventScroll: true})
    requestAnimationFrame(() => alcanzar(this.map, popup))
  }

  _abrirFicha(ficha, id) {
    const a = this.datos.get(id)
    if (!a) return
    ficha.setDOMContent(this.borrador?.id === id ? this._editar(ficha, a) : this._leer(ficha, a))
    requestAnimationFrame(() => alcanzar(this.map, ficha))
  }

  _medida(a) {
    const p = document.createElement("span")
    p.className = "ficha-autor"
    p.textContent = [a.autor, medida(a)].filter(Boolean).join(" · ")
    return p
  }

  _leer(ficha, a) {
    const el = document.createElement("div")
    el.className = "ficha"
    el.style.setProperty("--lapiz", `var(--lapiz-${a.lapiz})`)
    el.append(this._medida(a))
    for (const [clase, texto] of [["ficha-texto", a.texto], ["ficha-detalle", a.detalle]]) {
      if (!texto) continue
      const p = document.createElement("div")
      p.className = clase
      p.textContent = texto
      // Una nota larga se desplaza: con teclado, tiene que poder enfocarse.
      if (clase === "ficha-detalle") p.tabIndex = 0
      el.append(p)
    }
    const botones = document.createElement("div")
    botones.className = "acciones"
    const boton = (texto, clase, alClic) => {
      const b = document.createElement("button")
      b.type = "button"
      b.textContent = texto
      b.className = clase
      b.addEventListener("click", alClic)
      botones.append(b)
    }
    boton(a.texto || a.detalle ? "Editar" : "Escribir nota", "chico", () => {
      this.borrador = {id: a.id, texto: a.texto, detalle: a.detalle}
      this._abrirFicha(ficha, a.id)
      ficha.getElement().querySelector("input")?.focus({preventScroll: true})
    })
    boton("Borrar", "chico borrar", () => {
      if (window.confirm("¿Borrar esta marca para todo el equipo?")) this.push("borrar_anotacion", {id: a.id})
    })
    el.append(botones)
    return el
  }

  _editar(ficha, a) {
    const b = this.borrador
    const {el, input, area, botones} = this._formulario(b, "Guardar", notas => {
      this.borrador = null
      this.push("editar_anotacion", {id: a.id, ...notas})
      this._abrirFicha(ficha, a.id)
    })
    el.addEventListener("input", () => Object.assign(b, {texto: input.value, detalle: area.value}))
    if (b.ajeno) {
      const aviso = document.createElement("p")
      aviso.setAttribute("role", "status")
      aviso.textContent = "Alguien más cambió esta marca mientras escribías; si guardas, queda lo tuyo."
      el.prepend(aviso)
    }
    el.prepend(this._medida(a))
    const dejar = document.createElement("button")
    dejar.type = "button"
    dejar.className = "chico"
    dejar.textContent = "No cambiar"
    dejar.addEventListener("click", () => {
      this.borrador = null
      this._abrirFicha(ficha, a.id)
    })
    botones.append(dejar)
    return el
  }

  _formulario({texto, detalle}, boton, alMandar) {
    const el = document.createElement("form")
    el.className = "ficha"
    const campo = (tipo, valor, tope, pista, nombre) => {
      const c = document.createElement(tipo)
      c.value = valor
      c.maxLength = tope
      c.placeholder = pista
      c.setAttribute("aria-label", nombre)
      c.className = "campo"
      return c
    }
    const input = campo("input", texto, 255, "Nota (opcional)", "Nota de la marca, la que sale en el plano")
    const area = campo("textarea", detalle, 5000, "Nota larga, se lee al tocar la marca (opcional)", "Nota larga de la marca")
    area.rows = detalle ? 7 : 3
    const botones = document.createElement("div")
    botones.className = "acciones"
    const mandar = document.createElement("button")
    mandar.type = "submit"
    mandar.textContent = boton
    mandar.className = "chico primario"
    botones.append(mandar)
    el.append(input, area, botones)
    el.addEventListener("submit", e => {
      e.preventDefault()
      alMandar({texto: input.value.trim(), detalle: area.value.trim()})
    })
    return {el, input, area, botones}
  }
}
