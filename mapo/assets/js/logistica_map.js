import L from "../vendor/leaflet/leaflet"
import {entintar} from "./plano_tinta"

// Plano de /logistica. El estado (paradas, flota, rutas) vive en el
// LiveView; aquí solo se dibuja y se avisa: un clic pone una parada, el
// arrastre la mueve y la ficha de cada marca cambia su demanda, la vuelve
// depósito o la quita. Las rutas se pintan con la tinta de su vehículo
// sobre un halo del color del papel; si dejaron de corresponder a las
// paradas (vigente: false) se quedan desvanecidas y punteadas, igual que
// las que salieron en línea recta (sin geometría de carretera).

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5
const TINTAS = ["--f-movilidad", "--f-urbanismo", "--f-demografia", "--f-comercio", "--f-seguridad"]

const raiz = document.documentElement
const css = nombre => getComputedStyle(raiz).getPropertyValue(nombre).trim()
const tinta = k => css(TINTAS[k % TINTAS.length])

function pin(p) {
  const tipo = p.deposito ? "deposito" : p.ruta === null ? "pendiente" : ""
  const color = !p.deposito && p.ruta !== null ? `style="--v:var(${TINTAS[p.ruta % TINTAS.length]})"` : ""
  return `<span class="pin ${tipo}" ${color}>${p.deposito ? "D" : p.id}</span>`
}

function ficha(p) {
  const quitar = `<button type="button" class="chico" data-accion="quitar" data-id="${p.id}">Quitar</button>`
  if (p.deposito) {
    return `<div class="ficha"><b>Depósito</b><p>Aquí empiezan y terminan todas las rutas.</p>
      <div class="acciones">${quitar}</div></div>`
  }
  return `<div class="ficha"><b>${p.nombre}</b>
    <div class="linea">Demanda <span class="paso">
      <button type="button" data-accion="demanda" data-id="${p.id}" data-d="-1" aria-label="Menos: demanda" ${p.demanda <= 0 ? "disabled" : ""}>−</button>
      <output class="num">${p.demanda}</output>
      <button type="button" data-accion="demanda" data-id="${p.id}" data-d="1" aria-label="Más: demanda">+</button>
    </span></div>
    <div class="acciones">
      <button type="button" class="chico" data-accion="volver_deposito" data-id="${p.id}">Volverla depósito</button>
      ${quitar}
    </div></div>`
}

