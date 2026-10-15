#!/usr/bin/env python3
"""Attended stock-C172 KSEE East Transient 12 taxi and initial-takeoff trial."""
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
from services.ai_pilot.ground_guidance import GroundObservation, TaxiGuidance
from services.ai_pilot.ksee_surface import read_survey
from services.ai_pilot.runway_entry import RunwayEntryGuidance
from services.ai_pilot.takeoff_guidance import TakeoffGuidance, TakeoffObservation
from services.ai_pilot.taxi import ClearanceSource, TaxiCoordinator, TaxiPhase
from scripts.ai_pilot_experiment import inventory
from services.ai_pilot.aircraft_profiles import PROFILES


def run(args):
    config = json.loads(args.config.read_text())
    if config.get("mode") != "surface" or config.get("parking") != "KSEE East Transient Parking 12":
        raise ValueError("Requires an expiring KSEE East Transient 12 surface lab")
    apt = args.xplane / "Global Scenery/Global Airports/Earth nav data/apt.dat"
    survey = read_survey(apt)
    route, points = survey.taxi_route()
    taxi = TaxiCoordinator(route.start, towered=True)
    taxi.load_route(route)
    taxi.authorize_taxi(ClearanceSource.ATC)  # Explicit simulated trial authority.
    if args.start_at == "hold":
        if args.phase != "takeoff":
            raise ValueError("D8 hold diagnostic checkpoint requires takeoff phase")
        for _ in route.legs:
            taxi.complete_leg()
    profile = PROFILES[args.profile]
    taxi_guide = TaxiGuidance(taxi, route, points, corridor_half_width_m=10., profile=profile)
    entry_guide = RunwayEntryGuidance(taxi, survey.entry_geometry(), profile=profile)
    heading, length, _entry_along = survey.runway_frame()
    takeoff = TakeoffGuidance(taxi, runway="27R", runway_heading_true_deg=heading,
                              runway_length_m=length, field_elevation_ft=388., profile=profile)
    inv = inventory(args.xplane, include_surface=True, profile=args.profile)
    inv["profile_tuning_validated"] = profile.tuning_validated
    for name, installed in inv["installed_bridge_sha256"].items():
        if installed != inv["source_sha256"]["xplane/"+name]:
            raise ValueError("Installed surface bridge mismatch: " + name)
    inv["surface_runner_sha256"] = digest(Path(__file__))
    inv["surface_route_sha256"] = digest(ROOT / "services/ai_pilot/ksee_surface.py")
    inv["apt_dat_sha256"] = digest(apt)
    manifest = {"purpose": "KSEE East Transient 12 to 27R " + args.phase,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "inventory": inv, "qualification_only": True,
                "start_at": args.start_at,
                "diagnostic_checkpoint": args.start_at == "hold",
                "simulated_authority": ["taxi clearance to D8 hold"] +
                                       (["27R takeoff clearance"] if args.phase == "takeoff" else []),
                "criteria": {"taxi_max_mps": 8, "hold_stop_mps": .5,
                             "rotation_kias": 55, "takeoff_stop_agl_ft": 300}}
    recorder = Recorder(args.output, manifest)
    client = BridgeClient(config)
    result = {"outcome": "FAIL", "reason": "setup incomplete"}
    session = secrets.token_hex(16)
    generation = 0
    sequence = 0
    controls = {"roll": 0., "pitch": 0., "yaw": 0., "throttle": 0.,
                "flap": 0., "trim": 0., "brake": .35}
    if profile.constant_speed_prop:
        controls["prop"] = 1.
    stage = "settle"
    previous_frame = None
    start_sim = None
    climb_distance_nm = 0.
    last_climb_sim = None
    samples = 0
    try:
        status = client.request("fault_pause", reason="KSEE surface reset between trials")
        deadline = time.monotonic()+3
        while not status["pause_confirmed"]:
            if time.monotonic() > deadline:
                raise ValueError("Setup pause not confirmed")
            time.sleep(.03)
            status = client.request("status")
        reset_kwargs = {"checkpoint": "D8 hold"} if args.start_at == "hold" else {}
        reset = client.request("lab_reset", session=session, **reset_kwargs)
        recorder.write("setup", reset)
        deadline = time.monotonic()+15
        while True:
            try:
                snapshot = client.request("snapshot")
                v = snapshot["values"]
                ready = (snapshot["session"] == session and v["paused"] == 1
                         and all(abs(v[f"local_{axis}_m"]-value) < 1
                                 for axis, value in zip("xyz", reset["local_position_m"]))
                         and snapshot["override_state"] is False
                         and snapshot["ap_engaged"] is False
                         and v["parking_brake_ratio"] <= .05)
                recorder.write("setup_snapshot", snapshot)
                if ready:
                    break
            except (RuntimeError, OSError):
                pass
            if time.monotonic() > deadline:
                raise ValueError("Parking reset not confirmed")
            time.sleep(.1)
        started = client.request("lab_start", session=session, controls=controls,
                                 snapshot_frame=snapshot["frame"],
                                 snapshot_wall_time_s=snapshot["wall_time_s"])
        if started["state"] != "ACTIVE":
            raise ValueError("Surface activation not confirmed")
        generation, sequence = started["generation"], started["frame_sequence"]
        wall_started = time.monotonic()
        while time.monotonic()-wall_started < args.max_wall_s:
            sequence += 1
            response = client.request("exchange", session=session, generation=generation,
                                      sequence=sequence, expires_at=time.monotonic()+.18,
                                      controls=controls)
            if response["bridge"]["state"] != "ACTIVE":
                raise ValueError("Surface bridge lost active authority")
            snapshot = response["snapshot"]
            if snapshot is None or snapshot["frame"] == previous_frame:
                time.sleep(.01)
                continue
            previous_frame = snapshot["frame"]
            v = snapshot["values"]
            if v["paused"]:
                if time.monotonic()-wall_started < .2:
                    continue
                raise ValueError("Simulator paused during surface trial")
            recorder.write("snapshot", snapshot)
            samples += 1
            if start_sim is None:
                start_sim = v["sim_time_s"]
            position = survey.local((v["latitude_deg"], v["longitude_deg"]))
            observation = GroundObservation(position.east_m, position.north_m,
                                            v["heading_true_deg"], v["groundspeed_mps"],
                                            bool(v["on_ground"]), bool(v["paused"]))
            if stage == "settle":
                if v["sim_time_s"]-start_sim > 5:
                    raise ValueError("Aircraft did not settle at parking in five seconds")
                if (v["sim_time_s"]-start_sim >= 1.5 and v["on_ground"]
                        and v["groundspeed_mps"] < .5 and v["engine_running"]
                        and v["engine_rpm"] >= 450):
                    if args.start_at == "hold":
                        taxi.authorize_departure_runway("27R", ClearanceSource.ATC,
                                                        takeoff=True)
                        recorder.write("simulated_clearance", {"runway": "27R", "action": "takeoff"})
                        stage = "lineup"
                    else:
                        stage = "taxi"
                command = controls
            elif stage == "taxi":
                command = taxi_guide.step(observation)
                if taxi_guide.fault:
                    raise ValueError(taxi_guide.fault)
                if taxi.phase is TaxiPhase.HOLDING_SHORT_DEPARTURE:
                    if v["groundspeed_mps"] > .5:
                        raise ValueError("D8 hold stop not verified")
                    recorder.write("milestone", {"name": "D8 hold short", "frame": snapshot["frame"]})
                    if args.phase == "taxi":
                        result = {"outcome": "PASS", "phase": "taxi", "samples": samples,
                                  "hold_position": [v["latitude_deg"], v["longitude_deg"]]}
                        break
                    taxi.authorize_departure_runway("27R", ClearanceSource.ATC,
                                                    takeoff=True)
                    recorder.write("simulated_clearance", {"runway": "27R", "action": "takeoff"})
                    stage = "lineup"
                command = command.actuator_frame(snapshot["controls"]["trim"])
            elif stage == "lineup":
                command = entry_guide.step(observation)
                if entry_guide.fault:
                    raise ValueError(entry_guide.fault)
                if entry_guide.phase == "complete":
                    stage = "takeoff"
                    recorder.write("milestone", {"name": "27R lined up", "frame": snapshot["frame"]})
                command = command.actuator_frame(snapshot["controls"]["trim"])
            else:
                if last_climb_sim is not None and not v["on_ground"]:
                    climb_distance_nm += v["groundspeed_mps"] * max(0., v["sim_time_s"]-last_climb_sim)/1852.
                last_climb_sim = v["sim_time_s"]
                along, cross = _runway_coordinates(survey, v)
                takeoff_observation = TakeoffObservation(
                    sim_time_s=v["sim_time_s"], along_runway_m=along,
                    cross_runway_m=cross, heading_true_deg=v["heading_true_deg"],
                    kias=v["kias"], groundspeed_mps=v["groundspeed_mps"],
                    on_ground=bool(v["on_ground"]), agl_ft=v["agl_m"]*3.28084,
                    altitude_msl_ft=v["altitude_msl_m"]*3.28084,
                    climb_distance_nm=climb_distance_nm, pitch_deg=v["pitch_deg"],
                    pitch_rate_dps=v["pitch_rate_dps"], roll_deg=v["roll_deg"],
                    engine_rpm=v["engine_rpm"], flap_ratio=v["flap_actual"])
                command = takeoff.step(takeoff_observation)
                if command.intervention_required:
                    raise ValueError("Takeoff intervention: " + command.reason)
                if command.phase == "climb" and takeoff_observation.agl_ft >= 300:
                    result = {"outcome": "PASS", "phase": "initial_takeoff",
                              "samples": samples, "max_agl_ft": takeoff_observation.agl_ft,
                              "takeoff_kias": v["kias"]}
                    break
                command = command.actuator_frame(snapshot["controls"]["trim"])
            if stage != "settle":
                controls = command
            recorder.write("command", {"source_frame": snapshot["frame"],
                                       "stage": stage, "controls": controls})
        else:
            raise ValueError("Surface trial wall deadline exceeded")
    except BaseException as error:
        reason = str(error) or type(error).__name__
        recorder.write("intervention", {"error": type(error).__name__, "reason": reason,
                                        "stage": stage})
        result = {"outcome": "FAIL", "reason": reason, "stage": stage,
                  "samples": samples}
    finally:
        try:
            status = client.request("fault_pause", reason="KSEE surface trial ended")
            deadline = time.monotonic()+2
            while not status["pause_confirmed"] and time.monotonic() < deadline:
                time.sleep(.03)
                status = client.request("status")
            end = client.request("snapshot")
            if (not status["pause_confirmed"] or end["override_state"] is not False
                    or end["values"]["toe_brake_left"] != 0
                    or end["values"]["toe_brake_right"] != 0):
                raise RuntimeError("Final pause, override or brake release not confirmed")
            result["end_bridge"] = status
        except Exception as error:
            result["containment_error"] = str(error)
            result["outcome"] = "FAIL"
        recorder.write("end", result)
        recorder.close()
    print(json.dumps({"result": result, "trace": str(args.output)}, indent=2))
    return 0 if result["outcome"] == "PASS" else 1


def _runway_coordinates(survey, values):
    frame = survey._frame(survey.runway_ends["27R"], survey.runway_ends["9L"])
    return survey._coordinates(frame, (values["latitude_deg"], values["longitude_deg"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--xplane", type=Path, default=Path.home()/"X-Plane 12")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("taxi", "takeoff"), default="taxi")
    parser.add_argument("--start-at", choices=("parking", "hold"), default="parking")
    parser.add_argument("--max-wall-s", type=float, default=600.)
    parser.add_argument("--profile", choices=sorted(PROFILES), required=True,
                        help="aircraft profile; C182T tuning is not yet validated")
    args = parser.parse_args()
    if not 30 <= args.max_wall_s <= 900:
        parser.error("Surface trial wall deadline outside 30–900 seconds")
    with ControllerLock():
        return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
