#!/usr/bin/env python3
"""Sweep the CAP 487 prop lever in level flight and record the governed RPM.

THIS TOOL LAUNCHES AND WRITES TO THE SIMULATOR (weather, power levers, the
aircraft's own GFC 700 heading and altitude hold). It never writes a control
surface; the autopilot flies. It exists to measure the lever-to-RPM map the AI
pilot's `profile.prop_cruise_ratio` needs (docs/C182T_AI_PILOT_PROP_2026-10-15.md):
at each fixed throttle, step `prop_ratio` down from full forward, let the
governor settle, and average RPM, manifold pressure, power and airspeed.

The lever is written through the same dataref the flight-control bridge uses
(`sim/cockpit2/engine/actuators/prop_ratio[0]`), so the map is the bridge's map.

Usage:
    python3 scripts/c182t_prop_sweep.py --run p1
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

HARNESS = Path.home() / "Projects/g1000-sar/scripts/sim_harness.py"
ACF = "Aircraft/CAP/Cessna 182T NAV III/Cessna_182T_G1000.acf"
OUT = Path.home() / ".cache/capvsar/measurements"
# Open water west of Point Loma, heading west, 2,000 ft, 100 kt.
START = {"latitude": 32.70, "longitude": -117.40, "elevation_in_meters": 609.6,
         "heading_true": 270.0, "speed_in_meters_per_second": 51.4}
LEVER = "sim/cockpit2/engine/actuators/prop_ratio[0]"
THROTTLE = "sim/cockpit2/engine/actuators/throttle_ratio_all"
READ = {"rpm": "sim/cockpit2/engine/indicators/engine_speed_rpm[0]",
        "mp_inhg": "sim/cockpit2/engine/indicators/MPR_in_hg[0]",
        "power_w": "sim/cockpit2/engine/indicators/power_watts[0]",
        "prop_ratio": LEVER,
        "engn_prop": "sim/flightmodel/engine/ENGN_prop[0]",
        "kias": "sim/flightmodel/position/indicated_airspeed",
        "ktas": "sim/flightmodel/position/true_airspeed",
        "alt_ft": "sim/cockpit2/gauges/indicators/altitude_ft_pilot",
        "vvi_fpm": "sim/flightmodel/position/vh_ind_fpm"}


def load_harness():
    spec = importlib.util.spec_from_file_location("sim_harness", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample(h, seconds, period=1.0):
    rows = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        rows.append(h.dref_get(list(READ.values())))
        time.sleep(period)
    return {key: statistics.fmean(r[ref] for r in rows if ref in r) for key, ref in READ.items()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--throttles", type=float, nargs="+", default=[.55, .80])
    ap.add_argument("--levers", type=float, nargs="+",
                    default=[1.0, .95, .90, .85, .80, .75, .70, .60, .50])
    ap.add_argument("--settle-s", type=float, default=20.)
    ap.add_argument("--sample-s", type=float, default=6.)
    args = ap.parse_args(argv)
    h = load_harness()
    OUT.mkdir(parents=True, exist_ok=True)
    spec_path = OUT / f"prop_sweep_{args.run}_start.json"
    spec_path.write_text(json.dumps({
        "aircraft": {"path": ACF}, "lle_air_start": START,
        "engine_status": {"all_engines": {"running": True}},
        "local_time": {"day_of_year": 160, "time_in_24_hours": 12.0}}, indent=1))
    log = {"run": args.run, "start": START, "acf": ACF, "sweeps": []}
    for _ in range(60):
        if not h.running():
            break
        time.sleep(3)
    h.launch(True, None, None, ["--new_flight_json=%s" % spec_path])
    try:
        if not h.wait(600):
            log["error"] = "simulator not ready"
            return 2
        h.cmd("sim/operation/pause_on")
        h.dref_set("sim/weather/region/weather_preset", 0)
        h.dref_set("sim/weather/region/change_mode", 3)
        h.dref_set("sim/weather/region/sealevel_temperature_c", 15.0)
        h.dref_set("sim/weather/region/sealevel_pressure_pas", 101325.0)
        h.dref_set("sim/weather/region/variability_pct", 0.0)
        h.dref_set("sim/weather/region/thermal_rate_ms", 0.0)
        for i in range(13):
            for ref in ("wind_speed_msc", "shear_speed_msc", "turbulence"):
                h.dref_set("sim/weather/region/%s[%d]" % (ref, i), 0.0)
        h.dref_set("sim/weather/region/update_immediately", 1)
        h.dref_set("sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot", 29.92)
        for ref in ("mixture_ratio_all", "prop_ratio_all"):
            h.dref_set("sim/cockpit2/engine/actuators/" + ref, 1.0)
        h.dref_set(THROTTLE, args.throttles[0])
        h.dref_set("sim/cockpit2/controls/flap_handle_request_ratio", 0.0)
        h.dref_set("sim/cockpit2/engine/actuators/cowl_flap_ratio[0]", 0.0)
        h.cmd("sim/operation/pause_off")
        time.sleep(2)
        state = h.dref_get(["sim/flightmodel/position/mag_psi",
                            "sim/cockpit2/gauges/indicators/altitude_ft_pilot"])
        h.dref_set("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot",
                   state.get("sim/flightmodel/position/mag_psi", 270.0))
        h.dref_set("sim/cockpit2/autopilot/altitude_dial_ft", 2000)
        h.cmd("sim/autopilot/servos_on")
        time.sleep(1)
        h.cmd("sim/autopilot/heading")
        h.cmd("sim/autopilot/altitude_hold")
        time.sleep(2)
        log["ap_modes"] = h.dref_get(["sim/cockpit2/autopilot/autopilot_on",
                                      "sim/cockpit2/autopilot/heading_status",
                                      "sim/cockpit2/autopilot/altitude_hold_status"])
        print("AP modes", log["ap_modes"], flush=True)
        for throttle in args.throttles:
            h.dref_set(THROTTLE, throttle)
            h.dref_set(LEVER, 1.0)
            time.sleep(args.settle_s)
            points = []
            for lever in args.levers:
                h.dref_set(LEVER, lever)
                time.sleep(args.settle_s)
                row = {"lever_cmd": lever, **sample(h, args.sample_s)}
                points.append(row)
                print("thr %.2f lever %.2f -> %.0f RPM, %.1f inHg, %.0f HP, %.0f KIAS" % (
                    throttle, lever, row["rpm"], row["mp_inhg"], row["power_w"] / 745.7,
                    row["kias"]), flush=True)
            log["sweeps"].append({"throttle": throttle, "points": points})
        h.dref_set(LEVER, 1.0)
    finally:
        h.cmd("sim/operation/pause_on")
        (OUT / f"prop_sweep_{args.run}.json").write_text(json.dumps(log, indent=1))
        time.sleep(1)
        h.cmd("sim/operation/quit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
