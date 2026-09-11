"""
The console's DF stub, and the boundary between it and the real engine (P-11).

`services/exercise/app/propagation.py` is a mock-bridge stub, not a second
propagation model. It used to run whenever a station omitted `df`, so a plugin
that was loading, disabled or mid-reconnect silently handed the instructor a
different DF picture than the crew had - a fabricated display with nothing
marking it as fabricated.

These tests pin the two things that keep that from coming back: the stub agrees
with the engine on the figures it does model, and it says so about itself.

    python3 tests/test_propagation.py

Runs without FastAPI - propagation.py imports only the standard library, which
is itself part of it staying a stub.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import xp  # the stub, for the engine


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    # @dataclass resolves annotations through sys.modules, so register the
    # module before executing it.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# propagation.py imports the console's shared geodesy (C15-2), so it has to be
# loaded as part of its package rather than as a lone file.
sys.path.insert(0, os.path.join(ROOT, "services", "exercise"))
import app.propagation as prop  # noqa: E402
engine = load("capvsar_engine", os.path.join(ROOT, "xplane", "PI_capvsar_df.py"))

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("   " + detail if detail else ""))
    if not cond:
        FAILED.append(name)


BEACON = {"lat": 39.0, "lon": -105.0, "elev_ft": 9000.0, "band": "406", "power": 1.0}
AIRCRAFT = {"lat": 39.0833, "lon": -105.0, "alt_ft": 12000.0, "hdg_true": 180.0}

print("\n== the stub agrees with the engine where it models the same thing ==")
check("406 burst length matches the engine's",
      prop.BURST_LEN_S == engine.BURST_LEN_S,
      "stub %.2f s, engine %.2f s" % (prop.BURST_LEN_S, engine.BURST_LEN_S))
check("406 burst period matches the engine's",
      prop.BURST_PERIOD_S == engine.BURST_PERIOD_S,
      "stub %.0f s, engine %.0f s" % (prop.BURST_PERIOD_S, engine.BURST_PERIOD_S))

# The horizon is the one piece of real physics both carry, so it must agree.
for alt, elev in ((12000.0, 9000.0), (500.0, 0.0), (8500.0, 9000.0)):
    theirs = prop.radio_horizon_nm(alt, elev)
    ours = 1.23 * ((alt ** 0.5) + (elev ** 0.5))
    check("radio horizon at %.0f/%.0f ft matches the engine's form" % (alt, elev),
          abs(theirs - ours) < 1e-9, "%.1f NM" % theirs)

print("\n== the 406 burst gate (P-11) ==")
# 1.5 s was the old window, and it only composed a note: signal and bearing
# stayed live through the 49.5 s a 406 beacon is silent.
during = prop.compute(AIRCRAFT, BEACON, {}, elapsed_s=0.2)
between = prop.compute(AIRCRAFT, BEACON, {}, elapsed_s=25.0)
just_after = prop.compute(AIRCRAFT, BEACON, {}, elapsed_s=1.0)
check("a bearing is produced during the burst", during.valid,
      "signal %.2f" % during.signal)
check("between bursts there is no bearing and no signal",
      not between.valid and between.signal == 0.0,
      "valid=%s signal=%.2f note=%r" % (between.valid, between.signal, between.note))
check("...and 1.0 s in is already between bursts, not still in it",
      not just_after.valid, "the old window was 1.5 s")
check("the gap is reported rather than hidden", "between 406 burst" in between.note,
      between.note)

print("\n== band matching ==")
# Compared as the string "406" only, so a scenario carrying the float, or a
# real channel, silently got no burst cadence at all.
for band, expect in (("406", True), (406, True), (406.0, True), ("406.025", True),
                     (406_025_000 / 1e6, True),
                     ("121.5", False), (121.5, False), (243.0, False),
                     (None, False), ("", False)):
    check("band %-12r -> 406 is %s" % (band, expect),
          prop.is_406(band) == expect)

for band in ("406", 406.0, "406.025"):
    b = dict(BEACON, band=band)
    check("burst cadence applies for band %r" % band,
          not prop.compute(AIRCRAFT, b, {}, elapsed_s=25.0).valid)

print("\n== a stub result says it is a stub ==")
check("every result is marked synthetic",
      during.synthetic is True and between.synthetic is True)

print("\n== the stub is still a stub ==")
with open(os.path.join(ROOT, "services", "exercise", "app", "propagation.py"),
          encoding="utf-8") as fh:
    src = fh.read()
check("it pulls in nothing heavier than the console's own geodesy",
      "import requests" not in src and "fastapi" not in src
      and "import numpy" not in src)
check("it uses the shared geodesy rather than its own copy (C15-2)",
      "from .geo import" in src and "def distance_nm" not in src)
check("it does not claim to model terrain",
      "probeTerrain" not in src and "line_of_sight" not in src)
check("it names the engine as the authority",
      "PI_capvsar_df.py" in src)

# The guard that matters: the console must not synthesise DF for a station
# that simply did not report it.
# The ingest endpoint moved out of main.py into routers/telemetry.py when the
# console was split (C15-1). Read whichever file defines it rather than naming
# one, so this guard survives the next move.
INGEST = os.path.join(ROOT, "services", "exercise", "app", "routers",
                      "telemetry.py")
if not os.path.exists(INGEST):
    INGEST = os.path.join(ROOT, "services", "exercise", "app", "main.py")
with open(INGEST, encoding="utf-8") as fh:
    main_src = fh.read()
check("the console only synthesises DF when a caller opts in",
      "elif p.mock:" in main_src,
      "the fallback must be gated on the mock flag, not on 'df is None'")
check("the synthetic marker reaches the client",
      '"synthetic": True' in main_src)

print("\n" + ("ALL PASS" if not FAILED else "FAILURES: " + ", ".join(FAILED)))
sys.exit(1 if FAILED else 0)
