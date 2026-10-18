#!/usr/bin/env python3
"""Attended profile-based runway landing trial and independent trace replay."""
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
from services.ai_pilot.experiment import (BridgeClient, Recorder, digest, FRAME_LEASE_S,
                                          wait_for_ready_snapshot)
from services.ai_pilot.landing_trial import LandingController, LandingObserver
from xplane.capvsar_landing import RUNWAYS
from scripts.ai_pilot_experiment import inventory, validate_staged_profile


def replay(path):
    observer = None
    end = None
    profile = None
    with Path(path).open() as stream:
        for line in stream:
            record = json.loads(line)
            if record["kind"] == "manifest":
                manifest = record["payload"]
                entry = manifest.get("entry", {})
                profile = PROFILES[manifest.get("profile", "C172SP")]
                observer = LandingObserver(entry.get("wind_speed_kt", 0.),
                                           entry.get("wind_from_offset_deg", 0.),
                                           entry.get("runway", "KMYF 28R"),
                                           profile=profile)
            elif record["kind"] == "snapshot":
                if observer is None:
                    raise ValueError("Landing trace has no manifest")
                observer.observe(record["payload"])
            elif record["kind"] == "end":
                end = record["payload"]
    if observer is None:
        raise ValueError("Landing trace has no manifest")
    result = observer.report()
    if end is None or end.get("outcome") != "PASS" or result["outcome"] != "PASS":
        result["outcome"] = "FAIL"
        result["trace_end"] = end
    return result


