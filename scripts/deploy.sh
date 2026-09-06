#!/usr/bin/env bash
# CAP V-SAR - deploy/refresh the lab service stack on ms01.
# Idempotent: safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

[ -f .env ] || { echo "ERROR: .env missing. cp .env.example .env and fill it in."; exit 1; }
set -a; . ./.env; set +a

# The mumble image generates /data/mumble_server_config.ini from the
# MUMBLE_CONFIG_* variables in docker-compose.yml on every start. Do not write
# that file here - it will be overwritten.
mkdir -p mumble/data

echo "==> pulling images"
docker compose pull --quiet

echo "==> starting stack"
docker compose up -d

echo "==> status"
docker compose ps
echo
echo "Mumble: $(hostname -I | awk '{print $1}'):64738   (server password in .env)"
echo
echo "NOTE: not reachable from the internet until the router forwards 64738"
echo "      TCP+UDP to this host - see infra/ROUTER.md."
echo "      WireGuard runs on the ROUTER (wgserver), not on this host."
