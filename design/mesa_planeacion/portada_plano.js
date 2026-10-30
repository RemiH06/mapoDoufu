// Genera el plano de la portada de Phoenix (page_html/plano_portada.html.heex)
// a partir de los datos reales del prototipo (datos.js): los 442 AGEB de
// Guadalajara, la población del censo 2020 por quintil, los 1,858 negocios de
// DENUE con "papel" en el giro y la isócrona de 10 minutos por OSRM.
// Uso: node design/mesa_planeacion/portada_plano.js
const fs = require("fs")
const path = require("path")

global.window = global
eval(fs.readFileSync(path.join(__dirname, "datos.js"), "utf8"))
const {coropleta, voronoi, isocrona} = window.DATOS

const anillos = g => (g.type === "MultiPolygon" ? g.coordinates.flat() : g.coordinates)
const todos = coropleta.features.flatMap(f => anillos(f.geometry)).flat()
const xs = todos.map(p => p[0]), ys = todos.map(p => p[1])
const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
// Misma proyección que el plano de /perfil: la longitud por el coseno de la latitud.
const k = Math.cos(((y0 + y1) / 2) * Math.PI / 180) * 10000
const px = ([x, y]) => [Math.round((x - x0) * k), Math.round((y1 - y) * 10000)]
const trazo = rings => rings.map(r => "M" + r.map(p => px(p).join(",")).join("L") + "Z").join("")

// Quintiles de población, como los cortes que calcula el servidor en /mapa.
const valores = coropleta.features.map(f => f.properties.valor_choropleth).filter(v => v != null).sort((a, b) => a - b)
const cortes = [0.2, 0.4, 0.6, 0.8].map(q => valores[Math.floor(q * (valores.length - 1))])
const clase = v => cortes.filter(c => v > c).length
const porClase = [[], [], [], [], []]
coropleta.features.forEach(f => {
  const v = f.properties.valor_choropleth
  if (v != null) porClase[clase(v)].push(...anillos(f.geometry))
})

const negocios = voronoi.features.map(f => px([f.properties.lon, f.properties.lat]))
const puntos = negocios.map(([x, y]) => `M${x},${y}h0`).join("")

const iso = isocrona.poligono.coordinates[0]
const origen = px([(Math.min(...iso.map(p => p[0])) + Math.max(...iso.map(p => p[0]))) / 2, iso.find(p => p[0] === Math.min(...iso.map(q => q[0])))[1]])

// La marca del equipo: dentro de la isócrona, el AGEB con menos negocios del
// giro a 500 m de su centro y, entre esos, el de más gente. No es un puntaje: la
// nota dice las dos cifras y termina en pregunta.
const dentro = ([x, y], poly) => {
  let c = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j]
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c
  }
  return c
}
const isoPx = iso.map(px)
const centro = rings => {
  const p = rings[0].map(px)
  return [p.reduce((s, q) => s + q[0], 0) / p.length, p.reduce((s, q) => s + q[1], 0) / p.length]
}
const candidatos = coropleta.features
  .map(f => ({c: centro(anillos(f.geometry)), pob: f.properties.valor_choropleth}))
  .filter(a => a.pob != null && dentro(a.c, isoPx))
  .map(a => ({...a, cerca: negocios.filter(([x, y]) => Math.hypot(x - a.c[0], y - a.c[1]) < 500 * 10000 / 111320).length}))
  .sort((a, b) => a.cerca - b.cerca || b.pob - a.pob)
const marca = candidatos[0]
const [ancho, alto] = px([x1, y0])
const r = n => Math.round(n)

const heex = `<%!-- Generado por design/mesa_planeacion/portada_plano.js; no editar a mano. --%>
<svg
  class="plano-portada"
  viewBox="-120 -120 ${ancho + 240} ${alto + 240}"
  preserveAspectRatio="xMidYMid meet"
  aria-hidden="true"
>
  <path class="plano-agebs" d="${trazo(coropleta.features.flatMap(f => anillos(f.geometry)))}" />
  <g class="acetato" data-acetato="censo">
${porClase.map((rings, i) => `    <path class="quintil q${i}" d="${trazo(rings)}" />`).join("\n")}
  </g>
  <g class="acetato" data-acetato="denue">
    <path class="negocios" d="${puntos}" />
  </g>
  <g class="acetato" data-acetato="isocrona">
    <path class="isocrona" d="M${isoPx.map(p => p.join(",")).join("L")}Z" />
    <circle class="onda" cx="${origen[0]}" cy="${origen[1]}" r="60" />
    <circle class="origen" cx="${origen[0]}" cy="${origen[1]}" r="38" />
  </g>
  <g class="acetato marca-equipo" data-acetato="marca" data-nota="${marca.pob.toLocaleString("en-US")} habitantes y ${marca.cerca === 1 ? "1 negocio" : marca.cerca + " negocios"} del giro a 500 m">
    <path class="circulo-mano" d="M${r(marca.c[0] + 160)},${r(marca.c[1] - 40)}C${r(marca.c[0] + 170)},${r(marca.c[1] + 120)} ${r(marca.c[0] - 120)},${r(marca.c[1] + 190)} ${r(marca.c[0] - 175)},${r(marca.c[1] + 30)}C${r(marca.c[0] - 220)},${r(marca.c[1] - 110)} ${r(marca.c[0] + 20)},${r(marca.c[1] - 200)} ${r(marca.c[0] + 145)},${r(marca.c[1] - 90)}L${r(marca.c[0] + 185)},${r(marca.c[1] - 140)}" />
    <text class="nota-mano" x="${r(marca.c[0] + 200)}" y="${r(marca.c[1] - 150)}">¿aquí?</text>
  </g>
</svg>
`
const destino = path.join(__dirname, "../../mapo/lib/mapo_web/controllers/page_html/plano_portada.html.heex")
fs.writeFileSync(destino, heex)
console.log({cortes, negocios: negocios.length, marca: {pob: marca.pob, cerca: marca.cerca, c: marca.c.map(r)}, origen, kb: Math.round(heex.length / 1024)})
