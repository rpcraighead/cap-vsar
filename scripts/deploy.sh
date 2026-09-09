#!/usr/bin/env bash
# CAP V-SAR - deploy/refresh the lab service stack on ms01.
# Idempotent: safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

[ -f .env ] || { echo "ERROR: .env missing. cp .env.example .env and fill it in."; exit 1; }
set -a; . ./.env; set +a

# ---------------------------------------------------------------- host paths
# Every path compose bind-mounts has to exist before it starts, and all of them
# are runtime state, so all of them are gitignored - which means a fresh clone
# has none of them. Docker's behaviour on a missing path is what makes this
# worth doing carefully: for a DIRECTORY mount it silently creates the
# directory, but for a FILE mount it creates a DIRECTORY where a file was
# meant to be. The flight planner then dies at import with
# "unable to open database file" and gunicorn crash-loops, which is a
# confusing way to learn that a directory was created for you.
#
# The mumble image generates /data/mumble_server_config.ini from the
# MUMBLE_CONFIG_* variables in docker-compose.yml on every start. Do not write
# that file here - it will be overwritten.
echo "==> host paths"
mkdir -p mumble/data
mkdir -p services/exercise/data                 # exercise.db lives here
mkdir -p services/exercise/radio-public         # CA cert served at /radio-ca.crt
mkdir -p services/flightplanner/data/charts     # cached chart tiles

# A file mount, not a directory mount - see above. An empty file is a valid
# SQLite database; init_database() creates the schema on first run.
[ -e services/flightplanner/data/aviation_data.db ] \
  || : > services/flightplanner/data/aviation_data.db

echo "==> pulling images"
docker compose pull --quiet

echo "==> starting stack"
docker compose up -d

# --------------------------------------------------------- mumble channel tree
# Murmur has no config-file channel definition and caches its ACL/channel
# state in memory, so provision_mumble.py has to run against a stopped
# server - and needs the sqlite schema Murmur creates on its own first boot,
# which "docker compose up -d" above just did. Idempotent: an
# already-provisioned tree (including ms01's hand-made one) is left alone,
# so stopping mumble briefly on every deploy is the only real cost of running
# this unconditionally.
#
# mumble-server.sqlite is owned by the container's internal uid (10000:10000
# in the image, shows up as a bare numeric uid on the host since a bind mount
# doesn't remap it) mode 640 - the deploying user normally cannot open it at
# all, let alone write it. sudo, not a chmod/chown on data a running database
# depends on the ownership of.
echo "==> mumble channel tree"
docker compose stop mumble
sudo python3 scripts/provision_mumble.py mumble/data/mumble-server.sqlite
docker compose start mumble

# ------------------------------------------------------- browser radio trust
# Tablets need a trusted secure context before a browser will hand the radio
# console a microphone. Caddy mints its own root CA on first boot and keeps it
# inside a named volume, where nothing else can read it - so the console serves
# /radio-ca.crt from services/exercise/radio-public instead, and this is the
# step that puts it there. Until this ran, that directory was populated by hand
# on ms01 and was simply empty anywhere else.
CA_SRC=/data/caddy/pki/authorities/local/root.crt
CA_DST=services/exercise/radio-public/mission-base-ca.crt
echo "==> browser radio CA"
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if docker compose exec -T radio-https test -f "$CA_SRC" 2>/dev/null; then
    docker compose exec -T radio-https cat "$CA_SRC" > "$CA_DST.tmp" 2>/dev/null \
      && mv "$CA_DST.tmp" "$CA_DST" \
      && echo "    published $CA_DST" \
      && break
  fi
  rm -f "$CA_DST.tmp"
  [ "$attempt" = 10 ] && echo "    WARNING: Caddy has not minted its CA yet;" \
      "re-run this script once it is up or tablets cannot reach the radio."
  sleep 2
done

echo "==> status"
docker compose ps
echo
echo "Mumble: $(hostname -I | awk '{print $1}'):64738   (server password in .env)"
echo
echo "NOTE: not reachable from the internet until the router forwards 64738"
echo "      TCP+UDP to this host - see infra/ROUTER.md."
echo "      WireGuard runs on the ROUTER (wgserver), not on this host."
