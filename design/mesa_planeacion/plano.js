// El plano del fondo de las vistas sin mapa: los AGEB del municipio, solo
// trazo, en el color de las líneas de la piel. Recibe un FeatureCollection.
window.dibujarPlano = function (svg, coleccion) {
  const anillos = coleccion.features.flatMap(f => f.geometry.type === "MultiPolygon" ? f.geometry.coordinates.flat() : f.geometry.coordinates);
  const pts = anillos.flat(), xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const d = anillos.map(a => "M" + a.map(([x, y]) => `${((x - x0) * 1000).toFixed(1)},${((y1 - y) * 1000).toFixed(1)}`).join("L") + "Z").join("");
  svg.setAttribute("viewBox", `-20 -20 ${(x1 - x0) * 1000 + 40} ${(y1 - y0) * 1000 + 40}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid slice");
  svg.innerHTML = `<path d="${d}" fill="none" stroke="currentColor" stroke-width="1" vector-effect="non-scaling-stroke"/>`;
};
