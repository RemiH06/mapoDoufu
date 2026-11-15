#!/bin/bash
# Saca de la base de Mapo las capas que ya están cargadas (AGEB con su censo y
# DENUE) para una caja, en CSV con geometría WKT. `recorte.py` las mete al
# GeoPackage si encuentra la carpeta `mapo/` dentro de la salida.
#
#   scripts/ambiental/desde_mapo.sh SALIDA OESTE SUR ESTE NORTE [CONTENEDOR] [BASE] [USUARIO]
#
# Por omisión usa la base de producción en Pixilate (mapo-prod-db-1).
set -euo pipefail

salida=$1/mapo
oeste=$2 sur=$3 este=$4 norte=$5
contenedor=${6:-mapo-prod-db-1} base=${7:-mapo_prod} usuario=${8:-mapo}
mkdir -p "$salida"

# Los números se validan para que no viajen a SQL como texto arbitrario.
for v in "$oeste" "$sur" "$este" "$norte"; do
  [[ $v =~ ^-?[0-9]+(\.[0-9]+)?$ ]] || { echo "coordenada inválida: $v" >&2; exit 1; }
done
caja="ST_MakeEnvelope($oeste, $sur, $este, $norte, 4326)"

copiar() {
  docker exec -i "$contenedor" psql -v ON_ERROR_STOP=1 -U "$usuario" -d "$base" \
    -c "COPY ($2) TO STDOUT WITH CSV HEADER" > "$salida/$1.csv"
  echo "  $1: $(($(wc -l < "$salida/$1.csv") - 1)) filas"
}

# AGEB urbanas y rurales que tocan la caja. El censo por AGEB solo existe para
# las urbanas (RESAGEBURB): las rurales salen con el censo vacío y su población
# está en las localidades (ITER).
copiar agebs "
  SELECT a.cvegeo, a.cve_mun, a.cve_loc, a.cve_ageb, a.ambito,
         c.pobtot, c.vivtot, c.tvivhab, c.datos_json::text AS censo_json,
         ST_AsText(a.geom) AS wkt
  FROM agebs a
  LEFT JOIN fuente_censo_poblacion c ON c.cvegeo = a.cvegeo AND c.nivel = 'ageb'
  WHERE a.geom && $caja AND ST_Intersects(a.geom, $caja)"

# Sin teléfono, correo ni sitio web: para estudiar la zona no hacen falta.
copiar denue "
  SELECT id, nombre, razon_social, clase_actividad, estrato, tipo,
         cve_ent, cve_mun, cve_ageb, lat, lon,
         ST_AsText(ST_SetSRID(ST_MakePoint(lon, lat), 4326)) AS wkt
  FROM fuente_denue_negocios
  WHERE lon BETWEEN $oeste AND $este AND lat BETWEEN $sur AND $norte"
