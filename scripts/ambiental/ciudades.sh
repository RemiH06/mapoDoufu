#!/usr/bin/env bash
# Corre ciudades.py e imagenes.py para cada metrópoli y al final la tabla comparativa.
# Se puede relanzar: cada paso se salta si su salida ya existe.
#
#   scripts/ambiental/ciudades.sh BASE [ciudad ...]      (sin ciudades: todas)
#
# Ver docs/producto/comparacion-ciudades.md.
set -uo pipefail

aqui="$(cd "$(dirname "$0")" && pwd)"
base="${1:?falta la carpeta BASE}"
shift
ciudades=("$@")
[ $# -eq 0 ] && ciudades=(zmg mty pue leo mer hmo cdmx)
anio=2025
uv="${UV:-uv}"
py() { "$uv" run -q --script "$aqui/ciudades.py" --base "$base" "$@"; }

for c in "${ciudades[@]}"; do
  echo "== $c $(date '+%F %T')"
  py --paso agebs --ciudad "$c" || { echo "FALLÓ agebs $c"; continue; }
  read -r caja epsg < <(python3 -c "import json;d=json.load(open('$base/$c/ciudad.json'));print(','.join(map(str,d['caja'])),d['epsg'])")
  "$uv" run -q --script "$aqui/imagenes.py" --salida "$base/$c/imagenes" --caja="$caja" --epsg "$epsg" \
    --lst "$anio/$anio" --indices "$anio-03/$anio-05" || echo "FALLÓ imagenes $c"
  py --paso reales --ciudad "$c" --anio "$anio" || echo "FALLÓ reales $c"
  py --paso dosel --ciudad "$c" || echo "FALLÓ dosel $c"
  py --paso zonal --ciudad "$c" --anio "$anio" || echo "FALLÓ zonal $c"
  if [ "$c" = zmg ]; then py --paso colonias --ciudad "$c" --anio "$anio" || echo "FALLÓ colonias $c"; fi
done
py --paso resumen --anio "$anio"
echo "TERMINADO $(date '+%F %T')"
