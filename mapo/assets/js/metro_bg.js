// Fondo animado del tema metro: grafo de nodos cuadrados moviendose
// lentamente sobre una grilla. Ver design/metro_theme_demo.html para
// la referencia visual original.
//
// Vive en root.html.heex (fuera del contenido que cada LiveView
// controla), no como hook de LiveView: si fuera un phx-hook normal,
// cada vez que el usuario navega de una pantalla a otra (login ->
// registro -> configuracion...) el canvas se destruiria y se volveria
// a montar, reiniciando la animacion. Al inicializarse una sola vez
// como JS plano sobre el canvas que ya vive en el layout raiz, sigue
// corriendo sin interrupcion mientras el usuario navegue entre
// LiveViews (root.html.heex no se vuelve a renderizar en esas
// navegaciones, solo el contenido de adentro). Solo se reinicia en una
// recarga real de pagina (F5, o el primer salto desde una pantalla
// que no es LiveView, como la home).
//
// Se oculta en las pantallas de mapa grande (compiten visualmente con
// el contenido): como root.html.heex solo se renderiza en la carga
// inicial, ese "ocultarse" no puede resolverse del lado del servidor
// para navegaciones live posteriores, asi que se revisa la ruta
// actual del lado del cliente, en cada navegacion.
//
// Respeta prefers-reduced-motion y una preferencia guardada en
// localStorage ("mapo:bg-animation" = "off"), que la pantalla de
// configuracion escribe sin tener que tocar este archivo: solo hace
// falta despachar "mapo:toggle-bg-animation" en window con
// {detail: {enabled: true|false}}.

const PALETTES = {
  light: ["#8B1A1A", "#C4691A", "#2A6B3A"],
  dark: ["#ff4560", "#f5a623", "#00e5a0"],
}

const BG = {light: "#F5F0E8", dark: "#0a0c10"}
const GRID = {light: "rgba(200,191,176,0.30)", dark: "rgba(30,37,53,0.55)"}

// Pantallas con mapa grande: el fondo animado no debe aparecer detras.
const RUTAS_SIN_FONDO = ["/mapa", "/coropletas", "/voronoi", "/coloreado"]

function currentTheme() {
  const explicit = document.documentElement.getAttribute("data-theme")
  if (explicit === "dark" || explicit === "light") return explicit
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function animationsEnabled() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return false
  return localStorage.getItem("mapo:bg-animation") !== "off"
}

function ocultoPorRuta() {
  return RUTAS_SIN_FONDO.some(ruta => window.location.pathname.startsWith(ruta))
}

export function iniciarFondoAnimado() {
  const el = document.getElementById("metro-bg")
  if (!el) return

  const ctx = el.getContext("2d")
  let w, h, nodes, theme, raf, running, oculto

  const resize = () => {
    w = el.width = el.clientWidth
    h = el.height = el.clientHeight
  }

  const rebuildNodes = () => {
    const cols = PALETTES[theme]
    nodes = Array.from({length: 36}, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.5,
      vy: (Math.random() - 0.5) * 0.5,
      r: 2 + Math.random() * 3,
      col: cols[Math.floor(Math.random() * cols.length)],
      alpha: 0.35 + Math.random() * 0.45,
    }))
  }

  const drawStatic = () => {
    resize()
    ctx.fillStyle = BG[theme]
    ctx.fillRect(0, 0, w, h)
  }

  const draw = () => {
    ctx.clearRect(0, 0, w, h)
    ctx.fillStyle = BG[theme]
    ctx.fillRect(0, 0, w, h)

    ctx.strokeStyle = GRID[theme]
    ctx.lineWidth = 1
    for (let x = 0; x < w; x += 40) {
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, h)
      ctx.stroke()
    }
    for (let y = 0; y < h; y += 40) {
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(w, y)
      ctx.stroke()
    }

    nodes.forEach(n => {
      n.x += n.vx
      n.y += n.vy
      if (n.x < 0 || n.x > w) n.vx *= -1
      if (n.y < 0 || n.y > h) n.vy *= -1
    })

    const maxD = Math.min(w, h) * 0.2
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x - nodes[j].x
        const dy = nodes[i].y - nodes[j].y
        const d = Math.sqrt(dx * dx + dy * dy)
        if (d < maxD) {
          const s = 1 - d / maxD
          ctx.beginPath()
          ctx.moveTo(nodes[i].x, nodes[i].y)
          ctx.lineTo(nodes[j].x, nodes[j].y)
          ctx.strokeStyle = GRID[theme]
          ctx.globalAlpha = s
          ctx.lineWidth = s * 1.5
          ctx.stroke()
        }
      }
    }
    ctx.globalAlpha = 1

    nodes.forEach(n => {
      const s = n.r * 2
      ctx.fillStyle = n.col
      ctx.globalAlpha = n.alpha
      ctx.fillRect(n.x - s / 2, n.y - s / 2, s, s)
    })
    ctx.globalAlpha = 1

    raf = requestAnimationFrame(draw)
  }

  const pausar = () => {
    if (raf) cancelAnimationFrame(raf)
    raf = null
  }

  const pintar = () => {
    if (oculto) return
    resize()
    if (running) {
      rebuildNodes()
      raf = requestAnimationFrame(draw)
    } else {
      drawStatic()
    }
  }

  const actualizarVisibilidad = () => {
    oculto = ocultoPorRuta()
    el.style.display = oculto ? "none" : ""
    pausar()
    if (!oculto) pintar()
  }

  const onThemeChange = () => {
    const next = currentTheme()
    if (next === theme) return
    theme = next
    if (oculto) return
    if (running) rebuildNodes()
    else drawStatic()
  }

  const onResize = () => {
    if (oculto) return
    resize()
    if (running) rebuildNodes()
    else drawStatic()
  }

  const onToggle = e => {
    running = e.detail?.enabled ?? animationsEnabled()
    pausar()
    if (!oculto) pintar()
  }

  new MutationObserver(onThemeChange).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  })
  window.addEventListener("resize", onResize)
  window.addEventListener("mapo:toggle-bg-animation", onToggle)
  window.addEventListener("phx:page-loading-stop", actualizarVisibilidad)

  running = animationsEnabled()
  theme = currentTheme()
  actualizarVisibilidad()
}
