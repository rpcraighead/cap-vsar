#!/usr/bin/env python3
"""Fly flight-test card points C1 (max level speed) and B1 (Vy climb) on CAP 487.

THIS TOOL LAUNCHES AND WRITES TO THE SIMULATOR: weather, mass (through
scripts/set_test_condition.py), power levers and the aircraft's own GFC 700
autopilot modes and bugs. It never writes a control surface; the aircraft's
autopilot flies, as on the 2026-09-15 baseline runs, so speed (C1) and climb
rate (B1) are the dependent variables. Telemetry is recorded and reduced by the
existing read-only tools (capture_flight_test.py, reduce_cruise_point.py,
reduce_climb_point.py).

Conditions (docs/C182T_FLIGHT_TEST_CARD.md): 3,100 lb, ISA sea level, no wind,
full throttle / 2400 RPM / full rich, flaps up, cowl flaps as left. Air start
over open water west of Point Loma.

Usage:
    python3 scripts/c182t_perf_card.py --run a2-1
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS = Path.home() / "Projects/g1000-sar/scripts/sim_harness.py"
ACF = "Aircraft/CAP/Cessna 182T NAV III/Cessna_182T_G1000.acf"
TRACES = Path.home() / ".cache/capvsar/flight-tests"
START = {"latitude": 32.70, "longitude": -117.40, "elevation_in_meters": 182.9,
         "heading_true": 270.0, "speed_in_meters_per_second": 62.0}


def load_harness():
    spec = importlib.util.spec_from_file_location("sim_harness", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(cmd, **kw):
    print("$", " ".join(str(c) for c in cmd), flush=True)
    out = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    print(out.stdout[-3000:], out.stderr[-1500:], flush=True)
    return out


COWL = "sim/cockpit2/engine/actuators/cowl_flap_ratio[0]"
ENGINE = {"mp": "sim/cockpit2/engine/indicators/MPR_in_hg[0]",
          "rpm": "sim/cockpit2/engine/indicators/engine_speed_rpm[0]",
          "hp": "sim/cockpit2/engine/indicators/power_watts[0]",
          "egt": "sim/cockpit2/engine/indicators/EGT_deg_C[0]",
          "ktas": "sim/flightmodel/position/true_airspeed",
          "oat": "sim/weather/aircraft/temperature_ambient_deg_c",
          "palt": "sim/flightmodel2/position/pressure_altitude",
          "cowl": COWL}


def read_engine(h):
    raw = h.dref_get(list(ENGINE.values()))
    out = {k: raw.get(ref) for k, ref in ENGINE.items()}
    if out["hp"] is not None:
        out["hp"] /= 745.7
    if out["ktas"] is not None:
        out["ktas"] *= 1.94384
    return out


def hold_mp(h, target=23.0, seconds=20.0):
    """Nudge the throttle lever toward the target manifold pressure (no surface writes)."""
    throttle = 0.85
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        mp = read_engine(h)["mp"] or target
        throttle = min(1.0, max(0.3, throttle + 0.02 * (target - mp)))
        h.dref_set("sim/cockpit2/engine/actuators/throttle_ratio_all", throttle)
        time.sleep(1.0)
    return throttle


def lean_to_peak_egt(h):
    """POH cruise tables assume the recommended lean mixture (peak EGT)."""
    best = (None, 1.0)
    for mixture in [1.0 - 0.025 * i for i in range(17)]:
        h.dref_set("sim/cockpit2/engine/actuators/mixture_ratio_all", mixture)
        time.sleep(2.5)
        egt = read_engine(h)["egt"]
        if egt is not None and (best[0] is None or egt > best[0]):
            best = (egt, mixture)
    h.dref_set("sim/cockpit2/engine/actuators/mixture_ratio_all", best[1])
    return {"peak_egt_c": best[0], "mixture": best[1]}


def lean_to_best_power(h):
    """POH Section 5 climb/max-power figures: mixture at the maximum-power fuel
    flow, i.e. best power. X-Plane's full-rich runs ~6 % below rated (A2-4)."""
    best = (None, 1.0)
    for mixture in [1.0 - 0.02 * i for i in range(14)]:
        h.dref_set("sim/cockpit2/engine/actuators/mixture_ratio_all", mixture)
        time.sleep(2.5)
        hp = read_engine(h)["hp"]
        if hp is not None and (best[0] is None or hp > best[0]):
            best = (hp, mixture)
    h.dref_set("sim/cockpit2/engine/actuators/mixture_ratio_all", best[1])
    return {"best_hp": best[0], "mixture": best[1]}


