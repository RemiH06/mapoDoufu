import {crearPlano, alListo, clics, css, escapar, ficha, fuente, quitar, bordes} from "./plano"
import {conZona} from "./zona_plano"

// Plano de /perfil: la gente por km² de cada AGEB (de cada municipio, si la zona es
// muy grande) y el contorno de la zona. El LiveView manda "perfil_plano" al llegar el
// perfil; el contorno provisional y el dibujo son los de siempre (zona_plano.js).

// Cortes fijos, los mismos para todas las zonas: se pueden comparar de una a otra.
const CORTES = {ageb: [2500, 5000, 10000, 20000], municipio: [10, 40, 100, 500]}
const TINTA = [0.08, 0.24, 0.42, 0.62, 0.85]
const MARGEN = 28

const cifra = n => n.toLocaleString("es-MX")

class Leyenda {
  onAdd() {
    this.el = document.createElement("div")
    this.el.className = "maplibregl-ctrl leyenda-acc leyenda-perfil"
    this.el.hidden = true
    return this.el
  }
  onRemove() {
    this.el.remove()
  }
}

export const PerfilMapa = {
  mounted() {
    this.listo = crearPlano(this.el, {
      alTema: () => { this._pintar(); this.zonaComun.repintar() },
      margen: () => MARGEN,
      // Está dentro de una página que se recorre: la rueda sola no lo acerca.
      gestos: true,
    }).then(({map, ml}) => {
      this.map = map
      this.ml = ml
      this.leyenda = new Leyenda()
      map.addControl(this.leyenda, "top-left")
      this.clic = clics(map)
    })
    const cuando = alListo(this, this.listo)
    this.zonaComun = conZona(this, cuando, {margen: () => MARGEN})

    // Otra zona (un parecido, abajo de la página) empieza por su nombre y su plano.
    this.handleEvent("zona_elegida", () => window.scrollTo({top: 0}))

    this.handleEvent("perfil_plano", cuando(({zona, plano}) => {
      this.zonaComun.limpiar()
      this.zona = zona
      this.plano = plano
      this._pintar()
      const caja = bordes(zona)
      if (caja) this.map.fitBounds(caja, {padding: MARGEN, maxZoom: 16})
    }))
  },

  _pintar() {
    const map = this.map
    if (!map || !this.plano) return
    quitar(map, "per-")
    const tinta = css("--f-demografia")
    const cortes = CORTES[this.plano.nivel] || CORTES.ageb
    fuente(map, "per-f", {
      type: "FeatureCollection",
      features: this.plano.features.map((f, i) => {
        const {d, dentro} = f.properties
        const k = d === null ? -1 : cortes.filter(c => d >= c).length
        return {type: "Feature", geometry: f.geometry, properties: {i, k, dentro}}
      }),
    })
    const opacidad = ["match", ["get", "k"], 0, TINTA[0], 1, TINTA[1], 2, TINTA[2], 3, TINTA[3], 4, TINTA[4], 0]
    map.addLayer({id: "per-relleno", type: "fill", source: "per-f",
      // Las vecinas, en tenue: dicen dónde está la zona, no son de ella.
      paint: {"fill-color": tinta, "fill-opacity": ["case", ["get", "dentro"], opacidad, ["*", opacidad, 0.3]]}})
    map.addLayer({id: "per-borde", type: "line", source: "per-f",
      paint: {"line-color": tinta, "line-width": 0.5, "line-opacity": ["case", ["get", "dentro"], 0.55, 0.2]}})
    // El campo: cada localidad sin AGEB, un punto con área según su gente.
    const puntos = this.plano.localidades || []
    const mayor = Math.max(500, ...puntos.map(([, , p]) => p || 0))
    fuente(map, "per-loc-f", {
      type: "FeatureCollection",
      features: puntos.map(([lon, lat, p], i) => ({type: "Feature",
        geometry: {type: "Point", coordinates: [lon, lat]}, properties: {i, r: 1.5 + 8 * Math.sqrt((p || 0) / mayor)}})),
    })
    map.addLayer({id: "per-loc", type: "circle", source: "per-loc-f",
      paint: {"circle-radius": ["get", "r"], "circle-color": tinta, "circle-opacity": 0.55,
        "circle-stroke-color": tinta, "circle-stroke-width": 0.8}})
    fuente(map, "per-zona-f", this.zona)
    map.addLayer({id: "per-zona", type: "line", source: "per-zona-f",
      paint: {"line-color": css("--text"), "line-width": 2.5}})
    this.clic.fuera("per-")
    this.clic.en("per-relleno", (f, lugar) => {
      const p = this.plano.features[f.properties.i].properties
      const nombre = p.n || `AGEB ${p.c.slice(-4)}`
      ficha(map, this.ml, lugar, `<p class="ficha-titulo">${escapar(nombre)}</p><p>${
        p.p === null ? "Sin dato en el censo 2020" : `${cifra(p.p)} personas, ${cifra(p.d)} por km²`}</p>${
        p.dentro ? "" : "<p>Fuera de la zona</p>"}`)
    })

    this.clic.en("per-loc", (f, lugar) => {
      const [, , p, n] = puntos[f.properties.i]
      ficha(map, this.ml, lugar, `<p class="ficha-titulo">${escapar(n)}</p><p>${
        p === null ? "INEGI reserva su población" : `${cifra(p)} personas`}</p>`)
    })

    const rangos = [`menos de ${cifra(cortes[0])}`,
      ...cortes.slice(1).map((c, i) => `${cifra(cortes[i])} a ${cifra(c)}`), `${cifra(cortes[3])} o más`]
    // En el celular la leyenda es una tira con el piso de cada clase.
    const pisos = ["0", ...cortes.map(cifra)]
    this.leyenda.el.innerHTML = `<p>Personas por km², censo 2020</p><ul>${rangos.map((t, i) =>
      `<li><span class="muestra" style="background:color-mix(in srgb, ${tinta} ${TINTA[i] * 100}%, var(--bg))"></span>` +
      `<span class="largo">${t}</span><span class="corto">${pisos[i]}</span></li>`).join("")}</ul>${
      puntos.length ? `<p class="nota-leyenda"><span class="muestra punto"></span>localidad sin AGEB</p>` : ""}`
    this.leyenda.el.hidden = false
  },

  destroyed() {
    this.cerrado = true
    this.map?.remove()
  },
}
