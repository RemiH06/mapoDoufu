// Cada pantalla de Mapo en 3 tamaños y 2 modos. Mide el scroll lateral y
// junta los errores de consola; el resto se revisa mirando las capturas.
// Uso: node pantallas.js <nombre-de-corrida> [filtro-de-pantalla]
const fs = require("fs");
const path = require("path");
const { BASE, iniciar, porCadaVista, carpeta } = require("./comun");

const [corrida = "corrida", filtro = ""] = process.argv.slice(2);

function pantallas(ids) {
  const lista = [
    ["portada", "/"],
    ["privacidad", "/privacidad"],
    ["entrar", "/users/log-in"],
    ["registro", "/users/register"],
    ["cuenta", "/users/settings"],
    ["equipos", "/teams"],
    ["mapa", "/mapa"],
    ["buscador", "/buscador"],
    ["buscador-consulta", "/buscador?q=" + encodeURIComponent("dónde poner una papelería en Zapopan")],
    ["perfil", "/perfil"],
    ["logistica", "/logistica"],
  ];
  if (ids.equipo) lista.push(["equipo", `/teams/${ids.equipo}`], ["datos", `/teams/${ids.equipo}/datos`]);
  if (ids.cruzable) lista.push(["cruce", `/teams/${ids.equipo}/datos/${ids.cruzable}/cruce`]);
  if (ids.sesion) lista.push(["sesion", `/sesiones/${ids.sesion}`]);
  return lista.filter(([n]) => n.includes(filtro));
}

// Elementos que se salen por la derecha (sin contar los fijos, como la charola).
const medir = () => {
  const fuera = [];
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect();
    if (r.width && r.right > innerWidth + 1 && getComputedStyle(el).position !== "fixed") {
      fuera.push((el.id ? "#" + el.id : el.tagName.toLowerCase()) + "." + [...el.classList].slice(0, 2).join("."));
      if (fuera.length > 4) break;
    }
  }
  const de = document.scrollingElement;
  return { scrollX: de.scrollWidth - innerWidth, alto: de.scrollHeight, fuera };
};

(async () => {
  const { browser, estado, ids } = await iniciar();
  const dir = carpeta(corrida);
  const reporte = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    for (const [n, url] of pantallas(ids)) {
      const p = await ctx.newPage();
      const errores = [];
      p.on("console", (m) => m.type() === "error" && errores.push(m.text().slice(0, 160)));
      p.on("pageerror", (e) => errores.push("pageerror: " + e.message.slice(0, 160)));
      await p.goto(BASE + url, { waitUntil: "networkidle", timeout: 90000 }).catch((e) => errores.push("goto: " + e.message.slice(0, 120)));
      // Sin teselas cargadas la captura de un plano sale en blanco.
      if (await p.locator(".leaflet-container").count()) await p.waitForSelector(".leaflet-tile-loaded", { timeout: 30000 }).catch(() => errores.push("sin teselas"));
      await p.waitForTimeout(n.startsWith("buscador-") ? 6000 : 1500);
      const m = await p.evaluate(medir).catch(() => ({ scrollX: 0, alto: 0, fuera: [] }));
      await p.screenshot({ path: path.join(dir, `${n}_${tn}_${modo}.png`), fullPage: tn !== "acostado" && m.alto < 4000 });
      reporte.push({ pantalla: n, tamano: tn, modo, ...m, errores });
      await p.close();
    }
  });

  fs.writeFileSync(path.join(dir, "reporte.json"), JSON.stringify(reporte, null, 1));
  for (const r of reporte) {
    const avisos = [];
    if (r.scrollX > 0) avisos.push(`scroll lateral de ${r.scrollX} px (${r.fuera.join(", ")})`);
    if (r.errores.length) avisos.push(r.errores.join(" | "));
    if (avisos.length) console.log(`${r.pantalla} ${r.tamano} ${r.modo}: ${avisos.join("; ")}`);
  }
  console.log(`${reporte.length} capturas en ${dir}`);
  await browser.close();
})();
