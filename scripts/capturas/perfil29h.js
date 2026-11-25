// Sesión 29h: /perfil de cualquier zona (colonia, municipio, varios, dibujo y estado),
// con el plano, los ocho papeles y las zonas que se parecen con un desglose abierto.
//
//   node perfil29h.js <corrida> [filtro]
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciarSinIds, porCadaVista, carpeta } = require("./comun");

const CASOS = [
  ["colonia", "zona=col:14039_0010&parecidas=todas&margen=cerca"],
  ["municipio", "zona=mun:14015&parecidas=vivienda,economia&margen=cerca"],
  ["varios", "zona=mun:14039,14120,14098"],
  ["dibujo", "zona=pol:-103.366,20.680;-103.352,20.680;-103.352,20.668;-103.366,20.668&parecidas=poblacion&margen=muy_cerca"],
  ["rural", "zona=mun:14061"],
  ["estado", "zona=ent:14&parecidas=todas&margen=cerca"],
];

(async () => {
  const dir = carpeta(process.argv[2] || "perfil29h");
  const filtro = process.argv[3] || "";
  const { browser, estado } = await iniciarSinIds();
  const textos = [];
  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    for (const [nombre, query] of CASOS.filter(([n]) => n.includes(filtro))) {
      const p = await ctx.newPage();
      p.on("pageerror", (e) => textos.push(`## error ${nombre} ${tn} ${modo}: ${e}`));
      await p.goto(`${BASE}/perfil?${query}`);
      await conectado(p);
      await p.locator("#documentos").waitFor({ timeout: 120000 }).catch(() => textos.push(`## sin documentos: ${nombre}`));
      const ver = p.locator(".sim-cab button").first();
      if (query.includes("parecidas")) {
        await p.locator("#similares-resultado, #similares-motivo").first().waitFor({ timeout: 60000 }).catch(() => {});
        if (await ver.count()) await ver.click();
      }
      await quieto(p, 3500);
      const lateral = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      if (lateral > 0) textos.push(`## scroll lateral ${lateral}px: ${nombre} ${tn} ${modo}`);
      await p.screenshot({ path: path.join(dir, `${nombre}-${tn}-${modo}.png`), fullPage: true });
      if (tn === "escritorio" && modo === "light") textos.push(`## ${nombre}\n` + (await p.locator("main").innerText()));
      await p.close();
    }
  });
  fs.writeFileSync(path.join(dir, "textos.md"), textos.join("\n\n"));
  await browser.close();
  console.log(dir, textos.filter((t) => /^## (error|sin|scroll)/.test(t)));
})();
