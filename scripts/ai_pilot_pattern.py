#!/usr/bin/env python3
"""Attended search-pattern trial on the mission bridge (C172 or CAP 487 C182T).

Adopts an aircraft that is already PAUSED and airborne inside the mission
bridge's region, flies a CAP search pattern with SearchPatternController on the
primary controls, and scores it with the independent PatternObserver. Every
frame goes through the expiring, authenticated mission bridge; a fault pauses
the simulator and releases the overrides (the bridge's own containment).

Usage:
    python3 scripts/ai_pilot_pattern.py --config <PythonPlugins>/capvsar_flight_control_config.json \
        --output ~/.cache/capvsar/ai-pilot/pattern_c182_ss.jsonl --profile C182T \
        --pattern expanding_square --lat 32.70 --lon -117.30 --heading 0 --spacing-nm 1 --legs 6 \
        --altitude-ft 2000
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.ai_pilot.aircraft_profiles import PROFILES
from services.ai_pilot.control_ownership import ControllerLock
from services.ai_pilot.experiment import BridgeClient, Recorder, digest
from services.ai_pilot.terrain_guard import TerrainGuard
from xplane.capvsar_mission import AIRBORNE_MAX_ALTITUDE_FT
from services.ai_pilot.search_patterns import (PatternObserver, SearchPatternController,
                                               creeping_line, expanding_square, parallel_track,
                                               track_miles)
from scripts.ai_pilot_experiment import inventory

CHANNELS = ("roll", "pitch", "yaw", "throttle", "flap", "trim", "brake")


def build_pattern(a):
    if a.pattern == "expanding_square":
        return expanding_square(a.lat, a.lon, a.heading, a.spacing_nm, a.legs, a.turn)
    if a.pattern == "parallel":
        return parallel_track(a.lat, a.lon, a.heading, a.length_nm, a.spacing_nm, a.legs, a.turn)
    return creeping_line(a.lat, a.lon, a.heading, a.width_nm, a.spacing_nm, a.legs, a.turn)


def run(args):
    config = json.loads(args.config.read_text())
    if config.get("mode") != "mission":
        raise ValueError("Requires the expiring mission bridge configuration")
    profile = PROFILES[args.profile]
    channels = CHANNELS + (("prop",) if profile.constant_speed_prop else ())
    waypoints = build_pattern(args)
    inv = inventory(args.xplane, include_mission=True, profile=args.profile)
    for name, installed in inv["installed_bridge_sha256"].items():
        if installed != inv["source_sha256"]["xplane/" + name]:
            raise ValueError("Installed mission bridge mismatch: " + name)
    inv["runner_sha256"] = digest(Path(__file__))
    inv["controller_sha256"] = digest(ROOT / "services/ai_pilot/search_patterns.py")
    inv["profile_tuning_validated"] = profile.tuning_validated
    manifest = {"purpose": "search pattern trial", "created_utc": datetime.now(timezone.utc).isoformat(),
                "inventory": inv, "pattern": args.pattern,
                "parameters": {k: getattr(args, k) for k in ("lat", "lon", "heading", "spacing_nm", "legs",
                                                             "turn", "length_nm", "width_nm", "altitude_ft")},
                "waypoints": [w.__dict__ for w in waypoints], "track_nm": track_miles(waypoints),
                "criteria": {"pass_nm": .35, "altitude_tol_ft": 200., "kias_band": [80., 140.],
                             "max_bank_deg": 32.},
                "simulated_clearance": "Self-assigned pattern over open water; no ATC service"}
    recorder = Recorder(args.output, manifest)
    client = BridgeClient(config)
    controller = SearchPatternController(waypoints, altitude_indicated_ft=args.altitude_ft,
                                         profile=profile, kias=args.kias)
    observer = PatternObserver(waypoints, altitude_indicated_ft=args.altitude_ft,
                               aircraft_name=profile.acf_name)
    # The executive's terrain guard (it flew as a demo script until 2026-10-15): a
    # floor on the altitude target, never above what the bridge envelope accepts.
    guard = None if args.no_terrain_guard else TerrainGuard(
        ceiling_ft=AIRBORNE_MAX_ALTITUDE_FT - 500)
    result = {"outcome": "FAIL", "reason": "Setup incomplete"}
    session = secrets.token_hex(16)
    samples = 0
    guard_said = ""
    previous_frame = None
    try:
        status = client.request("fault_pause", reason="pattern trial setup")
        deadline = time.monotonic() + 3
        while not status["pause_confirmed"]:
            if time.monotonic() > deadline:
                raise ValueError("Setup pause not confirmed")
            time.sleep(.03)
            status = client.request("status")
        recorder.write("setup", client.request("lab_reset", session=session))
        deadline = time.monotonic() + 15
        while True:
            snap = client.request("snapshot")
            if (snap["session"] == session and snap["values"]["paused"] == 1
                    and snap["override_state"] is False and snap["ap_engaged"] is False):
                break
            if time.monotonic() > deadline:
                raise ValueError("Pattern readiness not confirmed")
            time.sleep(.1)
        measured = snap["controls"]
        controls = {"roll": 0., "pitch": max(-.4, min(.4, measured.get("pitch", 0.))), "yaw": 0.,
                    "throttle": max(.2, min(1., measured.get("throttle", .6))), "flap": 0.,
                    "trim": max(-.6, min(.6, measured["trim"])), "brake": 0.}
        if profile.constant_speed_prop:
            controls["prop"] = max(.5, min(1., measured.get("prop", 1.)))
        started = client.request("lab_start", session=session, controls=controls,
                                 snapshot_frame=snap["frame"], snapshot_wall_time_s=snap["wall_time_s"])
        if started["state"] != "ACTIVE":
            raise ValueError("Pattern start not active")
        generation, seq = started["generation"], started["frame_sequence"]
        start_wall = time.monotonic()
        last_report = 0.
        while time.monotonic() - start_wall < args.max_wall_s:
            seq += 1
            response = client.request("exchange", session=session, generation=generation, sequence=seq,
                                      expires_at=time.monotonic() + .18, controls=controls)
            if response["bridge"]["state"] != "ACTIVE":
                raise ValueError("Mission bridge lost authority")
            snap = response["snapshot"]
            if snap is None or snap["frame"] == previous_frame:
                time.sleep(.005)
                continue
            previous_frame = snap["frame"]
            v = snap["values"]
            if v["paused"]:
                if time.monotonic() - start_wall < .2:
                    continue
                raise ValueError("Simulator paused during pattern")
            samples += 1
            report = observer.observe(snap)
            if samples % 5 == 0:
                recorder.write("snapshot", snap)
            if report["outcome"] != "INCOMPLETE":
                result = {**report, "controller_transitions": controller.transitions}
                break
            if guard is not None:
                if "terrain" not in snap and not guard_said:
                    guard_said = "no terrain in snapshots"
                    print("GUARD WARNING: snapshots carry no terrain scan; stage the session with the "
                          "current stage-mission so the guard can see the ground", flush=True)
                advice = guard.update(snap)
                controller.altitude_ft = guard.apply_to_altitude(args.altitude_ft, advice)
                observer.terrain_override = controller.altitude_ft > args.altitude_ft
                if advice.turn_back:
                    raise ValueError("Terrain guard: " + advice.reason)
                if advice.reason and advice.reason != guard_said:
                    guard_said = advice.reason
                    print("GUARD", advice.reason, flush=True)
                    recorder.write("guard", {"frame": snap["frame"], "reason": advice.reason,
                                             "floor_ft": advice.floor_indicated_ft})
            frame = controller.step(snap)
            controls = {k: float(frame[k]) for k in channels}
            if samples % 5 == 0:
                recorder.write("command", {"frame": snap["frame"], "controls": controls,
                                           "diagnostics": controller.last_diagnostics})
            if time.monotonic() - last_report > 20:
                d = controller.last_diagnostics
                print("PROGRESS", json.dumps({"wp": d.get("waypoint"), "dist_nm": round(d.get("distance_nm") or 0, 2),
                                              "xtk_m": round(d.get("cross_track_m") or 0), "alt": round(v["altitude_indicated_ft"]),
                                              "kias": round(v["kias"]), "bank": round(v["roll_deg"], 1),
                                              "reached": len(observer.reached)}), flush=True)
                last_report = time.monotonic()
        else:
            raise ValueError("Pattern wall deadline exceeded")
    except BaseException as error:
        result = {"outcome": "FAIL", "reason": str(error) or type(error).__name__, "samples": samples,
                  "observer": observer.report(), "controller_transitions": controller.transitions}
        recorder.write("intervention", result)
    finally:
        try:
            status = client.request("fault_pause", reason="pattern trial ended")
            deadline = time.monotonic() + 2
            while not status["pause_confirmed"] and time.monotonic() < deadline:
                time.sleep(.03)
                status = client.request("status")
            end = client.request("snapshot")
            result["end"] = {"status": status, "values": end["values"]}
            if not status["pause_confirmed"] or end["override_state"] is not False:
                result["outcome"] = "FAIL"
                result["containment_error"] = "Pause/override release not confirmed"
        except Exception as error:
            result["outcome"] = "FAIL"
            result["containment_error"] = str(error)
        recorder.write("end", result)
        recorder.close()
    print("RESULT", json.dumps({k: result.get(k) for k in ("outcome", "reason", "samples",
                                                           "max_altitude_error_ft", "max_bank_deg")}
                               | {"reached": [r["waypoint"] for r in result.get("reached", [])],
                                  "trace": str(args.output)}), flush=True)
    return 0 if result["outcome"] == "PASS" else 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--xplane", type=Path, default=Path.home() / "X-Plane 12")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--profile", choices=sorted(PROFILES), default="C172SP")
    p.add_argument("--pattern", choices=("expanding_square", "parallel", "creeping_line"), required=True)
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--heading", type=float, default=0.)
    p.add_argument("--spacing-nm", type=float, default=1.)
    p.add_argument("--legs", type=int, default=6)
    p.add_argument("--turn", choices=("right", "left"), default="right")
    p.add_argument("--length-nm", type=float, default=4.)
    p.add_argument("--width-nm", type=float, default=3.)
    p.add_argument("--altitude-ft", type=float, default=2000.)
    p.add_argument("--kias", type=float, default=None)
    p.add_argument("--max-wall-s", type=float, default=1800.)
    p.add_argument("--no-terrain-guard", action="store_true",
                   help="fly the pattern altitude whatever the ground ahead (the bridge fence still applies)")
    a = p.parse_args()
    with ControllerLock():
        return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
