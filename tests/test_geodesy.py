"""
Every copy of the geodesy agrees (C15-2).

Bearing and distance are written out five times in this project. Four of those
cannot import the fifth: the DF plugin runs inside X-Plane's interpreter, the
flight planner is a separate container, and two are browser JavaScript. Copying
is the only option across those boundaries - so this is the guard instead, and
it is the guard that would have caught the F-3 bug, where `debrief.js` computed
a track heading without scaling longitude by cos(latitude): about 10 degrees of
error at 33 N, on the one number a debrief is read for.

Inside the exercise console there is no boundary and no excuse; app/geo.py is
the single implementation and app/propagation.py and mock_bridge.py import it.

    python3 tests/test_geodesy.py
"""
import importlib.util
import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "services", "exercise"))
import xp  # the stub, so the plugin will import  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("   " + detail if detail else ""))
    if not cond:
        FAILED.append(name)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


from app import geo                                            # noqa: E402
engine = load("capvsar_engine_geo", os.path.join(ROOT, "xplane", "PI_capvsar_df.py"))
planner_src = open(os.path.join(ROOT, "services", "flightplanner", "app.py"),
                   encoding="utf-8").read()

# The planner drags in Flask and an aviation database at import time, and this
# test only cares about four functions. Execute just those, from its own source,
# so what is compared is genuinely the planner's code and not a copy of it.
planner = {"math": math}
for fname in ("gc_dist", "bearing", "destination_point"):
    m = re.search(r"^def %s\(.*?(?=^\S)" % fname, planner_src, re.S | re.M)
    assert m, "could not extract %s from the planner" % fname
    exec(compile(m.group(0), "flightplanner/app.py", "exec"), planner)

# Real search-area geometry, plus the awkward cases: the equator, a long leg,
# a pole-ward pair, and one straddling the antimeridian.
FIXTURES = [
    (33.1700, -117.0790, 33.2870, -116.9800),   # a Pauma Valley search leg
    (32.8200, -117.0000, 34.0000, -116.0000),   # ~80 NM across the area
    (0.0, 0.0, 0.0, 1.0),                       # on the equator
    (61.1700, -149.9900, 61.5000, -149.0000),   # Alaska Wing
    (33.0, 179.5, 33.0, -179.5),                # across the antimeridian
]

print("\n== the console's geodesy and the plugin's agree ==")
for lat1, lon1, lat2, lon2 in FIXTURES:
    d_console = geo.distance_nm(lat1, lon1, lat2, lon2)
    d_engine = engine.distance_nm(lat1, lon1, lat2, lon2)
    b_console = geo.bearing_true(lat1, lon1, lat2, lon2)
    b_engine = engine.bearing_true(lat1, lon1, lat2, lon2)
    check("distance %.2f,%.2f -> %.2f,%.2f" % (lat1, lon1, lat2, lon2),
          abs(d_console - d_engine) < 1e-9, "%.6f NM" % d_console)
    check("bearing  %.2f,%.2f -> %.2f,%.2f" % (lat1, lon1, lat2, lon2),
          abs(b_console - b_engine) < 1e-9, "%.4f deg" % b_console)

print("\n== and the flight planner's ==")
for lat1, lon1, lat2, lon2 in FIXTURES:
    d_planner = planner["gc_dist"](lat1, lon1, lat2, lon2)
    b_planner = planner["bearing"](lat1, lon1, lat2, lon2)
    d_console = geo.distance_nm(lat1, lon1, lat2, lon2)
    b_console = geo.bearing_true(lat1, lon1, lat2, lon2)
    # gc_dist uses the atan2 form of haversine and geo.py the asin form. They
    # are the same function; they differ only in floating-point rounding, which
    # is why this tolerance is a foot rather than zero.
    check("planner distance %.2f,%.2f -> %.2f,%.2f" % (lat1, lon1, lat2, lon2),
          abs(d_planner - d_console) < 1e-6,
          "%.6f vs %.6f NM" % (d_planner, d_console))
    check("planner bearing  %.2f,%.2f -> %.2f,%.2f" % (lat1, lon1, lat2, lon2),
          abs(((b_planner - b_console + 180) % 360) - 180) < 1e-9,
          "%.4f deg" % b_planner)

print("\n== the direct solution agrees too ==")
for lat, lon in ((33.17, -117.08), (0.0, 0.0), (61.17, -149.99)):
    for bearing, dist in ((0.0, 10.0), (90.0, 25.0), (217.0, 3.5)):
        a_lat, a_lon = geo.move(lat, lon, bearing, dist)
        p_lat, p_lon = planner["destination_point"](lat, lon, dist, bearing)
        check("move %.2f,%.2f %03.0f deg %.1f NM" % (lat, lon, bearing, dist),
              abs(a_lat - p_lat) < 1e-5 and abs(a_lon - p_lon) < 1e-5,
              "%.6f,%.6f" % (a_lat, a_lon))
        # ...and it is the inverse of the distance/bearing pair.
        back = geo.distance_nm(lat, lon, a_lat, a_lon)
        check("...and it lands %.1f NM away" % dist, abs(back - dist) < 1e-6,
              "%.6f NM" % back)

print("\n== the browser copies have not drifted ==")
static = os.path.join(ROOT, "services", "exercise", "app", "static")
debrief = open(os.path.join(static, "debrief.js"), encoding="utf-8").read()
base_js = open(os.path.join(static, "base.js"), encoding="utf-8").read()

