import {crearPlano, alListo, clics, css, escapar, fuente, quitar, bordes, margenHoja} from "./plano"
import {conZona} from "./zona_plano"
import {cargarPeligros, iconoHtml} from "./peligros"
import {pintarServicio, rangosMinutos, TINTA} from "./servicios_capa"

// Plano de /accesibilidad. El LiveView manda "zona" (el contorno, sus límites
// municipales, sus AGEB y localidades con los minutos a cada servicio, y los
// destinos) y "estilo" (qué servicio pintar y con qué umbral).

const raiz = document.documentElement

class Leyenda {
  onAdd() {
    this.el = document.createElement("div")
    this.el.className = "maplibregl-ctrl leyenda-acc"
    this.el.hidden = true
    return this.el
  }
  onRemove() {
    this.el.remove()
  }
}

export const AccesibilidadMapa = {
  mounted() {
    raiz.dataset.piel = "laboral"
    cargarPeligros(this.el)
    this.listo = crearPlano(this.el, {alTema: () => { this._pintar(); this.zonaComun.repintar() }, margen: margenHoja}).then(({map, ml}) => {
      this.map = map
      this.ml = ml
      this.leyenda = new Leyenda()
      map.addControl(this.leyenda, "bottom-left")
      this.clic = clics(map)
    })
    const cuando = alListo(this, this.listo)
    this.zonaComun = conZona(this, cuando)

    this.handleEvent("zona", cuando(datos => this._dibujar(datos)))
    this.handleEvent("estilo", cuando(({servicio, umbral}) => {
      this.servicio = servicio
      this.umbral = umbral
      this._pintar()
    }))
  },

  _dibujar({zona, limites, plano, destinos, titulos, servicio, umbral}) {
    this.zonaComun.limpiar()
    Object.assign(this, {zona, limites, plano, destinos, titulos, servicio, umbral})
    this._pintar()
    const caja = bordes(zona)
    // La hoja puede acabar de cambiar de ancho (lista o matriz).
    if (caja) requestAnimationFrame(() => this.map.fitBounds(caja, {padding: margenHoja()}))
  },

  _pintar() {
    const map = this.map
    if (!map || !this.plano) return
    quitar(map, "acc-")
    const titulo = this.titulos?.[this.servicio] || ""
    pintarServicio(map, this.ml, "acc-", {...this, titulo}, this.clic)
    fuente(map, "acc-limites-f", this.limites)
    map.addLayer({id: "acc-limites", type: "line", source: "acc-limites-f", paint: {"line-color": css("--text2"), "line-width": 1}}, "acc-destinos")
    fuente(map, "acc-zona-f", this.zona)
    map.addLayer({id: "acc-zona", type: "line", source: "acc-zona-f", paint: {"line-color": css("--text"), "line-width": 2.5}}, "acc-destinos")

    const tinta = css("--f-movilidad")
    const filas = rangosMinutos(this.umbral).map((t, i) =>
      `<li><span class="muestra" style="background:color-mix(in srgb, ${tinta} ${TINTA[i] * 100}%, var(--bg))"></span>${escapar(t)}</li>`)
    filas.push(`<li><span class="muestra vacia"></span>sin dato</li>`, `<li><span class="muestra punto"></span>${escapar(titulo)}</li>`)
    this.leyenda.el.innerHTML = `<p>${iconoHtml(this.servicio)}
      Minutos a: ${escapar(titulo)}</p><ul>${filas.join("")}</ul>`
    this.leyenda.el.hidden = !this.servicio
  },

  destroyed() {
    this.cerrado = true
    this.map?.remove()
  },
}
