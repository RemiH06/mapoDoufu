// Accesibilidad a servicios (sesión 26): /accesibilidad de un municipio urbano y
// uno rural, en los tres tamaños y los dos modos, con el umbral movido y otro
// servicio en el plano. Deja el texto de la hoja.
//
//   node accesibilidad.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciar, porCadaVista, carpeta } = require("./comun");

const CASOS = [
  ["zapopan", "/accesibilidad?ent=14&mun=120&modo=pie&umbral=15&servicio=centro_salud"],
  ["mezquitic", "/accesibilidad?ent=14&mun=061&modo=pie&umbral=30&servicio=primaria_publica"],
];

(async () => {
  const dir = carpeta(process.argv[2] || "accesibilidad");
  const { browser, estado } = await iniciar();
  const textos = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    const p = await ctx.newPage();
    const errores = [];
    p.on("pageerror", (e) => errores.push(String(e)));
    for (const [nombre, ruta] of CASOS) {
      await p.goto(BASE + ruta);
      await conectado(p);
      await p.locator("#accesibilidad-resultado").waitFor({ timeout: 60000 }).catch(() => {});
      await quieto(p, 3000);
      await p.screenshot({ path: path.join(dir, `${nombre}-${tn}-${modo}.png`) });
      if (tn === "escritorio" && modo === "light") {
        textos.push(`## ${nombre}\n` + (await p.locator("#hoja").innerText()));
        // Otro servicio en el plano y el umbral movido.
        await p.locator("#ver-supermercado").click().catch(() => {});
        await p.locator("#accesibilidad_form input[name='acc[umbral]']").fill("10");
        await p.locator("#accesibilidad_form input[name='acc[umbral]']").dispatchEvent("change");
        await quieto(p, 2000);
        await p.screenshot({ path: path.join(dir, `${nombre}-supermercado-10min.png`) });
        // La ficha de un lugar al tocarlo (el primero que se ve del plano).
        const lugar = await p.evaluate(() => {
          const m = document.querySelector("#accesibilidad-map").planoMapo;
          const f = m.queryRenderedFeatures({ layers: ["acc-lugares"] })[5];
          if (!f) return null;
          const anillo = f.geometry.type === "Polygon" ? f.geometry.coordinates[0] : f.geometry.coordinates[0][0];
          const c = anillo.reduce(([x, y], [a, b]) => [x + a / anillo.length, y + b / anillo.length], [0, 0]);
          const r = m.getContainer().getBoundingClientRect(), q = m.project(c);
          return { x: r.left + q.x, y: r.top + q.y };
        });
        if (lugar) await p.mouse.click(lugar.x, lugar.y);
        await quieto(p, 1000);
        await p.screenshot({ path: path.join(dir, `${nombre}-ficha.png`) });
        textos.push(`url: ${p.url()}`);
      }
    }
    if (errores.length) textos.push(`## errores ${tn} ${modo}\n` + errores.join("\n"));
    await p.close();
  });

  fs.writeFileSync(path.join(dir, "textos.md"), textos.join("\n\n"));
  await browser.close();
  console.log(dir);
})();
