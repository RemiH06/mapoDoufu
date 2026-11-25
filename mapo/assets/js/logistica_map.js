import {crearPlano, alListo, clics, css, escapar, fuente, quitar, recuadroDePuntos, relleno, margenHoja} from "./plano"

// Plano de /logistica. El estado (paradas, flota, rutas) vive en el
// LiveView; aquí solo se dibuja y se avisa: un clic pone una parada, el
// arrastre la mueve y la ficha de cada marca cambia su demanda, la vuelve
// depósito o la quita. Las rutas se pintan con la tinta de su vehículo
// sobre un halo del color del papel; si dejaron de corresponder a las
// paradas (vigente: false) se quedan desvanecidas y punteadas, igual que
// las que salieron en línea recta (sin geometría de carretera).

const TINTAS = ["--f-movilidad", "--f-urbanismo", "--f-demografia", "--f-comercio", "--f-seguridad"]

const raiz = document.documentElement

function pin(p) {
  const tipo = p.deposito ? "deposito" : p.ruta === null ? "pendiente" : ""
  const color = !p.deposito && p.ruta !== null ? `style="--v:var(${TINTAS[p.ruta % TINTAS.length]})"` : ""
  return `<span class="pin ${tipo}" ${color}>${p.deposito ? "D" : p.id}</span>`
}

function textoFicha(p) {
  const quitar = `<button type="button" class="chico" data-accion="quitar" data-id="${p.id}">Quitar</button>`
  if (p.deposito) {
    return `<div class="ficha"><b>Depósito</b><p>Aquí empiezan y terminan todas las rutas.</p>
      <div class="acciones">${quitar}</div></div>`
  }
  return `<div class="ficha"><b>${escapar(p.nombre)}</b>
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
    this.marcadores = new Map()
    this.paradas = []
    this.rutas = []
    this.vigente = true

    this.listo = crearPlano(this.el, {alTema: () => { this._marcas(); this._rutas() }, margen: margenHoja}).then(({map, ml}) => {
      this.map = map
      this.ml = ml
      this.clic = clics(map, {
        vacio: lugar => this.pushEvent("poner", {lat: lugar.lat, lon: lugar.lng}),
        cursor: () => "crosshair",
      })
      this.clic.cursor()
    })
    const cuando = alListo(this, this.listo)

    // Botones de las fichas (viven dentro del mapa, en el popup).
    this.el.addEventListener("click", e => {
      const b = e.target.closest("[data-accion]")
      if (!b) return
      const id = Number(b.dataset.id)
      if (b.dataset.accion !== "demanda") this.marcadores.get(id)?.getPopup()?.remove()
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
    this.handleEvent("paradas", cuando(({paradas, vigente}) => {
      this.paradas = paradas
      this.vigente = vigente
      this._marcas()
      this._rutas()
    }))
    this.handleEvent("rutas", cuando(({rutas}) => {
      this.rutas = rutas
      this._rutas()
      if (rutas.length) this._encuadrar()
    }))
  },

  // Las marcas se actualizan en su lugar (no se rehacen) para que la ficha
  // abierta no se cierre al cambiar la demanda.
  _marcas() {
    const vivas = new Set(this.paradas.map(p => p.id))
    for (const [id, m] of this.marcadores) {
      if (!vivas.has(id)) { m.remove(); this.marcadores.delete(id) }
    }
    this.paradas.forEach(p => {
      let m = this.marcadores.get(p.id)
      if (!m) {
        const el = document.createElement("div")
        el.className = "marca-parada"
        m = new this.ml.Marker({element: el, draggable: true})
          .setLngLat([p.lon, p.lat])
          // En este orden: `addTo` quita el oyente de Enter y espacio que pone `setPopup`.
          .addTo(this.map)
          .setPopup(new this.ml.Popup({offset: 16, focusAfterOpen: false, maxWidth: "300px"}))
        m.on("dragend", () => {
          const {lat, lng} = m.getLngLat()
          this.pushEvent("mover", {id: p.id, lat, lon: lng})
        })
        el.addEventListener("mouseenter", () => this._resaltar(p.id, true))
        el.addEventListener("mouseleave", () => this._resaltar(p.id, false))
        this.marcadores.set(p.id, m)
      } else {
        m.setLngLat([p.lon, p.lat])
      }
      const el = m.getElement()
      el.innerHTML = pin(p)
      el.title = p.nombre
      el.setAttribute("aria-label", p.deposito ? "Depósito" : p.nombre)
      el.style.zIndex = p.deposito ? 2 : 1
      m.getPopup().setHTML(textoFicha(p))
    })
  },

  _rutas() {
    const map = this.map
    quitar(map, "log-")
    if (!this.rutas.length) return
    const features = this.rutas.map((r, k) => ({
      type: "Feature",
      properties: {k: k % TINTAS.length, recta: !r.geometria || !this.vigente},
      geometry: r.geometria || {type: "LineString", coordinates: r.puntos.map(([lat, lon]) => [lon, lat])},
    }))
    fuente(map, "log-rutas-f", {type: "FeatureCollection", features})
    const tinta = ["match", ["get", "k"], ...TINTAS.flatMap((t, k) => [k, css(t)]), css(TINTAS[0])]
    const recta = ["get", "recta"]
    const bordes = {"line-cap": "round", "line-join": "round"}
    map.addLayer({id: "log-halo", type: "line", source: "log-rutas-f", layout: bordes,
      paint: {"line-color": css("--bg"), "line-width": 8, "line-opacity": this.vigente ? 0.85 : 0.4}})
    map.addLayer({id: "log-ruta", type: "line", source: "log-rutas-f", filter: ["!", recta], layout: bordes,
      paint: {"line-color": tinta, "line-width": 4, "line-opacity": this.vigente ? 1 : 0.45}})
    // El guion se mide en anchos de línea: 8 y 7 px con 4 de ancho.
    map.addLayer({id: "log-recta", type: "line", source: "log-rutas-f", filter: recta,
      paint: {"line-color": tinta, "line-width": 4, "line-opacity": this.vigente ? 1 : 0.45, "line-dasharray": [2, 1.75]}})
  },

  _resaltar(id, si) {
    document.querySelector(`[data-fila="${id}"]`)?.classList.toggle("resalta", si)
    this.marcadores.get(id)?.getElement()?.querySelector(".pin")?.classList.toggle("resalta", si)
  },

  // Encuadra en el hueco que deja la hoja: a la izquierda en escritorio,
  // abajo en celular, a la derecha en celular acostado.
  _encuadrar() {
    const puntos = this.paradas.map(p => [p.lon, p.lat])
    if (puntos.length < 2) return
    const hoja = document.getElementById("hoja").getBoundingClientRect()
    const margen = hoja.top > innerHeight / 3
      ? relleno([20, 170], [20, innerHeight - hoja.top + 20])
      : hoja.left > innerWidth / 3
        ? relleno([20, 100], [innerWidth - hoja.left + 20, 20])
        : relleno([hoja.right + 20, 60], [60, 40])
    this.map.fitBounds(recuadroDePuntos(puntos), {padding: margen, maxZoom: 14})
  },

  destroyed() {
    this.cerrado = true
    document.removeEventListener("mouseover", this.alPasar)
    document.removeEventListener("mouseout", this.alPasar)
    raiz.dataset.piel = "urbanismo"
    this.map?.remove()
  },
}
