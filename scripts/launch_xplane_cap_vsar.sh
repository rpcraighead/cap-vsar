#!/usr/bin/env bash
# Launch X-Plane with ms01's local CA trusted only by this process tree.
set -euo pipefail

XPLANE_BIN=${CAPVSAR_XPLANE_BIN:-"$HOME/X-Plane 12/X-Plane-x86_64"}
CAPVSAR_CA=${CAPVSAR_CA_CERT:-"${XDG_DATA_HOME:-$HOME/.local/share}/cap-vsar/mission-base-ca.crt"}
SYSTEM_CA=/etc/ssl/certs/ca-certificates.crt
BUNDLE_DIR=${XDG_CACHE_HOME:-$HOME/.cache}/cap-vsar
BUNDLE=$BUNDLE_DIR/xplane-ca-bundle.crt

[[ -x "$XPLANE_BIN" ]] || { echo "X-Plane executable not found: $XPLANE_BIN" >&2; exit 1; }
[[ -r "$CAPVSAR_CA" ]] || {
  echo "CAP V-SAR CA not found: $CAPVSAR_CA" >&2
  echo "Copy ms01:/srv/capvsar/services/exercise/radio-public/mission-base-ca.crt there first." >&2
  exit 1
}
[[ -r "$SYSTEM_CA" ]] || { echo "System CA bundle not found: $SYSTEM_CA" >&2; exit 1; }

mkdir -p "$BUNDLE_DIR"
umask 077
cat "$SYSTEM_CA" "$CAPVSAR_CA" > "$BUNDLE.tmp"
mv "$BUNDLE.tmp" "$BUNDLE"

exec env SSL_CERT_FILE="$BUNDLE" "$XPLANE_BIN" "$@"
