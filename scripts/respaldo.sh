#!/usr/bin/env bash
# Respaldo de la base de producción con pg_dump (docs/despliegue.md).
# Guarda los últimos 7. Uso: scripts/respaldo.sh [carpeta]
set -euo pipefail

destino="${1:-$HOME/srv/mapo-respaldos}"
guardar=7

# El volcado trae correos y tokens de sesión: solo lo lee el dueño
umask 077
mkdir -p "$destino"

archivo="$destino/mapo_prod-$(date +%Y%m%d-%H%M).dump"
trap 'rm -f "$archivo.tmp"' EXIT
docker compose -p mapo-prod exec -T db pg_dump -U mapo -Fc mapo_prod > "$archivo.tmp"
mv "$archivo.tmp" "$archivo"

ls -1t "$destino"/mapo_prod-*.dump | tail -n +$((guardar + 1)) | xargs -r rm --
echo "$(date '+%F %T') $archivo $(du -h "$archivo" | cut -f1)"
