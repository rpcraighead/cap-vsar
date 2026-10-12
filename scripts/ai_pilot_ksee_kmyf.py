#!/usr/bin/env python3
"""Attended continuation of KSEE 27R departure through KMYF ILS 28R."""
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
from services.ai_pilot.control_ownership import ControllerLock
from services.ai_pilot.experiment import BridgeClient, Recorder, digest
from services.ai_pilot.ksee_kmyf_mission import MissionController, STAGES
from services.ai_pilot.landing_trial import LandingObserver
from xplane.capvsar_landing import RUNWAYS
from scripts.ai_pilot_experiment import inventory
from services.ai_pilot.aircraft_profiles import PROFILES


def run(args):
    if args.rollout_only and args.start_stage != "landing":
        raise ValueError("Rollout-only continuation requires landing stage")
    config = json.loads(args.config.read_text())
    if config.get("mode") != "mission":
        raise ValueError("Requires expiring mission bridge")
    profile = PROFILES[args.profile]
    inv = inventory(args.xplane, include_mission=True, profile=args.profile)
    inv["profile_tuning_validated"] = profile.tuning_validated
    for name, installed in inv["installed_bridge_sha256"].items():
        if installed != inv["source_sha256"]["xplane/"+name]:
            raise ValueError("Installed mission bridge mismatch: "+name)
    inv["controller_sha256"] = digest(ROOT/"services/ai_pilot/ksee_kmyf_mission.py")
    inv["runner_sha256"] = digest(Path(__file__))
    manifest = {"purpose": "KSEE 27R Mission Bay Two to KMYF ILS 28R",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "inventory": inv, "start_stage": args.start_stage,
                "chart_cycle": "FAA 2610", "sim_cifp_cycle": "2406",
                "simulated_clearance": "Departure and approach self-vector; no ATC service"}
    recorder = Recorder(args.output, manifest)
    client = BridgeClient(config)
    controller = MissionController(args.start_stage, profile=profile)
    observer = LandingObserver(0., 0., "KMYF 28R", profile=profile)
    result = {"outcome": "FAIL", "reason": "Setup incomplete"}
    session = secrets.token_hex(16)
    seq = 0
    generation = 0
    samples = 0
    previous_frame = None
    previous_stage = controller.stage
    try:
        status = client.request("fault_pause", reason="KSEE-KMYF mission setup")
        deadline = time.monotonic()+3
        while not status["pause_confirmed"]:
            if time.monotonic()>deadline:
                raise ValueError("Setup pause not confirmed")
            time.sleep(.03)
            status = client.request("status")
        reset = client.request("lab_reset", session=session)
        recorder.write("setup", reset)
        deadline = time.monotonic()+15
        while True:
            snap = client.request("snapshot")
            v = snap["values"]
            if (snap["session"] == session and v["paused"] == 1 and
                    v["nav1_frequency_10khz"] == 11195 and
                    snap["override_state"] is False and snap["ap_engaged"] is False):
                break
            if time.monotonic()>deadline:
                raise ValueError("Mission readiness not confirmed")
            time.sleep(.1)
        controls = {"roll": .0, "pitch": .06, "yaw": .10, "throttle": 1.,
                    "flap": 0., "trim": max(-.6, min(.6, snap["controls"]["trim"])), "brake": 0.}
        if args.start_stage == "missed_runway":
            controls.update(pitch=.4, flap=1/3)
        if args.rollout_only:
            controls.update(pitch=.08, yaw=0., throttle=0., flap=1., brake=.25)
        started = client.request("lab_start", session=session, controls=controls,
                                 snapshot_frame=snap["frame"],
                                 snapshot_wall_time_s=snap["wall_time_s"])
        if started["state"] != "ACTIVE":
            raise ValueError("Mission start not active")
        generation, seq = started["generation"], started["frame_sequence"]
        start_wall = time.monotonic()
        last_report_wall = 0.
        while time.monotonic()-start_wall < args.max_wall_s:
            seq += 1
            response = client.request("exchange", session=session, generation=generation,
                                      sequence=seq, expires_at=time.monotonic()+.18,
                                      controls=controls)
            if response["bridge"]["state"] != "ACTIVE":
                raise ValueError("Mission bridge lost authority")
            snap = response["snapshot"]
            if snap is None or snap["frame"] == previous_frame:
                time.sleep(.005)
                continue
            previous_frame = snap["frame"]
            v = snap["values"]
            if v["paused"]:
                if time.monotonic()-start_wall < .2:
                    continue
                raise ValueError("Simulator paused during mission")
            samples += 1
            if samples%5 == 0:
                recorder.write("snapshot", snap)
            if args.rollout_only:
                along, cross = RUNWAYS["KMYF 28R"].coordinates(v["latitude_deg"], v["longitude_deg"])
                if not v["on_ground"] or abs(cross)>5 or along>RUNWAYS["KMYF 28R"].length_m-100:
                    raise ValueError("KMYF rollout runway corridor lost")
                if v["groundspeed_mps"] <= 1.0 and samples > 20:
                    result = {"outcome": "ROLLOUT_PASS", "samples": samples,
                              "stop_along_m": along, "stop_cross_m": cross,
                              "stop_groundspeed_mps": v["groundspeed_mps"]}
                    break
            elif controller.stage == "landing":
                report = observer.observe(snap)
                if report["outcome"] != "INCOMPLETE":
                    result = {**report, "samples": samples, "transitions": controller.transitions}
                    break
            controls = controller.step(snap)
            if samples%5 == 0:
                recorder.write("command", {"frame": snap["frame"],
                                           "controls": controls,
                                           "diagnostics": controller.last_diagnostics})
            if controller.stage != previous_stage:
                transition = controller.transitions[-1]
                recorder.write("milestone", transition)
                print("MILESTONE", json.dumps(transition), flush=True)
                previous_stage = controller.stage
                if controller.stage == args.stop_at:
                    result = {"outcome": "CHECKPOINT", "stage": controller.stage,
                              "samples": samples, "transition": transition}
                    break
            if time.monotonic()-last_report_wall > 30:
                print("PROGRESS", json.dumps({"stage": controller.stage,
                    "alt_ft": round(v["altitude_indicated_ft"]), "kias": round(v["kias"]),
                    "heading": round(v["heading_true_deg"]), "lat": round(v["latitude_deg"],5),
                    "lon": round(v["longitude_deg"],5), "sim_s": round(v["sim_time_s"])}), flush=True)
                last_report_wall = time.monotonic()
        else:
            raise ValueError("Mission wall deadline exceeded")
    except BaseException as error:
        result = {"outcome": "FAIL", "reason": str(error) or type(error).__name__,
                  "stage": controller.stage, "samples": samples,
                  "transitions": controller.transitions}
        recorder.write("intervention", result)
    finally:
        try:
            status = client.request("fault_pause", reason="KSEE-KMYF trial ended")
            deadline = time.monotonic()+2
            while not status["pause_confirmed"] and time.monotonic()<deadline:
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
    print("RESULT", json.dumps({"outcome": result["outcome"], "stage": controller.stage,
                                 "reason": result.get("reason"), "samples": samples,
                                 "trace": str(args.output)}), flush=True)
    return 0 if result["outcome"] in ("PASS", "CHECKPOINT", "ROLLOUT_PASS") else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--xplane", type=Path, default=Path.home()/"X-Plane 12")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--start-stage", choices=STAGES, default="runway_climb")
    p.add_argument("--stop-at", choices=STAGES)
    p.add_argument("--max-wall-s", type=float, default=3600)
    p.add_argument("--rollout-only", action="store_true")
    p.add_argument("--profile", choices=sorted(PROFILES), default="C172SP",
                   help="aircraft profile; C182T tuning is not yet validated")
    a = p.parse_args()
    with ControllerLock():
        return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