def fly_c2(h, args, log):
    h.dref_set("sim/cockpit2/engine/actuators/prop_ratio_all", 1.0)       # governor at 2400
    hold_mp(h, 23.0, 30.0)
    log["leaning"] = lean_to_peak_egt(h)
    for _ in range(int(args.c1_settle_s // 30)):
        log["throttle"] = hold_mp(h, 23.0, 30.0)
    samples = []
    proc = subprocess.Popen([sys.executable, REPO / "scripts/capture_flight_test.py", "--card", "C2",
                             "--run", args.run, "--seconds", str(args.c1_seconds),
                             "--note", "C2 independent point: 6000 ft ISA, 2400/23 in.hg, peak EGT"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.monotonic() + args.c1_seconds
    while time.monotonic() < end:
        samples.append(read_engine(h))
        time.sleep(2.0)
    out, _ = proc.communicate(timeout=120)
    print(out[-2500:], flush=True)
    log["c2_capture"] = out[-2500:]
    def mean(k):
        vals = [s[k] for s in samples if s.get(k) is not None]
        return sum(vals) / len(vals) if vals else None
    log["c2_engine_mean"] = {k: mean(k) for k in ENGINE}
    print("C2 ENGINE", json.dumps(log["c2_engine_mean"]), flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--acf", default=ACF, help="aircraft path relative to the X-Plane folder")
    ap.add_argument("--mixture", choices=("rich", "best"), default="rich",
                    help="C1/B1 mixture: full rich (the September card) or best power (POH placard)")
    ap.add_argument("--card", choices=("c1b1", "c2"), default="c1b1",
                    help="c2: POH Figure 5-9 sheet 7, 6,000 ft ISA, 2400 RPM / 23 in.hg = 79%% MCP, 143 KTAS")
    ap.add_argument("--c1-settle-s", type=float, default=150.0)
    ap.add_argument("--c1-seconds", type=float, default=120.0)
    ap.add_argument("--b1-settle-s", type=float, default=30.0)
    ap.add_argument("--b1-seconds", type=float, default=90.0)
    args = ap.parse_args(argv)
    h = load_harness()
    TRACES.mkdir(parents=True, exist_ok=True)
    spec_path = TRACES / f"perf_card_{args.run}_start.json"
    spec_path.write_text(json.dumps({
        "aircraft": {"path": args.acf}, "lle_air_start": START,
        "engine_status": {"all_engines": {"running": True}},
        "local_time": {"day_of_year": 160, "time_in_24_hours": 12.0}}, indent=1))
    log = {"run": args.run, "start": START, "acf": args.acf, "card": args.card}
    if args.card == "c2":
        spec = json.loads(spec_path.read_text())
        spec["lle_air_start"] = dict(START, elevation_in_meters=1828.8, speed_in_meters_per_second=70.0)
        spec_path.write_text(json.dumps(spec, indent=1))
        log["start"] = spec["lle_air_start"]
    for _ in range(60):                 # a previous run may still be shutting down
        if not h.running():
            break
        time.sleep(3)
    h.launch(True, None, None, ["--new_flight_json=%s" % spec_path])
    try:
        if not h.wait(600):
            log["error"] = "simulator not ready"
            return 2
        h.cmd("sim/operation/pause_on")
        # ISA sea level, calm, static.
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
        for ref in ("mixture_ratio_all", "prop_ratio_all", "throttle_ratio_all"):
            h.dref_set("sim/cockpit2/engine/actuators/" + ref, 1.0)
        h.dref_set("sim/cockpit2/controls/flap_handle_request_ratio", 0.0)
        h.dref_set(COWL, 0.0)        # POH cruise tables: cowl flaps CLOSED
        h.cmd("sim/operation/pause_off")
        time.sleep(2)
        state = h.dref_get(["sim/flightmodel/position/mag_psi",
                            "sim/cockpit2/gauges/indicators/altitude_ft_pilot"])
        alt = round(state.get("sim/cockpit2/gauges/indicators/altitude_ft_pilot", 600) / 10) * 10
        h.dref_set("sim/cockpit2/autopilot/heading_dial_deg_mag_pilot",
                   state.get("sim/flightmodel/position/mag_psi", 258.0))
        h.dref_set("sim/cockpit2/autopilot/altitude_dial_ft", alt)
        h.cmd("sim/autopilot/servos_on")
        time.sleep(1)
        h.cmd("sim/autopilot/heading")
        h.cmd("sim/autopilot/altitude_hold")
        time.sleep(2)
        modes = h.dref_get(["sim/cockpit2/autopilot/autopilot_on", "sim/cockpit2/autopilot/heading_status",
                            "sim/cockpit2/autopilot/altitude_hold_status"])
        log["c1_modes"] = modes
        print("AP modes", modes, flush=True)
        mass = run([sys.executable, REPO / "scripts/set_test_condition.py",
                    "--weight-lb", "3100", "--fuel-lb", "522"])
        log["mass"] = mass.stdout[-1500:]
        if args.card == "c2":
            return fly_c2(h, args, log)
        if args.mixture == "best":
            log["c1_leaning"] = lean_to_best_power(h)
            print("C1 leaning", log["c1_leaning"], flush=True)
        time.sleep(args.c1_settle_s)
        cap = run([sys.executable, REPO / "scripts/capture_flight_test.py", "--card", "C1",
                   "--run", args.run, "--seconds", args.c1_seconds,
                   "--note", "A2 rerun: 79-in prop, TCDS pitch stops, 3100 lb ISA calm, AP ALT"])
        log["c1_capture"] = cap.stdout[-2500:]
        # B1: level change at Vy with full power toward a high selected altitude.
        # POH Figure 5-7/5-8 climb figures are with cowl flaps OPEN.
        h.dref_set(COWL, 1.0)
        if args.mixture == "best":
            log["b1_leaning"] = lean_to_best_power(h)
            print("B1 leaning", log["b1_leaning"], flush=True)
        h.dref_set("sim/cockpit2/autopilot/altitude_dial_ft", 7000.0)
        h.cmd("sim/autopilot/level_change")
        time.sleep(1)
        h.dref_set("sim/cockpit2/autopilot/airspeed_dial_kts", 80.0)   # FLC syncs the bug on engage
        time.sleep(args.b1_settle_s)
        log["b1_modes"] = h.dref_get(["sim/cockpit2/autopilot/speed_status",
                                      "sim/cockpit2/autopilot/airspeed_dial_kts",
                                      "sim/flightmodel/position/indicated_airspeed"])
        print("B1 modes", log["b1_modes"], flush=True)
        cap = run([sys.executable, REPO / "scripts/capture_flight_test.py", "--card", "B1",
                   "--run", args.run, "--seconds", args.b1_seconds,
                   "--note", "A2 rerun: 79-in prop, TCDS pitch stops, 3100 lb ISA calm, AP FLC 80"])
        log["b1_capture"] = cap.stdout[-2500:]
    finally:
        h.cmd("sim/operation/pause_on")
        (TRACES / f"perf_card_{args.run}.json").write_text(json.dumps(log, indent=1))
        time.sleep(1)
        h.cmd("sim/operation/quit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
