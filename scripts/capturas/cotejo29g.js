// Riesgos y servicios legibles (sesión 29g): lista, matriz y mapas chicos de /riesgos y
// /accesibilidad, y sus acetatos en /mapa, en los tres tamaños y los dos modos.
//
//   node cotejo29g.js <corrida> [filtro]
const C = require("./comun");
const dir = C.carpeta(process.argv[2] || "cotejo29g"), filtro = process.argv[3] || "";
const CASOS = [
  ["r-zm", "/riesgos?zona=zm:14.1.01&cerca=1000", "#riesgos-resultado"],
  ["r-zm-mapas", "/riesgos?zona=zm:14.1.01&cerca=1000&vista=mapas&peligro=fuego", "#riesgos-resultado"],
  ["r-gdl", "/riesgos?zona=mun:14039&cerca=1000&peligro=retc", "#riesgos-resultado"],
  ["a-zm", "/accesibilidad?zona=zm:14.1.01&modo=pie&umbral=15", "#accesibilidad-resultado"],
  ["a-zm-mapas", "/accesibilidad?zona=zm:14.1.01&modo=pie&umbral=15&vista=mapas", "#accesibilidad-resultado"],
  ["a-mez", "/accesibilidad?zona=mun:14061&modo=pie&umbral=30&servicio=primaria_publica", "#accesibilidad-resultado"],
  ["m-riesgos", "/mapa?zona=mun:14039&riesgos=agua_superficial,descargas,retc,fuego&cerca=1000&ver=riesgos", "#cinta-riesgos .cinta-fuentes"],
  ["m-servicios", "/mapa?zona=mun:14039&servicio=centro_salud&modo=pie&umbral=15&ver=servicios", "#cinta-servicios .cinta-clases"],
];
(async () => {
  const { browser, estado } = await C.iniciarSinIds();
  await C.porCadaVista(browser, estado, async (ctx, tn, modo) => {
    for (const [n, u, sel] of CASOS.filter(c => c[0].includes(filtro))) {
      const p = await ctx.newPage();
      p.on("pageerror", e => console.log("ERR", n, tn, modo, String(e)));
      p.on("console", m => m.type() === "error" && console.log("CON", n, tn, m.text().slice(0, 200)));
      await p.goto(C.BASE + u); await C.conectado(p);
      await p.locator(sel).first().waitFor({ timeout: 120000 }).catch(() => console.log("SIN", n, tn));
      await C.quieto(p, 4500);
      await p.screenshot({ path: `${dir}/${n}-${tn}-${modo}.png` });
      const lateral = await p.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      if (lateral) console.log("LATERAL", n, tn);
      await p.close();
    }
  });
  await browser.close();
})();
