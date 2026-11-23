import {crearPlano, alListo, clics, css, escapar, fuente, quitar, bordes, ficha, margenHoja} from "./plano"
import {conZona} from "./zona_plano"

// Plano de /accesibilidad. El LiveView manda "zona" (el contorno del municipio,
// sus AGEB y localidades con los minutos a cada servicio, y los destinos) y
// "estilo" (qué servicio pintar y con qué umbral). Más lejos, más tinta; sin
// dato, solo el borde punteado. Un solo servicio a la vez: nunca se suman.

const raiz = document.documentElement
// Clases por fracción del umbral: hasta la mitad, hasta el umbral, hasta el
// doble y más del doble.
const CORTES = [0.5, 1, 2]
const TINTA = [0.06, 0.2, 0.5, 0.78]

const cifra = n => (n ?? 0).toLocaleString("es-MX")

function clase(minutos, umbral) {
  if (minutos === null || minutos === undefined) return -1
  return CORTES.filter(c => minutos > c * umbral).length
}

function leyenda(umbral) {
  const mitad = (umbral / 2).toLocaleString("es-MX")
  return [
    `${mitad} min o menos`,
    `${mitad} a ${umbral} min`,
    `${umbral} a ${umbral * 2} min`,
    `más de ${umbral * 2} min`,
  ]
}

const opacidadPorClase = ["match", ["get", "k"], 0, TINTA[0], 1, TINTA[1], 2, TINTA[2], 3, TINTA[3], 0]

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
    this.listo = crearPlano(this.el, {alTema: () => { this._pintar(); this.zonaComun.repintar() }, margen: margenHoja}).then(({map, ml}) => {
      this.map = map
      this.ml = ml
      this.leyenda = new Leyenda()
      map.addControl(this.leyenda, "bottom-left")
      this.clic = clics(map)
      this.clic.en("acc-lugares", (f, lugar) => this._fichaLugar(f, lugar))
      this.clic.en("acc-puntos", (f, lugar) => this._fichaLugar(f, lugar))
      this.clic.en("acc-destinos", (f, lugar) =>
        ficha(map, ml, lugar, `<b>${escapar(f.properties.n || "Sin nombre")}</b>`))
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

  _dibujar({zona, plano, destinos, titulos, servicio, umbral}) {
    this.zonaComun.limpiar()
    Object.assign(this, {zona, plano, destinos, titulos, servicio, umbral})
    this._pintar()
    const caja = bordes(zona)
    if (caja) this.map.fitBounds(caja, {padding: margenHoja()})
  },

  _pintar() {
    const map = this.map
    if (!map || !this.plano) return
    quitar(map, "acc-")
    const tinta = css("--f-movilidad")
    const linea = css("--line")

    fuente(map, "acc-zona-f", this.zona)
    map.addLayer({id: "acc-zona", type: "line", source: "acc-zona-f", paint: {"line-color": css("--text"), "line-width": 2.5}})

    // La clase de cada lugar se calcula aquí: MapLibre no lee objetos anidados.
    const conClase = {
      type: "FeatureCollection",
      features: this.plano.features.map((f, i) => ({
        ...f, properties: {i, k: clase(f.properties.m?.[this.servicio], this.umbral)},
      })),
    }
    fuente(map, "acc-lugares-f", conClase)
    const poligono = ["==", ["geometry-type"], "Polygon"]
    const punto = ["==", ["geometry-type"], "Point"]
    const sinDato = ["<", ["get", "k"], 0]
    // Sin dato también toma clics (relleno transparente), como antes.
    map.addLayer({id: "acc-lugares", type: "fill", source: "acc-lugares-f", filter: poligono,
      paint: {"fill-color": tinta, "fill-opacity": ["case", sinDato, 0, opacidadPorClase]}})
    map.addLayer({id: "acc-borde", type: "line", source: "acc-lugares-f", filter: ["all", poligono, ["!", sinDato]],
      paint: {"line-color": tinta, "line-width": 0.5, "line-opacity": 0.6}})
    map.addLayer({id: "acc-sin-dato", type: "line", source: "acc-lugares-f", filter: ["all", poligono, sinDato],
      paint: {"line-color": linea, "line-width": 0.8, "line-dasharray": [3, 3]}})
    map.addLayer({id: "acc-puntos", type: "circle", source: "acc-lugares-f", filter: punto,
      paint: {
        "circle-radius": 5,
        "circle-color": tinta,
        "circle-opacity": ["case", sinDato, 0, opacidadPorClase],
        "circle-stroke-color": ["case", sinDato, linea, tinta],
        "circle-stroke-width": ["case", sinDato, 1, 1.2],
        "circle-stroke-opacity": 0.9,
      }})

    // Miles de paradas de camión taparían el plano: con muchos destinos, puntos chicos.
    const puntos = {...this.destinos, features: this.destinos.features.filter(f => f.properties.s === this.servicio)}
    const muchos = puntos.features.length > 400
    fuente(map, "acc-destinos-f", puntos)
    map.addLayer({id: "acc-destinos", type: "circle", source: "acc-destinos-f",
      paint: {
        "circle-radius": muchos ? 2 : 4.5,
        "circle-color": css("--text"),
        "circle-stroke-color": css("--bg"),
        "circle-stroke-width": muchos ? 0.5 : 1.5,
      }})

    const titulo = this.titulos?.[this.servicio] || ""
    const filas = leyenda(this.umbral).map((t, i) =>
      `<li><span class="muestra" style="background:${tinta};opacity:${Math.max(TINTA[i], 0.25)}"></span>${escapar(t)}</li>`)
    filas.push(`<li><span class="muestra vacia"></span>sin dato</li>`, `<li><span class="muestra punto"></span>${escapar(titulo)}</li>`)
    this.leyenda.el.innerHTML = `<p>Minutos a: ${escapar(titulo)}</p><ul>${filas.join("")}</ul>`
    this.leyenda.el.hidden = false
  },

  _fichaLugar(f, lugar) {
    const p = this.plano.features[f.properties.i].properties
    const m = p.m?.[this.servicio]
    const tipo = p.t === "ageb" ? `AGEB ${escapar(p.c.slice(-4))}` : `Localidad ${escapar(p.c)}`
    const minutos = m === null || m === undefined ? "sin dato" : `${cifra(Math.round(m))} min`
    const texto = `<b>${tipo}</b><br>${cifra(p.p)} personas<br>${escapar(this.titulos?.[this.servicio] || "")}: ${minutos}`
    ficha(this.map, this.ml, lugar, texto)
  },

  destroyed() {
    this.cerrado = true
    this.map?.remove()
  },
}
