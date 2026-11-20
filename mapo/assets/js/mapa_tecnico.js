import L from "../vendor/leaflet/leaflet"
import {entintar} from "./plano_tinta"
import {Marcas, escapar} from "./marcas"
import {ESTADOS_BBOX} from "./estados_bbox"

// La url viene del archivo de alguien: solo se vuelve liga si es http(s).
const valorFicha = (columna, valor) =>
  columna === "url" && /^https?:\/\//i.test(valor)
    ? `<a href="${escapar(valor)}" target="_blank" rel="noopener noreferrer">${escapar(valor)}</a>`
    : escapar(valor)

// Valor de suelo por AGEB (docs/producto/precio-estimado.md): el catastro tal
// cual, o el rango con la cobertura medida en su municipio. Nunca un número solo
// donde lo que hay es un rango.
const pesos = v => `$${Math.round(v).toLocaleString("es-MX")}`
const valorSuelo = ({fuente, valor, rango_bajo, rango_alto, anio_tabla, cobertura, n_base}) => {
  if (fuente === "catastro")
    return `Catastro ${anio_tabla}: ${pesos(valor)}/m²<br>Mediana de ${n_base} ${n_base === 1 ? "valor" : "valores"} de zona de la tabla`
  if (fuente === "modelo")
    return `Estimado: de ${pesos(rango_bajo)} a ${pesos(rango_alto)}/m² (pesos de ${anio_tabla})<br>` +
      `En AGEB que el modelo no vio de este municipio, el catastro cayó dentro del rango el ${Math.round(cobertura * 100)} % de las veces`
  return "Sin dato: el municipio no tiene tabla de valores ubicada"
}

// Mapa tecnico: cada capa (coropleta, Voronoi, coloreado, isocrona) es un
// acetato sobre el plano. El servidor las prende y apaga por push_event y
// dice el orden de la pila y la piel de la mesa; aqui se pintan con la
// pelicula de su enfoque y el mapa base se reentinta con la piel activa
// (docs/arquitectura/decisiones.md, "Concepto visual"). El contenedor tiene
// phx-update="ignore": lo dibujado vive aqui, nunca en el DOM de LiveView.
//
// Canvas en vez de SVG: una coropleta de estado son ~5 mil poligonos y en
// SVG arrastrar el mapa baja a 30 o 40 fps. Cada acetato tiene su propio
// canvas, para que se mezcle con el plano (mix-blend-mode) por separado.
//
// "Tus marcas" no es un acetato: va encima de todos, sin mezclarse, y sus
// marcas son las de la sesion elegida (marcas.js, compartido con
// /sesiones/:id). Con su cinta abierta, el clic en el plano pone marca; si
// no, y hay isocrona activa, elige el punto de salida.
//
// /buscador usa este mismo hook: le manda las mismas capas, mas "puntos"
// (un punto por negocio) y "pedir_ubicacion" para el punto de partida.

const CENTRO_MEXICO = [23.6345, -102.5528]
const ZOOM_MEXICO = 5
const ENFOQUE = {propios: "consumo", puntos: "comercio", zonas: "comercio", focos: "comercio", coropleta: "demografia", vivienda: "urbanismo", voronoi: "comercio", coloreado: "urbanismo", isocrona: "movilidad"}
// Opacidad de la pelicula por clase: mas valor, mas tinta.
const TINTA_QUINTIL = [0.12, 0.26, 0.42, 0.6, 0.8]
const TINTA_COLOREADO = [0.14, 0.32, 0.5, 0.68]
const ZOOM_PUNTOS = 14
const PIXEL_VACIO = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="

const raiz = document.documentElement
const tinta = nombre => getComputedStyle(raiz).getPropertyValue(nombre).trim()
const oscuro = () => raiz.dataset.theme === "dark"

function clase(valor, cortes) {
  if (valor === null || valor === undefined) return -1
  return cortes.filter(c => valor > c).length
}

// Caja en pantalla de un papel encima del plano, o null si no se ve.
const caja = sel => {
  const r = document.querySelector(sel)?.getBoundingClientRect()
  return r && r.width > 0 ? r : null
}

