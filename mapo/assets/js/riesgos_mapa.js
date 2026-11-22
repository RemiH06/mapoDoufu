import {crearPlano, alListo, clics, css, escapar, fuente, quitar, bordes, circulo, ficha, relleno, margenHoja} from "./plano"

// Plano de /riesgos. El LiveView decide la zona y manda lo que hay que dibujar:
// "previa" (el círculo antes de consultar) y "zona" (el contorno y una capa por
// peligro con puntos). Un clic en el plano propone el centro de un círculo.
// Cada capa se prende y apaga sola en el control de capas: nunca se suman.

const raiz = document.documentElement

const COLOR_CAPA = {
  descargas: "--f-urbanismo",
  retc: "--f-seguridad",
  fuego: "--f-movilidad",
}

function colorPunto(clave) {
  if (!clave.startsWith("agua_")) return css(COLOR_CAPA[clave] || "--text")
  return ["match", ["get", "semaforo"],
    "ROJO", css("--r-rojo"), "AMARILLO", css("--r-amarillo"), "VERDE", css("--r-verde"),
    css("--text2")]
}

function textoFicha(clave, p) {
  const filas = []
  // MapLibre entrega las listas de propiedades como texto JSON.
  const incumple = typeof p.incumple === "string" ? JSON.parse(p.incumple) : p.incumple
  if (clave.startsWith("agua_")) {
    filas.push(`<b>${escapar(p.nombre || p.clave)}</b>`, escapar(p.cuerpo), `Semáforo: ${escapar(p.semaforo || "sin")}`)
    if (incumple?.length) filas.push(`Incumple: ${incumple.map(escapar).join(", ")}`)
  } else if (clave === "descargas") {
    filas.push(`<b>Descarga con permiso</b>`, `Uso: ${escapar(p.uso)}`,
      `${escapar(Math.round(p.volumen_anual || 0).toLocaleString("es-MX"))} m³ al año`,
      `Recibe: ${escapar(p.cuerpo_receptor)}`)
  } else if (clave === "retc") {
    filas.push(`<b>${escapar(p.actividad || "Establecimiento")}</b>`, `Último reporte: ${escapar(p.anio)}`)
  } else if (clave === "fuego") {
    filas.push(`<b>Foco de calor</b>`, escapar(p.fecha), `Confianza: ${escapar(p.confianza)}`)
  }
  return filas.filter(Boolean).join("<br>")
}

// Control de capas: una casilla por peligro, con cuántos puntos trae.
class ControlCapas {
  constructor(alCambiar) {
    this.alCambiar = alCambiar
  }
  onAdd() {
    this.el = document.createElement("fieldset")
    this.el.className = "maplibregl-ctrl control-capas"
    this.el.addEventListener("change", e => this.alCambiar(e.target.value, e.target.checked))
    return this.el
  }
  onRemove() {
    this.el.remove()
  }
  poner(capas, visibles) {
    this.el.hidden = capas.length === 0
    this.el.innerHTML = `<legend>Capas</legend>` + capas.map(({clave, titulo, datos}) =>
      `<label><input type="checkbox" value="${escapar(clave)}" ${visibles.has(clave) ? "checked" : ""}>
        ${escapar(titulo)} (${datos.features.length})</label>`).join("")
  }
}

export const RiesgosMapa = {
  mounted() {
    raiz.dataset.piel = "laboral"
    this.capas = []
    this.visibles = new Set()
    this.listo = crearPlano(this.el, {alTema: () => this._pintar(), margen: margenHoja}).then(({map, ml}) => {
      this.map = map
      this.ml = ml
      this.control = new ControlCapas((clave, si) => {
        if (si) this.visibles.add(clave)
        else this.visibles.delete(clave)
        if (map.getLayer(`r-${clave}`)) map.setLayoutProperty(`r-${clave}`, "visibility", si ? "visible" : "none")
      })
      map.addControl(this.control, "top-right")
      this.control.poner([], this.visibles)
      this.clic = clics(map, {
        vacio: lugar => this.pushEvent("punto", {lat: lugar.lat, lon: lugar.lng}),
        cursor: () => "crosshair",
      })
      this.clic.cursor()
    })
    const cuando = alListo(this, this.listo)

    this.handleEvent("previa", cuando(({lat, lon, radio_m}) => {
      this.previa = circulo([lon, lat], radio_m)
      this._pintarPrevia()
    }))
    this.handleEvent("zona", cuando(({zona, capas}) => this._dibujar(zona, capas)))
  },

  _pintarPrevia() {
    const map = this.map
    quitar(map, "previa")
    if (!this.previa) return
    fuente(map, "previa-f", this.previa)
    map.addLayer({id: "previa", type: "line", source: "previa-f",
      paint: {"line-color": css("--accent"), "line-width": 2, "line-dasharray": [3, 3]}})
  },

  _dibujar(zona, capas) {
    this.previa = null
    this.zona = zona
    this.capas = capas
    this.visibles = new Set(capas.map(c => c.clave))
    this.control.poner(capas, this.visibles)
    this._pintar()
    const ancho = window.innerWidth > 760
    const caja = bordes(zona)
    if (caja) this.map.fitBounds(caja, {padding: relleno([ancho ? 460 : 20, 40], [40, ancho ? 40 : 260])})
  },

  _pintar() {
    const map = this.map
    if (!map) return
    this._pintarPrevia()
    quitar(map, "r-")
    this.clic.fuera("r-")
    if (!this.zona) return
    quitar(map, "zona")
    fuente(map, "zona-f", this.zona)
    map.addLayer({id: "zona", type: "line", source: "zona-f", paint: {"line-color": css("--text"), "line-width": 2.5}})
    for (const {clave, datos} of this.capas) {
      const id = `r-${clave}`
      fuente(map, `${id}-f`, datos)
      map.addLayer({
        id, type: "circle", source: `${id}-f`,
        layout: {visibility: this.visibles.has(clave) ? "visible" : "none"},
        paint: {
          "circle-radius": clave === "fuego" ? 4 : 7,
          "circle-color": colorPunto(clave),
          "circle-opacity": 0.9,
          "circle-stroke-color": css("--bg"),
          "circle-stroke-width": 1.5,
        },
      })
      this.clic.en(id, (f, lugar) => ficha(map, this.ml, lugar, textoFicha(clave, f.properties)))
    }
  },

  destroyed() {
    this.cerrado = true
    this.map?.remove()
  },
}
