import {crearPlano, alListo, clics, css, oscuro, escapar, fuente, quitar, indexar, bordes, recuadroDePuntos, relleno, ficha} from "./plano"
import {Marcas} from "./marcas"
import {ESTADOS_BBOX} from "./estados_bbox"
import {conZona} from "./zona_plano"

// La url viene del archivo de alguien: solo se vuelve liga si es http(s).
const valorFicha = (columna, valor) =>
  columna === "url" && /^https?:\/\//i.test(valor)
    ? `<a href="${escapar(valor)}" target="_blank" rel="noopener noreferrer">${escapar(valor)}</a>`
    : escapar(valor)

// Precio de oferta por AGEB (docs/producto/precio-estimado.md): la mediana de los
// anuncios tal cual, o el rango con la cobertura medida en su municipio. Nunca un
// número solo donde lo que hay es un rango.
const pesos = v => `$${Math.round(v).toLocaleString("es-MX")}`
const valorPrecio = ({fuente, valor, rango_bajo, rango_alto, anio_tabla, cobertura, n_base, metodo}) => {
  if (fuente === "anuncios")
    return `Precio pedido: ${pesos(valor)} por vivienda (julio de ${anio_tabla})<br>Mediana de unos ${n_base} ${n_base === 1 ? "anuncio" : "anuncios"} de venta (IIEG)`
  if (fuente === "modelo")
    return `Estimado: de ${pesos(rango_bajo)} a ${pesos(rango_alto)} por vivienda (julio de ${anio_tabla})<br>` +
      `En AGEB que el modelo no vio de este municipio, la mediana de anuncios cayó dentro del rango el ${Math.round(cobertura * 100)} % de las veces`
  return `Sin dato: ${metodo ? escapar(metodo) : "el IIEG no tiene anuncios de este municipio"}`
}

// Mapa tecnico: cada capa (coropleta, Voronoi, coloreado, isocrona) es un
// acetato sobre el plano. El servidor las prende y apaga por push_event y
// dice el orden de la pila y la piel de la mesa; aqui se pintan con la
// pelicula de su enfoque. El contenedor tiene phx-update="ignore": lo
// dibujado vive aqui, nunca en el DOM de LiveView.
//
// Cada acetato es un grupo de capas de MapLibre con el prefijo `a-<id>:`;
// el orden de la pila se aplica moviendo los grupos (_ordenar). Todo va en el
// mismo lienzo de WebGL: ya no hay mezcla por acetato (mix-blend-mode), la
// película se ve por su opacidad.
//
// "Tus marcas" no es un acetato: va encima de todos y sus marcas son las de
// la sesion elegida (marcas.js, compartido con /sesiones/:id). Con su cinta
// abierta, el clic en el plano pone marca; si no, y hay isocrona activa,
// elige el punto de salida. Mientras se dibuja, los acetatos no toman clics.
//
// /buscador usa este mismo hook: le manda las mismas capas, mas "puntos"
// (un punto por negocio) y "pedir_ubicacion" para el punto de partida.

const ENFOQUE = {propios: "consumo", puntos: "comercio", zonas: "comercio", focos: "comercio", coropleta: "demografia", vivienda: "urbanismo", voronoi: "comercio", coloreado: "urbanismo", isocrona: "movilidad", transporte: "movilidad"}
// Opacidad de la pelicula por clase: mas valor, mas tinta.
const TINTA_QUINTIL = [0.12, 0.26, 0.42, 0.6, 0.8]
const TINTA_COLOREADO = [0.14, 0.32, 0.5, 0.68]
// Un nivel abajo que en Leaflet (MapLibre usa mosaicos de 512 px).
const ZOOM_PUNTOS = 13
const ZOOM_PARADAS = 13
// Transporte: más seguido, más tinta y más grueso; sin horario, punteado.
const CLASES_CON_HORARIO = ["10", "15", "30", "mas"]
const MASIVO = ["metro", "tren", "tren_ligero", "monorriel", "cable", "funicular"]

