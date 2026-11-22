#!/usr/bin/env bash
# Rutas de transporte público de OSM de todo México, para `cli transporte_osm`
# (docs/fuentes/gtfs.md). Del pbf de Geofabrik que ya baja scripts/osrm/pie.sh:
# las relaciones type=route de transporte, sus vías con coordenadas y sus paradas,
# en texto OPL.
#
# Uso: [PBF_FECHA=AAMMDD] scripts/transporte/rutas_osm.sh [CARPETA_PBF] [DESTINO]
#   CARPETA_PBF  donde está mexico-AAMMDD.osm.pbf (~/srv/mapo-osrm-pie)
#   DESTINO      carpeta de salida (~/srv/mapo-crudos/transporte)
# Sale DESTINO/rutas-AAMMDD.opl; la fecha del nombre es la del pbf y va a la cita.
set -euo pipefail

PBF_FECHA="${PBF_FECHA:-261120}"
ORIGEN="${1:-$HOME/srv/mapo-osrm-pie}"
DESTINO="${2:-$HOME/srv/mapo-crudos/transporte}"
PBF="mexico-$PBF_FECHA.osm.pbf"
RUTAS="route=bus,share_taxi,trolleybus,tram,light_rail,subway,train,monorail,aerialway,ferry,funicular"

[ -s "$ORIGEN/$PBF" ] || { echo "no está $ORIGEN/$PBF (scripts/osrm/pie.sh lo baja)"; exit 1; }
mkdir -p "$DESTINO"

# osmium no está en el WSL: contenedor de paso, como en pie.sh. tags-filter agrega
# lo que referencian las relaciones (vías y sus nodos; los filtros de osmium se
# suman con O, así que no se filtra por type=route: route=* basta en relaciones); add-locations-to-ways pone
# la coordenada en cada vía para no cargar todos los nodos en el lector.
docker run --rm -v "$ORIGEN":/o:ro -v "$DESTINO":/d debian:trixie-slim bash -c "
  set -e
  apt-get update -qq && apt-get install -y -qq osmium-tool >/dev/null
  osmium tags-filter /o/$PBF r/$RUTAS -O -o /tmp/rutas.pbf
  osmium add-locations-to-ways /tmp/rutas.pbf -O -o /tmp/loc.pbf
  osmium cat /tmp/loc.pbf -O -f opl,locations_on_ways=true -o /d/rutas-$PBF_FECHA.opl.tmp
  chown $(id -u):$(id -g) /d/rutas-$PBF_FECHA.opl.tmp
"
mv "$DESTINO/rutas-$PBF_FECHA.opl.tmp" "$DESTINO/rutas-$PBF_FECHA.opl"
ls -la "$DESTINO/rutas-$PBF_FECHA.opl"
echo "relaciones: $(grep -c '^r' "$DESTINO/rutas-$PBF_FECHA.opl")"
