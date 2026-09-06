#!/usr/bin/env bash
# Show a WireGuard peer config (and QR) for handing to a participant.
#   scripts/wg-peer.sh              -> list peers
#   scripts/wg-peer.sh base-ic      -> print that peer's config + QR
set -euo pipefail
cd "$(dirname "$0")/.."
if [ $# -eq 0 ]; then
  echo "Peers:"; sudo ls wireguard/config 2>/dev/null | grep '^peer_' | sed 's/^peer_/  /'
  echo; echo "Usage: $0 <peer-name>"; exit 0
fi
P="peer_$1"
sudo test -d "wireguard/config/$P" || { echo "No such peer: $1"; exit 1; }
echo "--- $1.conf ---"
sudo cat "wireguard/config/$P/$P.conf"
echo
echo "--- QR (scan with the WireGuard mobile app) ---"
docker exec capvsar-wireguard /app/show-peer "$1" 2>/dev/null || \
  echo "(QR unavailable; hand over the .conf above)"