const raiz = document.documentElement
const tinta = nombre => css(nombre)

function clase(valor, cortes) {
  if (valor === null || valor === undefined) return -1
  return cortes.filter(c => valor > c).length
}

// Caja en pantalla de un papel encima del plano, o null si no se ve.
const caja = sel => {
  const r = document.querySelector(sel)?.getBoundingClientRect()
  return r && r.width > 0 ? r : null
}

const porClase = (valores, otro = 0) => ["match", ["get", "k"], ...valores.flatMap((v, k) => [k, v]), otro]

export const MapaTecnico = {
  mounted() {
    this.datos = Object.fromEntries(Object.keys(ENFOQUE).map(id => [id, null]))
    this.orden = Object.keys(ENFOQUE)
    this.propias = []
    this.rasters = []
    this.modoIsocrona = false
    this.modoMarcas = false
    this.origen = null

    this.listo = crearPlano(this.el, {escala: "bottom-left", alTema: () => { this._repintar(); this.zonaComun.repintar() }, margen: () => this._margen()})
      .then(({map, ml}) => {
        this.map = map
        this.ml = ml
        this.clic = clics(map, {
          activo: () => !this._dibujando(),
          cursor: () => this._dibujando() ? "crosshair" : "",
          vacio: lugar => this._clicVacio(lugar),
        })
        this.marcas = new Marcas(map, ml, {push: (e, p) => this.pushEvent(e, p), clic: this.clic})
      })
    const cuando = alListo(this, this.listo)
    // La zona del membrete (selector común): su contorno se queda como guía.
    this.zonaComun = conZona(this, cuando, {margen: () => this._margen()})

    this.handleEvent("capa_coropleta", cuando(datos => this._recibir("coropleta", datos)))
    this.handleEvent("capa_voronoi", cuando(datos => this._recibir("voronoi", datos)))
    this.handleEvent("capa_vivienda", cuando(datos => this._recibir("vivienda", datos)))
    this.handleEvent("capa_coloreado", cuando(datos => this._recibir("coloreado", datos)))
    this.handleEvent("capa_isocrona", cuando(datos => this._recibir("isocrona", datos)))
    this.handleEvent("capa_transporte", cuando(datos => this._recibir("transporte", datos)))
    this.handleEvent("capa_puntos", cuando(datos => this._recibir("puntos", datos)))
    this.handleEvent("capa_propios", cuando(capa => {
      this.propias = [...this.propias.filter(c => c.id !== capa.id), capa]
      this._recibirPropias()
    }))
    this.handleEvent("capa_propios_fuera", cuando(({id}) => {
      this.propias = this.propias.filter(c => c.id !== id)
      this._recibirPropias()
    }))
    this.handleEvent("capa_zonas", cuando(datos => {
      this.datos.zonas = datos.activa ? datos : null
      this._dibujar("zonas")
    }))
    // Los focos llegan después de la respuesta, como las zonas: no reencuadran.
    this.handleEvent("capa_focos", cuando(datos => {
      this.datos.focos = datos.activa ? datos : null
      this._dibujar("focos")
    }))
    this.handleEvent("pedir_ubicacion", cuando(() => this._ubicacion()))
    // Lo usa el buscador (/buscador), que todavía elige por estado.
    this.handleEvent("encuadrar_estado", cuando(({cve_ent}) => {
      const bbox = ESTADOS_BBOX[cve_ent]
      // Sin animación: al reconstruir de la URL llega justo antes del acetato.
      if (bbox) this.map.fitBounds([[bbox[0][1], bbox[0][0]], [bbox[1][1], bbox[1][0]]], {padding: this._margen(), animate: false})
    }))
    // El servidor manda zooms de Leaflet: en MapLibre van un nivel abajo.
    this.handleEvent("centrar", cuando(({lat, lon, zoom}) => {
      this.map.jumpTo({center: [lon, lat], zoom: Math.max(this.map.getZoom(), zoom - 1)})
    }))
    this.handleEvent("modo_isocrona", cuando(({activo}) => {
      this.modoIsocrona = activo
      this.clic.cursor()
    }))
    this.handleEvent("modo_marcas", cuando(({activo}) => {
      this.modoMarcas = activo
      if (!activo) this.marcas.cancelar()
      this.clic.cursor()
    }))
    this.handleEvent("marcas", cuando(({anotaciones}) => {
      this.marcas.poner(anotaciones)
      const bordesMarcas = this.marcas.bordes()
      if (bordesMarcas) this.map.fitBounds(bordesMarcas, {padding: this._margen(), maxZoom: 14})
    }))
    this.handleEvent("nueva_anotacion", cuando(anotacion => this.marcas.agregar(anotacion, true)))
    this.handleEvent("anotacion_actualizada", cuando(anotacion => this.marcas.actualizar(anotacion)))
    this.handleEvent("anotacion_borrada", cuando(({id}) => this.marcas.quitar(id)))
    this.handleEvent("herramienta", cuando(({herramienta}) => this.marcas.usar(herramienta)))
    this.handleEvent("orden_capas", cuando(({orden}) => {
      this.orden = [...orden, ...this.orden.filter(id => !orden.includes(id))]
      this._ordenar()
    }))
    this.handleEvent("piel", cuando(({piel}) => {
      raiz.dataset.piel = piel
      this._repintar()
    }))
  },

  _dibujando() {
    return this.modoMarcas || this.modoIsocrona
  },

  _clicVacio(lugar) {
    if (this.modoMarcas) return this.marcas.clic(lugar)
    if (this.modoIsocrona) {
      this.origen = lugar
      return this.pushEvent("click_mapa", {lat: lugar.lat, lon: lugar.lng})
    }
    // Un ráster propio no es una capa con objetos: su clic se reconoce aquí.
    const r = this.rasters.find(({oeste, sur, este, norte}) => lugar.lng >= oeste && lugar.lng <= este && lugar.lat >= sur && lugar.lat <= norte)
    if (r) this._ficha(lugar, {capa: r.capa, lat: lugar.lat, lon: lugar.lng})
  },

  _recibir(id, datos) {
    this.datos[id] = datos.activa ? datos : null
    this._dibujar(id)
    const recuadro = this.datos[id] && this._recuadro(id, this.datos[id])
    if (recuadro) this.map.fitBounds(recuadro, {padding: this._margen()})
  },

  _recuadro(id, d) {
    switch (id) {
      case "puntos": return recuadroDePuntos(d.puntos.map(p => [p.lon, p.lat]))
      case "isocrona": return bordes(d.poligono)
      case "transporte": return bordes(d.rutas)
      case "propios": return bordes(...d.capas.map(c =>
        c.raster ? {type: "MultiPoint", coordinates: [[c.raster.oeste, c.raster.sur], [c.raster.este, c.raster.norte]]}
          : c.puntos ? {type: "MultiPoint", coordinates: c.puntos.map(p => [p.lon, p.lat])}
            : c.geojson))
      default: return d.geojson ? bordes(d.geojson) : null
    }
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
      return relleno([20, tope], [20, abajo])
    }
    // Cada papel empuja el margen del lado donde está su centro.
    let izq = 20, der = 20
    for (const r of [pregunta, respuesta]) {
      if (!r) continue
      if ((r.left + r.right) / 2 < W / 2) izq = Math.max(izq, r.right + 20)
      else der = Math.max(der, W - r.left + 20)
    }
    if (W - izq - der < 200) der = 20
    return relleno([izq, arriba], [der, 20])
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
    return relleno([izq, tope], [60, abajo])
  },

  _repintar() {
    Object.keys(this.datos).forEach(id => this._dibujar(id))
    this.marcas.repintar()
    this._ordenar()
  },

  _quitar(id) {
    quitar(this.map, `a-${id}:`)
    this.clic.fuera(`a-${id}:`)
    if (id === "propios") {
      this.rasters = []
      this.vueltaPropios = (this.vueltaPropios || 0) + 1
    }
  },

  _dibujar(id) {
    this._quitar(id)
    const datos = this.datos[id]
    if (datos) this[`_${id}`](datos, tinta(`--f-${ENFOQUE[id]}`), `a-${id}:`)
    this._ordenar()
  },

  // La pila: el primero de `orden` va arriba. Se mueven los grupos de abajo
  // hacia arriba, cada uno con sus capas en su orden, y al final las marcas.
  _ordenar() {
    const capas = this.map.getStyle().layers.map(l => l.id)
    for (const id of [...this.orden].reverse()) {
      for (const capa of capas) if (capa.startsWith(`a-${id}:`)) this.map.moveLayer(capa)
    }
    this.marcas.alFrente()
  },

  // Coropleta por quintiles: más valor, más tinta; sin dato, solo el borde punteado.
  _quintiles(p, geojson, cortes, color, extra = () => ({})) {
    const map = this.map
    const factor = oscuro() ? 0.85 : 1
    fuente(map, `${p}f`, indexar(geojson, (props, f) => ({k: clase(props.valor_choropleth, cortes || []), ...extra(props, f)})))
    map.addLayer({id: `${p}relleno`, type: "fill", source: `${p}f`,
      paint: {"fill-color": color, "fill-opacity": porClase(TINTA_QUINTIL.map(t => t * factor), 0)}})
    map.addLayer({id: `${p}borde`, type: "line", source: `${p}f`, filter: [">=", ["get", "k"], 0],
      paint: {"line-color": color, "line-width": 0.5, "line-opacity": 0.6}})
    map.addLayer({id: `${p}sin-dato`, type: "line", source: `${p}f`, filter: ["<", ["get", "k"], 0],
      paint: {"line-color": tinta("--line"), "line-width": 0.6, "line-dasharray": [5, 5]}})
    return `${p}relleno`
  },

  _recibirPropias() {
    this._recibir("propios", {activa: this.propias.length > 0, capas: this.propias})
  },

  // Datos propios: hasta tres capas en el mismo acetato, cada una con su tinta.
  // Los lugares viajan solos y la ficha se pide al abrirla. Lo que llega de un
  // archivo se escapa siempre: la ficha es HTML.
  _propios({capas}, _color, p) {
    capas.forEach(c => this._capaPropia(c, tinta(`--f-${c.tono}`), `${p}${c.id}-`))
  },

  _capaPropia({id: capa, puntos, geojson, cortes, raster}, color, p) {
    const map = this.map
    if (raster) return this._raster(raster, color, p, capa)
    const circulo = {"circle-radius": 3.5, "circle-color": color, "circle-opacity": 0.9, "circle-stroke-color": tinta("--bg"), "circle-stroke-width": 1}
    if (puntos) {
      fuente(map, `${p}f`, {type: "FeatureCollection", features: puntos.map(pt => ({type: "Feature", properties: {id: pt.id}, geometry: {type: "Point", coordinates: [pt.lon, pt.lat]}}))})
      map.addLayer({id: `${p}puntos`, type: "circle", source: `${p}f`, paint: circulo})
      this.clic.en(`${p}puntos`, (f, lugar) => this._ficha(lugar, {capa, id: f.properties.id}))
      return
    }
    const llave = i => {
      const props = geojson.features[i].properties || {}
      return props.cvegeo ? {capa, clave: props.cvegeo} : {capa, id: props.id}
    }
    const abrir = (f, lugar) => this._ficha(lugar, llave(f.properties._i))
    const esPunto = ["==", ["geometry-type"], "Point"]
    if (cortes) {
      const relleno = this._quintiles(p, geojson, cortes, color)
      map.setFilter(relleno, ["!", esPunto])
      this.clic.en(relleno, abrir)
    } else {
      fuente(map, `${p}f`, indexar(geojson))
      map.addLayer({id: `${p}relleno`, type: "fill", source: `${p}f`, filter: ["!", esPunto],
        paint: {"fill-color": color, "fill-opacity": 0.3}})
      map.addLayer({id: `${p}borde`, type: "line", source: `${p}f`, filter: ["!", esPunto],
        paint: {"line-color": color, "line-width": 0.8, "line-opacity": 0.8}})
      this.clic.en(`${p}relleno`, abrir)
      this.clic.en(`${p}borde`, abrir)
    }
    map.addLayer({id: `${p}puntos`, type: "circle", source: `${p}f`, filter: esPunto, paint: circulo})
    this.clic.en(`${p}puntos`, abrir)
  },

  // La imagen trae solo la transparencia de cada quintil: aqui recibe la tinta,
  // para que siga al tema. El clic pide el valor del pixel al servidor.
  _raster({url, oeste, sur, este, norte}, color, p, capa) {
    if (capa !== undefined) this.rasters.push({capa, oeste, sur, este, norte})
    const vuelta = this.vueltaPropios
    const imagen = new Image()
    imagen.onload = () => {
      // El acetato se quitó o se redibujó mientras cargaba la imagen.
      if (vuelta !== this.vueltaPropios) return
      const lienzo = document.createElement("canvas")
      lienzo.width = imagen.width
      lienzo.height = imagen.height
      const c = lienzo.getContext("2d")
      c.drawImage(imagen, 0, 0)
      c.globalCompositeOperation = "source-in"
      c.fillStyle = color
      c.fillRect(0, 0, lienzo.width, lienzo.height)
      this.map.addSource(`${p}imagen`, {type: "image", url: lienzo.toDataURL(), coordinates: [[oeste, norte], [este, norte], [este, sur], [oeste, sur]]})
      this.map.addLayer({id: `${p}raster`, type: "raster", source: `${p}imagen`, paint: {"raster-fade-duration": 0}})
      this._ordenar()
    }
    imagen.src = url
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
      ficha(this.map, this.ml, lugar, `<div class="ficha-alta"><dl class="ficha-datos">${filas}</dl>${origen}${mas}</div>`)
    })
  },

  _coropleta({geojson, etiqueta, cortes}, color, p) {
    const relleno = this._quintiles(p, geojson, cortes, color)
    this.clic.en(relleno, (f, lugar) => {
      const valor = geojson.features[f.properties._i].properties.valor_choropleth
      ficha(this.map, this.ml, lugar, `<strong>${escapar(etiqueta)}</strong><br>${valor === null || valor === undefined ? "sin dato" : valor.toLocaleString("es-MX")}`)
    })
  },

  // Vivienda: un indicador de una sola fuente, por municipio o por AGEB. El clic abre la
  // ficha del municipio (las cuatro fuentes) en la cinta de la capa.
  _vivienda({geojson, etiqueta, unidad, cortes}, color, p) {
    const relleno = this._quintiles(p, geojson, cortes, color, props => ({modelo: props.fuente === "modelo"}))
    // Precio por AGEB: las estimadas por rango van con borde punteado.
    this.map.setFilter(`${p}borde`, ["all", [">=", ["get", "k"], 0], ["!", ["get", "modelo"]]])
    this.map.addLayer({id: `${p}estimada`, type: "line", source: `${p}f`, filter: ["all", [">=", ["get", "k"], 0], ["get", "modelo"]],
      paint: {"line-color": color, "line-width": 1.2, "line-opacity": 0.9, "line-dasharray": [3.3, 2.5]}})
    this.clic.en(relleno, (f, lugar) => {
      const props = geojson.features[f.properties._i].properties
      const {nomgeo, valor_choropleth: valor, cv, nota, cve_mun} = props
      // Por AGEB solo la ventana: la ficha del municipio agranda la cinta y la tapaba.
      if (props.fuente) {
        ficha(this.map, this.ml, lugar, `<strong>${escapar(nomgeo)}</strong><br>${valorPrecio(props)}`)
        return
      }
      const cifra = valor === null || valor === undefined
        ? `sin dato${nota ? ` (${escapar(nota)})` : ""}`
        : `${valor.toLocaleString("es-MX", {maximumFractionDigits: 1})} ${escapar(unidad)}${cv != null ? ` · CV ${cv.toLocaleString("es-MX", {maximumFractionDigits: 1})}` : ""}`
      ficha(this.map, this.ml, lugar, `<strong>${escapar(nomgeo)}</strong><br>${escapar(etiqueta)}: ${cifra}`)
      this.pushEvent("ficha_vivienda", {cve_mun})
    })
  },

  // Las zonas candidatas son AGEB que ya estan en la coropleta: viaja solo la
  // lista de claves, y mover un criterio no reencuadra el plano.
  _zonas({cvegeos}, _color, p) {
    const elegidas = new Set(cvegeos)
    const features = (this.datos.coropleta?.geojson.features || []).filter(f => elegidas.has(f.properties.cvegeo))
    fuente(this.map, `${p}f`, {type: "FeatureCollection", features: features.map(f => ({type: "Feature", geometry: f.geometry, properties: {}}))})
    // Linea de texto con halo de papel: se lee sobre cualquier tinta y tema.
    this.map.addLayer({id: `${p}halo`, type: "line", source: `${p}f`, paint: {"line-color": tinta("--bg"), "line-width": 4, "line-opacity": 0.95}})
    this.map.addLayer({id: `${p}linea`, type: "line", source: `${p}f`, paint: {"line-color": tinta("--text"), "line-width": 1.8}})
  },

  // Focos de un rubro que se agrupa (patrones.py): contorno punteado, sin
  // relleno, para no tapar la coropleta ni las zonas.
  _focos({focos}, color, p) {
    const features = focos.map((f, i) => ({type: "Feature", properties: {i}, geometry: JSON.parse(f.geojson)}))
    fuente(this.map, `${p}f`, {type: "FeatureCollection", features})
    this.map.addLayer({id: `${p}relleno`, type: "fill", source: `${p}f`, paint: {"fill-color": color, "fill-opacity": 0.08}})
    this.map.addLayer({id: `${p}borde`, type: "line", source: `${p}f`, paint: {"line-color": color, "line-width": 2, "line-dasharray": [2, 1.5]}})
    this.clic.en(`${p}relleno`, (f, lugar) => {
      const foco = focos[f.properties.i]
      ficha(this.map, this.ml, lugar, `${escapar(foco.colonia || "Sin colonia")}<br>${foco.negocios} del rubro`)
    })
  },

  // De lejos solo las celdas: miles de puntos a escala de ciudad son una mancha.
  // Las celdas de negocios de fuera de la zona (que compiten por su borde) van
  // con un velo y su punto hueco: la parte de la zona que se lleva alguien de afuera.
  _voronoi({geojson}, color, p) {
    const map = this.map
    const fuera = ["==", ["get", "fuera"], 1]
    fuente(map, `${p}f`, indexar(geojson, q => ({fuera: q.fuera ? 1 : 0})))
    map.addLayer({id: `${p}relleno`, type: "fill", source: `${p}f`,
      paint: {"fill-color": color, "fill-opacity": ["case", fuera, 0.14, 0]}})
    map.addLayer({id: `${p}borde`, type: "line", source: `${p}f`, paint: {"line-color": color, "line-width": 0.8, "line-opacity": 0.9}})
    const puntos = geojson.features.filter(f => f.properties.lat !== undefined)
      .map(f => ({type: "Feature", properties: {fuera: f.properties.fuera ? 1 : 0},
        geometry: {type: "Point", coordinates: [f.properties.lon, f.properties.lat]}}))
    fuente(map, `${p}puntos-f`, {type: "FeatureCollection", features: puntos})
    map.addLayer({id: `${p}puntos`, type: "circle", source: `${p}puntos-f`, minzoom: ZOOM_PUNTOS,
      paint: {"circle-radius": 2.2, "circle-color": ["case", fuera, css("--bg"), color],
        "circle-stroke-color": color, "circle-stroke-width": ["case", fuera, 1.2, 0]}})
    this.clic.en(`${p}relleno`, (f, lugar) => {
      const props = geojson.features[f.properties._i].properties
      const nombre = escapar(props.nombre || `Negocio ${props.id}`)
      const otros = props.num_puntos - 1
      const de_fuera = props.fuera ? "<br>Está fuera de la zona y compite por esta parte" : ""
      ficha(map, this.ml, lugar, (otros > 0 ? `${nombre}<br>y ${otros} más en el mismo punto` : nombre) + de_fuera)
    })
  },

  // Rutas del GTFS (o de OSM, sin horarios). Lo masivo lleva un halo de papel
  // para leerse encima de los camiones. Las paradas, solo de cerca.
  _transporte({rutas, paradas, clases, origen, modos}, color, p) {
    const map = this.map
    const c = ["to-string", ["get", "c"]]
    const conHorario = ["in", c, ["literal", CLASES_CON_HORARIO]]
    const masivo = ["in", ["get", "modo"], ["literal", MASIVO]]
    const ancho = ["+", ["match", c, "10", 3, "15", 2.4, "30", 1.8, 1.4], ["case", masivo, 2.5, 0]]
    const opacidad = ["match", c, "10", 1, "15", 0.8, "30", 0.55, "mas", 0.35, 0.6]
    fuente(map, `${p}f`, indexar(rutas, props => ({c: props.c ?? "sin_dato", modo: props.modo ?? ""})))
    map.addLayer({id: `${p}halo`, type: "line", source: `${p}f`, filter: masivo,
      paint: {"line-color": tinta("--bg"), "line-width": ["+", ancho, 3], "line-opacity": 0.9}})
    map.addLayer({id: `${p}lineas`, type: "line", source: `${p}f`, filter: conHorario,
      layout: {"line-join": "round"}, paint: {"line-color": color, "line-width": ancho, "line-opacity": opacidad}})
    map.addLayer({id: `${p}sin-horario`, type: "line", source: `${p}f`, filter: ["!", conHorario],
      paint: {"line-color": color, "line-width": ancho, "line-opacity": opacidad, "line-dasharray": [2.9, 2.9]}})
    const abrirRuta = (f, lugar) => ficha(map, this.ml, lugar, this._fichaRuta(rutas.features[f.properties._i].properties, origen, modos))
    this.clic.en(`${p}lineas`, abrirRuta)
    this.clic.en(`${p}sin-horario`, abrirRuta)

    if (!paradas) return
    fuente(map, `${p}paradas-f`, indexar(paradas, props => ({c: props.c ?? "sin_dato"})))
    map.addLayer({id: `${p}paradas`, type: "circle", source: `${p}paradas-f`, minzoom: ZOOM_PARADAS,
      paint: {"circle-radius": 3, "circle-color": color, "circle-opacity": opacidad, "circle-stroke-color": tinta("--bg"), "circle-stroke-width": 1}})
    this.clic.en(`${p}paradas`, (f, lugar) => {
      const props = paradas.features[f.properties._i].properties
      ficha(map, this.ml, lugar, `<strong>${escapar(props.n || "Parada")}</strong><br>${clases[props.c] || ""}`)
    })
  },

  _fichaRuta({n, l, a, modo, int: cada, vd, est}, origen, modos) {
    const nombre = [n, l].filter(Boolean).map(escapar).join(" · ") || "Ruta sin nombre"
    const quien = [escapar(modos[modo] || modo), a && escapar(a)].filter(Boolean).join(" · ")
    const paso = origen === "osm"
      ? "De OpenStreetMap: sin horarios"
      : cada
        ? `Pasa cada ${cada.toLocaleString("es-MX")} min de 7 a 9 de un día hábil${est ? " (frecuencia del feed, no horario exacto)" : ""}`
        : "Sin pasadas útiles de 7 a 9 de un día hábil"
    const dia = vd ? `<br>${vd.toLocaleString("es-MX")} viajes en el día` : ""
    return `<strong>${nombre}</strong><br>${quien}<br>${paso}${dia}`
  },

  _coloreado({geojson}, color, p) {
    fuente(this.map, `${p}f`, indexar(geojson, props => ({k: (props.color_indice ?? 0) % TINTA_COLOREADO.length})))
    this.map.addLayer({id: `${p}relleno`, type: "fill", source: `${p}f`, paint: {"fill-color": color, "fill-opacity": porClase(TINTA_COLOREADO)}})
    this.map.addLayer({id: `${p}borde`, type: "line", source: `${p}f`, paint: {"line-color": color, "line-width": 0.8, "line-opacity": 0.7}})
    this.clic.en(`${p}relleno`, (f, lugar) => {
      const props = geojson.features[f.properties._i].properties
      ficha(this.map, this.ml, lugar, escapar(props.nomgeo || props.cvegeo))
    })
  },

  _puntos({puntos}, color, p) {
    fuente(this.map, `${p}f`, {type: "FeatureCollection", features: puntos.map((pt, i) => ({type: "Feature", properties: {i}, geometry: {type: "Point", coordinates: [pt.lon, pt.lat]}}))})
    this.map.addLayer({id: `${p}puntos`, type: "circle", source: `${p}f`,
      paint: {"circle-radius": 3.5, "circle-color": color, "circle-opacity": 0.9, "circle-stroke-color": tinta("--bg"), "circle-stroke-width": 1}})
    this.clic.en(`${p}puntos`, (f, lugar) => ficha(this.map, this.ml, lugar, escapar(puntos[f.properties.i].nombre || "Negocio sin nombre")))
  },

  // El navegador pregunta antes de dar la ubicacion; si la niega o no hay
  // HTTPS, se dice y queda el clic en el plano.
  _ubicacion() {
    if (!navigator.geolocation) return this.pushEvent("ubicacion_fallida", {})
    navigator.geolocation.getCurrentPosition(
      ({coords}) => {
        this.origen = {lat: coords.latitude, lng: coords.longitude}
        this.map.jumpTo({center: [coords.longitude, coords.latitude], zoom: Math.max(this.map.getZoom(), 12)})
        this.pushEvent("click_mapa", {lat: coords.latitude, lon: coords.longitude})
      },
      () => this.pushEvent("ubicacion_fallida", {}),
      {timeout: 10000},
    )
  },

  _isocrona({poligono, metodo, origen: zona}, color, p) {
    const map = this.map
    fuente(map, `${p}f`, {type: "Feature", properties: {}, geometry: poligono})
    map.addLayer({id: `${p}area`, type: "fill", source: `${p}f`, paint: {"fill-color": color, "fill-opacity": 0.2}})
    map.addLayer({id: `${p}borde`, type: "line", source: `${p}f`, paint: {"line-color": color, "line-width": 2, "line-dasharray": [3, 2]}})
    this.clic.en(`${p}area`, (_f, lugar) =>
      ficha(map, this.ml, lugar, metodo === "osrm_real" ? "Por carretera real" : "Círculo aproximado: OSRM no respondió"))
    const origen = zona ? [zona.lon, zona.lat] : this.origen && [this.origen.lng, this.origen.lat]
    if (!origen) return
    fuente(map, `${p}origen-f`, {type: "Feature", properties: {}, geometry: {type: "Point", coordinates: origen}})
    ;[4, 9, 14].forEach(r => map.addLayer({id: `${p}origen-${r}`, type: "circle", source: `${p}origen-f`,
      paint: {"circle-radius": r, "circle-opacity": 0, "circle-stroke-color": color, "circle-stroke-width": 1.3}}))
  },

  destroyed() {
    this.cerrado = true
    raiz.dataset.piel = "urbanismo"
    this.marcas?.destruir()
    this.map?.remove()
  },
}
