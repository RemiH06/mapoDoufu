# Fase 4: Isócronas


- **Decidido y construido: muestreo radial con OSRM (`sources=0`), no
  un segundo motor de ruteo.** Se descartó Valhalla/ORS a propósito:
  ya hay OSRM integrado para VRP, meter un segundo motor solo para
  isócronas duplicaría infraestructura por precisión marginal.
  `mapo_core/isocronas.py` + `POST /isocronas/calcular`: samplea
  puntos en N direcciones alrededor del origen, le pide a OSRM la
  duración real por carretera a todos en una sola llamada, arma un
  polígono con el punto más lejano alcanzable en cada dirección.
  Fallback honesto a círculo aproximado si OSRM no responde, mismo
  patrón `metodo` que VRP. 53 tests en `mapo_core`. **Probado en vivo
  contra el demo público real de OSRM**: polígono real de 13 vértices
  alrededor del centro de CDMX a 10 minutos, `metodo: "osrm_real"`
- Nota permanente, no un pendiente: es una aproximación poligonal (N
  vértices, no el área exacta alcanzable). Suficiente por ahora; si
  hace falta más precisión, subir `num_direcciones`/
  `muestras_por_direccion` en vez de cambiar de algoritmo
