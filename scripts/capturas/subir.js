// Sube al primer equipo de la cuenta tres capas inventadas, para ver la
// cinta de "Tus datos" con tres capas y el cruce: puntos con coordenadas,
// clientes por AGEB de Zapopan y dos polígonos en GeoJSON. Ningún dato es
// real. Las claves AGEB las da mapo_core (MAPO_CORE_URL).
// Uso: node subir.js
const fs = require("fs");
const path = require("path");
const { BASE, conectado, iniciar, entrar, carpeta } = require("./comun");

const CORE = process.env.MAPO_CORE_URL || "http://127.0.0.1:8010";

// Pseudoaleatorio con semilla: los mismos archivos en cada corrida.
let semilla = 1;
const azar = () => (semilla = (semilla * 16807) % 2147483647) / 2147483647;

async function archivos(dir) {
  let puntos = "nombre,ventas_mensuales,latitud,longitud\n";
  for (let i = 1; i <= 40; i++) {
    const lat = (20.67 + azar() * 0.08).toFixed(5);
    const lon = (-103.43 + azar() * 0.08).toFixed(5);
    puntos += `Sucursal ${i},${Math.round(20000 + azar() * 80000)},${lat},${lon}\n`;
  }

  const res = await fetch(`${CORE}/geo/agebs?cve_ent=14&cve_mun=120`);
  if (!res.ok) throw new Error(`mapo_core respondió ${res.status} al pedir los AGEB de Zapopan`);
  const claves = (await res.json()).features.slice(0, 80).map((f) => f.properties.cvegeo);
  let agebs = "cvegeo,clientes,ticket_promedio\n";
  for (const c of claves) agebs += `${c},${Math.round(azar() * 300)},${Math.round(80 + azar() * 400)}\n`;

  const rect = (nombre, o, s, e, n) => ({
    type: "Feature",
    properties: { nombre },
    geometry: { type: "Polygon", coordinates: [[[o, s], [e, s], [e, n], [o, n], [o, s]]] },
  });
  const zonas = {
    type: "FeatureCollection",
    features: [rect("Zona de reparto norte", -103.42, 20.71, -103.37, 20.75), rect("Zona de reparto sur", -103.4, 20.66, -103.35, 20.69)],
  };

  const salida = {
    "sucursales.csv": puntos,
    "clientes_por_ageb.csv": agebs,
    "zonas_reparto.geojson": JSON.stringify(zonas),
  };
  for (const [n, contenido] of Object.entries(salida)) fs.writeFileSync(path.join(dir, n), contenido);
  return Object.keys(salida).map((n) => path.join(dir, n));
}

(async () => {
  const { ids, browser } = await iniciar();
  if (!ids.equipo) throw new Error("la cuenta no tiene equipo: créalo antes en /teams");
  const rutas = await archivos(carpeta("archivos"));
  const { p } = await entrar(browser);

  for (const ruta of rutas) {
    await p.goto(`${BASE}/teams/${ids.equipo}/datos`);
    await conectado(p);
    await p.setInputFiles("#subir_form input[type=file]", ruta);
    await p.locator("#subir_form button").click();
    await p.waitForSelector("#capa_form", { timeout: 30000 });
    await p.locator("#capa_form button").first().click();
    await p.waitForSelector("#capa_form", { state: "detached", timeout: 30000 });
    console.log(`subida: ${path.basename(ruta)}`);
  }
  await browser.close();
})();
