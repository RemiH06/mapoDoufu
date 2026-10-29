# OSRM (ruteo por carretera)

No es una fuente de datos, es un servicio que `mapo_core` consulta
para distancias y tiempos reales por carretera. Lo usan el VRP
(`/vrp/calcular`, `/logistica`) y las isócronas (capa de `/mapa`).

- Cliente: `mapo_core/src/mapo_core/osrm_client.py`, adaptado de
  `gaiarda/src/gaiarda/ruteo_osrm.py` (async con `httpx`).
- URL: variable `MAPO_OSRM_URL`. Sin ella usa el servidor demo
  público (`https://router.project-osrm.org`).
- Servicios que usa: `table` (matriz de distancias y duraciones, una
  sola llamada para todos los pares) y `route` (geometría real de una
  ruta ya ordenada).
- Nunca truena: si el servicio no responde o algún par no es
  alcanzable, regresa `None` y quien llama cae a línea recta
  (haversine). El resultado siempre trae `metodo` (`carretera_real` /
  `linea_recta_aproximada` en VRP, `osrm_real` / `circulo_aproximado`
  en isócronas).

## Servidor propio

El demo público sirve para desarrollar, pero tiene límites de uso y no
garantiza disponibilidad: para hostear Mapo hace falta un OSRM propio.
Gaiarda ya lo corrió con el mapa de México completo: `osrm-extract`
llega a un pico de ~14.8 GB de RAM, así que Docker/WSL2 necesita 16 GB
asignados (con menos, muere sin avisar a medio preprocesar). La guía
con las cifras reales está en `gaiarda/docs/osrm_propio.md` del repo
de Gaiarda.
