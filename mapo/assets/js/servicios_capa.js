import {css, escapar, ficha, fuente} from "./plano"

// Los minutos a un servicio por AGEB y localidad, y sus destinos: el plano de
// /accesibilidad y el acetato "Servicios" de /mapa. Más lejos, más tinta; sin
// dato, solo el borde punteado. Un servicio a la vez: nunca se suman.

// Clases por fracción del umbral: hasta la mitad, hasta el umbral, hasta el
// doble y más del doble.
const CORTES = [0.5, 1, 2]
export const TINTA = [0.06, 0.2, 0.5, 0.78]

const cifra = n => (n ?? 0).toLocaleString("es-MX")

export function claseMinutos(minutos, umbral) {
  if (minutos === null || minutos === undefined) return -1
  return CORTES.filter(c => minutos > c * umbral).length
}

export function rangosMinutos(umbral) {
  const mitad = (umbral / 2).toLocaleString("es-MX")
  return [`${mitad} min o menos`, `${mitad} a ${umbral} min`, `${umbral} a ${umbral * 2} min`, `más de ${umbral * 2} min`]
}

const opacidadPorClase = ["match", ["get", "k"], 0, TINTA[0], 1, TINTA[1], 2, TINTA[2], 3, TINTA[3], 0]

// Pone las capas con el prefijo `p` y sus fichas con `clic`.
export function pintarServicio(map, ml, p, {plano, destinos, servicio, umbral, titulo}, clic) {
  const tinta = css("--f-movilidad"), linea = css("--line")
  const minutosDe = f => f.properties.m?.[servicio]
  // La clase de cada lugar se calcula aquí: MapLibre no lee objetos anidados.
  fuente(map, `${p}lugares-f`, {
    type: "FeatureCollection",
    features: plano.features.map((f, i) => ({...f, properties: {i, k: claseMinutos(minutosDe(f), umbral)}})),
  })
  const poligono = ["==", ["geometry-type"], "Polygon"]
  const punto = ["==", ["geometry-type"], "Point"]
  const sinDato = ["<", ["get", "k"], 0]
  // Sin dato también toma clics (relleno transparente).
  map.addLayer({id: `${p}lugares`, type: "fill", source: `${p}lugares-f`, filter: poligono,
    paint: {"fill-color": tinta, "fill-opacity": ["case", sinDato, 0, opacidadPorClase]}})
  map.addLayer({id: `${p}borde`, type: "line", source: `${p}lugares-f`, filter: ["all", poligono, ["!", sinDato]],
    paint: {"line-color": tinta, "line-width": 0.5, "line-opacity": 0.6}})
  map.addLayer({id: `${p}sin-dato`, type: "line", source: `${p}lugares-f`, filter: ["all", poligono, sinDato],
    paint: {"line-color": linea, "line-width": 0.8, "line-dasharray": [3, 3]}})
  map.addLayer({id: `${p}puntos`, type: "circle", source: `${p}lugares-f`, filter: punto,
    paint: {
      // De lejos, más chicos: en una metrópoli tapaban las AGEB.
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 2, 11, 5],
      "circle-color": tinta,
      "circle-opacity": ["case", sinDato, 0, opacidadPorClase],
      "circle-stroke-color": ["case", sinDato, linea, tinta],
      "circle-stroke-width": ["case", sinDato, 1, 1.2],
      "circle-stroke-opacity": 0.9,
    }})

  // Miles de paradas de camión taparían el plano: con muchos destinos, puntos chicos.
  const suyos = {...destinos, features: destinos.features.filter(f => f.properties.s === servicio)}
  const muchos = suyos.features.length > 400
  fuente(map, `${p}destinos-f`, suyos)
  map.addLayer({id: `${p}destinos`, type: "circle", source: `${p}destinos-f`,
    paint: {
      "circle-radius": muchos ? 2 : 4.5,
      "circle-color": css("--text"),
      "circle-stroke-color": css("--bg"),
      "circle-stroke-width": muchos ? 0.5 : 1.5,
    }})

  const abrirLugar = (f, lugar) => {
    const q = plano.features[f.properties.i].properties, m = q.m?.[servicio]
    const tipo = q.t === "ageb" ? `AGEB ${escapar(q.c.slice(-4))}` : `Localidad ${escapar(q.c)}`
    const minutos = m === null || m === undefined ? "sin dato" : `${cifra(Math.round(m))} min`
    ficha(map, ml, lugar, `<b>${tipo}</b><br>${cifra(q.p)} personas<br>${escapar(titulo)}: ${minutos}`)
  }
  clic.en(`${p}lugares`, abrirLugar)
  clic.en(`${p}puntos`, abrirLugar)
  clic.en(`${p}destinos`, (f, lugar) => ficha(map, ml, lugar, `<b>${escapar(f.properties.n || "Sin nombre")}</b>`))
}
