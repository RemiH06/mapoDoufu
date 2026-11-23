// Buscador sin mapa (sesión 29c): la pregunta sola antes de la respuesta, el
// autocompletado con flechas y Enter, Enter que resuelve, el plano que entra
// con la respuesta, el menú de rubros con su filtro y, en celular, la
// respuesta que se agranda. Deja el texto de lo revisado y los errores.
//
//   node buscador.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciar, porCadaVista, carpeta } = require("./comun");

// Escribe de a poco, como una persona, y espera a que el servidor conteste.
async function escribir(p, texto) {
  await p.locator("#pregunta-texto").pressSequentially(texto, { delay: 40 });
  await p.waitForTimeout(600);
}

const opacidadPlano = (p) =>
  p.evaluate(() => {
    const e = getComputedStyle(document.querySelector("#mapa-tecnico"));
    return `${e.visibility} ${e.opacity}`;
  });

(async () => {
  const dir = carpeta(process.argv[2] || "buscador");
  const { browser, estado } = await iniciar();
  const textos = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    const p = await ctx.newPage();
    const errores = [];
    p.on("pageerror", (e) => errores.push(String(e)));
    const foto = (n) => p.screenshot({ path: path.join(dir, `${n}-${tn}-${modo}.png`) });
    const nota = (t) => textos.push(`## ${tn} ${modo} ${t}`);

    await p.goto(BASE + "/buscador");
    await conectado(p);
    await quieto(p, 1500);
    nota(`inicio: plano ${await opacidadPlano(p)}`);
    await foto("1-inicio");

    // Autocompletado: la palabra a medias, flecha abajo y Enter.
    await p.locator("#pregunta-texto").click();
    await escribir(p, "¿Dónde pongo una flor");
    await p.locator("#sugerencias").waitFor({ timeout: 10000 }).catch(() => {});
    nota("sugerencias:\n" + (await p.locator("#sugerencias").innerText().catch(() => "(ninguna)")));
    await p.keyboard.press("ArrowDown");
    await foto("2-sugerencias");
    await p.keyboard.press("Enter");
    await p.waitForTimeout(400);
    await escribir(p, "en zapo");
    await p.locator("#sugerencias").waitFor({ timeout: 10000 }).catch(() => {});
    await p.keyboard.press("ArrowDown");
    await p.keyboard.press("Enter");
    await p.waitForTimeout(400);
    nota(`texto armado: «${await p.locator("#pregunta-texto").inputValue()}»`);

    // Enter sin sugerencia marcada pregunta, y la pregunta completa se resuelve.
    await p.keyboard.press("Enter");
    await p.locator("#respuesta").waitFor({ timeout: 90000 }).catch(() => {});
    await quieto(p, 5000);
    nota(`respondida: plano ${await opacidadPlano(p)} url ${decodeURIComponent(p.url())}`);
    await foto("3-respuesta");
    if (tn === "celular") {
      await p.locator("#respuesta .agrandar").click();
      await p.waitForTimeout(500);
      await foto("4-respuesta-alta");
      await p.locator("#respuesta .agrandar").click();
    }

    // Caja vacía: las sugerencias se van y vuelven los ejemplos.
    await p.goto(BASE + "/buscador");
    await conectado(p);
    await p.locator("#pregunta-texto").click();
    await escribir(p, "farm");
    const hay = await p.locator("#sugerencias").count();
    await p.locator("#pregunta-texto").fill("");
    await p.waitForTimeout(900);
    nota(`vaciar: sugerencias antes ${hay}, después ${await p.locator("#sugerencias").count()}, ejemplos ${await p.locator(".ejemplos").count()}`);

    // Menú de rubros: elegir "Contar negocios", abrir el hueco, filtrar.
    await p.selectOption("select[name='plantilla[intencion]']", "cuantos");
    await p.waitForTimeout(600);
    await p.locator("#hueco-rubro").click();
    await p.waitForTimeout(400);
    await foto("5-menu");
    await p.keyboard.type("tortas", { delay: 40 });
    await p.waitForTimeout(300);
    nota("menú filtrado con «tortas»:\n" + (await p.locator("#menu-rubros").innerText()));
    await foto("6-menu-filtrado");
    await p.keyboard.press("Enter");
    await p.waitForTimeout(800);
    nota(`hueco tras Enter: «${await p.locator("#hueco-rubro").innerText()}», menú abierto: ${await p.locator("#menu-rubros:popover-open").count()}`);
    await p.locator("#hueco-rubro").click();
    await p.keyboard.type("zzzz");
    await p.waitForTimeout(300);
    nota(`sin coincidencias: ${await p.locator("#menu-rubros .sin-coincidencias:not([hidden])").count()}`);
    await p.keyboard.press("Escape");
    await p.waitForTimeout(300);
    nota(`tras Esc, menú abierto: ${await p.locator("#menu-rubros:popover-open").count()}`);
    await foto("7-plantilla");

    if (errores.length) nota("errores\n" + errores.join("\n"));
    await p.close();
  });

  fs.writeFileSync(path.join(dir, "textos.md"), textos.join("\n\n"));
  await browser.close();
  console.log(dir);
})();