export const MapaTecnico = {
  mounted() {
    entintar()
    this.map = L.map(this.el, {zoomControl: false}).setView(CENTRO_MEXICO, ZOOM_MEXICO)
    L.control.zoom({position: "topright"}).addTo(this.map)
    L.control.scale({imperial: false, position: "bottomleft"}).addTo(this.map)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; colaboradores de OpenStreetMap",
      maxZoom: 19,
    }).addTo(this.map)

    this.renderers = {}
    Object.keys(ENFOQUE).forEach((id, i) => {
      const pane = this.map.createPane(`p-${id}`)
      pane.classList.add("acetato")
      pane.style.zIndex = 460 - i
      this.renderers[id] = L.canvas({pane: `p-${id}`})
    })
    this.map.createPane("p-marcas").style.zIndex = 480
    this.marcas = new Marcas(this.map, {push: (e, p) => this.pushEvent(e, p), pane: "p-marcas"})
    this.modoMarcas = false

    this.capas = Object.fromEntries(Object.keys(ENFOQUE).map(id => [id, null]))
    this.datos = {...this.capas}
    this.propias = []
    this.modoIsocrona = false
    this.interactivas = true
    this.origen = null

    this.map.on("click", e => {
      if (this.modoMarcas) {
        this.marcas.clic(e.latlng)
      } else if (this.modoIsocrona) {
        this.origen = e.latlng
        this.pushEvent("click_mapa", {lat: e.latlng.lat, lon: e.latlng.lng})
      }
    })
    this.map.on("zoomend", () => this._puntosVoronoi())

    this.handleEvent("capa_coropleta", datos => this._recibir("coropleta", datos))
    this.handleEvent("capa_voronoi", datos => this._recibir("voronoi", datos))
    this.handleEvent("capa_vivienda", datos => this._recibir("vivienda", datos))
    this.handleEvent("capa_coloreado", datos => this._recibir("coloreado", datos))
    this.handleEvent("capa_isocrona", datos => this._recibir("isocrona", datos))
    this.handleEvent("capa_puntos", datos => this._recibir("puntos", datos))
    this.handleEvent("capa_propios", capa => {
      this.propias = [...this.propias.filter(c => c.id !== capa.id), capa]
      this._recibirPropias()
    })
    this.handleEvent("capa_propios_fuera", ({id}) => {
      this.propias = this.propias.filter(c => c.id !== id)
      this._recibirPropias()
    })
    this.handleEvent("capa_zonas", datos => {
      this.datos.zonas = datos.activa ? datos : null
      this._dibujar("zonas")
    })
    // Los focos llegan después de la respuesta, como las zonas: no reencuadran.
    this.handleEvent("capa_focos", datos => {
      this.datos.focos = datos.activa ? datos : null
      this._dibujar("focos")
    })
    this.handleEvent("pedir_ubicacion", () => this._ubicacion())
    this.handleEvent("encuadrar_estado", ({cve_ent}) => {
      const bbox = ESTADOS_BBOX[cve_ent]
      if (bbox) this.map.fitBounds(bbox, this._margen())
    })
    this.handleEvent("centrar", ({lat, lon, zoom}) => {
      this.map.setView([lat, lon], Math.max(this.map.getZoom(), zoom))
    })
    this.handleEvent("modo_isocrona", ({activo}) => {
      this.modoIsocrona = activo
      this._cambioModo()
    })
    this.handleEvent("modo_marcas", ({activo}) => {
      this.modoMarcas = activo
      if (!activo) this.marcas.cancelar()
      this._cambioModo()
    })
    this.handleEvent("marcas", ({anotaciones}) => {
      this.marcas.poner(anotaciones)
      const bordes = this.marcas.bordes()
      if (bordes) this.map.fitBounds(bordes, {...this._margen(), maxZoom: 15})
    })
    this.handleEvent("nueva_anotacion", anotacion => this.marcas.agregar(anotacion, true))
    this.handleEvent("anotacion_actualizada", anotacion => this.marcas.actualizar(anotacion))
    this.handleEvent("anotacion_borrada", ({id}) => this.marcas.quitar(id))
    this.handleEvent("herramienta", ({herramienta}) => this.marcas.usar(herramienta))
    this.handleEvent("orden_capas", ({orden}) => {
      orden.forEach((id, i) => { this.map.getPane(`p-${id}`).style.zIndex = 460 - i })
    })
    this.handleEvent("piel", ({piel}) => {
      raiz.dataset.piel = piel
      this._repintar()
    })
    this.alCambiarTema = () => this._repintar()
    window.addEventListener("mapo:tema", this.alCambiarTema)
  },

  _dibujando() {
    return this.modoMarcas || this.modoIsocrona
  },

  // Mientras se dibuja, los acetatos no toman clics: en canvas, la ficha de
  // una celda detiene el clic y nunca llega al plano, asi que la marca o el
  // origen de la isocrona no se ponian encima del Voronoi o la coropleta.
  _cambioModo() {
    this.el.style.cursor = this._dibujando() ? "crosshair" : ""
    if (this.interactivas === !this._dibujando()) return
    this.interactivas = !this._dibujando()
    Object.keys(this.datos).forEach(id => this._dibujar(id))
  },

  _recibir(id, datos) {
    const nueva = !this.datos[id] && datos.activa
    this.datos[id] = datos.activa ? datos : null
    this._dibujar(id)
    if (nueva) this._deslizar(id)
    const capa = this.capas[id]
    const bordes = capa && capa.getBounds && capa.getBounds()
    if (bordes && bordes.isValid()) this.map.fitBounds(bordes, this._margen())
  },

  // /buscador (data-margen) trae papeles fijos encima del plano: la pregunta
  // y la respuesta. Se miden al encuadrar para que lo encuadrado quede en el
  // hueco entre ellos: a los lados en escritorio y acostado, arriba y abajo
  // en celular. Si el hueco queda muy chico, se ignora la respuesta.
  _margen() {
    if (!("margen" in this.el.dataset)) return this._margenMesa()
    const W = window.innerWidth, H = window.innerHeight
    const pregunta = caja(".pregunta"), respuesta = caja(".respuesta")
    const cabecera = caja(".membrete")
    const arriba = (cabecera ? cabecera.bottom : 0) + 12
    if (W <= 760) {
      const tope = pregunta ? pregunta.bottom + 12 : arriba
      let abajo = respuesta ? H - respuesta.top + 12 : 20
      if (H - tope - abajo < 160) abajo = 20
      return {paddingTopLeft: [20, tope], paddingBottomRight: [20, abajo]}
    }
    // Cada papel empuja el margen del lado donde está su centro.
    let izq = 20, der = 20
    for (const r of [pregunta, respuesta]) {
      if (!r) continue
      if ((r.left + r.right) / 2 < W / 2) izq = Math.max(izq, r.right + 20)
      else der = Math.max(der, W - r.left + 20)
    }
    if (W - izq - der < 200) der = 20
    return {paddingTopLeft: [izq, arriba], paddingBottomRight: [der, 20]}
  },

  // /mapa: lo encuadrado queda entre la cabecera y la cinta abierta (o la
  // charola). Acostado, la cinta va a la izquierda y empuja ese lado.
  _margenMesa() {
    const W = window.innerWidth, H = window.innerHeight
    const cabecera = caja(".membrete"), cinta = caja(".cinta:not([hidden])")
    const charola = caja(".charola")
    const tope = (cabecera ? cabecera.bottom : 0) + 20
    const piso = charola ? charola.top : H
    let izq = 20, abajo = H - piso + 20
    if (cinta && cinta.width < W * 0.6) izq = cinta.right + 20
    else if (cinta) abajo = H - cinta.top + 20
    if (H - tope - abajo < 120) abajo = 20
    if (W - izq - 60 < 200) izq = 20
    return {paddingTopLeft: [izq, tope], paddingBottomRight: [60, abajo]}
  },

  // El acetato entra deslizandose sobre el plano.
  _deslizar(id) {
    const pane = this.map.getPane(`p-${id}`)
    pane.classList.remove("entra")
    void pane.offsetWidth
    pane.classList.add("entra")
  },

  _repintar() {
    entintar()
    Object.keys(this.datos).forEach(id => this._dibujar(id))
  },

  _quitar(id) {
    if (this.capas[id]) {
      this.map.removeLayer(this.capas[id])
      this.capas[id] = null
    }
    if (id === "voronoi" && this.puntos) {
      this.map.removeLayer(this.puntos)
      this.puntos = null
    }
  },

  _dibujar(id) {
    this._quitar(id)
    const datos = this.datos[id]
    if (!datos) return
    const color = tinta(`--f-${ENFOQUE[id]}`)
    const opciones = {pane: `p-${id}`, renderer: this.renderers[id], interactive: this.interactivas}
    this.capas[id] = this[`_${id}`](datos, color, opciones)
    this.capas[id].addTo(this.map)
    if (id === "voronoi") this._puntosVoronoi()
  },

  _estiloQuintil(f, cortes, color) {
    const factor = oscuro() ? 0.85 : 1
    const k = clase(f.properties.valor_choropleth, cortes || [])
    return k < 0
      ? {color: tinta("--line"), weight: 0.6, dashArray: "3 3", fillOpacity: 0}
      : {color, weight: 0.5, opacity: 0.6, fillColor: color, fillOpacity: TINTA_QUINTIL[k] * factor}
  },

  _recibirPropias() {
    this._recibir("propios", {activa: this.propias.length > 0, capas: this.propias})
  },

  // Datos propios: hasta tres capas en el mismo acetato, cada una con su tinta.
  // Los lugares viajan solos y la ficha se pide al abrirla. Lo que llega de un
  // archivo se escapa siempre: la ficha es HTML.
  _propios({capas}, _color, opciones) {
    return L.featureGroup(capas.map(c => this._capaPropia(c, tinta(`--f-${c.tono}`), opciones)))
  },

  _capaPropia({id: capa, puntos, geojson, cortes, raster}, color, opciones) {
    if (raster) return this._raster(raster, color, opciones, capa)
    const circulo = (lugar, extra) => L.circleMarker(lugar, {
      ...opciones, ...extra, radius: 3.5, weight: 1, color: tinta("--bg"), fillColor: color, fillOpacity: 0.9,
    })
    if (puntos) {
      return L.featureGroup(puntos.map(p => circulo([p.lat, p.lon]).on("click", e => this._ficha(e.latlng, {capa, id: p.id}))))
    }
    return L.geoJSON(geojson, {
      ...opciones,
      pointToLayer: (_f, lugar) => circulo(lugar),
      style: f => cortes
        ? this._estiloQuintil(f, cortes, color)
        : {color, weight: 0.8, opacity: 0.8, fillColor: color, fillOpacity: 0.3},
      onEachFeature: (f, c) => c.on("click", e => this._ficha(e.latlng, f.properties.cvegeo ? {capa, clave: f.properties.cvegeo} : {capa, id: f.properties.id})),
    })
  },

  // La imagen trae solo la transparencia de cada quintil: aqui recibe la tinta,
  // para que siga al tema. El clic pide el valor del pixel al servidor.
  _raster({url, oeste, sur, este, norte}, color, {pane}, id) {
    const capa = L.imageOverlay(PIXEL_VACIO, [[sur, oeste], [norte, este]], {pane, interactive: id !== undefined})
    if (id !== undefined) capa.on("click", e => this._ficha(e.latlng, {capa: id, lat: e.latlng.lat, lon: e.latlng.lng}))
    const imagen = new Image()
    imagen.onload = () => {
      const lienzo = document.createElement("canvas")
      lienzo.width = imagen.width
      lienzo.height = imagen.height
      const c = lienzo.getContext("2d")
      c.drawImage(imagen, 0, 0)
      c.globalCompositeOperation = "source-in"
      c.fillStyle = color
      c.fillRect(0, 0, lienzo.width, lienzo.height)
      capa.setUrl(lienzo.toDataURL())
    }
    imagen.src = url
    return capa
  },

  _ficha(lugar, llave) {
    this.pushEvent("ver_fila", llave, ({campos, procedencia, otras}) => {
      const par = ([c, v]) => `<dt>${escapar(c)}</dt><dd>${valorFicha(c, v)}</dd>`
      const filas = campos.map(par).join("")
      // De dónde sale el renglón, aparte de lo que dice.
      const origen = procedencia.length
        ? `<p class="ficha-procedencia">Procedencia</p><dl class="ficha-datos">${procedencia.map(par).join("")}</dl>`
        : ""
      const mas = otras > 0 ? `<p>y ${otras} renglones más en esta zona</p>` : ""
      L.popup({maxHeight: 260}).setLatLng(lugar).setContent(`<dl class="ficha-datos">${filas}</dl>${origen}${mas}`).openOn(this.map)
    })
  },

  _coropleta({geojson, etiqueta, cortes}, color, opciones) {
    return L.geoJSON(geojson, {
      ...opciones,
      style: f => this._estiloQuintil(f, cortes, color),
      onEachFeature: (f, capa) => {
        const valor = f.properties.valor_choropleth
        capa.bindPopup(`<strong>${escapar(etiqueta)}</strong><br>${valor === null || valor === undefined ? "sin dato" : valor.toLocaleString("es-MX")}`)
      },
    })
  },

  // Vivienda: un indicador de una sola fuente, por municipio o por AGEB. El clic abre la
  // ficha del municipio (las cuatro fuentes) en la cinta de la capa.
  _vivienda({geojson, etiqueta, unidad, cortes}, color, opciones) {
    return L.geoJSON(geojson, {
      ...opciones,
      // Valor de suelo por AGEB: las estimadas por rango van con borde punteado.
      style: f => ({
        ...this._estiloQuintil(f, cortes, color),
        ...(f.properties.fuente === "modelo" ? {dashArray: "4 3", weight: 1.2, opacity: 0.9} : {}),
      }),
      onEachFeature: (f, capa) => {
        const {nomgeo, valor_choropleth: valor, cv, nota, cve_mun} = f.properties
        // Por AGEB solo la ventana: la ficha del municipio agranda la cinta y la tapaba.
        if (f.properties.fuente) {
          capa.bindPopup(`<strong>${escapar(nomgeo)}</strong><br>${valorSuelo(f.properties)}`)
          return
        }
        const cifra = valor === null || valor === undefined
          ? `sin dato${nota ? ` (${escapar(nota)})` : ""}`
          : `${valor.toLocaleString("es-MX", {maximumFractionDigits: 1})} ${escapar(unidad)}${cv != null ? ` · CV ${cv.toLocaleString("es-MX", {maximumFractionDigits: 1})}` : ""}`
        capa.bindPopup(`<strong>${escapar(nomgeo)}</strong><br>${escapar(etiqueta)}: ${cifra}`)
        capa.on("click", () => this.pushEvent("ficha_vivienda", {cve_mun}))
      },
    })
  },

  // Las zonas candidatas son AGEB que ya estan en la coropleta: viaja solo la
  // lista de claves, y mover un criterio no reencuadra el plano.
  _zonas({cvegeos}, _color, opciones) {
    const elegidas = new Set(cvegeos)
    const features = (this.datos.coropleta?.geojson.features || []).filter(f => elegidas.has(f.properties.cvegeo))
    const trazo = style => L.geoJSON({type: "FeatureCollection", features}, {...opciones, interactive: false, style})
    // Linea de texto con halo de papel: se lee sobre cualquier tinta y tema.
    return L.featureGroup([
      trazo({color: tinta("--bg"), weight: 4, opacity: 0.95, fill: false}),
      trazo({color: tinta("--text"), weight: 1.8, opacity: 1, fill: false}),
    ])
  },

  // Focos de un rubro que se agrupa (patrones.py): contorno punteado, sin
  // relleno, para no tapar la coropleta ni las zonas.
  _focos({focos}, color, opciones) {
    return L.featureGroup(focos.map(f => L.geoJSON(JSON.parse(f.geojson), {
      ...opciones,
      style: {color, weight: 2, dashArray: "4 3", opacity: 1, fillColor: color, fillOpacity: 0.08},
    }).bindPopup(`${escapar(f.colonia || "Sin colonia")}<br>${f.negocios} del rubro`)))
  },

  _voronoi({geojson}, color, opciones) {
    this.datosPuntos = geojson.features
    return L.geoJSON(geojson, {
      ...opciones,
      style: {color, weight: 0.8, opacity: 0.9, fill: true, fillOpacity: 0},
      onEachFeature: (f, capa) => {
        const nombre = escapar(f.properties.nombre || `Negocio ${f.properties.id}`)
        const otros = f.properties.num_puntos - 1
        capa.bindPopup(otros > 0 ? `${nombre}<br>y ${otros} más en el mismo punto` : nombre)
      },
    })
  },

  // De lejos solo las celdas: miles de puntos a escala de ciudad son una mancha.
  _puntosVoronoi() {
    const ver = this.capas.voronoi && this.map.getZoom() >= ZOOM_PUNTOS
    if (!ver) {
      if (this.puntos) { this.map.removeLayer(this.puntos); this.puntos = null }
      return
    }
    if (this.puntos) return
    const color = tinta("--f-comercio")
    this.puntos = L.layerGroup(this.datosPuntos
      .filter(f => f.properties.lat !== undefined)
      .map(f => L.circleMarker([f.properties.lat, f.properties.lon], {
        pane: "p-voronoi", renderer: this.renderers.voronoi, radius: 2.2, stroke: false, fillColor: color, fillOpacity: 1,
      }))).addTo(this.map)
  },

  _coloreado({geojson}, color, opciones) {
    return L.geoJSON(geojson, {
      ...opciones,
      style: f => ({
        color, weight: 0.8, opacity: 0.7, fillColor: color,
        fillOpacity: TINTA_COLOREADO[(f.properties.color_indice ?? 0) % TINTA_COLOREADO.length],
      }),
      onEachFeature: (f, capa) => capa.bindPopup(escapar(f.properties.nomgeo || f.properties.cvegeo)),
    })
  },

  _puntos({puntos}, color, opciones) {
    return L.featureGroup(puntos.map(p => L.circleMarker([p.lat, p.lon], {
      ...opciones, radius: 3.5, weight: 1, color: tinta("--bg"), fillColor: color, fillOpacity: 0.9,
    }).bindPopup(escapar(p.nombre || "Negocio sin nombre"))))
  },

  // El navegador pregunta antes de dar la ubicacion; si la niega o no hay
  // HTTPS, se dice y queda el clic en el plano.
  _ubicacion() {
    if (!navigator.geolocation) return this.pushEvent("ubicacion_fallida", {})
    navigator.geolocation.getCurrentPosition(
      ({coords}) => {
        this.origen = L.latLng(coords.latitude, coords.longitude)
        this.map.setView(this.origen, Math.max(this.map.getZoom(), 13))
        this.pushEvent("click_mapa", {lat: coords.latitude, lon: coords.longitude})
      },
      () => this.pushEvent("ubicacion_fallida", {}),
      {timeout: 10000},
    )
  },

  _isocrona({poligono, metodo, origen: zona}, color, opciones) {
    const area = L.geoJSON({type: "Feature", properties: {}, geometry: poligono}, {
      ...opciones,
      style: {color, weight: 2, dashArray: "6 4", fillColor: color, fillOpacity: 0.2},
    }).bindPopup(metodo === "osrm_real" ? "Por carretera real" : "Círculo aproximado: OSRM no respondió")
    const partes = [area]
    const origen = zona ? [zona.lat, zona.lon] : this.origen
    if (origen) {
      [4, 9, 14].forEach(r => partes.push(L.circleMarker(origen, {...opciones, radius: r, color, weight: 1.3, fill: false})))
    }
    const grupo = L.featureGroup(partes)
    return grupo
  },

  destroyed() {
    window.removeEventListener("mapo:tema", this.alCambiarTema)
    raiz.dataset.piel = "urbanismo"
    this.marcas.destruir()
    this.map.remove()
  },
}
