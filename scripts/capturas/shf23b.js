// La ficha de vivienda con la serie del SHF de la zona metropolitana (Tonalá, sin
// índice propio), del municipio (Guadalajara) y del estado (Tamazula).
//
//   node shf23b.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciarSinIds, porCadaVista, carpeta } = require("./comun");

const FICHAS = { tonala: "14101", guadalajara: "14039", tamazula: "14085" };

(async () => {
  const dir = carpeta(process.argv[2] || "shf23b");
  const { browser, estado } = await iniciarSinIds();
  const errores = [];
  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    for (const [nombre, cvegeo] of Object.entries(FICHAS)) {
      if (nombre !== "tonala" && (tn !== "escritorio" || modo !== "light")) continue;
      const p = await ctx.newPage();
      p.on("pageerror", (e) => errores.push(`${tn} ${modo} ${nombre}: ${e.message}`));
      await p.goto(`${BASE}/mapa?zona=mun:${cvegeo}&viv=shf_anual&ficha=${cvegeo}&ver=vivienda`);
      await conectado(p);
      const b = p.locator(".charola-boton");
      await quieto(p, 3000);
      if (!(await p.locator("#ficha-vivienda").isVisible()) && (await b.isVisible())) await b.click();
      await p.waitForSelector("#ficha-vivienda", { timeout: 120000 });
      const seccion = p.locator("#ficha-vivienda section[aria-label='Índice SHF']");
      await seccion.scrollIntoViewIfNeeded();
      await quieto(p, 1500);
      await p.screenshot({ path: path.join(dir, `${nombre}-${tn}-${modo}.png`) });
      if (tn === "escritorio" && modo === "light") fs.writeFileSync(path.join(dir, `${nombre}.txt`), await seccion.innerText());
      if (await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth))
        errores.push(`${tn} ${modo} ${nombre}: scroll lateral`);
      await p.close();
    }
  });
  await browser.close();
  console.log(errores.length ? errores.join("\n") : "sin errores");
})();
