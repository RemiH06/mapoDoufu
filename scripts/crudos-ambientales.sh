#!/usr/bin/env bash
# Descarga en crudo las fuentes ambientales de la sesión 22, sin cargarlas.
# Uso: crudos-ambientales.sh <lista.tsv> [destino]
# Se puede relanzar: salta lo que ya bajó y reanuda lo que quedó a medias.
# Deja MANIFIESTO.tsv (archivo, bytes, sha256, fecha, url) y FALLAS.tsv.
set -uo pipefail

LISTA="${1:?falta la lista .tsv}"
DESTINO="${2:-$HOME/srv/mapo-crudos/ambiental}"
mkdir -p "$DESTINO"
MANIFIESTO="$DESTINO/MANIFIESTO.tsv"
FALLAS="$DESTINO/FALLAS.tsv"
: > "$FALLAS"
[ -f "$MANIFIESTO" ] || printf 'archivo\tbytes\tsha256\tfecha\turl\n' > "$MANIFIESTO"

bajar() {  # carpeta archivo url
  local carpeta="$1" archivo="$2" url="$3"
  local ruta="$DESTINO/$carpeta/$archivo"
  mkdir -p "$DESTINO/$carpeta"
  if [ -s "$ruta" ]; then echo "ya estaba: $carpeta/$archivo"; return; fi
  echo "bajando: $carpeta/$archivo"
  if curl -fL --retry 4 --retry-delay 15 --connect-timeout 60 --max-time 3600 \
       -A "Mozilla/5.0" -C - -o "$ruta.part" "$url"; then
    # Algunos servidores responden 200 con una página HTML en vez del archivo.
    if head -c 1024 "$ruta.part" | grep -qiE '<!doctype html|<html'; then
      printf '%s/%s\thtml en vez de archivo\t%s\n' "$carpeta" "$archivo" "$url" >> "$FALLAS"
      rm -f "$ruta.part"; return
    fi
    mv "$ruta.part" "$ruta"
    printf '%s/%s\t%s\t%s\t%s\t%s\n' "$carpeta" "$archivo" "$(stat -c %s "$ruta")" \
      "$(sha256sum "$ruta" | cut -d' ' -f1)" "$(date -Iseconds)" "$url" >> "$MANIFIESTO"
  else
    printf '%s/%s\tcurl %s\t%s\n' "$carpeta" "$archivo" "$?" "$url" >> "$FALLAS"
  fi
}

# Lista fija.
grep -v '^#' "$LISTA" | while IFS=$'\t' read -r carpeta archivo url; do
  [ -n "${url:-}" ] && bajar "$carpeta" "$archivo" "$url"
done

# Series por año.
for y in $(seq 2003 2025); do
  bajar agricultura "siap_municipal_$y.csv" \
    "https://nube.agricultura.gob.mx/index.php?view=10AE434F-A2158368-A120BC5A-EDF4AFAA&ANIO=$y"
done
for y in $(seq 2000 2025); do
  bajar incendios "firms_modis_$y.csv" \
    "https://firms.modaps.eosdis.nasa.gov/data/country/modis/$y/modis_${y}_Mexico.csv"
done
for y in $(seq 2012 2025); do
  bajar incendios "firms_viirs_snpp_$y.csv" \
    "https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/$y/viirs-snpp_${y}_Mexico.csv"
done
for y in $(seq 2020 2023); do
  bajar salud "defunciones_$y.zip" \
    "https://www.inegi.org.mx/contenidos/programas/edr/datosabiertos/defunciones/$y/conjunto_de_datos_defunciones_registradas_${y}_csv.zip"
done

# Relieve: Copernicus DEM GLO-30, mosaicos de 1 grado que cubren Jalisco.
# Los que caen en el mar no existen y quedan en FALLAS.tsv.
for lat in 18 19 20 21 22; do
  for lon in 101 102 103 104 105 106; do
    t="Copernicus_DSM_COG_10_N${lat}_00_W${lon}_00_DEM"
    bajar relieve "$t.tif" "https://copernicus-dem-30m.s3.amazonaws.com/$t/$t.tif"
  done
done

echo "listo: $(($(wc -l < "$MANIFIESTO") - 1)) archivos, $(wc -l < "$FALLAS") fallas"
du -sh "$DESTINO"
