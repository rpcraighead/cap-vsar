#!/usr/bin/env python3
"""Ground checks for the CAP 487 package: wheel geometry and static full-throttle RPM.

THIS TOOL LAUNCHES AND WRITES TO THE SIMULATOR (parking brake, throttle,
propeller and mixture only, on the ground). It drives X-Plane through the
g1000-sar headless harness (`~/Projects/g1000-sar/scripts/sim_harness.py`):
launch with a Flight Initialization API ground start, wait for UDP readiness,
read, quit.

Two acceptance checks, both from FAA TCDS 3A13 Rev 66 and the 182T POH:

* wheel geometry (tracker A2-3): main wheel track 108.0 in and wheelbase
  66.5 in (POH Figure 1-1), read from `sim/flightmodel/parts/tire_[xz]_no_deflection`,
  the simulator's own wheel positions;
* static RPM (A2-2): "Static RPM at full throttle: Not over 2400; Not under 2300"
  (TCDS 3A13 p.32), which is the check that the propeller pitch stops are right.

Usage:
    python3 scripts/c182t_ground_check.py --out ~/.cache/capvsar/flight-tests/ground_check.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
import time
from pathlib import Path

HARNESS = Path.home() / "Projects/g1000-sar/scripts/sim_harness.py"
ACF = "Aircraft/CAP/Cessna 182T NAV III/Cessna_182T_G1000.acf"
# KNZY 29, 150 m in from the threshold: sea level, so static RPM is a sea-level figure.
THRESHOLD = (32.691411, -117.200589)
OPPOSITE = (32.702341, -117.221289)
M_TO_IN = 39.3700787


def load_harness():
    spec = importlib.util.spec_from_file_location("sim_harness", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bearing(a, b):
    la1, la2 = map(math.radians, (a[0], b[0]))
    dl = math.radians(b[1] - a[1])
    return math.degrees(math.atan2(math.sin(dl) * math.cos(la2),
                                   math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl))) % 360


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--spec", type=Path, default=Path.home() / ".cache/capvsar/flight-tests/ground_check_start.json")
    ap.add_argument("--hold-s", type=float, default=20.0)
    ap.add_argument("--mixture-sweep", action="store_true")
    ap.add_argument("--shots", type=Path, default=None,
                    help="directory for cockpit/outside screenshots of the propeller")
    args = ap.parse_args(argv)
    h = load_harness()
    heading = bearing(THRESHOLD, OPPOSITE)
    north = 150 * math.cos(math.radians(heading)) / 111132.92
    east = 150 * math.sin(math.radians(heading)) / (111412.84 * math.cos(math.radians(THRESHOLD[0])))
    spec = {"aircraft": {"path": ACF},
            "lle_ground_start": {"latitude": THRESHOLD[0] + north, "longitude": THRESHOLD[1] + east,
                                 "heading_true": heading},
            "engine_status": {"all_engines": {"running": True}},
            "local_time": {"day_of_year": 160, "time_in_24_hours": 12.0}}
    args.spec.parent.mkdir(parents=True, exist_ok=True)
    args.spec.write_text(json.dumps(spec, indent=1))
    for _ in range(60):                 # a previous run may still be shutting down
        if not h.running():
            break
        time.sleep(3)
    h.launch(True, None, None, ["--new_flight_json=%s" % args.spec])
    result = {"spec": spec, "acf": ACF}
    try:
        if not h.wait(600):
            result["error"] = "simulator not ready"
            return 2
        time.sleep(10)
        tire = ["sim/flightmodel/parts/tire_%s_no_deflection[%d]" % (axis, i) for axis in "xyz" for i in range(3)]
        attach = ["sim/aircraft/parts/acf_gear_%snodef[%d]" % (axis, i) for axis in "xz" for i in range(3)]
        geo = h.dref_get(tire + attach)
        result["attach_m"] = {"x": [geo.get(attach[i]) for i in range(3)],
                              "z": [geo.get(attach[3 + i]) for i in range(3)]}
        rpm_now = h.dref_get(["sim/cockpit2/engine/indicators/engine_speed_rpm[0]"])
        result["engine_rpm_at_ready"] = rpm_now.get("sim/cockpit2/engine/indicators/engine_speed_rpm[0]")
        if (result["engine_rpm_at_ready"] or 0) < 400:
            h.cmd("sim/operation/auto_start")        # the flight-start engine state is not reliable
            time.sleep(15)
        x = [geo[tire[i]] for i in range(3)]
        z = [geo[tire[6 + i]] for i in range(3)]
        result["tires_m"] = {"x": x, "z": z, "y": [geo[tire[3 + i]] for i in range(3)]}
        result["track_in"] = abs(x[2] - x[1]) * M_TO_IN
        result["wheelbase_in"] = abs((z[1] + z[2]) / 2 - z[0]) * M_TO_IN
        brakes = (("sim/flightmodel/controls/parkbrake", 1.0),
                  ("sim/cockpit2/controls/parking_brake_ratio", 1.0),
                  ("sim/cockpit2/controls/left_brake_ratio", 1.0),
                  ("sim/cockpit2/controls/right_brake_ratio", 1.0))
        for ref, value in brakes + (("sim/cockpit2/engine/actuators/mixture_ratio_all", 1.0),
                                    ("sim/cockpit2/engine/actuators/prop_ratio_all", 1.0)):
            h.dref_set(ref, value)
        shots = []
        disc = "sim/flightmodel2/engines/prop_is_disc[0]"
        rpm_ref = "sim/cockpit2/engine/indicators/engine_speed_rpm[0]"
        if args.shots:
            for label, throttle in (("idle", 0.0), ("runup", 0.45)):
                h.dref_set("sim/cockpit2/engine/actuators/throttle_ratio_all", throttle)
                for ref, value in brakes:
                    h.dref_set(ref, value)
                time.sleep(8)
                state = h.dref_get([rpm_ref, disc])
                h.cmd("sim/view/default_view")
                time.sleep(2)
                path = h.shot("c182t_cockpit_%s" % label, args.shots)
                shots.append({"label": label, "file": str(path), "rpm": state.get(rpm_ref),
                              "prop_is_disc": state.get(disc), "view": "cockpit"})
        h.dref_set("sim/cockpit2/engine/actuators/throttle_ratio_all", 1.0)
        deadline = time.monotonic() + args.hold_s
        while time.monotonic() < deadline:     # toe brakes are momentary: keep them on
            for ref, value in brakes:
                h.dref_set(ref, value)
            time.sleep(0.5)
        names = ["sim/cockpit2/engine/indicators/engine_speed_rpm[0]",
                 "sim/cockpit2/engine/indicators/MPR_in_hg[0]",
                 "sim/cockpit2/engine/indicators/power_watts[0]",
                 "sim/flightmodel2/engines/prop_pitch_deg[0]",
                 "sim/flightmodel/position/groundspeed",
                 "sim/weather/aircraft/temperature_ambient_deg_c",
                 "sim/weather/aircraft/barometer_current_pas"]
        samples = []
        for _ in range(10):
            for ref, value in brakes:
                h.dref_set(ref, value)
            samples.append(h.dref_get(names))
            time.sleep(0.5)
        if args.shots:
            state = h.dref_get([rpm_ref, disc])
            path = h.shot("c182t_cockpit_full", args.shots)
            shots.append({"label": "full", "file": str(path), "rpm": state.get(rpm_ref),
                          "prop_is_disc": state.get(disc), "view": "cockpit"})
            h.cmd("sim/view/chase")
            time.sleep(3)
            path = h.shot("c182t_outside_full", args.shots)
            shots.append({"label": "full", "file": str(path), "view": "chase"})
            h.cmd("sim/view/default_view")
        result["shots"] = shots
        def mean(n):
            vals = [s[n] for s in samples if n in s]
            return statistics.fmean(vals) if vals else None
        result["static"] = {"rpm": mean(names[0]), "mp_inhg": mean(names[1]),
                            "hp": (mean(names[2]) or 0) / 745.7, "prop_pitch_deg": mean(names[3]),
                            "groundspeed_mps": mean(names[4]), "oat_c": mean(names[5]),
                            "baro_pa": mean(names[6])}
        result["static"]["tcds_2300_2400"] = 2300 <= (result["static"]["rpm"] or 0) <= 2400
        if args.mixture_sweep:
            # A2-4: is the full-throttle power shortfall a mixture effect? Sweep the
            # mixture lever at full throttle and record power at each setting.
            sweep = []
            for mixture in [1.0 - 0.04 * i for i in range(13)]:
                h.dref_set("sim/cockpit2/engine/actuators/mixture_ratio_all", mixture)
                for ref, value in brakes:
                    h.dref_set(ref, value)
                time.sleep(3.0)
                r = h.dref_get(names[:3] + ["sim/cockpit2/engine/indicators/EGT_deg_C[0]",
                                            "sim/cockpit2/engine/indicators/fuel_flow_kg_sec[0]"])
                sweep.append({"mixture": mixture, "rpm": r.get(names[0]), "mp": r.get(names[1]),
                              "hp": (r.get(names[2]) or 0) / 745.7,
                              "egt_c": r.get("sim/cockpit2/engine/indicators/EGT_deg_C[0]"),
                              "ff_gph": (r.get("sim/cockpit2/engine/indicators/fuel_flow_kg_sec[0]") or 0) * 3600 / 2.72})
            result["mixture_sweep"] = sweep
            best = max(sweep, key=lambda e: e["hp"])
            result["best_power"] = best
            print("BEST POWER", json.dumps(best), flush=True)
        h.dref_set("sim/cockpit2/engine/actuators/throttle_ratio_all", 0.0)
        time.sleep(2)
    finally:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1))
        print(json.dumps(result, indent=1))
        h.cmd("sim/operation/quit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
