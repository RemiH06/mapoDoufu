// /mapa con el acetato de vivienda en "Precio de oferta por AGEB" (Jalisco), en
// los tres tamaños y los dos modos: el plano, de cerca y la ventana de una AGEB
// estimada (borde punteado). Deja el texto de la cinta.
//
//   node precio_ageb.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciar, porCadaVista, carpeta } = require("./comun");

const tocar = async (p, sel) => {
  const l = p.locator(sel).first();
  await l.scrollIntoViewIfNeeded().catch(() => {});
  await l.click();
};
const abrirCharola = async (p) => {
  const b = p.locator(".charola-boton");
  if (await b.isVisible()) await b.click();
};

(async () => {
  const dir = carpeta(process.argv[2] || "precio_ageb");
  const { browser, estado } = await iniciar();
  const errores = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    const p = await ctx.newPage();
    p.on("pageerror", (e) => errores.push(`${tn} ${modo}: ${e.message}`));
    await p.goto(BASE + "/mapa", { timeout: 120000 });
    await conectado(p);
    await p.locator("#ubicacion_form select").nth(0).selectOption("14");
    await quieto(p, 2000);
    await p.locator("#ubicacion_form select").nth(1).selectOption("039");
    await quieto(p, 3000);
    await abrirCharola(p);
    await tocar(p, ".charola .pestana[aria-controls=cinta-vivienda]");
    await p.waitForSelector("#vivienda_capa_form", { timeout: 60000 });
    await p.selectOption("#vivienda_capa_form select[name='vivienda_capa[indicador]']", "precio_ageb");
    await quieto(p, 800);
    await tocar(p, "#vivienda_capa_form button:not([type=button])");
    await p.waitForSelector("#cinta-vivienda .cinta-metodo", { timeout: 120000 });
    await quieto(p, 3000);
    await p.screenshot({ path: path.join(dir, `plano-${tn}-${modo}.png`) });
    if (tn === "escritorio" && modo === "light") {
      fs.writeFileSync(path.join(dir, "cinta.txt"), await p.locator("#cinta-vivienda").innerText());
      const ancho = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      if (ancho) errores.push("scroll lateral en escritorio");
    }

    // Una AGEB estimada de Guadalajara (1403900013016, 96 ha). El plano es canvas:
    // se ubica en pantalla con el mapa de MapLibre (planoMapo, de plano.js).
    const ubicar = () => p.evaluate(([lat, lon]) => {
      const m = document.querySelector("#mapa-tecnico")?.planoMapo;
      if (!m) return null;
      const r = m.getContainer().getBoundingClientRect(), q = m.project([lon, lat]);
      return { x: r.left + q.x, y: r.top + q.y };
    }, [20.726751, -103.295323]);
    // Si la cinta o un membrete tapan la AGEB, se arrastra el mapa hasta un hueco
    // libre (arriba a la derecha) antes de acercar: el clic caería en el panel.
    const libre = (q) => p.evaluate(({x, y}) => {
      const e = document.elementFromPoint(x, y);
      return !!e && !!e.closest(".maplibregl-map") && !e.closest(".maplibregl-ctrl, .maplibregl-popup");
    }, q);
    const destino = await p.evaluate(() => ({x: innerWidth * 0.75, y: innerHeight * 0.3}));
    const despejar = async (punto) => {
      for (let i = 0; punto && !(await libre(punto)) && i < 8; i++) {
        // Se arrastra desde el hueco libre, de a lo más 200 px por vez.
        const dx = Math.max(-200, Math.min(200, destino.x - punto.x));
        const dy = Math.max(-200, Math.min(200, destino.y - punto.y));
        await p.mouse.move(destino.x, destino.y);
        await p.mouse.down();
        await p.mouse.move(destino.x + dx, destino.y + dy, {steps: 10});
        await p.mouse.up();
        await quieto(p, 800);
        punto = await ubicar();
      }
      return punto;
    };
    let punto = await despejar(await ubicar());
    // De cerca, para ver el borde punteado de las estimadas junto a las coloreadas.
    if (punto) {
      await p.mouse.move(punto.x, punto.y);
      for (let i = 0; i < 4; i++) {
        await p.mouse.wheel(0, -300);
        await p.waitForTimeout(400);
      }
      await quieto(p, 2500);
      punto = await despejar(await ubicar());
      await p.screenshot({ path: path.join(dir, `cerca-${tn}-${modo}.png`) });
    }
    if (punto) {
      await p.mouse.click(punto.x, punto.y);
      await quieto(p, 1500);
      await p.screenshot({ path: path.join(dir, `estimada-${tn}-${modo}.png`) });
      const ventana = await p.locator(".maplibregl-popup-content").innerText().catch(() => "");
      if (!ventana.includes("Estimado")) errores.push(`${tn} ${modo}: la ventana no es de una estimada: ${ventana}`);
      if (tn === "escritorio" && modo === "light") fs.writeFileSync(path.join(dir, "estimada.txt"), ventana);
    } else errores.push(`${tn} ${modo}: sin mosaicos para ubicar la AGEB`);
    await p.close();
  });

  fs.writeFileSync(path.join(dir, "errores.txt"), errores.join("\n"));
  console.log(errores.length ? errores.join("\n") : "sin errores de página");
  await browser.close();
})();