check("debrief.js uses the same earth radius",
      ("const R_NM = %s;" % geo.R_NM) in debrief, "R_NM = %s" % geo.R_NM)
check("debrief.js scales longitude by cos(latitude) in the track heading",
      re.search(r"\(p\.lon\s*-\s*prev\.lon\)\s*\*\s*Math\.cos\(", debrief) is not None,
      "this is the F-3 bug; without it a debrief heading is ~10 deg out at 33 N")
check("debrief.js still uses the haversine, not a flat approximation",
      "Math.asin(Math.min(1, Math.sqrt(h)))" in debrief)
# base.js draws the 40 NM bearing rays flat, which is fine at that scale and is
# F-8's business - but it must at least scale longitude, or the rays lean.

print("\n== F-8 bearing cut matches the hand plot ==")
# Hand plot on an equatorial chart (longitude is east/west, latitude north/south):
#   A  00.0000, -00.1000  observes 090 T (due east)
#   B -00.1000,  00.0000  observes 000 T (due north)
#   C  00.1000,  00.1000  observes 220 T
# A/B cross at 00.0000, 00.0000.  Resolving C's 220-degree ray into north/east
# components gives its A and B crossings near (00.0000, 00.0161) and
# (-00.0192, 00.0000).  Those three written-down points are the confidence
# triangle; the 0.0002-degree tolerance is about 12 metres at the equator.
HAND_PLOT = [
    {"callsign": "A", "lat": 0.0, "lon": -0.1, "bearing_true": 90.0},
    {"callsign": "B", "lat": -0.1, "lon": 0.0, "bearing_true": 0.0},
    {"callsign": "C", "lat": 0.1, "lon": 0.1, "bearing_true": 220.0},
]
HAND_EXPECTED = [(0.0, 0.0), (0.0, 0.0161), (-0.0192, 0.0)]


def polygon_matches(actual, expected, tolerance=0.0002):
    """Order-independent vertex comparison for the hand-plotted triangle."""
    unmatched = list(expected)
    for lat, lon in actual:
        for i, (want_lat, want_lon) in enumerate(unmatched):
            if abs(lat - want_lat) <= tolerance and abs(lon - want_lon) <= tolerance:
                unmatched.pop(i)
                break
        else:
            return False
    return not unmatched and len(actual) == len(expected)


cut_fn = getattr(geo, "bearing_cut_polygon", None)
check("geo.py exposes bearing_cut_polygon", callable(cut_fn))
python_cut = cut_fn(HAND_PLOT) if callable(cut_fn) else []
check("three bearings make the written-down confidence triangle",
      polygon_matches(python_cut, HAND_EXPECTED), repr(python_cut))

# Execute the browser's actual pure geodesy block under Node.  This is not a
# source-grep assertion: the functions are called with the same hand plot and
# their numeric vertices must agree with geo.py.
browser_block = re.search(
    r"// BEGIN F-8 PURE GEODESY\n(.*?)// END F-8 PURE GEODESY",
    base_js, re.S)
check("base.js provides executable bearing-cut geodesy", browser_block is not None)
if browser_block is not None:
    node_script = browser_block.group(1) + "\nconsole.log(JSON.stringify({" \
        "cut:bearingCutPolygon(" + json.dumps(HAND_PLOT) + ")," \
        "destination:bearingDestination(33.17,-117.08,90,40)," \
        "callsigns:bearingCallsignChoices([" \
        "{callsign:'CAP-2'},{callsign:'CAP-1'},{callsign:'CAP-2'}])}));"
    node = subprocess.run(["node", "-e", node_script], capture_output=True,
                          text=True, timeout=10)
    check("browser bearing-cut functions execute", node.returncode == 0,
          node.stderr.strip())
    if node.returncode == 0:
        browser_result = json.loads(node.stdout)
        check("browser cut matches the hand plot",
              polygon_matches(browser_result["cut"], HAND_EXPECTED),
              repr(browser_result["cut"]))
        expected_destination = geo.move(33.17, -117.08, 90.0, 40.0)
        check("browser bearing ray uses the shared direct-solution convention",
              all(abs(a - b) < 1e-9 for a, b in
                  zip(browser_result["destination"], expected_destination)),
              repr(browser_result["destination"]))
        check("browser callsign choices are unique and sorted",
              browser_result["callsigns"] == ["CAP-1", "CAP-2"],
              repr(browser_result["callsigns"]))

print("\n== inside the console there is one implementation ==")
prop_src = open(os.path.join(ROOT, "services", "exercise", "app", "propagation.py"),
                encoding="utf-8").read()
mock_src = open(os.path.join(ROOT, "services", "exercise", "mock_bridge.py"),
                encoding="utf-8").read()
for name, src in (("propagation.py", prop_src), ("mock_bridge.py", mock_src)):
    check("%s imports the shared geodesy" % name,
          "geo import" in src, "")
    check("%s no longer defines its own" % name,
          "def distance_nm" not in src and "def move(" not in src)
check("only app/geo.py names the earth radius inside the console",
      "3440.065" not in prop_src and "3440.065" not in mock_src)

print("\n" + ("ALL PASS" if not FAILED else "FAILURES: " + ", ".join(FAILED)))
if __name__ == "__main__":
    sys.exit(1 if FAILED else 0)
if FAILED:
    raise AssertionError("geodesy checks failed: " + ", ".join(FAILED))
