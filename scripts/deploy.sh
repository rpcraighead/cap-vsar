#!/usr/bin/env bash
# CAP V-SAR - deploy/refresh the lab service stack on ms01.
# Idempotent: safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

[ -f .env ] || { echo "ERROR: .env missing. cp .env.example .env and fill it in."; exit 1; }

# .env is NOT sourced: compose parses it with its own rules, and a shell parser
# mangles values containing $, # or spaces (and would execute a stray line).
# deploy_lib.sh reads only the keys this script needs.
. "$ROOT/scripts/deploy_lib.sh"

# O2-3: a blank Mumble password deploys a password-less voice net on the one
# port the router forwards to the internet. Compose refuses it too; failing
# here says why before anything is pulled or built.
for var in MUMBLE_SUPERUSER_PASSWORD MUMBLE_SERVER_PASSWORD; do
  [ -n "$(cfg "$var")" ] || { echo "ERROR: $var is empty in .env. Set it before deploying."; exit 1; }
done

# ---------------------------------------------------------------- host paths
# Every path compose bind-mounts has to exist before it starts, and all of them
# are runtime state, so all of them are gitignored - which means a fresh clone
# has none of them. Docker's behaviour on a missing path is what makes this
# worth doing carefully: for a DIRECTORY mount it silently creates the
# directory, but for a FILE mount it creates a DIRECTORY where a file was
# meant to be. The flight planner then dies at import with
# "unable to open database file" and gunicorn crash-loops, which is a
# confusing way to learn that a directory was created for you. The board's
# SSH key and known_hosts are file mounts too (O2-5), which is why the board
# is an opt-in compose profile started only once those files are real.
#
# CAPVSAR_STATE_DIR (O2-7) moves all of this out of the checkout; see
# docker-compose.yml. Nothing is moved for you.
#
# The mumble image generates /data/mumble_server_config.ini from the
# MUMBLE_CONFIG_* variables in docker-compose.yml on every start. Do not write
# that file here - it will be overwritten.
echo "==> host paths"
prepare_host_paths
STATE="$(state_dir)"

# The exercise image runs as uid/gid 1000. Older deployments created the
# SQLite file as root, so a newly rebuilt non-root image could read it but
# crash on the first schema migration. Repair only this service's data mount.
sudo chown -R 1000:1000 "$STATE/services/exercise/data"

# O2-5: the board needs a clone, a deploy key and known_hosts that cannot be
# invented here. Without them it is simply not part of this deploy.
PROFILE_ARGS=()
BUILD_SERVICES=(exercise flightplanner)
if BOARD_WHY=$(board_configured); then
  PROFILE_ARGS=(--profile board)
  BUILD_SERVICES+=(board)
  echo "    board: configured, included in this deploy"
else
  echo "    $BOARD_WHY"
  echo "    (see services/board/README.md for the one-time setup)"
fi
dc() { docker compose ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} "$@"; }

echo "==> pulling images"
dc pull --quiet

echo "==> building source services"
# exercise, flightplanner (and board, when configured) are local build contexts. `compose up` recreates
# them when configuration changes but does not rebuild after a source-only
# update, which can leave ms01 running an older application under a new proxy.
dc build "${BUILD_SERVICES[@]}"

echo "==> starting stack"
dc up -d

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
dc stop mumble
sudo python3 scripts/provision_mumble.py "$STATE/mumble/data/mumble-server.sqlite"
dc start mumble

# ------------------------------------------------------- browser radio trust
# Tablets need a trusted secure context before a browser will hand the radio
# console a microphone. Caddy mints its own root CA on first boot and keeps it
# inside a named volume, where nothing else can read it - so the console serves
# /radio-ca.crt from services/exercise/radio-public instead, and this is the
# step that puts it there. Until this ran, that directory was populated by hand
# on ms01 and was simply empty anywhere else.
CA_SRC=/data/caddy/pki/authorities/local/root.crt
CA_DST="$STATE/services/exercise/radio-public/mission-base-ca.crt"
echo "==> browser radio CA"
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if dc exec -T radio-https test -f "$CA_SRC" 2>/dev/null; then
    dc exec -T radio-https cat "$CA_SRC" > "$CA_DST.tmp" 2>/dev/null \
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
dc ps
echo
echo "Mumble: $(hostname -I | awk '{print $1}'):64738   (server password in .env)"
echo "CAP V-SAR: https://$(hostname -I | awk '{print $1}')/"
echo "Planner:   https://$(hostname -I | awk '{print $1}')/planner/"
echo
echo "NOTE: not reachable from the internet until the router forwards 64738"
echo "      TCP+UDP to this host - see infra/ROUTER.md."
echo "      WireGuard runs on the ROUTER (wgserver), not on this host."
echo "      Exercise :8700 and planner :8080 are private container ports."
