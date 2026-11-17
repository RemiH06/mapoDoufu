// Estados con datos que las pantallas vacías no muestran: capas propias
// abiertas, coropleta encima, charola abierta y consulta resuelta.
// Uso: node estados.js <nombre-de-corrida> [filtro-de-estado]
const path = require("path");
const { BASE, conectado, quieto, iniciar, porCadaVista, carpeta } = require("./comun");

const [corrida = "corrida", filtro = ""] = process.argv.slice(2);

const tocar = async (p, sel) => {
  const l = p.locator(sel).first();
  await l.scrollIntoViewIfNeeded().catch(() => {});
  await l.click();
};
// En pantallas angostas las pestañas viven dentro de la charola plegada.
const abrirCharola = async (p) => {
  const b = p.locator(".charola-boton");
  if (await b.isVisible()) await b.click();
};

const estados = (ids) => ({
  // Hasta tres capas propias abiertas, la segunda pintada por columna.
  "mapa-propios": async (p) => {
    if (!ids.capas.length) throw new Error("el equipo no tiene capas (ver subir.js)");
    await p.goto(`${BASE}/mapa?capa=${ids.capas[0]}`);
    await conectado(p);
    await quieto(p);
    for (let i = 0; i < 2; i++) {
      const s = p.locator("#capa_propia_form select");
      if (!(await s.count())) break;
      await s.selectOption({ index: 1 });
      await quieto(p, 2000);
    }
    const pintar = p.locator("form[id^=pintar_] select").first();
    if (await pintar.count()) {
      await pintar.selectOption({ index: 1 });
      await quieto(p, 2000);
    }
  },
  // Jalisco / Zapopan con la coropleta del censo.
  "mapa-coropleta": async (p) => {
    await p.goto(BASE + "/mapa");
    await conectado(p);
    await p.locator("#ubicacion_form select").nth(0).selectOption("14");
    await quieto(p, 2000);
    await p.locator("#ubicacion_form select").nth(1).selectOption("120");
    await quieto(p, 3000);
    await abrirCharola(p);
    await tocar(p, ".charola .pestana[aria-controls=cinta-coropleta]");
    await quieto(p, 1000);
    await tocar(p, "#coropleta_capa_form button:not([type=button])");
    await quieto(p, 4000);
  },
  "mapa-charola": async (p) => {
    await p.goto(BASE + "/mapa" + (ids.capas[0] ? `?capa=${ids.capas[0]}` : ""));
    await conectado(p);
    await quieto(p);
    await abrirCharola(p);
    await p.waitForTimeout(600);
  },
  "buscador-resuelto": async (p) => {
    await p.goto(BASE + "/buscador?q=" + encodeURIComponent("dónde poner una papelería en Zapopan"));
    await conectado(p);
    await quieto(p);
    await tocar(p, "form[phx-submit=resolver] button");
    await quieto(p, 8000);
  },
});

(async () => {
  const { browser, estado, ids } = await iniciar();
  const dir = carpeta(corrida);
  let n = 0;

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    for (const [nombre, pasos] of Object.entries(estados(ids))) {
      if (!nombre.includes(filtro)) continue;
      const p = await ctx.newPage();
      const errores = [];
      p.on("pageerror", (e) => errores.push(e.message.slice(0, 150)));
      await pasos(p).catch((e) => errores.push("paso: " + e.message.split("\n")[0].slice(0, 150)));
      // Una recarga en vivo de dev puede destruir el contexto a media corrida.
      await p.evaluate(() => scrollTo(0, 0)).catch(() => {});
      await p.screenshot({ path: path.join(dir, `${nombre}_${tn}_${modo}.png`) });
      if (errores.length) console.log(`${nombre} ${tn} ${modo}: ${errores.join(" | ")}`);
      await p.close();
      n++;
    }
  });

  console.log(`${n} capturas en ${dir}`);
  await browser.close();
})();
