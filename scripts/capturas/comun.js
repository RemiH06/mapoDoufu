// Lo que comparten pantallas.js, estados.js y subir.js: configuración,
// tamaños, entrar con la cuenta de prueba y descubrir sus ids.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.MAPO_URL || "http://127.0.0.1:1864";
const CORREO = process.env.MAPO_CORREO;
const CLAVE = process.env.MAPO_CLAVE;

// Celular y acostado son los de las sesiones de diseño: 390×844 y 844×390.
const TAMANOS = {
  escritorio: { viewport: { width: 1280, height: 800 } },
  celular: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
  acostado: { viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true },
};
const MODOS = ["light", "dark"];

// TAM=celular,acostado y MODO=dark recortan la corrida.
const elegidos = (todos, variable) =>
  process.env[variable] ? todos.filter((t) => process.env[variable].split(",").includes(t)) : todos;

// Dev compila cada página la primera vez: los tiempos son holgados a propósito.
const conectado = (p) => p.waitForSelector(".phx-connected", { timeout: 90000 });
const quieto = (p, ms = 2500) =>
  p.waitForLoadState("networkidle").catch(() => {}).then(() => p.waitForTimeout(ms));

async function entrar(browser) {
  if (!CORREO || !CLAVE) {
    console.error("Faltan MAPO_CORREO y MAPO_CLAVE (cuenta de prueba de dev).");
    process.exit(1);
  }
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await p.goto(BASE + "/users/log-in");
  await conectado(p);
  const f = p.locator("#login_form_password");
  await f.locator("input[type=email]").fill(CORREO);
  await f.locator("input[type=password]").fill(CLAVE);
  await Promise.all([
    p.waitForURL((u) => !u.pathname.includes("log-in"), { timeout: 120000, waitUntil: "domcontentloaded" }),
    f.locator("button").last().click(),
  ]);
  return { ctx, p };
}

// Primer equipo, su primera sesión y sus capas, leídos de los enlaces.
async function descubrir(p) {
  const ids = { equipo: null, sesion: null, capas: [], cruzable: null };
  const num = (href, re) => (href.match(re) || [])[1] || null;
  await p.goto(BASE + "/teams");
  await conectado(p);
  const equipo = await p.locator("a[href^='/teams/']:not([href='/teams/new'])").first().getAttribute("href").catch(() => null);
  ids.equipo = equipo && num(equipo, /\/teams\/(\d+)/);
  if (!ids.equipo) return ids;
  await p.goto(`${BASE}/teams/${ids.equipo}`);
  await conectado(p);
  const sesion = await p.locator("a[href^='/sesiones/']").first().getAttribute("href").catch(() => null);
  ids.sesion = sesion && num(sesion, /\/sesiones\/(\d+)/);
  await p.goto(`${BASE}/teams/${ids.equipo}/datos`);
  await conectado(p);
  for (const a of await p.locator("a[href^='/mapa?capa=']").all()) ids.capas.push(num(await a.getAttribute("href"), /capa=(\d+)/));
  const cruce = await p.locator("a[href$='/cruce']").first().getAttribute("href").catch(() => null);
  ids.cruzable = cruce && num(cruce, /datos\/(\d+)\/cruce/);
  return ids;
}

async function iniciar() {
  const browser = await chromium.launch();
  const { ctx, p } = await entrar(browser);
  const ids = await descubrir(p);
  const estado = await ctx.storageState();
  await ctx.close();
  return { browser, estado, ids };
}

// Un contexto por tamaño y modo, con el modo puesto antes de cargar.
async function porCadaVista(browser, estado, fn) {
  for (const tn of elegidos(Object.keys(TAMANOS), "TAM")) {
    for (const modo of elegidos(MODOS, "MODO")) {
      const ctx = await browser.newContext({ ...TAMANOS[tn], deviceScaleFactor: 1, storageState: estado });
      await ctx.addInitScript((m) => localStorage.setItem("phx:theme", m), modo);
      await fn(ctx, tn, modo);
      await ctx.close();
    }
  }
}

function carpeta(nombre) {
  const dir = path.join(__dirname, "salida", nombre);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

module.exports = { BASE, conectado, quieto, iniciar, entrar, porCadaVista, carpeta };
