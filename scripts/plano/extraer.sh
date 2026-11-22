#!/usr/bin/env bash
# Recorta la build diaria de Protomaps (todo el planeta, ~140 GB) al contorno de
# México con 10 km de margen (mexico.geojson) y deja `mexico.pmtiles` en la
# carpeta que se pase (la de MAPO_PLANO_DATOS). Baja solo los pedazos que
# necesita: ~1.3 GB de red, ~1.2 GB en disco, unos minutos.
#
#   scripts/plano/extraer.sh ~/srv/mapo-plano            # la build más nueva
#   scripts/plano/extraer.sh ~/srv/mapo-plano 20261122   # una fecha fija
#
# Necesita `pmtiles` (go-pmtiles) en el PATH; en Linux x86_64 lo baja solo a
# ~/.local/bin si falta. Detalle en docs/fuentes/plano.md.
set -euo pipefail

destino="${1:?uso: extraer.sh CARPETA [AAAAMMDD]}"
fecha="${2:-}"
aqui="$(cd "$(dirname "$0")" && pwd)"
version_cli=1.31.2

if ! command -v pmtiles >/dev/null; then
  if [[ "$(uname -s)-$(uname -m)" != "Linux-x86_64" ]]; then
    echo "Falta pmtiles: https://github.com/protomaps/go-pmtiles/releases" >&2
    exit 1
  fi
  mkdir -p ~/.local/bin
  curl -fsSL "https://github.com/protomaps/go-pmtiles/releases/download/v${version_cli}/go-pmtiles_${version_cli}_Linux_x86_64.tar.gz" |
    tar xz -C ~/.local/bin pmtiles
  export PATH="$HOME/.local/bin:$PATH"
fi

if [[ -z "$fecha" ]]; then
  fecha="$(curl -fsSL https://build-metadata.protomaps.dev/builds.json |
    grep -o '"key": *"[0-9]\{8\}\.pmtiles"' | tail -1 | grep -o '[0-9]\{8\}')"
fi
echo "Build de Protomaps: $fecha"

mkdir -p "$destino"
temporal="$destino/mexico.pmtiles.parcial"
pmtiles extract "https://build.protomaps.com/${fecha}.pmtiles" "$temporal" \
  --region="$aqui/mexico.geojson"
# Se cambia de una vez: Mapo nunca sirve un archivo a medias.
mv -f "$temporal" "$destino/mexico.pmtiles"
echo "$fecha" > "$destino/BUILD"
# sed y no head: head corta el tubo y, con pipefail, el script daría error.
pmtiles show "$destino/mexico.pmtiles" | sed -n 1,12p
