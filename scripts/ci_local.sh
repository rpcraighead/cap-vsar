#!/usr/bin/env bash
# CAP V-SAR — run every suite that needs neither X-Plane nor Air Manager.
#
# Install at: scripts/ci_local.sh   (chmod +x). CI calls the same script.
#
#   scripts/ci_local.sh            # developer machine; sandboxes HOME, shims liblua if absent
#   scripts/ci_local.sh --no-shim  # CI: liblua5.4-0 is installed by apt, no shim
#
# Exit code is non-zero if any suite fails. Per-suite logs land in .ci-out/.
# Nothing here writes outside the repo and .ci-out/; HOME is redirected so a
# test that resolves ~/Air Manager or ~/X-Plane 12 cannot touch a real one.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/.ci-out"
PY="${PYTHON:-python3}"
SHIM=1; [ "${1:-}" = "--no-shim" ] && SHIM=0
rm -rf "$OUT"; mkdir -p "$OUT/home" "$OUT/shim"

# The Lua tests dlopen /usr/lib/x86_64-linux-gnu/liblua5.4.so.0 by absolute
# path. Where the distro ships only the C++ build (no C-linkage symbols), fetch
# the real package into .ci-out without root and redirect the load.
if [ "$SHIM" = 1 ] && [ ! -e /usr/lib/x86_64-linux-gnu/liblua5.4.so.0 ]; then
  if command -v apt-get >/dev/null && command -v dpkg-deb >/dev/null; then
    ( cd "$OUT" && apt-get download liblua5.4-0 >/dev/null 2>&1 && dpkg-deb -x liblua5.4-0_*.deb lua ) || true
  fi
  LIB="$(find "$OUT/lua" -name 'liblua5.4.so.0' 2>/dev/null | head -1)"
  if [ -n "$LIB" ]; then
    cat > "$OUT/shim/sitecustomize.py" <<EOF
import ctypes, os
_orig = ctypes.CDLL
class _CDLL(_orig):
    def __init__(self, name, *a, **k):
        if isinstance(name, str) and name.endswith('liblua5.4.so.0') and not os.path.exists(name):
            name = '$LIB'
        super().__init__(name, *a, **k)
ctypes.CDLL = _CDLL
EOF
    echo "liblua5.4.so.0 not installed; shimmed to $LIB"
  else
    echo "WARNING: liblua5.4.so.0 not available — Lua suites will error" >&2
  fi
fi

export HOME="$OUT/home" XDG_CACHE_HOME="$OUT/home/.cache" XDG_CONFIG_HOME="$OUT/home/.config"
export PYTHONPATH="$OUT/shim:$ROOT" PYTHONDONTWRITEBYTECODE=1
cd "$ROOT" || exit 1

FAILED=()
run() { local name=$1; shift; local start=$SECONDS
  ( timeout 900 "$@" ) > "$OUT/$name.log" 2>&1; local rc=$?
  echo "exit=$rc seconds=$((SECONDS-start))" >> "$OUT/$name.log"
  printf '%-14s %s  %s\n' "$name" "$([ $rc = 0 ] && echo PASS || echo FAIL)" "$(grep -E 'passed|failed|ALL PASS|FAILURES|error' "$OUT/$name.log" | tail -1 | cut -c1-90)"
  [ $rc = 0 ] || FAILED+=("$name")
}

echo "commit $(git rev-parse --short HEAD 2>/dev/null || echo '?')  $($PY --version 2>&1)  $(date -u +%FT%TZ)"
run engine       $PY tests/test_engine.py
run faceplate    $PY tests/test_faceplate.py
run geodesy      $PY tests/test_geodesy.py
run propagation  $PY tests/test_propagation.py
run luacheck     $PY scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua instruments/_shared/lib/*.lua
run pytest_root  $PY -m pytest tests -q -p no:cacheprovider -rf \
                   --ignore=tests/test_engine.py --ignore=tests/test_faceplate.py \
                   --ignore=tests/test_geodesy.py --ignore=tests/test_propagation.py
run pytest_ai    $PY -m pytest services/ai_pilot/tests -q -p no:cacheprovider -rf
run pytest_fp    $PY -m pytest services/flightplanner/tests -q -p no:cacheprovider -rf
run pytest_board $PY -m pytest services/board/tests -q -p no:cacheprovider -rf

echo
if [ ${#FAILED[@]} = 0 ]; then echo "ALL SUITES PASS"; exit 0; fi
echo "FAILED: ${FAILED[*]}   (logs in .ci-out/)"; exit 1
