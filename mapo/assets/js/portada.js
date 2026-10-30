import {createTimeline, svg, utils} from "../vendor/anime/anime.esm.min.js"

// Portada: la mesa se arma. Sobre el plano de Guadalajara entran, uno tras
// otro, el censo, los negocios de DENUE, la isócrona de 10 minutos y la marca
// del equipo; la mesa se viste con la piel del acetato de arriba, igual que en
// /mapa. Al terminar (o al tocar una pestaña) la charola prende y apaga cada
// acetato.
//
// El HTML ya trae la mesa armada: si este script no carga, o la persona pidió
// movimiento reducido, eso es lo que se ve. Los estados ocultos los pone el
// script justo antes de animar.

const raiz = document.documentElement
const ORDEN = ["censo", "denue", "isocrona", "marca"]
const ROTULO = {
  censo: {
    piel: "demografia",
    tipo: "Cédula censal · INEGI, Censo 2020",
    pregunta: "¿Dónde vive más gente?",
    dato: "Población por AGEB en quintiles: más tinta, más gente.",
  },
  denue: {
    piel: "comercio",
    tipo: "Libro mayor · INEGI, DENUE",
    pregunta: "¿Dónde falta una papelería?",
    dato: "1,858 negocios con «papel» en el giro.",
  },
  isocrona: {
    piel: "movilidad",
    tipo: "Hoja de ruta · OSRM",
    pregunta: "¿Hasta dónde llego en diez minutos?",
    dato: "Por carretera, desde el Centro.",
  },
  marca: {
    piel: null,
    tipo: "Tus marcas · el equipo",
    pregunta: "¿Aquí?",
    dato: "",
  },
}

export function iniciarPortada(portada) {
  const charola = document.getElementById("charola-portada")
  const capas = Object.fromEntries(ORDEN.map(k => [k, portada.querySelector(`[data-acetato="${k}"]`)]))
  const pestanas = Object.fromEntries(ORDEN.map(k => [k, charola.querySelector(`[data-acetato="${k}"]`)]))
  const rotulo = {
    tipo: document.getElementById("rotulo-tipo"),
    pregunta: document.getElementById("rotulo-pregunta"),
    dato: document.getElementById("rotulo-dato"),
  }
  ROTULO.marca.dato = `${capas.marca.dataset.nota}. Mapo junta las fuentes; la decisión la anota el equipo.`
  const visibles = new Set(ORDEN)

  document.querySelectorAll("[data-modo]").forEach(b =>
    b.addEventListener("click", () => window.dispatchEvent(new Event("mapo:modo"))))

  // La piel la pone el acetato impreso de más arriba; la marca no tiene piel.
  function vestir() {
    const arriba = ORDEN.filter(k => visibles.has(k) && ROTULO[k].piel).pop()
    raiz.dataset.piel = arriba ? ROTULO[arriba].piel : "urbanismo"
  }
  function rotular(k) {
    const r = ROTULO[k]
    rotulo.tipo.textContent = r.tipo
    rotulo.pregunta.textContent = r.pregunta
    rotulo.dato.textContent = r.dato
  }
  function poner(k, visible) {
    visible ? visibles.add(k) : visibles.delete(k)
    capas[k].style.display = visible ? "" : "none"
    pestanas[k].setAttribute("aria-pressed", String(visible))
    vestir()
  }

  charola.hidden = false
  let armado = null
  charola.addEventListener("click", e => {
    const pestana = e.target.closest("[data-acetato]")
    if (!pestana) return
    // Tocar la charola a media animación termina de armar la mesa primero.
    if (armado) {
      armado.complete()
      armado = null
    }
    const k = pestana.dataset.acetato
    poner(k, !visibles.has(k))
    const arriba = visibles.has(k) ? k : ORDEN.filter(x => visibles.has(x)).pop()
    if (arriba) rotular(arriba)
  })

  window.addEventListener("pagehide", () => { raiz.dataset.piel = "urbanismo" }, {once: true})

  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    rotular("marca")
    vestir()
    return
  }
  armado = armar(capas, poner, rotular)
}

function armar(capas, poner, rotular) {
  const tapado = "inset(0% 0% 100% 0%)"
  const destapado = "inset(0% 0% 0% 0%)"
  const isocrona = svg.createDrawable(capas.isocrona.querySelector(".isocrona"))
  const circulo = svg.createDrawable(capas.marca.querySelector(".circulo-mano"))
  const nota = capas.marca.querySelector(".nota-mano")
  const onda = capas.isocrona.querySelector(".onda")
  const origen = capas.isocrona.querySelector(".origen")

  ORDEN.forEach(k => poner(k, false))
  utils.set([capas.censo, capas.denue], {clipPath: tapado})
  utils.set(isocrona, {draw: "0 0"})
  utils.set(circulo, {draw: "0 0"})
  utils.set([nota, origen], {opacity: 0})

  // Cada acetato se desliza de arriba abajo (el barrido de la charola de
  // /mapa) y el rótulo cambia a su pregunta en cuanto empieza a entrar.
  const entra = (tl, k, en) => tl
    .call(() => { poner(k, true); rotular(k) }, en)
    .add(capas[k], {clipPath: [tapado, destapado], duration: 900, ease: "out(3)"}, "<<")

  const tl = createTimeline({autoplay: true})
  entra(tl, "censo", 500)
  entra(tl, "denue", "+=1900")
  tl.call(() => { poner("isocrona", true); rotular("isocrona") }, "+=1900")
    .add(origen, {opacity: [0, 1], duration: 300}, "<<")
    .add(isocrona, {draw: ["0 0", "0 1"], duration: 1300, ease: "inOut(2)"}, "<<+=150")
    .add(onda, {r: [60, 520], opacity: [0.8, 0], duration: 1400, ease: "out(2)"}, "<<+=200")
    .call(() => { poner("marca", true); rotular("marca") }, "+=900")
    .add(circulo, {draw: ["0 0", "0 1"], duration: 1000, ease: "inOut(2)"}, "<<")
    .add(nota, {opacity: [0, 1], duration: 400}, "<<+=700")
  return tl
}
