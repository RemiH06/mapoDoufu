// Selector de zona común (sesión 29b): buscar y elegir una colonia en /riesgos,
// dibujar un polígono, la ZMG en /accesibilidad, el Voronoi con la competencia
// de fuera en /mapa, el autocompletado del membrete y sumar un municipio. Deja
// el texto de las hojas y los errores de la página.
//
//   node zona.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciar, porCadaVista, carpeta } = require("./comun");

// Escribe en el selector y espera las sugerencias.
async function buscar(p, texto) {
  const q = p.locator("#zona-q");
  await q.fill(texto);
  await p.locator("#zona-lista").waitFor({ timeout: 15000 }).catch(() => {});
}

// Un clic en el plano en coordenadas de mapa.
async function clicEn(p, sel, lonlat) {
  const punto = await p.evaluate(([s, c]) => {
    const m = document.querySelector(s).planoMapo;
    const r = m.getContainer().getBoundingClientRect(), q = m.project(c);
    return { x: r.left + q.x, y: r.top + q.y };
  }, [sel, lonlat]);
  await p.mouse.click(punto.x, punto.y);
}

(async () => {
  const dir = carpeta(process.argv[2] || "zona");
  const { browser, estado } = await iniciar();
  const textos = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    const p = await ctx.newPage();
    const errores = [];
    p.on("pageerror", (e) => errores.push(String(e)));
    const foto = (n) => p.screenshot({ path: path.join(dir, `${n}-${tn}-${modo}.png`) });

    // /riesgos: buscar una colonia y elegirla (consulta de una vez).
    await p.goto(BASE + "/riesgos");
    await conectado(p);
    await buscar(p, "lopez coti");
    await quieto(p, 800);
    await foto("riesgos-sugerencias");
    await p.locator("#zona-lista button").first().click();
    await p.locator("#riesgos-resultado").waitFor({ timeout: 60000 }).catch(() => {});
    await quieto(p, 2500);
    await foto("riesgos-colonia");
    if (tn === "escritorio" && modo === "light") textos.push("## riesgos colonia\n" + (await p.locator("#hoja").innerText()));

    // Dibujar un polígono en el centro de Guadalajara.
    if (tn === "escritorio") {
      await p.locator("#zona-cambiar").click();
      await p.locator("#zona-dibujar").click();
      await p.evaluate(() => document.querySelector("#riesgos-map").planoMapo.jumpTo({ center: [-103.35, 20.675], zoom: 13 }));
      await quieto(p, 1500);
      for (const v of [[-103.365, 20.665], [-103.335, 20.665], [-103.335, 20.685], [-103.365, 20.685]]) {
        await clicEn(p, "#riesgos-map", v);
        await p.waitForTimeout(250);
      }
      await foto("riesgos-dibujando");
      await clicEn(p, "#riesgos-map", [-103.365, 20.665]);
      await p.locator("#riesgos-resultado h2").first().waitFor({ timeout: 60000 }).catch(() => {});
      await quieto(p, 3000);
      await foto("riesgos-dibujo");
      if (modo === "light") textos.push("## riesgos dibujo\n" + (await p.locator("#hoja").innerText()) + `\nurl: ${p.url()}`);
    }

    // /accesibilidad de la ZMG entera.
    await p.goto(BASE + "/accesibilidad?zona=zm:14.1.01&modo=pie&umbral=15&servicio=centro_salud");
    await conectado(p);
    await p.locator("#accesibilidad-resultado").waitFor({ timeout: 90000 }).catch(() => {});
    await quieto(p, 4000);
    await foto("accesibilidad-zmg");
    if (tn === "escritorio" && modo === "light") textos.push("## accesibilidad zmg\n" + (await p.locator("#hoja").innerText()));

    // /mapa: Voronoi de farmacias en Guadalajara, con las de fuera.
    await p.goto(BASE + "/mapa?zona=mun:14039&negocios=farmacia&ver=voronoi");
    await conectado(p);
    await quieto(p, 6000);
    await foto("mapa-voronoi");
    if (tn === "escritorio" && modo === "light") textos.push("## mapa voronoi\n" + (await p.locator("#cinta-voronoi").innerText()));

    // El membrete: sumar Zapopan a Guadalajara.
    await p.locator("#zona-sumar").click().catch(() => {});
    await buscar(p, "zapopan");
    await quieto(p, 800);
    await foto("mapa-sumar");
    await p.locator("#zona-q").press("Enter");
    await quieto(p, 3000);
    await foto("mapa-dos-municipios");
    textos.push(`## ${tn} ${modo} membrete\n` + (await p.locator(".ubicacion").innerText()) + `\nurl: ${p.url()}`);

    if (errores.length) textos.push(`## errores ${tn} ${modo}\n` + errores.join("\n"));
    await p.close();
  });

  fs.writeFileSync(path.join(dir, "textos.md"), textos.join("\n\n"));
  await browser.close();
  console.log(dir);
})();