export const LogisticaMap = {
  mounted() {
    raiz.dataset.piel = "movilidad"
    entintar()
    this.map = L.map(this.el, {zoomControl: false}).setView(CENTRO_MEXICO, ZOOM_MEXICO)
    L.control.zoom({position: "topright"}).addTo(this.map)
    L.control.scale({imperial: false, position: "bottomright"}).addTo(this.map)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    this.capaRutas = L.featureGroup().addTo(this.map)
    this.marcadores = new Map()
    this.paradas = []
    this.rutas = []
    this.vigente = true

    this.map.on("click", e => this.pushEvent("poner", {lat: e.latlng.lat, lon: e.latlng.lng}))

    // Botones de las fichas (viven dentro del mapa, en el popup).
    this.el.addEventListener("click", e => {
      const b = e.target.closest("[data-accion]")
      if (!b) return
      const id = Number(b.dataset.id)
      if (b.dataset.accion !== "demanda") this.marcadores.get(id)?.closePopup()
      if (b.dataset.accion === "demanda") this.pushEvent("demanda", {campo: id, d: Number(b.dataset.d)})
      else this.pushEvent(b.dataset.accion, {id})
    })

    // Pasar sobre una fila de la hoja resalta su marca, y al revés.
    this.alPasar = e => {
      const fila = e.target.closest?.("[data-fila]")
      if (fila) this._resaltar(Number(fila.dataset.fila), e.type === "mouseover")
    }
    document.addEventListener("mouseover", this.alPasar)
    document.addEventListener("mouseout", this.alPasar)

    // Sin encuadrar al poner paradas: quien hace clic ya está viendo dónde
    // la puso, y reencuadrar movería el mapa bajo el cursor.
    this.handleEvent("paradas", ({paradas, vigente}) => {
      this.paradas = paradas
      this.vigente = vigente
      this._marcas()
      this._rutas()
    })
    this.handleEvent("rutas", ({rutas}) => {
      this.rutas = rutas
      this._rutas()
      if (rutas.length) this._encuadrar()
    })

    this.alCambiarTema = () => { entintar(); this._marcas(); this._rutas() }
    window.addEventListener("mapo:tema", this.alCambiarTema)
  },

  // Las marcas se actualizan en su lugar (no se rehacen) para que la ficha
  // abierta no se cierre al cambiar la demanda.
  _marcas() {
    const vivas = new Set(this.paradas.map(p => p.id))
    for (const [id, m] of this.marcadores) {
      if (!vivas.has(id)) { m.remove(); this.marcadores.delete(id) }
    }
    this.paradas.forEach(p => {
      const icono = L.divIcon({className: "", html: pin(p), iconSize: [30, 30], iconAnchor: [15, 15], popupAnchor: [0, -14]})
      let m = this.marcadores.get(p.id)
      if (!m) {
        m = L.marker([p.lat, p.lon], {icon: icono, draggable: true, keyboard: true, title: p.nombre})
          .addTo(this.map)
          .bindPopup("")
        m.on("dragend", () => {
          const {lat, lng} = m.getLatLng()
          this.pushEvent("mover", {id: p.id, lat, lon: lng})
        })
        m.on("mouseover", () => this._resaltar(p.id, true))
        m.on("mouseout", () => this._resaltar(p.id, false))
        this.marcadores.set(p.id, m)
      } else {
        m.setIcon(icono)
        m.setLatLng([p.lat, p.lon])
        m.options.title = p.nombre
      }
      m.setPopupContent(ficha(p))
      m.setZIndexOffset(p.deposito ? 1000 : 0)
    })
  },

  _rutas() {
    this.capaRutas.clearLayers()
    const halo = css("--bg")
    this.rutas.forEach((r, k) => {
      const puntos = r.geometria ? r.geometria.coordinates.map(([lon, lat]) => [lat, lon]) : r.puntos
      const recta = !r.geometria || !this.vigente
      L.polyline(puntos, {color: halo, weight: 8, opacity: this.vigente ? 0.85 : 0.4, interactive: false}).addTo(this.capaRutas)
      L.polyline(puntos, {color: tinta(k), weight: 4, opacity: this.vigente ? 1 : 0.45, dashArray: recta ? "8 7" : null, interactive: false})
        .addTo(this.capaRutas)
    })
  },

  _resaltar(id, si) {
    document.querySelector(`[data-fila="${id}"]`)?.classList.toggle("resalta", si)
    this.marcadores.get(id)?.getElement()?.querySelector(".pin")?.classList.toggle("resalta", si)
  },

  // Encuadra en el hueco que deja la hoja: a la izquierda en escritorio,
  // abajo en celular, a la derecha en celular acostado.
  _encuadrar() {
    const puntos = this.paradas.map(p => [p.lat, p.lon])
    if (puntos.length < 2) return
    const hoja = document.getElementById("hoja").getBoundingClientRect()
    const relleno = hoja.top > innerHeight / 3
      ? {paddingTopLeft: [20, 170], paddingBottomRight: [20, innerHeight - hoja.top + 20]}
      : hoja.left > innerWidth / 3
        ? {paddingTopLeft: [20, 100], paddingBottomRight: [innerWidth - hoja.left + 20, 20]}
        : {paddingTopLeft: [hoja.right + 20, 60], paddingBottomRight: [60, 40]}
    this.map.fitBounds(L.latLngBounds(puntos), {...relleno, maxZoom: 15})
  },

  destroyed() {
    window.removeEventListener("mapo:tema", this.alCambiarTema)
    document.removeEventListener("mouseover", this.alPasar)
    document.removeEventListener("mouseout", this.alPasar)
    raiz.dataset.piel = "urbanismo"
    this.map.remove()
  },
}
