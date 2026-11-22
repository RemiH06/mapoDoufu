// Empleo formal del IMSS (sesión 25): la tarjeta de checador de /perfil de Zapopan
// y el bloque del buscador para un rubro, en los tres tamaños y los dos modos. Deja
// el texto de cada bloque. La CDMX (sin municipio en el IMSS) no se puede ver
// mientras solo Jalisco tenga municipios cargados: la cubre la prueba de LiveView.
//
//   node empleo.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciar, porCadaVista, carpeta } = require("./comun");

(async () => {
  const dir = carpeta(process.argv[2] || "empleo");
  const { browser, estado } = await iniciar();
  const textos = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    const p = await ctx.newPage();
    for (const [nombre, ruta] of [["zapopan", "/perfil?cve_ent=14&cve_mun=120"]]) {
      await p.goto(BASE + ruta);
      await conectado(p);
      const tarjeta = p.locator("[data-piel=laboral]:not(.esqueleto)");
      await tarjeta.waitFor({ timeout: 60000 }).catch(() => {});
      await quieto(p);
      if (await tarjeta.count()) {
        await tarjeta.scrollIntoViewIfNeeded();
        await tarjeta.screenshot({ path: path.join(dir, `perfil-${nombre}-${tn}-${modo}.png`) });
        if (tn === "escritorio" && modo === "light") textos.push(`## perfil ${nombre}\n` + (await tarjeta.innerText()));
      }
      await p.screenshot({ path: path.join(dir, `perfil-${nombre}-${tn}-${modo}-pagina.png`) });
    }

    await p.goto(BASE + "/buscador?q=" + encodeURIComponent("dónde poner una taquería en Zapopan y Guadalajara"));
    await conectado(p);
    await quieto(p, 3000);
    const boton = p.locator("#plantilla_form button[type=submit], #plantilla_form .boton.primario").last();
    if (await boton.isVisible().catch(() => false)) await boton.click();
    const bloque = p.locator(".empleo-formal");
    await bloque.waitFor({ timeout: 90000 }).catch(() => {});
    await quieto(p);
    if (await bloque.count()) {
      await bloque.scrollIntoViewIfNeeded();
      await bloque.screenshot({ path: path.join(dir, `buscador-${tn}-${modo}.png`) });
      if (tn === "escritorio" && modo === "light") textos.push("## buscador\n" + (await bloque.innerText()));
    }
    await p.screenshot({ path: path.join(dir, `buscador-${tn}-${modo}-pagina.png`) });
    await p.close();
  });

  fs.writeFileSync(path.join(dir, "textos.md"), textos.join("\n\n"));
  await browser.close();
  console.log(dir);
})();
