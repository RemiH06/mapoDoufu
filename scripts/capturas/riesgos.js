// /riesgos con una zona consultada: un municipio (Autlán) y un círculo en el
// plano, en los tres tamaños y los dos modos. Deja también el texto de la hoja
// para revisar las frases sin abrir cada captura.
//
//   node riesgos.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciar, porCadaVista, carpeta } = require("./comun");

(async () => {
  const dir = carpeta(process.argv[2] || "riesgos");
  const { browser, estado } = await iniciar();
  const errores = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    const p = await ctx.newPage();
    p.on("pageerror", (e) => errores.push(`${tn} ${modo}: ${e.message}`));
    await p.goto(BASE + "/riesgos", { timeout: 120000 });
    await conectado(p);
    await p.screenshot({ path: path.join(dir, `vacia-${tn}-${modo}.png`) });

    await p.selectOption("#riesgos_form select[name='riesgos[cve_ent]']", "14");
    await p.waitForSelector("#riesgos_form select[name='riesgos[cve_mun]']");
    await p.selectOption("#riesgos_form select[name='riesgos[cve_mun]']", "015");
    await p.click("#riesgos_form button");
    await p.waitForSelector("#riesgos-resultado", { timeout: 120000 });
    await quieto(p);
    await p.screenshot({ path: path.join(dir, `autlan-${tn}-${modo}.png`) });
    if (tn === "escritorio" && modo === "light") {
      fs.writeFileSync(path.join(dir, "autlan.txt"), await p.locator("#hoja").innerText());
      const ancho = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      if (ancho) errores.push("scroll lateral en escritorio");
    }

    // Círculo de 3 km: un clic en el plano, donde la hoja no lo tapa (sobre Autlán,
    // que quedó encuadrado).
    await p.selectOption("#riesgos_form select[name='riesgos[modo]']", "circulo");
    await p.fill("#riesgos_form input[name='riesgos[radio_km]']", "3");
    const { width, height } = p.viewportSize();
    const [x, y] = tn === "escritorio" ? [width * 0.7, height * 0.5] : tn === "acostado" ? [width * 0.3, height * 0.5] : [width * 0.5, height * 0.22];
    await p.mouse.click(x, y);
    await p.waitForTimeout(800);
    await p.click("#riesgos_form button");
    await p.waitForFunction(() => document.querySelector("#riesgos-resultado h2")?.textContent.includes("círculo"), null, { timeout: 120000 });
    await quieto(p);
    await p.screenshot({ path: path.join(dir, `grullo-${tn}-${modo}.png`) });
    if (tn === "escritorio" && modo === "light") fs.writeFileSync(path.join(dir, "grullo.txt"), await p.locator("#hoja").innerText());
    await p.close();
  });

  fs.writeFileSync(path.join(dir, "errores.txt"), errores.join("\n"));
  console.log(errores.length ? errores.join("\n") : "sin errores de página");
  await browser.close();
})();
