// Pieles de Mapo, una por enfoque (como los biomas de tarot). Cada una es un
// documento con sus tintas de día y de noche; `film` es el color de las capas
// y los datos de ese enfoque. Contraste verificado: texto 7:1, secundario y
// acento 4.5:1, bordes y película 3:1, en los dos modos. Ninguno llega a #000
// ni a #fff. Este archivo es la fuente de verdad: genera las reglas
// [data-piel="..."] que lee mesa.css, así cualquier elemento puede llevar su
// propia piel (los documentos de /perfil) o heredar la de la raíz (/mapa).
(function () {
  const PIELES = {
    urbanismo: {nombre: "Urbanismo", documento: "plano", mano: "Architects Daughter", modos: ["Papel", "Cianotipia"],
      dia:   {bg: "#EEF1F4", bg2: "#E1E6ED", text: "#12284D", text2: "#46587A", line: "#6A7C9A", accent: "#B3301C", film: "#1A3A6B"},
      noche: {bg: "#0F2444", bg2: "#16305A", text: "#EEF3F9", text2: "#B7C8E0", line: "#7E98BE", accent: "#FF9E85", film: "#BFD8FF"}},
    demografia: {nombre: "Demografía", documento: "cédula censal", mano: "Architects Daughter", modos: ["Cédula", "Archivo"],
      dia:   {bg: "#F4EEEE", bg2: "#EADFE0", text: "#3E0E1A", text2: "#6E4650", line: "#8F6E76", accent: "#1F4E8C", film: "#6B1A2A"},
      noche: {bg: "#24090F", bg2: "#33121A", text: "#F6ECEE", text2: "#D9BCC2", line: "#A88089", accent: "#9CC3FF", film: "#F2A0B0"}},
    comercio: {nombre: "Comercio", documento: "libro mayor", mano: "Caveat", modos: ["Libro", "Corte de caja"],
      dia:   {bg: "#EFF2EA", bg2: "#E2E8DA", text: "#14321F", text2: "#48604F", line: "#6F8574", accent: "#B3301C", film: "#2A6B3A"},
      noche: {bg: "#0C2216", bg2: "#133020", text: "#EAF3EC", text2: "#BCD3C2", line: "#84A48D", accent: "#FF9E85", film: "#9FE3B0"}},
    consumo: {nombre: "Consumo", documento: "ticket de caja", mano: "Caveat", modos: ["Mostrador", "Cierre"],
      dia:   {bg: "#F6F3EA", bg2: "#ECE6D6", text: "#3A2A08", text2: "#6A5A38", line: "#8C7C58", accent: "#1F4E8C", film: "#8A6414"},
      noche: {bg: "#221A08", bg2: "#30260E", text: "#F6F0E0", text2: "#D8CBA8", line: "#A8976E", accent: "#9CC3FF", film: "#F0CC7A"}},
    seguridad: {nombre: "Seguridad", documento: "expediente", mano: "Special Elite", modos: ["Expediente", "Guardia"],
      dia:   {bg: "#F1EBDD", bg2: "#E6DCC6", text: "#2A1640", text2: "#5E4A6E", line: "#85738F", accent: "#B3301C", film: "#4A1A6B"},
      noche: {bg: "#1F1A12", bg2: "#2B2419", text: "#F2ECE0", text2: "#D2C7B4", line: "#A0937C", accent: "#FF9E85", film: "#D6B4F2"}},
    laboral: {nombre: "Laboral", documento: "tarjeta de checador", mano: "Caveat", modos: ["Matutino", "Nocturno"],
      dia:   {bg: "#EDF2F1", bg2: "#DEE7E6", text: "#0F3236", text2: "#456468", line: "#6C878A", accent: "#B3301C", film: "#1E5F66"},
      noche: {bg: "#0B2124", bg2: "#122E32", text: "#E8F3F3", text2: "#B7D2D4", line: "#80A3A6", accent: "#FF9E85", film: "#8FD8DE"}},
    movilidad: {nombre: "Movilidad", documento: "hoja de ruta", mano: "Architects Daughter", modos: ["Día", "Nocturna"],
      dia:   {bg: "#F5F1EC", bg2: "#EBE3D9", text: "#2E1C0C", text2: "#634C38", line: "#8A7360", accent: "#1F4E8C", film: "#C4691A"},
      noche: {bg: "#221509", bg2: "#2F1F10", text: "#F6EEE6", text2: "#DCC7B2", line: "#A88D74", accent: "#9CC3FF", film: "#F5C48F"}},
  };

  const vars = (t, mano) => Object.entries(t).map(([k, v]) => `--${k}:${v}`).join(";") + `;--mano:"${mano}",cursive`;
  const films = modo => Object.entries(PIELES).map(([k, p]) => `--f-${k}:${p[modo].film}`).join(";");
  const reglas = Object.entries(PIELES).map(([k, p]) =>
    `[data-piel="${k}"]{${vars(p.dia, p.mano)}}` +
    `[data-theme="dark"] [data-piel="${k}"],[data-theme="dark"][data-piel="${k}"]{${vars(p.noche, p.mano)}}`).join("\n");
  const estilo = document.createElement("style");
  estilo.id = "pieles";
  estilo.textContent = `:root{${films("dia")}}:root[data-theme="dark"]{${films("noche")}}\n${reglas}`;
  document.head.appendChild(estilo);

  const rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
  const mezcla = (a, b, f) => "#" + rgb(a).map((x, i) =>
    Math.round(Math.min(1, Math.max(0, x + (rgb(b)[i] - x) * f)) * 255).toString(16).padStart(2, "0")).join("");

  // Modo claro u oscuro: arranca con el del sistema; el botón dice a qué modo
  // lleva, con el nombre que le da la piel (Papel / Cianotipia, Libro / Corte de caja...).
  const raiz = document.documentElement;
  const oscuro = () => raiz.dataset.theme === "dark";
  function iniciarModo(boton, alCambiar) {
    raiz.dataset.theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    const rotular = () => { boton.textContent = PIELES[raiz.dataset.piel || "urbanismo"].modos[oscuro() ? 0 : 1]; };
    boton.addEventListener("click", () => { raiz.dataset.theme = oscuro() ? "light" : "dark"; rotular(); alCambiar && alCambiar(); });
    rotular();
    return rotular;
  }

  window.Mesa = {PIELES, rgb, mezcla, oscuro, iniciarModo};
})();
