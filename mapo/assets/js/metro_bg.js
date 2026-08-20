// Fondo animado del tema metro: grafo de nodos cuadrados moviendose
// lentamente sobre una grilla. Ver design/metro_theme_demo.html para
// la referencia visual original.
//
// Respeta prefers-reduced-motion y una preferencia guardada en
// localStorage ("mapo:bg-animation" = "off"), que la pantalla de
// configuracion podra escribir mas adelante sin tener que tocar este
// archivo: solo hace falta despachar "mapo:toggle-bg-animation" en
// window con {detail: {enabled: true|false}}.

const PALETTES = {
  light: ["#8B1A1A", "#C4691A", "#2A6B3A"],
  dark: ["#ff4560", "#f5a623", "#00e5a0"],
}

const BG = {light: "#F5F0E8", dark: "#0a0c10"}
const GRID = {light: "rgba(200,191,176,0.30)", dark: "rgba(30,37,53,0.55)"}

function currentTheme() {
  const explicit = document.documentElement.getAttribute("data-theme")
  if (explicit === "dark" || explicit === "light") return explicit
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function animationsEnabled() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return false
  return localStorage.getItem("mapo:bg-animation") !== "off"
}

export const MetroBg = {
  mounted() {
    const ctx = this.el.getContext("2d")
    let w, h, nodes, theme, raf, running

    const resize = () => {
      w = this.el.width = this.el.clientWidth
      h = this.el.height = this.el.clientHeight
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

    const start = () => {
      running = animationsEnabled()
      theme = currentTheme()
      resize()
      if (running) {
        rebuildNodes()
        raf = requestAnimationFrame(draw)
      } else {
        drawStatic()
      }
    }

    const stop = () => {
      if (raf) cancelAnimationFrame(raf)
      raf = null
    }

    const onThemeChange = () => {
      const next = currentTheme()
      if (next === theme) return
      theme = next
      if (running) rebuildNodes()
      else drawStatic()
    }

    const onResize = () => {
      resize()
      if (running) rebuildNodes()
      else drawStatic()
    }

    const onToggle = e => {
      const enabled = e.detail?.enabled ?? animationsEnabled()
      stop()
      running = enabled
      if (running) {
        rebuildNodes()
        raf = requestAnimationFrame(draw)
      } else {
        drawStatic()
      }
    }

    this._observer = new MutationObserver(onThemeChange)
    this._observer.observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]})
    this._onResize = onResize
    this._onToggle = onToggle
    window.addEventListener("resize", onResize)
    window.addEventListener("mapo:toggle-bg-animation", onToggle)
    this._stop = stop

    start()
  },

  destroyed() {
    this._stop?.()
    this._observer?.disconnect()
    window.removeEventListener("resize", this._onResize)
    window.removeEventListener("mapo:toggle-bg-animation", this._onToggle)
  },
}
