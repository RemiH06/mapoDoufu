#!/usr/bin/env bash
# Prepara OSRM con el perfil a pie (foot.lua) para una caja, por omisión
# Jalisco con 0.15 grados de margen (los caminos que cruzan al estado vecino
# también cuentan). Sale en $DESTINO/pie.osrm.* con la misma imagen que el
# perfil de auto: los datos y la imagen tienen que ser de la misma versión
# (docs/fuentes/osrm.md).
#
# Uso: [PBF_FECHA=AAMMDD] scripts/osrm/pie.sh [DESTINO] [CAJA]
#   DESTINO  carpeta de salida (~/srv/mapo-osrm-pie)
#   CAJA     oeste,sur,este,norte (-105.85,18.78,-101.36,22.90)
# Relanzarlo reusa el pbf ya bajado; borrar pie.osrm* para rehacer el grafo.
set -euo pipefail

DESTINO="${1:-$HOME/srv/mapo-osrm-pie}"
CAJA="${2:--105.85,18.78,-101.36,22.90}"
IMAGEN=ghcr.io/project-osrm/osrm-backend:v26.7.3-debian
# Fecha fija: "latest" redirige al archivo del día aunque todavía no esté.
PBF_FECHA="${PBF_FECHA:-261120}"
PBF_URL="https://download.geofabrik.de/north-america/mexico/mexico-$PBF_FECHA.osm.pbf"

mkdir -p "$DESTINO"
cd "$DESTINO"

if [ ! -s mexico-$PBF_FECHA.osm.pbf ]; then
  curl -fL --retry 3 -o mexico-$PBF_FECHA.osm.pbf.tmp "$PBF_URL"
  mv mexico-$PBF_FECHA.osm.pbf.tmp mexico-$PBF_FECHA.osm.pbf
fi

# osmium no viene en la imagen de OSRM: se instala en un contenedor de paso.
if [ ! -s pie.osm.pbf ]; then
  docker run --rm -v "$DESTINO":/d debian:trixie-slim bash -c \
    "apt-get update -qq && apt-get install -y -qq osmium-tool >/dev/null && \
     osmium extract -b $CAJA -s complete_ways -o /d/pie.osm.pbf.tmp -f pbf /d/mexico-$PBF_FECHA.osm.pbf"
  mv pie.osm.pbf.tmp pie.osm.pbf
fi

# Tiempo y pico de memoria de cada paso, para saber si cabe el país.
medir() {
  local nombre=osrm-pie-paso pico=0 m inicio=$SECONDS
  docker run -d --name "$nombre" -v "$DESTINO":/data "$IMAGEN" "$@" >/dev/null
  while [ "$(docker inspect -f '{{.State.Running}}' "$nombre")" = true ]; do
    m=$(docker stats --no-stream --format '{{.MemUsage}}' "$nombre" | awk '{print $1}' | numfmt --from=iec-i --suffix=B 2>/dev/null | tr -d B || echo 0)
    [ "${m:-0}" -gt "$pico" ] 2>/dev/null && pico=$m
    sleep 2
  done
  local codigo
  codigo=$(docker inspect -f '{{.State.ExitCode}}' "$nombre")
  docker logs --tail 5 "$nombre"
  docker rm "$nombre" >/dev/null
  echo "[medida] $1: $((SECONDS - inicio)) s, pico $((pico / 1048576)) MiB, codigo $codigo"
  [ "$codigo" = 0 ]
}

if [ ! -s pie.osrm.cell_metrics ]; then
  medir osrm-extract -p /opt/foot.lua /data/pie.osm.pbf
  medir osrm-partition /data/pie.osrm
  medir osrm-customize /data/pie.osrm
fi

du -sh "$DESTINO"
echo listo