def run(args):
    config = json.loads(args.config.read_text())
    profile = PROFILES[args.profile]
    if config.get("mode") != "landing":
        raise ValueError("Requires an expiring landing laboratory installation")
    if config.get("runway", "KMYF 28R") != args.runway:
        raise ValueError("Installed runway does not match requested runway")
    runway = RUNWAYS[args.runway]
    client = BridgeClient(config)
    inv = inventory(args.xplane, include_landing=True, profile=args.profile)
    validate_staged_profile(config, profile, inv, mode="landing")
    inv["controller_sha256"] = digest(ROOT / "services/ai_pilot/landing_trial.py")
    inv["runner_sha256"] = digest(Path(__file__))
    manifest = {"purpose": args.runway.replace(" ", "-") + "-moderate-braking",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "inventory": inv, "qualification_only": True, "profile": args.profile,
                "criteria": {"touchdown_along_m": [runway.aimpoint_m, runway.aimpoint_m + 400. * .3048],
                             "touchdown_cross_m": [-4, 4],
                             "touchdown_sink_fpm_min": -600, "max_brake_ratio": .35,
                             "pre_touch_pitch_deg": [5, 7],
                             "max_flare_rebound_ft": 1.5,
                             "crosswind_pre_touch_heading_error_deg": 3,
                             "crosswind_max_rollout_heading_error_deg": 5,
                             "full_stop_groundspeed_kt": 2,
                             "max_stop_along_m": runway.length_m - 100},
                "entry": {"runway": args.runway, "lateral_offset": args.lateral_offset,
                          "altitude_offset": args.altitude_offset,
                          "speed_offset": args.speed_offset,
                          "wind_speed_kt": args.wind_speed_kt,
                          "wind_from_offset_deg": args.wind_from_offset_deg}}
    recorder = Recorder(args.output, manifest)
    observer = LandingObserver(args.wind_speed_kt, args.wind_from_offset_deg, args.runway,
                               profile=profile)
    controller = LandingController(args.runway, profile=profile)
    result = {"outcome": "FAIL", "reason": "Setup incomplete"}
    session = secrets.token_hex(16)
    generation = 0
    seq = 0
    def frame(controls):
        nonlocal seq
        seq += 1
        return {"session": session, "generation": generation, "sequence": seq,
                "expires_at": time.monotonic() + FRAME_LEASE_S, "controls": controls}
    try:
        for name, value in inv["installed_bridge_sha256"].items():
            if value != inv["source_sha256"]["xplane/" + name]:
                raise ValueError("Installed bridge mismatch: " + name)
        wait_for_ready_snapshot(client, timeout_s=120.)
        status = client.request("fault_pause", reason="Landing setup between trials")
        deadline = time.monotonic() + 3
        while not status["pause_confirmed"]:
            if time.monotonic() > deadline:
                raise ValueError("Setup pause not confirmed")
            time.sleep(.03)
            status = client.request("status")
        reset = client.request("lab_reset", session=session,
                               **{k: v for k, v in manifest["entry"].items() if k != "runway"})
        recorder.write("setup", reset)
        s = wait_for_ready_snapshot(
            client, timeout_s=120.,
            validate=lambda snap: (snap["session"] == session and snap["values"]["paused"] == 1
                                   and all(abs(snap["values"][f"local_{axis}_m"] - value) < 1
                                           for axis, value in zip("xyz", reset["local_position_m"]))
                                   and abs(snap["values"]["payload_kg"] - 170) < 1
                                   and abs(snap["values"]["fuel_kg"] - 100) < 1
                                   and snap["values"]["brake_left"] == 0
                                   and snap["values"]["brake_right"] == 0
                                   and snap["override_state"] is False and snap["ap_engaged"] is False))
        recorder.write("setup_snapshot", s)
        controls = dict(s["controls"])
        started = client.request("lab_start", session=session, controls=controls,
                                 snapshot_frame=s["frame"], snapshot_wall_time_s=s["wall_time_s"])
        if started["state"] != "ACTIVE":
            raise ValueError("Landing activation not confirmed")
        generation, seq = started["generation"], started["frame_sequence"]
        started_wall = time.monotonic()
        started_sim = None
        previous_frame = None
        while time.monotonic() - started_wall < 220:
            response = client.request("exchange", **frame(controls))
            if response["bridge"]["state"] != "ACTIVE":
                raise ValueError("Bridge lost active authority")
            s = response["snapshot"]
            if s is None or s["frame"] == previous_frame:
                time.sleep(.01)
                continue
            if s["values"]["paused"] and time.monotonic() - started_wall < .2:
                continue
            previous_frame = s["frame"]
            if started_sim is None:
                started_sim = s["values"]["sim_time_s"]
            if (observer.samples == 0 and s["values"]["kias"] < 40
                    and time.monotonic() - started_wall < 2):
                recorder.write("setup_snapshot", s)
                time.sleep(.02)
                continue
            recorder.write("snapshot", s)
            report = observer.observe(s)
            if report["outcome"] != "INCOMPLETE":
                result = report
                break
            measured_wind = s["values"]["wind_mps"]
            expected_wind = args.wind_speed_kt * .514444
            direction_error = abs((s["values"]["wind_from_true_deg"]
                                   - reset["wind_from_true_deg"] + 180) % 360 - 180)
            if (not s["values"]["engine_running"] or
                    (s["values"]["sim_time_s"] - started_sim > 6 and
                     ((measured_wind > .5 if args.wind_speed_kt == 0 else
                       not expected_wind * .5 <= measured_wind <= expected_wind + 1.5)
                      or (args.wind_speed_kt and direction_error > 6)))):
                raise ValueError("Landing engine or weather readiness lost")
            controls = controller.step(s)
            recorder.write("command", {"source_frame": s["frame"], "controls": controls,
                                        "diagnostics": controller.last_commands})
            # The exchange already waits for the simulator's flight loop.
            # Request the next measured frame immediately; an additional sleep
            # spends the 180 ms lease margin on scenery-heavy simulator frames.
        else:
            raise ValueError("Landing wall deadline exceeded")
    except BaseException as error:
        recorder.write("intervention", {"error": type(error).__name__, "reason": str(error)})
        result = {"outcome": "FAIL", "reason": str(error), "observer": observer.report()}
    finally:
        try:
            status = client.request("fault_pause", reason="Landing trial ended")
            deadline = time.monotonic() + 2
            while not status["pause_confirmed"] and time.monotonic() < deadline:
                time.sleep(.03)
                status = client.request("status")
            state = client.request("snapshot")
            if (not status["pause_confirmed"] or state["override_state"] is not False
                    or state["values"]["brake_left"] != 0 or state["values"]["brake_right"] != 0):
                raise RuntimeError("Final pause, override or brake release not confirmed")
            result["end_bridge"] = status
        except Exception as error:
            result["containment_error"] = str(error)
            result["outcome"] = "FAIL"
        recorder.write("end", result)
        recorder.close()
    measured = replay(args.output)
    print(json.dumps({"runner": result, "independent_score": measured,
                      "trace": str(args.output)}, indent=2))
    return 0 if measured["outcome"] == "PASS" else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    fly = sub.add_parser("fly")
    fly.add_argument("--config", type=Path, required=True)
    fly.add_argument("--xplane", type=Path, default=Path.home() / "X-Plane 12")
    fly.add_argument("--output", type=Path, required=True)
    fly.add_argument("--runway", choices=tuple(RUNWAYS), default="KMYF 28R")
    fly.add_argument("--profile", choices=sorted(PROFILES), required=True)
    fly.add_argument("--lateral-offset", type=float, default=0.)
    fly.add_argument("--altitude-offset", type=float, default=0.)
    fly.add_argument("--speed-offset", type=float, default=0.)
    fly.add_argument("--wind-speed-kt", type=float, default=0.)
    fly.add_argument("--wind-from-offset-deg", type=float, default=0.)
    score = sub.add_parser("score")
    score.add_argument("trace", type=Path)
    args = p.parse_args()
    if args.command == "score":
        result = replay(args.trace)
        print(json.dumps(result, indent=2))
        return 0 if result["outcome"] == "PASS" else 1
    with ControllerLock():
        return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
