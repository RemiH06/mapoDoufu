// Escalas y dos indicadores en /mapa (sesión 29e): el conteo en círculos, una
// tasa con paleta y cortes naturales, color con círculos, el 3x3, la segunda
// tasa como altura, vivienda con su confianza y, de cerca, que no queden
// huecos entre AGEB. Deja el texto de la cinta y los errores de la página.
//
//   node mapa29e.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, iniciar, porCadaVista, carpeta } = require("./comun");

const ZMG = "zona=zm:14.1.01";
const CASOS = [
  ["1-conteo", `${ZMG}&censo=pobtot&ver=coropleta`],
  ["2-tasa", `${ZMG}&censo=vph_inter&como=pct&esc=viridis:naturales:5&ver=coropleta`],
  ["3-color-circulos", `${ZMG}&censo=vph_inter&como=pct&censo2=pobtot&esc=ylgnbu:cuantiles:5&ver=coropleta`],
  ["4-bivariado", `${ZMG}&censo=vph_inter&como=pct&censo2=graproes&ver=coropleta`],
  ["5-altura", `${ZMG}&censo=vph_inter&como=pct&censo2=pobtot&como2=km2&modo2=altura&esc=cividis:cuantiles:5&ver=coropleta`],
  ["6-diferencia", `${ZMG}&censo=pobfem&como=dif&b=pobmas&ver=coropleta`],
  ["7-precio", `${ZMG}&viv=precio_ageb&vesc=orrd:cuantiles:5&ver=vivienda`],
  ["8-intercensal", `${ZMG}&viv=eic_alqui&ver=vivienda`],
];

// El encuadre se juzga con el plano detenido: a media animación engaña.
const detenido = async (p) => {
  await p.waitForFunction(() => document.querySelector("#mapa-tecnico").planoMapo?.getStyle()?.layers.some((l) => l.id.startsWith("a-")), null, { timeout: 60000 });
  for (let i = 0, quietas = 0; i < 40 && quietas < 3; i++) {
    await p.waitForTimeout(500);
    quietas = (await p.evaluate(() => { const m = document.querySelector("#mapa-tecnico").planoMapo; return m.isMoving() || !m.areTilesLoaded(); })) ? 0 : quietas + 1;
  }
};

(async () => {
  const dir = carpeta(process.argv[2] || "mapa29e");
  const { browser, estado } = await iniciar();
  const textos = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    const p = await ctx.newPage();
    const errores = [];
    p.on("pageerror", (e) => errores.push(String(e)));
    p.on("console", (m) => { if (m.type() === "error") errores.push(m.text()) });
    const foto = (n) => p.screenshot({ path: path.join(dir, `${n}-${tn}-${modo}.png`) });

    for (const [nombre, query] of CASOS) {
      if (tn !== "escritorio" && !["2-tasa", "3-color-circulos", "4-bivariado"].includes(nombre)) continue;
      const t0 = Date.now();
      await p.goto(`${BASE}/mapa?${query}`);
      await conectado(p);
      await p.waitForFunction(() => document.querySelector("#mapa-tecnico").planoMapo, null, { timeout: 60000 });
      await detenido(p);
      await foto(nombre);
      const cinta = await p.locator(".cinta:not([hidden])").innerText().catch(() => "(sin cinta)");
      textos.push(`## ${nombre} ${tn} ${modo} (${Date.now() - t0} ms)\nURL: ${p.url()}\n${cinta}\n`);
    }

    if (tn === "escritorio") {
      // De cerca: con la cobertura, sin huecos blancos entre AGEB.
      await p.goto(`${BASE}/mapa?${ZMG}&censo=vph_inter&como=pct&esc=viridis:naturales:5&ver=coropleta`);
      await conectado(p);
      await p.waitForFunction(() => document.querySelector("#mapa-tecnico").planoMapo, null, { timeout: 60000 });
      await p.waitForTimeout(3000);
      await p.evaluate(() => document.querySelector("#mapa-tecnico").planoMapo.jumpTo({ center: [-103.35, 20.675], zoom: 15.5 }));
      await p.waitForTimeout(3000);
      await foto("9-de-cerca");

      // La escala en manual: se escriben los cortes y se repinta sin recargar.
      await p.locator("#coropleta_escala_detalles summary").click()
      await p.locator("#coropleta_escala_form select[name='escala[metodo]']").selectOption("manual");
      await p.waitForTimeout(1500);
      await p.locator("#coropleta_escala_form input[name='escala[cortes]']").fill("50, 75, 90");
      await p.waitForTimeout(3000);
      await p.evaluate(() => document.querySelector("#mapa-tecnico").planoMapo.jumpTo({ center: [-103.35, 20.66], zoom: 11 }));
      await p.waitForTimeout(2500);
      await foto("10-manual");
      textos.push(`## manual ${modo}\nURL: ${p.url()}\n${await p.locator(".cinta:not([hidden])").innerText()}\n`);
    }

    textos.push(`errores ${tn} ${modo}: ${JSON.stringify(errores)}\n`);
    await p.close();
  });

  fs.writeFileSync(path.join(dir, "textos.md"), textos.join("\n"));
  await browser.close();
})();
