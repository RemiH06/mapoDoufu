// /mapa con el acetato de vivienda en "Valor de suelo por AGEB" (Jalisco), en
// los tres tamaños y los dos modos: el plano, la ventana de una AGEB con
// catastro y la de una estimada (borde punteado). Deja el texto de la cinta.
//
//   node suelo.js <corrida>
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
  const dir = carpeta(process.argv[2] || "suelo");
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
    await p.selectOption("#vivienda_capa_form select[name='vivienda_capa[indicador]']", "suelo_ageb");
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

    // Una AGEB estimada de Guadalajara (140390001215A, 28 ha). El plano es canvas:
    // se ubica en pantalla con la posición de un mosaico del mapa base (z/x/y).
    const ubicar = () => p.evaluate(([lat, lon]) => {
      for (const img of document.querySelectorAll("img.leaflet-tile")) {
        const m = img.src.match(/\/(\d+)\/(\d+)\/(\d+)(?:@2x)?\.\w+/);
        if (!m) continue;
        const [z, tx, ty] = m.slice(1).map(Number);
        const n = 2 ** z, r = img.getBoundingClientRect();
        const wx = ((lon + 180) / 360) * n;
        const s = Math.sin((lat * Math.PI) / 180);
        const wy = (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n;
        return { x: r.left + (wx - tx) * r.width, y: r.top + (wy - ty) * r.height };
      }
      return null;
    }, [20.662909, -103.358288]);
    // De cerca, para ver el borde punteado de las estimadas junto a las coloreadas.
    let punto = await ubicar();
    if (punto) {
      await p.mouse.move(punto.x, punto.y);
      for (let i = 0; i < 4; i++) {
        await p.mouse.wheel(0, -300);
        await p.waitForTimeout(400);
      }
      await quieto(p, 2500);
      await p.screenshot({ path: path.join(dir, `cerca-${tn}-${modo}.png`) });
      punto = await ubicar();
    }
    if (punto) {
      await p.mouse.click(punto.x, punto.y);
      await quieto(p, 1500);
      await p.screenshot({ path: path.join(dir, `estimada-${tn}-${modo}.png`) });
      const ventana = await p.locator(".leaflet-popup-content").innerText().catch(() => "");
      if (!ventana.includes("Estimado")) errores.push(`${tn} ${modo}: la ventana no es de una estimada: ${ventana}`);
      if (tn === "escritorio" && modo === "light") fs.writeFileSync(path.join(dir, "estimada.txt"), ventana);
    } else errores.push(`${tn} ${modo}: sin mosaicos para ubicar la AGEB`);
    await p.close();
  });

  fs.writeFileSync(path.join(dir, "errores.txt"), errores.join("\n"));
  console.log(errores.length ? errores.join("\n") : "sin errores de página");
  await browser.close();
})();
