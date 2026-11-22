// Sesión 28: /perfil con los Censos Económicos (libro mayor), el rezago social de
// CONEVAL (cédula) y la hacienda municipal de EFIPEM (papel nuevo).
//
//   node perfil28.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciar, porCadaVista, carpeta } = require("./comun");

const CASOS = [["guadalajara", "14", "039"], ["autlan", "14", "015"]];

(async () => {
  const dir = carpeta(process.argv[2] || "perfil28");
  const { browser, estado } = await iniciar();
  const textos = [];
  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    const p = await ctx.newPage();
    const errores = [];
    p.on("pageerror", (e) => errores.push(String(e)));
    for (const [nombre, ent, mun] of CASOS) {
      await p.goto(BASE + "/perfil");
      await conectado(p);
      await p.selectOption("select[name='perfil[cve_ent]']", ent);
      await p.waitForTimeout(1500);
      await p.selectOption("select[name='perfil[cve_mun]']", mun);
      await p.locator("button:has-text('Ver perfil')").click();
      await p.locator(".d-hacienda:not(.esqueleto)").waitFor({ timeout: 60000 }).catch(() => {});
      await quieto(p, 2500);
      await p.screenshot({ path: path.join(dir, `${nombre}-${tn}-${modo}.png`), fullPage: true });
      if (tn === "escritorio" && modo === "light") {
        for (const sel of [".d-demografia", ".d-comercio", ".d-hacienda"]) {
          textos.push(`## ${nombre} ${sel}\n` + (await p.locator(sel).first().innerText().catch(() => "sin papel")));
        }
      }
    }
    if (errores.length) textos.push(`## errores ${tn} ${modo}\n` + errores.join("\n"));
    await p.close();
  });
  fs.writeFileSync(path.join(dir, "textos.md"), textos.join("\n\n"));
  await browser.close();
  console.log(dir);
})();
