#!/usr/bin/env python3
"""Measure the steady-state (throttle, vertical speed) -> airspeed map of an aircraft.

THIS TOOL LAUNCHES AND WRITES TO THE SIMULATOR (weather, throttle, prop lever, the aircraft's own
autopilot modes and bugs). It never writes a control surface: the aircraft's autopilot flies. At each
point a fixed throttle is set, the autopilot holds a vertical speed (or altitude), and the airspeed that
settles is the dependent variable. Inverted, the map says what throttle a given airspeed and climb rate
need, which is the feed-forward the AI pilot's cruise law lacks (docs/GFC700_SECOND_OWNER_2026-10-15.md,
"Findings and fixes"). Output: raw JSON in ~/.cache/capvsar/measurements/ and a `[performance]` TOML
fragment for services/ai_pilot/profiles/<aircraft>.toml.

Points that would leave the AI pilot's envelope are not flown into: a point is abandoned (and recorded as
such) if the airspeed falls below 75 KIAS or rises above 138 KIAS, and the airplane is recovered.

Usage:
    python3 scripts/perf_table_sweep.py --profile C182T --run t1
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ai_pilot_experiment import AIRCRAFT_PATHS, digest          # noqa: E402
from services.ai_pilot.aircraft_profiles import PROFILES                # noqa: E402

HARNESS = Path.home() / "Projects/g1000-sar/scripts/sim_harness.py"
OUT = Path.home() / ".cache/capvsar/measurements"
XPLANE = Path.home() / "X-Plane 12"
M_TO_FT = 1 / .3048
AP_STATE = "sim/cockpit/autopilot/autopilot_state"
AP_VS, AP_ALT_HOLD, AP_HDG = 1 << 4, 1 << 14, 1 << 1
LOW_KIAS, HIGH_KIAS = 75., 138.
READ = {"kias": "sim/flightmodel/position/indicated_airspeed",
        "vvi": "sim/flightmodel/position/vh_ind_fpm",
        "alt": "sim/cockpit2/gauges/indicators/altitude_ft_pilot",
        "rpm": "sim/cockpit2/engine/indicators/engine_speed_rpm[0]",
        "mp": "sim/cockpit2/engine/indicators/MPR_in_hg[0]",
        "hp": "sim/cockpit2/engine/indicators/power_watts[0]",
        "throttle": "sim/cockpit2/engine/actuators/throttle_ratio[0]",
        "oat": "sim/weather/aircraft/temperature_ambient_deg_c",
        "mass": "sim/flightmodel/weight/m_total",
        "fuel": "sim/flightmodel/weight/m_fuel_total",
        "cowl": "sim/cockpit2/engine/actuators/cowl_flap_ratio[0]",
        "pitch": "sim/flightmodel/position/theta",
        "ap": AP_STATE}


def load_harness():
    spec = importlib.util.spec_from_file_location("sim_harness", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(h):
    raw = h.dref_get(list(READ.values()))
    out = {key: raw.get(ref) for key, ref in READ.items()}
    if out["hp"] is not None:
        out["hp"] /= 745.7
    return out


def ap_mode(h, target_vvi, altitude_now):
    """Hold `target_vvi` fpm (VS mode, far altitude bug) or the present altitude (target 0).
    The autopilot commands are toggles: read the state bit first."""
    state = int(h.dref_get([AP_STATE])[AP_STATE])
    if target_vvi == 0:
        h.dref_set("sim/cockpit/autopilot/altitude", float(round(altitude_now)))
        if not state & AP_ALT_HOLD:
            h.cmd("sim/autopilot/altitude_hold")
        return
    far = altitude_now + (2500. if target_vvi > 0 else -2500.)
    if not state & AP_VS:
        h.cmd("sim/autopilot/vertical_speed")        # engaging VS zeroes the rate: write it after
        time.sleep(0.5)
    h.dref_set("sim/cockpit/autopilot/altitude", float(far))
    h.dref_set("sim/cockpit/autopilot/vertical_velocity", float(target_vvi))


def settle(h, target_vvi, min_s, max_s):
    """Sample once a second until the airspeed has stopped changing; abandon at the envelope edges."""
    samples, started = [], time.monotonic()
    reason = "timeout"
    while time.monotonic() - started < max_s:
        time.sleep(1.0)
        s = read(h)
        samples.append(s)
        if s["kias"] < LOW_KIAS:
            return samples, "low_speed"
        if s["kias"] > HIGH_KIAS:
            return samples, "high_speed"
        if len(samples) >= max(min_s, 12):
            window = [x["kias"] for x in samples[-10:]]
            if (max(window) - min(window) < 1.0
                    and abs(statistics.fmean(x["vvi"] for x in samples[-10:]) - target_vvi) < 100):
                reason = "settled"
                break
    return samples, reason


def recover(h, altitude_ft):
    h.dref_set("sim/cockpit2/engine/actuators/throttle_ratio_all", 0.7)
    h.dref_set("sim/cockpit/autopilot/altitude", float(round(altitude_ft)))
    state = int(h.dref_get([AP_STATE])[AP_STATE])
    if not state & AP_ALT_HOLD:
        h.cmd("sim/autopilot/altitude_hold")
    time.sleep(12)


def recenter(h, target_alt, tol=350., max_s=75.):
    """Fly back to the measurement altitude before a point, so altitude cannot correlate with throttle:
    indicated airspeed at a given power falls as density does, and a drift of 2,000 ft hid a 5 kt effect."""
    alt = read(h)["alt"]
    if abs(alt - target_alt) <= tol:
        return 0.
    up = alt < target_alt
    h.dref_set("sim/cockpit2/engine/actuators/throttle_ratio_all", 0.85 if up else 0.45)
    ap_mode(h, 500. if up else -500., alt)
    started = time.monotonic()
    while time.monotonic() - started < max_s:
        time.sleep(1.0)
        here = read(h)["alt"]
        if (here >= target_alt - 100) if up else (here <= target_alt + 100):
            break
    h.dref_set("sim/cockpit2/engine/actuators/throttle_ratio_all", 0.7)
    ap_mode(h, 0., read(h)["alt"])
    time.sleep(4)
    return time.monotonic() - started


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", choices=sorted(PROFILES), required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--altitude-ft", type=float, default=4000.)
    ap.add_argument("--throttles", type=float, nargs="+", default=[.40, .50, .60, .70, .80, .90, 1.0])
    ap.add_argument("--vvis", type=float, nargs="+", default=[700., 400., 0., -400., -700.])
    ap.add_argument("--min-settle-s", type=float, default=25.)
    ap.add_argument("--max-settle-s", type=float, default=75.)
    ap.add_argument("--no-launch", action="store_true", help="use the simulator that is already running")
    args = ap.parse_args(argv)
    profile = PROFILES[args.profile]
    acf = AIRCRAFT_PATHS[args.profile]
    h = load_harness()
    OUT.mkdir(parents=True, exist_ok=True)
    spec = OUT / f"perf_table_{args.profile}_{args.run}_start.json"
    spec.write_text(json.dumps({
        "aircraft": {"path": acf},
        "lle_air_start": {"latitude": 32.70, "longitude": -117.40,
                          "elevation_in_meters": args.altitude_ft * .3048, "heading_true": 270.0,
                          "speed_in_meters_per_second": 52.0},
        "engine_status": {"all_engines": {"running": True}},
        "local_time": {"day_of_year": 160, "time_in_24_hours": 12.0}}, indent=1))
    log = {"profile": args.profile, "run": args.run, "acf": acf,
           "acf_sha256": digest(XPLANE / acf), "altitude_ft": args.altitude_ft, "points": [],
           "conditions": "ISA, calm, full rich, prop full forward, flaps up, autopilot holding vertical speed"}
    if not args.no_launch:
        for _ in range(60):
            if not h.running():
                break
            time.sleep(3)
        h.launch(True, None, None, ["--new_flight_json=%s" % spec])
    out_path = OUT / f"perf_table_{args.profile}_{args.run}.json"
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
        h.dref_set("sim/cockpit2/engine/actuators/mixture_ratio_all", 1.0)
        if profile.constant_speed_prop:
            h.dref_set("sim/cockpit2/engine/actuators/prop_rotation_speed_rad_sec_all", 2400 / 9.5493)
        h.dref_set("sim/cockpit2/controls/flap_handle_request_ratio", 0.0)
        h.dref_set("sim/cockpit2/engine/actuators/throttle_ratio_all", 0.7)
        h.cmd("sim/operation/pause_off")
        time.sleep(4)
        state = h.dref_get(["sim/flightmodel/position/mag_psi"])
        h.dref_set("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot", state["sim/flightmodel/position/mag_psi"])
        h.cmd("sim/autopilot/servos_on")
        time.sleep(1)
        h.cmd("sim/autopilot/heading")
        recover(h, args.altitude_ft)
        first = read(h)
        log["start_state"] = first
        print("start: %.0f ft %.0f KIAS mass %.0f kg cowl %s" % (first["alt"], first["kias"], first["mass"], first["cowl"]), flush=True)
        for row, throttle in enumerate(args.throttles):
            order = args.vvis if row % 2 == 0 else list(reversed(args.vvis))      # serpentine: altitude stays near the start
            for target in order:
                recenter(h, args.altitude_ft)
                h.dref_set("sim/cockpit2/engine/actuators/throttle_ratio_all", throttle)
                ap_mode(h, target, read(h)["alt"])
                samples, why = settle(h, target, args.min_settle_s, args.max_settle_s)
                tail = samples[-8:]
                point = {"throttle": throttle, "target_vvi_fpm": target, "outcome": why, "seconds": len(samples)}
                for key in ("kias", "vvi", "alt", "rpm", "mp", "hp", "oat", "mass", "fuel", "cowl", "pitch"):
                    point[key] = statistics.fmean(x[key] for x in tail)
                log["points"].append(point)
                print("thr %.2f vvi %+5.0f -> %-10s KIAS %5.1f vvi %+6.0f alt %5.0f rpm %4.0f MP %4.1f HP %3.0f (%ds)" % (
                    throttle, target, why, point["kias"], point["vvi"], point["alt"], point["rpm"], point["mp"],
                    point["hp"], len(samples)), flush=True)
                if why in ("low_speed", "high_speed"):
                    recover(h, args.altitude_ft)
        log["completed"] = True
    finally:
        try:
            h.cmd("sim/operation/pause_on")
        except Exception:
            pass
        out_path.write_text(json.dumps(log, indent=1))
        print("wrote", out_path, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
