#!/usr/bin/env bash
# CAP V-SAR - deploy/refresh the lab service stack on ms01.
# Idempotent: safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

[ -f .env ] || { echo "ERROR: .env missing. cp .env.example .env and fill it in."; exit 1; }
set -a; . ./.env; set +a

echo "==> rendering Mumble config"
mkdir -p mumble/data
sed "s|__SERVER_PASSWORD__|${MUMBLE_SERVER_PASSWORD}|g" \
    mumble/mumble_server_config.ini.tmpl > mumble/data/mumble_server_config.ini
chmod 600 mumble/data/mumble_server_config.ini

echo "==> pulling images"
docker compose pull --quiet

echo "==> starting stack"
docker compose up -d

echo "==> status"
docker compose ps
echo
echo "Mumble:    $(hostname -I | awk '{print $1}'):64738   (server password in .env)"
echo "WireGuard: peer configs in wireguard/config/peer_*/  (run scripts/wg-peer.sh to list)"
echo
echo "NOTE: neither is reachable from the internet until the router forwards"
echo "      the ports in infra/ROUTER.md to this host."
