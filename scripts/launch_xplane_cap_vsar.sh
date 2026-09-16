#!/usr/bin/env bash
# Launch X-Plane with ms01's local CA trusted only by this process tree.
#
# Optional, and OFF unless asked for: bring X-Plane up already flying, with no
# Quick Flight menu to click. Anything not recognised here is passed through to
# X-Plane untouched, so every existing invocation behaves exactly as before.
#
#   --no-menu               skip the Quick Flight screen (--pref:_show_qfl_on_start=0)
#   --engine-running        start with the engine running (--start_running)
#   --air-start ICAO/RWY[@NM]   come up on final, e.g. KRNM/09@9
#
#   ./scripts/launch_xplane_cap_vsar.sh --no-menu --engine-running --air-start KRNM/09@9
#
# UNVERIFIED: --load_llah and --start_running appear in the binary but in
# neither `--help` nor any format string, so the separator and the altitude
# UNITS inside --load_llah are hypotheses. Launch, then read the position back
# and confirm it is where you asked for - do not assume it took. The menu
# preference is documented (`--help` covers --pref:<key>=<value>) and is the
# part most likely to work first time.
set -euo pipefail

XP_ARGS=()
AIR_START=""
while (( $# )); do
  case "$1" in
    --no-menu)         XP_ARGS+=(--pref:_show_qfl_on_start=0); shift ;;
    --engine-running)  XP_ARGS+=(--start_running); shift ;;
    --air-start)
      [[ $# -ge 2 ]] || { echo "--air-start needs ICAO/RWY[@NM], e.g. KRNM/09@9" >&2; exit 2; }
      AIR_START=$2; shift 2 ;;
    *)                 XP_ARGS+=("$1"); shift ;;
  esac
done

CAPVSAR_USER_HOME=$(getent passwd "$(id -u)" | cut -d: -f6)
XPLANE_BIN=${CAPVSAR_XPLANE_BIN:-"$CAPVSAR_USER_HOME/X-Plane 12/X-Plane-x86_64"}
CAPVSAR_CA=${CAPVSAR_CA_CERT:-"$CAPVSAR_USER_HOME/.local/share/cap-vsar/mission-base-ca.crt"}
SYSTEM_CA=/etc/ssl/certs/ca-certificates.crt
BUNDLE_DIR=${CAPVSAR_XPLANE_CACHE:-"$CAPVSAR_USER_HOME/.cache/cap-vsar"}
BUNDLE=$BUNDLE_DIR/xplane-ca-bundle.crt

[[ -x "$XPLANE_BIN" ]] || { echo "X-Plane executable not found: $XPLANE_BIN" >&2; exit 1; }
[[ -r "$CAPVSAR_CA" ]] || {
  echo "CAP V-SAR CA not found: $CAPVSAR_CA" >&2
  echo "Copy ms01:/srv/capvsar/services/exercise/radio-public/mission-base-ca.crt there first." >&2
  exit 1
}
[[ -r "$SYSTEM_CA" ]] || { echo "System CA bundle not found: $SYSTEM_CA" >&2; exit 1; }

if [[ -n "$AIR_START" ]]; then
  # ICAO/RWY[@NM] -> the geometry already lives in set_air_start.py, which reads
  # X-Plane's own apt.dat. Recomputing runway positions here would be a second
  # copy of the truth, free to drift from the first.
  [[ "$AIR_START" =~ ^([A-Za-z0-9]+)/([0-9]{1,2}[LRClrc]?)(@([0-9.]+))?$ ]] || {
    echo "--air-start wants ICAO/RWY[@NM], e.g. KRNM/09@9 (got '$AIR_START')" >&2; exit 2; }
  AS_ICAO=${BASH_REMATCH[1]}; AS_RWY=${BASH_REMATCH[2]}; AS_NM=${BASH_REMATCH[4]:-9}
  AS_PY=${CAPVSAR_PYTHON:-python3}
  AS_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
  LLAH=$("$AS_PY" "$AS_REPO/scripts/set_air_start.py" --airport "$AS_ICAO" \
           --runway "$AS_RWY" --distance-nm "$AS_NM" --emit-llah) || {
    echo "could not compute the air start for $AIR_START" >&2; exit 2; }
  XP_ARGS+=("--load_llah=$LLAH")
  echo "air start: $AS_ICAO runway $AS_RWY, $AS_NM nm final -> --load_llah=$LLAH" >&2
  echo "  UNVERIFIED flag: read the position back after launch and confirm it took." >&2
fi

mkdir -p "$BUNDLE_DIR"
umask 077
cat "$SYSTEM_CA" "$CAPVSAR_CA" > "$BUNDLE.tmp"
mv "$BUNDLE.tmp" "$BUNDLE"

exec env SSL_CERT_FILE="$BUNDLE" "$XPLANE_BIN" "${XP_ARGS[@]}"
