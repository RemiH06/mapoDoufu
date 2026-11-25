// Marcas, segunda vuelta (sesión 29f): las cinco formas en el lápiz de quien las
// puso, la ficha con nota larga, y dibujar cada forma con ratón o con el dedo en
// /sesiones/:id y en /mapa. Deja las marcas que dibuja: usar una sesión de prueba.
//
//   MAPO_SESION=<id> node marcas29f.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, iniciarSinIds, porCadaVista, carpeta } = require("./comun");

const SESION = process.env.MAPO_SESION;
const PLANO = { sesion: "#mapa-colaborativo", mapa: "#mapa-tecnico" };

const listo = async (p, sel) => {
  await conectado(p);
  await p.waitForFunction((s) => document.querySelector(s)?.planoMapo?.getLayer("marcas-trazo"), sel, { timeout: 90000 });
  for (let i = 0, quietas = 0; i < 40 && quietas < 3; i++) {
    await p.waitForTimeout(400);
    quietas = (await p.evaluate((s) => { const m = document.querySelector(s).planoMapo; return m.isMoving() || !m.areTilesLoaded(); }, sel)) ? 0 : quietas + 1;
  }
};

// Un punto libre del plano: los papeles de encima no cuentan como plano.
const libres = (p, sel) => p.evaluate((s) => {
  const r = document.querySelector(s).getBoundingClientRect();
  const puntos = [];
  for (let y = r.top + 70; y < r.bottom - 20; y += 18) for (let x = r.left + 30; x < r.right - 70; x += 18) {
    const libre = (a, b) => document.elementFromPoint(a, b)?.tagName === "CANVAS";
    if ([[0, 0], [90, 0], [90, 60], [0, 60], [45, 30], [45, 0], [0, 30]].every(([dx, dy]) => libre(x + dx, y + dy))) puntos.push([x, y]);
  }
  return puntos;
}, sel);

async function trazoConDedo(p, puntos) {
  const cdp = await p.context().newCDPSession(p);
  const t = ([x, y]) => [{ x, y }];
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: t(puntos[0]) });
  for (const q of puntos.slice(1)) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: t(q) });
    await p.waitForTimeout(16);
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

async function dibujarTodas(p, sel, tactil, foto, nota) {
  const cuantas = () => p.locator(`${sel} .maplibregl-marker`).count();
  const tocar = async (x, y) => { if (tactil) await p.touchscreen.tap(x, y); else await p.mouse.click(x, y); await p.waitForTimeout(350); };
  const resultado = {};
  for (const forma of ["punto", "circulo", "flecha", "trazo", "poligono"]) {
    await p.locator(`.herramientas button[phx-value-herramienta=${forma}]:visible`).click();
    await p.waitForTimeout(300);
    const sitios = await libres(p, sel);
    if (!sitios.length) { resultado[forma] = "SIN HUECO"; continue; }
    const [x, y] = sitios[Math.floor(sitios.length / 2)];
    const antes = await cuantas();
    const centro = await p.evaluate((s) => document.querySelector(s).planoMapo.getCenter().toArray().join(), sel);
    if (forma === "punto") await tocar(x, y);
    if (forma === "circulo" || forma === "flecha") {
      await tocar(x, y);
      if (!tactil) await p.mouse.move(x + 60, y + 30, { steps: 4 });
      await p.waitForTimeout(150);
      if (forma === "flecha") await foto(`medio-flecha${nota}`);
      await tocar(x + 85, y + 45);
    }
    if (forma === "trazo") {
      const puntos = Array.from({ length: 30 }, (_, i) => [x + i * 3, y + 30 + 18 * Math.sin(i / 3)]);
      if (tactil) await trazoConDedo(p, puntos);
      else {
        await p.mouse.move(...puntos[0]);
        await p.mouse.down();
        for (const q of puntos) await p.mouse.move(...q);
        await p.mouse.up();
      }
      const despues = await p.evaluate((s) => document.querySelector(s).planoMapo.getCenter().toArray().join(), sel);
      resultado.trazoMovioElPlano = despues !== centro && "SÍ (o la ficha lo recorrió)";
    }
    if (forma === "poligono") {
      await tocar(x, y);
      await tocar(x + 85, y + 5);
      await tocar(x + 80, y + 50);
      await foto(`medio-poligono${nota}`);
      await tocar(x, y);
    }
    const ficha = p.locator(".ficha-marca form");
    await ficha.waitFor({ timeout: 5000 }).catch(() => {});
    if (!(await ficha.count())) { resultado[forma] = "SIN FICHA"; await foto(`sin-ficha-${forma}${nota}`); await p.keyboard.press("Escape"); continue; }
    await p.waitForTimeout(500);
    if (forma === "trazo") await foto(`nueva-trazo${nota}`);
    resultado[`${forma} ficha`] = (await ficha.innerText()).split("\n")[0] + " / " + (await ficha.locator(".ficha-autor").innerText());
    await ficha.locator("input").fill(`${forma} ${nota}`);
    await ficha.locator("button[type=submit]").click();
    await p.waitForTimeout(900);
    resultado[forma] = (await cuantas()) === antes + 1 ? "ok" : `NO (${antes} a ${await cuantas()})`;
  }
  return resultado;
}

