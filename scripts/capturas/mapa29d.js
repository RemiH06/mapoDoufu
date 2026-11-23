// Organización de /mapa (sesión 29d): la mesa neutra con el censo de la ZMG,
// el transporte con el color de cada ruta y una resaltada, dos alcances
// apilados con la gente dentro, el arrastre de una pestaña y una ficha cerca
// del membrete que se recorre para verse entera. Deja el texto de las cintas,
// el orden de las pestañas y los errores de la página.
//
//   node mapa29d.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciar, porCadaVista, carpeta } = require("./comun");

const ZMG = "zm:14.1.01";
const plano = (p) => p.evaluate(() => !!document.querySelector("#mapa-tecnico").planoMapo);

// Punto de pantalla de una coordenada del plano.
const enPantalla = (p, lonlat) => p.evaluate((c) => {
  const m = document.querySelector("#mapa-tecnico").planoMapo;
  const r = m.getContainer().getBoundingClientRect(), q = m.project(c);
  return { x: r.left + q.x, y: r.top + q.y };
}, lonlat);

(async () => {
  const dir = carpeta(process.argv[2] || "mapa29d");
  const { browser, estado } = await iniciar();
  const textos = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    const p = await ctx.newPage();
    const errores = [];
    p.on("pageerror", (e) => errores.push(String(e)));
    p.on("console", (m) => { if (m.type() === "error") errores.push(m.text()) });
    const foto = (n) => p.screenshot({ path: path.join(dir, `${n}-${tn}-${modo}.png`) });

    // Censo de la ZMG: la mesa neutra y los nombres de calles encima de los datos.
    await p.goto(`${BASE}/mapa?zona=${ZMG}&censo=pobtot&ver=coropleta`);
    await conectado(p);
    await p.waitForFunction(() => document.querySelector("#mapa-tecnico").planoMapo, null, { timeout: 60000 });
    await quieto(p, 4000);
    await foto("1-censo");
    textos.push(`## ${tn} ${modo} piel: ` + (await p.evaluate(() => document.documentElement.dataset.piel)));

    // Ficha cerca del membrete: un clic arriba del hueco, y se mide si quedó entera.
    if (tn === "escritorio") {
      const cab = await p.locator(".membrete").boundingBox();
      // Acerca el centro de Guadalajara y busca una AGEB justo bajo el membrete.
      await p.evaluate(() => document.querySelector("#mapa-tecnico").planoMapo.jumpTo({ center: [-103.35, 20.62], zoom: 13 }));
      await quieto(p, 2000);
      const y = cab.y + cab.height + 8;
      const x = await p.evaluate((y) => {
        const m = document.querySelector("#mapa-tecnico").planoMapo;
        for (let x = 300; x < 1100; x += 10) if (m.queryRenderedFeatures([x, y], { layers: ["a-coropleta:relleno"] }).length) return x;
        return null;
      }, y);
      await p.mouse.click(x ?? 640, y);
      await quieto(p, 1200);
      const ficha = await p.locator(".maplibregl-popup").boundingBox().catch(() => null);
      textos.push(`ficha: ${JSON.stringify(ficha)} membrete abajo en ${Math.round(cab.y + cab.height)}`);
      await foto("2-ficha");
    }

    // Transporte de la ZMG, con la cinta abierta; luego una ruta resaltada.
    await p.goto(`${BASE}/mapa?zona=${ZMG}&transporte=1&ver=transporte`);
    await conectado(p);
    await p.waitForFunction(() => document.querySelector("#mapa-tecnico").planoMapo, null, { timeout: 60000 });
    await quieto(p, 5000);
    await foto("3-transporte");
    if (tn === "escritorio" && modo === "light") textos.push("### transporte\n" + (await p.locator("#cinta-transporte").innerText()));
    if (tn === "escritorio") {
      await p.evaluate(() => document.querySelector("#mapa-tecnico").planoMapo.jumpTo({ center: [-103.35, 20.675], zoom: 14 }));
      await quieto(p, 2500);
      // Busca una ruta en pantalla y pasa el cursor por ella.
      const punto = await p.evaluate(() => {
        const m = document.querySelector("#mapa-tecnico").planoMapo;
        const c = m.getCanvas().getBoundingClientRect();
        for (let y = 250; y < 600; y += 23) for (let x = 400; x < 1100; x += 23) {
          const f = m.queryRenderedFeatures([x, y], { layers: ["a-transporte:lineas"] })
          if (f.length) return { x: c.left + x, y: c.top + y };
        }
        return null;
      });
      if (punto) {
        await p.mouse.move(punto.x, punto.y);
        await quieto(p, 800);
        await foto("4-resalte");
      }
      textos.push(`resalte en ${JSON.stringify(punto)}`);
      const select = p.locator("#transporte_color_form select");
      if (await select.count()) {
        await select.selectOption(await select.inputValue() === "ruta" ? "frecuencia" : "ruta");
        await quieto(p, 1500);
        await foto("5-otro-color");
      }
    }

    // Dos alcances apilados con la gente dentro.
    await p.goto(`${BASE}/mapa?zona=${ZMG}&alcance=20.6767,-103.3475,10;20.70,-103.39,15&ver=isocrona`);
    await conectado(p);
    await p.waitForFunction(() => document.querySelector("#mapa-tecnico").planoMapo, null, { timeout: 60000 });
    await p.locator(".alcances-suma").waitFor({ timeout: 60000 }).catch(() => {});
    await quieto(p, 3000);
    await foto("6-alcances");
    if (tn === "escritorio" && modo === "light") textos.push("### alcances\n" + (await p.locator("#cinta-isocrona").innerText()));

    // Arrastrar "Municipios" al principio de la charola (en celular, con la charola abierta).
    if (tn !== "celular") {
      const origen = await p.locator("#pestana-coloreado").boundingBox();
      const destino = await p.locator("#pestana-propios").boundingBox();
      if (origen && destino) {
        await p.mouse.move(origen.x + origen.width / 2, origen.y + origen.height / 2);
        await p.mouse.down();
        await p.mouse.move(origen.x + origen.width / 2 - 20, origen.y + origen.height / 2, { steps: 4 });
        await p.mouse.move(destino.x + 8, destino.y + destino.height / 2, { steps: 12 });
        await foto("7-arrastrando");
        await p.mouse.up();
        await quieto(p, 1200);
      }
      const orden = await p.locator(".pestana[data-capa]").evaluateAll((ps) => ps.map((x) => x.dataset.capa));
      textos.push(`orden tras arrastrar: ${orden.join(", ")}; cinta abierta: ${await p.locator(".cinta:not([hidden])").getAttribute("id").catch(() => "ninguna")}`);
      await foto("8-arrastrada");
    }

    if (errores.length) textos.push(`errores ${tn} ${modo}:\n` + errores.join("\n"));
    await p.close();
  });

  fs.writeFileSync(path.join(dir, "textos.md"), textos.join("\n\n"));
  console.log(textos.join("\n\n"));
  await browser.close();
})();
