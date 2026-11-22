// Transporte público (sesión 27): el acetato de /mapa en un municipio con GTFS,
// uno con solo OSM y uno sin nada, de lejos y de cerca (paradas), y las paradas
// en /accesibilidad. Deja el texto de la cinta y las fichas.
//
//   node transporte.js <corrida>
const fs = require("fs");
const path = require("path");
const { BASE, conectado, quieto, iniciar, porCadaVista, carpeta } = require("./comun");

const CASOS = [
  ["guadalajara", "/mapa?ent=14&mun=039&transporte=1&ver=transporte"],
  ["vallarta", "/mapa?ent=14&mun=067&transporte=1&ver=transporte"],
  ["autlan", "/mapa?ent=14&mun=015&transporte=1&ver=transporte"],
];
const ACCESIBILIDAD = "/accesibilidad?ent=14&mun=039&modo=pie&umbral=5&servicio=parada_frecuente";

(async () => {
  const dir = carpeta(process.argv[2] || "transporte");
  const { browser, estado } = await iniciar();
  const textos = [];

  await porCadaVista(browser, estado, async (ctx, tn, modo) => {
    const p = await ctx.newPage();
    const errores = [];
    p.on("pageerror", (e) => errores.push(String(e)));
    for (const [nombre, ruta] of CASOS) {
      await p.goto(BASE + ruta);
      await conectado(p);
      await quieto(p, 4000);
      await p.screenshot({ path: path.join(dir, `${nombre}-${tn}-${modo}.png`) });
      if (tn === "escritorio" && modo === "light") {
        textos.push(`## ${nombre}\n` + (await p.locator("#cinta-transporte").innerText().catch(() => "sin cinta")));
        // De cerca: las paradas, y la ficha de una ruta.
        if (nombre === "guadalajara") {
          // El plano pinta en canvas: la ficha se abre con un clic donde pasan rutas.
          await p.mouse.click(640, 250);
          await quieto(p, 800);
          textos.push("ficha: " + (await p.locator(".maplibregl-popup-content").innerText().catch(() => "sin ficha")));
          await p.screenshot({ path: path.join(dir, `${nombre}-ficha.png`) });
          await p.keyboard.press("Escape");
          for (let i = 0; i < 3; i++) {
            await p.locator(".maplibregl-ctrl-zoom-in").click();
            await p.waitForTimeout(700);
          }
          await quieto(p, 2500);
          await p.screenshot({ path: path.join(dir, `${nombre}-cerca.png`) });
          await p.mouse.click(640, 250);
          await quieto(p, 800);
          textos.push("ficha: " + (await p.locator(".maplibregl-popup-content").innerText().catch(() => "sin ficha")));
          await p.screenshot({ path: path.join(dir, `${nombre}-ficha.png`) });
          await p.locator("#citar-transporte").click().catch(() => {});
          await quieto(p, 800);
          textos.push("cita: " + (await p.locator("#cita-transporte").innerText().catch(() => "sin cita")));
          textos.push(`url: ${p.url()}`);
        }
      }
    }
    if (tn === "escritorio") {
      await p.goto(BASE + ACCESIBILIDAD);
      await conectado(p);
      await p.locator("#accesibilidad-resultado").waitFor({ timeout: 60000 }).catch(() => {});
      await quieto(p, 3000);
      await p.screenshot({ path: path.join(dir, `accesibilidad-${modo}.png`) });
      if (modo === "light") {
        textos.push("## accesibilidad\n" + (await p.locator("#servicio-parada_frecuente").innerText().catch(() => "")));
        await p.locator("#citar-parada_frecuente").click().catch(() => {});
        await quieto(p, 800);
        textos.push("cita: " + (await p.locator("#cita-parada_frecuente").innerText().catch(() => "sin cita")));
      }
    }
    if (errores.length) textos.push(`## errores ${tn} ${modo}\n` + errores.join("\n"));
    await p.close();
  });

  fs.writeFileSync(path.join(dir, "textos.md"), textos.join("\n\n"));
  await browser.close();
  console.log(dir);
})();
