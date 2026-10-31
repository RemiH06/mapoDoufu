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
En producción es el servicio `osrm` de `docker-compose.prod.yml`
([despliegue.md](../despliegue.md)), y `MAPO_OSRM_URL` apunta a él en
`mapo_core` y en `mapo` (que con eso cambia la línea de OSRM en
`/privacidad`). Una `MAPO_OSRM_URL` vacía cuenta como no definida.

**Los datos se reusan de Gaiarda.** Gaiarda ya preprocesó el mapa de
México completo (Geofabrik, 2026-08-01) con el algoritmo MLD: 8 GB en
su carpeta `osrm-data/`. Preprocesarlo de nuevo no hace falta, y es lo
caro: `osrm-extract` llega a un pico de ~14.8 GB de RAM, así que
Docker/WSL2 necesita 16 GB asignados (con menos, muere sin avisar a
medio preprocesar). Servirlo es mucho menos: 5.1 GB de RAM medidos.

**La versión de la imagen tiene que ser la misma con que se
prepararon los datos.** El archivo `.osrm.timestamp` (y cualquier
`.osrm.*`) lleva una huella en los bytes 512 a 519: `OSRO` seguido de
la versión (`1a 07 03` = 26.7.3). Por eso la imagen va fija en
`v26.7.3-debian`. Ensayo del 2026-10-30 con esos datos: una ruta dentro
de Guadalajara dio 7.9 km y 9 minutos por carretera.

Para actualizar el mapa: bajar `mexico-latest.osm.pbf` de Geofabrik y
correr con la misma imagen `osrm-extract -p /opt/car.lua`,
`osrm-partition` y `osrm-customize` sobre la carpeta, en una máquina
con 16 GB para Docker.