(async () => {
  const dir = carpeta(process.argv[2] || "marcas29f");
  const { browser, estado } = await iniciarSinIds();
  const textos = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    for (const vista of ["sesion", "mapa"]) {
      const p = await ctx.newPage();
      const errores = [];
      p.on("pageerror", (e) => errores.push(String(e)));
      p.on("console", (m) => { if (m.type() === "error") errores.push(m.text()) });
      const foto = (n) => p.screenshot({ path: path.join(dir, `${vista}-${n}-${tn}-${modo}.png`) });
      const sel = PLANO[vista];
      await p.goto(BASE + (vista === "sesion" ? `/sesiones/${SESION}` : `/mapa?sesion=${SESION}`));
      await listo(p, sel);
      await foto("1-abierta");

      // Leer la nota larga, editarla y arrepentirse. Con el teclado: una marca
      // puede haber quedado bajo un papel.
      await p.locator(`${sel} .maplibregl-marker[title^="bache"]`).focus();
      await p.keyboard.press("Enter");
      await p.locator(".ficha-detalle").waitFor({ timeout: 5000 });
      await p.waitForTimeout(600);
      await foto("2-ficha");
      await p.locator(".ficha-marca button", { hasText: "Editar" }).click();
      await p.waitForTimeout(400);
      await foto("3-editar");
      await p.locator(".ficha-marca button", { hasText: "No cambiar" }).click();
      await p.locator(".maplibregl-popup-close-button").click();

      // Al zoom de una colonia: de lejos, lo dibujado saldría de cientos de km.
      await p.evaluate((s) => document.querySelector(s).planoMapo.jumpTo({ center: [-103.38, 20.64], zoom: 13 }), sel);
      await p.waitForTimeout(1500);
      const r = modo === "light" ? await dibujarTodas(p, sel, tn !== "escritorio", foto, vista) : {};
      await foto("4-final");
      const desborde = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      textos.push(`## ${vista} ${tn} ${modo}\n${JSON.stringify(r, null, 1)}\ndesborde ${desborde}\nerrores ${errores.join(" | ") || "ninguno"}\n`);

      // El cambio de tema recarga el estilo: las líneas tienen que volver.
      if (tn === "escritorio") {
        await p.evaluate(() => { document.documentElement.dataset.theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; });
        await p.waitForTimeout(4000);
        await foto("5-otro-tema");
      }
      await p.close();
    }
  });
  fs.writeFileSync(path.join(dir, "textos.md"), textos.join("\n"));
  console.log(textos.join("\n"));
  await browser.close();
})();
