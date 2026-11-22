// Enlace permanente y "Cómo citar" (docs/producto/citar.md): abre /mapa y
// /riesgos desde una URL, revisa que la vista se reconstruya y que la URL se
// corrija, abre la cita, la copia y deja capturas y el texto copiado.
//
//   node citar.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciar, porCadaVista, carpeta } = require("./comun");

const MAPA = "/mapa?ent=14&mun=039&viv=sniiv_acciones&anio=2025&ficha=039&ver=vivienda";
const RARA = "/mapa?ent=99&censo=x%27%3BDROP&alcance=a,b,c&ver=propios";
const RIESGOS = "/riesgos?modo=municipio&ent=14&mun=039&cerca=1000";

(async () => {
  const dir = carpeta(process.argv[2] || "citar");
  const { browser, estado } = await iniciar();
  const errores = [];
  const notas = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE });
    const p = await ctx.newPage();
    p.on("pageerror", (e) => errores.push(`${tn} ${modo}: ${e.message}`));

    await p.goto(BASE + MAPA, { timeout: 120000 });
    await conectado(p);
    await p.waitForSelector("#ficha-vivienda", { timeout: 120000 });
    await quieto(p, 2500);
    if (!p.url().endsWith(MAPA)) errores.push(`${tn} ${modo}: la URL cambió a ${p.url()}`);
    await p.locator("#citar-vivienda").scrollIntoViewIfNeeded();
    await p.locator("#citar-vivienda").click();
    await p.waitForSelector("#cita-vivienda", { timeout: 60000 });
    await quieto(p, 800);
    await p.screenshot({ path: path.join(dir, `mapa-${tn}-${modo}.png`) });
    if (tn === "escritorio" && modo === "light") {
      await p.locator("#cita-vivienda-copiar-apa-0").click();
      await p.waitForTimeout(300);
      notas.push("Copiado del portapapeles:\n" + (await p.evaluate(() => navigator.clipboard.readText())));
      notas.push("\nCinta:\n" + (await p.locator("#cinta-vivienda").innerText()));
      const ancho = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      if (ancho) errores.push("scroll lateral en escritorio");
    }

    await p.goto(BASE + RARA, { timeout: 120000 });
    await conectado(p);
    await quieto(p, 2000);
    if (tn === "escritorio" && modo === "light") notas.push(`\nURL rara quedó en: ${p.url()}`);

    await p.goto(BASE + RIESGOS, { timeout: 120000 });
    await conectado(p);
    await p.waitForSelector("#riesgos-resultado", { timeout: 180000 });
    await quieto(p, 1500);
    await p.locator("#citar-sequia").scrollIntoViewIfNeeded();
    await p.locator("#citar-sequia").click();
    await p.waitForSelector("#cita-sequia", { timeout: 60000 });
    await p.locator("#cita-sequia").scrollIntoViewIfNeeded();
    await quieto(p, 600);
    await p.screenshot({ path: path.join(dir, `riesgos-${tn}-${modo}.png`) });
    if (tn === "escritorio" && modo === "light") {
      await p.locator("#cita-sequia details summary").click();
      notas.push("\nRiesgos:\n" + (await p.locator("#cita-sequia").innerText()));
    }
    await p.close();
  });

  fs.writeFileSync(path.join(dir, "cita.txt"), notas.join("\n"));
  fs.writeFileSync(path.join(dir, "errores.json"), JSON.stringify(errores, null, 2));
  console.log(errores.length ? errores.join("\n") : "sin errores");
  await browser.close();
})();
