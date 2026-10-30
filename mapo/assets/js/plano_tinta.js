// El plano (mosaicos de OSM) se reimprime en las tintas de la piel activa con
// un filtro SVG de duotono: luminancia del mosaico a color, por tramos (la
// idea del retinte por filtro viene de tanGo). Sin servidor de mosaicos
// propio. Lo usan /mapa y /logistica: el CSS aplica el filtro a
// `.plano-leaflet .leaflet-tile-pane`.

const raiz = document.documentElement
const tinta = nombre => getComputedStyle(raiz).getPropertyValue(nombre).trim()
const oscuro = () => raiz.dataset.theme === "dark"

const rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255)
const mezcla = (a, b, f) => "#" + rgb(a).map((x, i) =>
  Math.round(Math.min(1, Math.max(0, x + (rgb(b)[i] - x) * f)) * 255).toString(16).padStart(2, "0")).join("")

// El mapa base se reimprime en las tintas de la piel con un filtro SVG de
// duotono (la idea del retinte por filtro viene de tanGo): luminancia del
// mosaico de OSM a color, por tramos. Sin servidor de mosaicos propio.
function filtroPlano() {
  let filtro = document.getElementById("plano-tinta")
  if (filtro) return filtro
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg")
  svg.setAttribute("width", "0")
  svg.setAttribute("height", "0")
  svg.setAttribute("aria-hidden", "true")
  svg.style.position = "absolute"
  svg.innerHTML = `<filter id="plano-tinta" color-interpolation-filters="sRGB">
    <feColorMatrix type="saturate" values="0"/>
    <feComponentTransfer><feFuncR type="table"/><feFuncG type="table"/><feFuncB type="table"/></feComponentTransfer>
  </filter>`
  document.body.appendChild(svg)
  return svg.querySelector("filter")
}

export function entintar() {
  const [text, line, bg, bg2] = ["--text", "--line", "--bg", "--bg2"].map(tinta)
  if (!text.startsWith("#")) return
  const calles = oscuro() ? mezcla(bg2, line, 0.3) : mezcla(bg, "#F8F9FB", 0.7)
  const medio = oscuro() ? mezcla(bg2, bg, -0.4) : mezcla(bg2, line, 0.12)
  const tramos = [[0, text], [0.45, line], [0.72, medio], [0.9, bg], [1, calles]].map(([t, h]) => [t, rgb(h)])
  const valor = (t, c) => {
    let k = 1
    while (tramos[k][0] < t) k++
    const [t0, a] = tramos[k - 1], [t1, b] = tramos[k], f = (t - t0) / (t1 - t0)
    return (a[c] + (b[c] - a[c]) * f).toFixed(3)
  }
  const muestras = Array.from({length: 41}, (_, i) => i / 40)
  filtroPlano().querySelectorAll("feFuncR, feFuncG, feFuncB").forEach((fn, c) =>
    fn.setAttribute("tableValues", muestras.map(t => valor(t, c)).join(" ")))
}

