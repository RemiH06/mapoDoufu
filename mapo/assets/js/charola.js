// Charola de /mapa: arrastrar una pestaña cambia el orden de la pila de
// acetatos (la de más arriba en la charola, encima en el plano). Con ratón o
// pluma el arrastre empieza al moverse unos pixeles; con el dedo, después de
// dejarlo quieto un momento, para que deslizar siga recorriendo la lista. Al
// soltar se manda el orden entero ("ordenar") y LiveView vuelve a pintar las
// pestañas en él; el clic que sigue al arrastre no abre la cinta. Con teclado
// están los botones "Más arriba" y "Más abajo" de cada cinta.

const UMBRAL = 6
const ESPERA_DEDO = 280

export const Charola = {
  mounted() {
    this.arrastre = null
    this.recienSoltada = false

    this.alBajar = e => {
      const pestana = e.target.closest(".pestana[data-capa]")
      if (!pestana || e.button > 0) return
      this.arrastre = {pestana, x: e.clientX, y: e.clientY, id: e.pointerId, activo: false, listo: e.pointerType !== "touch"}
      if (e.pointerType === "touch") {
        this.arrastre.espera = setTimeout(() => {
          if (!this.arrastre) return
          this.arrastre.listo = true
          pestana.classList.add("lista-para-mover")
        }, ESPERA_DEDO)
      }
    }

    this.alMover = e => {
      const a = this.arrastre
      if (!a || e.pointerId !== a.id) return
      const lejos = Math.hypot(e.clientX - a.x, e.clientY - a.y) > UMBRAL
      if (!a.activo) {
        if (!lejos) return
        // El dedo se movió antes de tiempo: es un desplazamiento, no un arrastre.
        if (!a.listo) return this._soltar()
        a.activo = true
        a.pestana.setPointerCapture?.(e.pointerId)
        a.pestana.classList.add("arrastrando")
        this.el.classList.add("ordenando")
      }
      e.preventDefault()
      this._marcarDestino(e.clientX, e.clientY)
    }

    this.alSoltar = e => {
      const a = this.arrastre
      if (!a || e.pointerId !== a.id) return
      if (a.activo) {
        const orden = this._ordenNuevo()
        this.recienSoltada = true
        if (orden) this.pushEvent("ordenar", {orden})
      }
      this._soltar()
    }

    // El dedo quieto no debe hacer scroll una vez listo para mover.
    this.alTocar = e => { if (this.arrastre?.listo && e.cancelable) e.preventDefault() }

    // Después de arrastrar, el clic no abre la cinta.
    this.alClic = e => {
      if (!this.recienSoltada) return
      this.recienSoltada = false
      e.stopPropagation()
      e.preventDefault()
    }

    this.el.addEventListener("pointerdown", this.alBajar)
    window.addEventListener("pointermove", this.alMover, {passive: false})
    window.addEventListener("pointerup", this.alSoltar)
    window.addEventListener("pointercancel", this.alSoltar)
    this.el.addEventListener("touchmove", this.alTocar, {passive: false})
    this.el.addEventListener("click", this.alClic, true)
  },

  // Las pestañas en fila (escritorio) o en columna (charola abierta en
  // celular): el destino es la primera cuyo centro queda después del puntero.
  // Se compara el borde izquierdo y no la altura: las pestañas puestas van
  // levantadas unos pixeles.
  _marcarDestino(x, y) {
    const pestanas = [...this.el.querySelectorAll(".pestana[data-capa]")]
    const [p0, p1] = pestanas
    const columna = p0 && p1 && Math.abs(p0.getBoundingClientRect().left - p1.getBoundingClientRect().left) < 4
    let destino = null
    for (const p of pestanas) {
      const r = p.getBoundingClientRect()
      const centro = columna ? r.top + r.height / 2 : r.left + r.width / 2
      if ((columna ? y : x) < centro) { destino = p; break }
    }
    pestanas.forEach(p => p.classList.toggle("destino-antes", p === destino))
    this.el.classList.toggle("destino-final", destino === null)
    this.destino = destino
  },

  _ordenNuevo() {
    const a = this.arrastre
    const ids = [...this.el.querySelectorAll(".pestana[data-capa]")].map(p => p.dataset.capa)
    const movida = a.pestana.dataset.capa
    const sin = ids.filter(id => id !== movida)
    const antes = this.destino?.dataset.capa
    const i = antes && antes !== movida ? sin.indexOf(antes) : antes === movida ? ids.indexOf(movida) : sin.length
    const orden = [...sin.slice(0, i), movida, ...sin.slice(i)]
    return orden.join() === ids.join() ? null : orden
  },

  _soltar() {
    const a = this.arrastre
    if (!a) return
    clearTimeout(a.espera)
    a.pestana.classList.remove("arrastrando", "lista-para-mover")
    this.el.querySelectorAll(".destino-antes").forEach(p => p.classList.remove("destino-antes"))
    this.el.classList.remove("ordenando", "destino-final")
    this.arrastre = null
    this.destino = null
  },

  destroyed() {
    window.removeEventListener("pointermove", this.alMover)
    window.removeEventListener("pointerup", this.alSoltar)
    window.removeEventListener("pointercancel", this.alSoltar)
  },
}
