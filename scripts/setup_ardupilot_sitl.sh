#!/usr/bin/env bash
# Build ArduPilot ArduPlane SITL for the CAP V-SAR bounded trial (docs/ARDUPLANE_TRIAL.md).
#
# Everything lands under ~/.cache/capvsar; this script never writes into the
# repository. Idempotent: re-running updates nothing that is already at the
# pinned revision and already built.
#
#   scripts/setup_ardupilot_sitl.sh           # clone, venv, build
#   scripts/setup_ardupilot_sitl.sh --check   # report what would be done, change nothing
#
# The pin is a release tag that ships the DRef-based X-Plane backend and its
# Tools/autotest/models/xplane_plane.json (verified 2026-09-17). Bump it
# deliberately; the trial record must name the revision that flew.
set -euo pipefail

ARDUPILOT_REF="${ARDUPILOT_REF:-Plane-4.7.1}"
ARDUPILOT_URL="https://github.com/ArduPilot/ardupilot.git"
CACHE="${HOME}/.cache/capvsar"
SRC="${CACHE}/ardupilot"
VENV="${CACHE}/ardupilot-venv"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

say() { printf '%s\n' "$*"; }
plan() { if [ "$CHECK" = 1 ]; then say "would: $*"; else say "$*"; fi; }

for tool in git gcc g++ make python3; do
    command -v "$tool" >/dev/null || { say "missing: $tool"; exit 1; }
done

# 1. source at the pinned revision
if [ -d "$SRC/.git" ]; then
    have="$(git -C "$SRC" describe --tags --exact-match 2>/dev/null || git -C "$SRC" rev-parse --short HEAD)"
    if [ "$have" = "$ARDUPILOT_REF" ]; then
        say "source: $SRC already at $ARDUPILOT_REF"
    else
        plan "checkout $ARDUPILOT_REF in $SRC (currently $have)"
        [ "$CHECK" = 1 ] || { git -C "$SRC" fetch --depth 1 origin "tag" "$ARDUPILOT_REF"; git -C "$SRC" checkout -q "$ARDUPILOT_REF"; git -C "$SRC" submodule update --init --recursive --depth 1; }
    fi
else
    plan "clone $ARDUPILOT_URL@$ARDUPILOT_REF into $SRC"
    [ "$CHECK" = 1 ] || { mkdir -p "$CACHE"; git clone --depth 1 --branch "$ARDUPILOT_REF" --recurse-submodules --shallow-submodules "$ARDUPILOT_URL" "$SRC"; }
fi
if [ -f "$SRC/Tools/autotest/models/xplane_plane.json" ]; then
    say "mapping: stock xplane_plane.json present at $ARDUPILOT_REF"
elif [ "$CHECK" = 0 ]; then
    say "ERROR: $ARDUPILOT_REF has no Tools/autotest/models/xplane_plane.json - not the DRef X-Plane backend"; exit 1
fi

# 2. python for waf and MAVProxy. The system interpreter has no pip; use any
#    interpreter that does to seed the venv, else waf's own python needs empy.
if [ -x "$VENV/bin/python3" ]; then
    say "venv: $VENV present"
else
    seed=""
    for candidate in "$CACHE/capvsar-planner-venv/bin/python3" python3; do
        if "$candidate" -m pip --version >/dev/null 2>&1; then seed="$candidate"; break; fi
    done
    [ -n "$seed" ] || { say "no python with pip found to seed $VENV"; exit 1; }
    plan "create venv $VENV from $seed and install empy==3.3.4 pexpect future (+ optional pymavlink MAVProxy)"
    if [ "$CHECK" = 0 ]; then
        "$seed" -m venv "$VENV"
        "$VENV/bin/python3" -m pip install --quiet --upgrade pip
        # Required: waf's build generates code with empy and drives tests with pexpect.
        "$VENV/bin/python3" -m pip install --quiet "empy==3.3.4" pexpect future
        # Optional: only sim_vehicle.py needs these, and pymavlink builds a C
        # extension that wants Python headers this box does not have. The trial
        # runs the arduplane binary directly and speaks MAVLink with
        # services/ai_pilot/mavlink_min.py, so a failure here is not fatal.
        "$VENV/bin/python3" -m pip install --quiet pymavlink MAVProxy 2>/dev/null \
            || say "note: pymavlink/MAVProxy unavailable (needs python3-dev); sim_vehicle.py path disabled, binary path unaffected"
    fi
fi

# 3. build plane for the sitl board
BIN="$SRC/build/sitl/bin/arduplane"
if [ -x "$BIN" ]; then
    say "build: $BIN present"
else
    plan "waf configure --board sitl && waf plane in $SRC"
    [ "$CHECK" = 1 ] || ( cd "$SRC" && PATH="$VENV/bin:$PATH" ./waf configure --board sitl >/dev/null && PATH="$VENV/bin:$PATH" ./waf plane )
fi

cat <<EOF

Launch (X-Plane 12 already running with CAP 487 airborne; ports 49000/49001 per X-Plane.prf):

  # binary directly - what the trial uses; MAVLink on tcp:127.0.0.1:5760
  cd $SRC && ./build/sitl/bin/arduplane --model xplane --defaults $REPO/xplane/ardupilot/cap487.parm

  # or with MAVProxy console/map
  PATH=$VENV/bin:\$PATH $SRC/Tools/autotest/sim_vehicle.py -v ArduPlane -f xplane --no-rebuild \\
      --add-param-file $REPO/xplane/ardupilot/cap487.parm

Copy $REPO/xplane/ardupilot/xplane_plane_cap487.json to $SRC/xplane_plane.json
AFTER filling in this rig's joystick axis indices (see docs/ARDUPLANE_TRIAL.md, pre-check P4).
EOF
