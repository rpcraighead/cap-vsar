#!/usr/bin/env bash
# CAP V-SAR — run every suite that needs neither X-Plane nor Air Manager.
#
# The one test command is scripts/run_tests.sh, which is this script. CI
# (.gitea/workflows/ci.yml) calls it with --no-shim.
#
# SETUP (O2-2), once:  python3.12 -m venv .venv && . .venv/bin/activate &&
#                      pip install -r requirements-dev.txt
#
#   scripts/run_tests.sh               # developer machine; sandboxes HOME, shims liblua if absent
#   scripts/run_tests.sh --no-shim     # CI: liblua5.4-0 is installed by apt, no shim
#   scripts/run_tests.sh --pytest-only # just the four pytest suites (no Lua, no engine scripts)
#   PYTHON=/path/to/python scripts/run_tests.sh
#
# Four pytest suites run in four SEPARATE processes - root tests/, ai_pilot,
# flightplanner, board - because services/exercise/app, services/board/app and
# services/flightplanner/app.py are all imported as "app" and cannot coexist in
# one interpreter.
#
# Exit code is non-zero if any suite fails. Per-suite logs land in .ci-out/
# (gitignored).
# Nothing here writes outside the repo and .ci-out/; HOME is redirected so a
# test that resolves ~/Air Manager or ~/X-Plane 12 cannot touch a real one.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/.ci-out"
PY="${PYTHON:-python3}"
SHIM=1; PYTEST_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-shim) SHIM=0 ;;
    --pytest-only) PYTEST_ONLY=1; SHIM=0 ;;
    *) echo "usage: $0 [--no-shim] [--pytest-only]" >&2; exit 2 ;;
  esac
done

# Fail early and say how to fix it, rather than 4 suites of ImportError.
MISSING="$($PY - <<'PYEOF'
import importlib.util as u
need = {"fastapi": "fastapi", "httpx": "httpx", "pytest": "pytest", "flask": "Flask",
        "pygeomag": "pygeomag", "numpy": "numpy", "PIL": "Pillow", "markdown": "Markdown",
        "requests": "requests"}
print(" ".join(pkg for mod, pkg in need.items() if u.find_spec(mod) is None))
PYEOF
)"
if [ -n "$MISSING" ]; then
  echo "ERROR: $PY lacks: $MISSING" >&2
  echo "       python3.12 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt" >&2
  exit 2
fi
case "$($PY -c 'import sys;print("%d.%d" % sys.version_info[:2])')" in
  3.12) ;;
  *) echo "NOTE: $($PY --version 2>&1) is not 3.12, which the service images and CI use; results may differ." >&2 ;;
esac

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
export PYTHONPATH="$OUT/shim:$ROOT${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1
cd "$ROOT" || exit 1

FAILED=()
run() { local name=$1; shift; local start=$SECONDS
  ( timeout 900 "$@" ) > "$OUT/$name.log" 2>&1; local rc=$?
  echo "exit=$rc seconds=$((SECONDS-start))" >> "$OUT/$name.log"
  printf '%-14s %s  %s\n' "$name" "$([ $rc = 0 ] && echo PASS || echo FAIL)" "$(grep -E 'passed|failed|ALL PASS|FAILURES|error' "$OUT/$name.log" | tail -1 | cut -c1-90)"
  [ $rc = 0 ] || FAILED+=("$name")
}

echo "commit $(git rev-parse --short HEAD 2>/dev/null || echo '?')  $($PY --version 2>&1)  $(date -u +%FT%TZ)"
if [ "$PYTEST_ONLY" = 0 ]; then
run engine       $PY tests/test_engine.py
run faceplate    $PY tests/test_faceplate.py
run geodesy      $PY tests/test_geodesy.py
run propagation  $PY tests/test_propagation.py
run luacheck     $PY scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua instruments/_shared/lib/*.lua
fi
run pytest_root  $PY -m pytest tests -q -p no:cacheprovider -rf \
                   --ignore=tests/test_engine.py --ignore=tests/test_faceplate.py \
                   --ignore=tests/test_geodesy.py --ignore=tests/test_propagation.py
run pytest_ai    $PY -m pytest services/ai_pilot/tests -q -p no:cacheprovider -rf
run pytest_fp    $PY -m pytest services/flightplanner/tests -q -p no:cacheprovider -rf
run pytest_board $PY -m pytest services/board/tests -q -p no:cacheprovider -rf

echo
if [ ${#FAILED[@]} = 0 ]; then echo "ALL SUITES PASS"; exit 0; fi
echo "FAILED: ${FAILED[*]}   (logs in .ci-out/)"; exit 1
