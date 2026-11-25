import {crearPlano, alListo, clics, css, escapar, fuente, quitar, bordes, circulo, ficha, margenHoja} from "./plano"
import {conZona} from "./zona_plano"
import {cargarPeligros, pintarPeligro, textoPeligro, iconoHtml, tintaDe, coloresDe, esPuntos} from "./peligros"

// Plano de /riesgos. El LiveView decide la zona y manda lo que hay que dibujar:
// "previa" (el círculo antes de consultar), "zona" (el contorno y una capa por
// peligro) y "solo" (el peligro elegido en la hoja, o ninguno). Un clic en el
// plano propone el centro de un círculo. Cada capa se prende y apaga sola en la
// leyenda: nunca se suman.

const raiz = document.documentElement

// Leyenda y control a la vez: cada peligro con su ícono, su casilla y cuántos hay.
class ControlCapas {
  constructor(alCambiar) {
    this.alCambiar = alCambiar
  }
  onAdd() {
    this.el = document.createElement("details")
    this.el.className = "maplibregl-ctrl control-capas"
    this.el.hidden = true
    this.el.addEventListener("change", e => this.alCambiar(e.target.value, e.target.checked))
    return this.el
  }
  onRemove() {
    this.el.remove()
  }
  poner(capas, visibles) {
    this.el.hidden = capas.length === 0
    const colores = coloresDe([...visibles])
    this.el.innerHTML = `<summary>En el plano</summary>` + capas.map(({clave, titulo, datos}) =>
      `<label><input type="checkbox" value="${escapar(clave)}" ${visibles.has(clave) ? "checked" : ""}>
        ${iconoHtml(clave, tintaDe(clave))} <span>${escapar(titulo)}${esPuntos(clave) ? ` (${(datos.total ?? datos.features.length).toLocaleString("es-MX")})` : ""}</span></label>`).join("") +
      (colores.length ? `<ul class="control-colores">${colores.map(([v, t, hueco]) =>
        `<li><span class="muestra${hueco ? " hueca" : ""}" style="--color:var(${v})"></span>${t}</li>`).join("")}</ul>` : "")
  }
}

export const RiesgosMapa = {
  mounted() {
    raiz.dataset.piel = "laboral"
    cargarPeligros(this.el)
    this.capas = []
    this.visibles = new Set()
    this.listo = crearPlano(this.el, {alTema: () => { this._pintar(); this.zonaComun.repintar() }, margen: margenHoja}).then(({map, ml}) => {
      this.map = map
      this.ml = ml
      this.control = new ControlCapas((clave, si) => {
        if (si) this.visibles.add(clave)
        else this.visibles.delete(clave)
        this._visibilidad()
      })
      map.addControl(this.control, "top-right")
      this.clic = clics(map, {
        vacio: lugar => this.pushEvent("punto", {lat: lugar.lat, lon: lugar.lng}),
        cursor: () => "crosshair",
      })
      this.clic.cursor()
    })
    const cuando = alListo(this, this.listo)
    this.zonaComun = conZona(this, cuando)

    this.handleEvent("previa", cuando(({lat, lon, radio_m}) => {
      this.previa = circulo([lon, lat], radio_m)
      this._pintarPrevia()
    }))
    this.handleEvent("zona", cuando(datos => this._dibujar(datos)))
    this.handleEvent("solo", cuando(({clave}) => {
      this._elegir(clave)
      this._visibilidad()
    }))
  },

  // Con uno elegido, solo ese. Sin elegir, los de puntos: los de áreas (acuíferos,
  // sequía, ANP) taparían todo.
  _elegir(clave) {
    this.visibles = new Set(this.capas.map(c => c.clave).filter(c => clave ? c === clave : esPuntos(c)))
  },

  _visibilidad() {
    for (const {clave} of this.capas) {
      const v = this.visibles.has(clave) ? "visible" : "none"
      for (const id of [`r-${clave}`, `r-${clave}-borde`]) if (this.map.getLayer(id)) this.map.setLayoutProperty(id, "visibility", v)
    }
    this.control.poner(this.capas, this.visibles)
  },

  _pintarPrevia() {
    const map = this.map
    quitar(map, "previa")
    if (!this.previa) return
    fuente(map, "previa-f", this.previa)
    map.addLayer({id: "previa", type: "line", source: "previa-f",
      paint: {"line-color": css("--accent"), "line-width": 2, "line-dasharray": [3, 3]}})
  },

  _dibujar({zona, limites, capas, solo}) {
    this.previa = null
    this.zonaComun.limpiar()
    this.zona = zona
    this.limites = limites
    this.capas = capas
    this._elegir(solo)
    this._pintar()
    const caja = bordes(zona)
    // La hoja puede acabar de cambiar de ancho (lista o matriz). Abierta, la
    // leyenda tapaba los datos donde el plano es angosto.
    requestAnimationFrame(() => {
      const hoja = document.getElementById("hoja").getBoundingClientRect()
      this.control.el.open = window.innerWidth - hoja.right > 700
      if (caja) this.map.fitBounds(caja, {padding: margenHoja()})
    })
  },

  _pintar() {
    const map = this.map
    if (!map) return
    this._pintarPrevia()
    quitar(map, "r-")
    this.clic.fuera("r-")
    if (!this.zona) return
    quitar(map, "zona")
    fuente(map, "zona-l-f", this.limites)
    fuente(map, "zona-f", this.zona)
    // Las áreas debajo de los límites y los puntos encima de todo.
    const poner = capa => {
      const id = pintarPeligro(map, "r-", capa, this.visibles.has(capa.clave))
      this.clic.en(id, (f, lugar) => ficha(map, this.ml, lugar, textoPeligro(capa.clave, capa.datos.features[f.properties._i].properties)))
    }
    this.capas.filter(c => !esPuntos(c.clave)).forEach(poner)
    map.addLayer({id: "zona-l", type: "line", source: "zona-l-f", paint: {"line-color": css("--line"), "line-width": 1}})
    map.addLayer({id: "zona", type: "line", source: "zona-f", paint: {"line-color": css("--text"), "line-width": 2.5}})
    this.capas.filter(c => esPuntos(c.clave)).forEach(poner)
    this._visibilidad()
  },

  destroyed() {
    this.cerrado = true
    this.map?.remove()
  },
}
