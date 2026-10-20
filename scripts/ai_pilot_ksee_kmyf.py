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
from services.ai_pilot.experiment import (BridgeClient, Recorder, digest, FRAME_LEASE_S,
                                          wait_for_ready_snapshot)
from services.ai_pilot.ksee_kmyf_mission import MissionController, STAGES
from services.ai_pilot.landing_trial import LandingObserver
from services.ai_pilot.mission_retask import MissionRetaskServer
from services.ai_pilot.ground_guidance import GroundObservation, TaxiGuidance
from services.ai_pilot.ksee_surface import read_survey
from services.ai_pilot.runway_entry import RunwayEntryGuidance
from services.ai_pilot.takeoff_guidance import TakeoffGuidance, TakeoffObservation
from services.ai_pilot.taxi import ClearanceSource, TaxiCoordinator, TaxiPhase
from xplane.capvsar_landing import RUNWAYS
from scripts.ai_pilot_experiment import inventory, validate_staged_profile
from services.ai_pilot.aircraft_profiles import PROFILES


def run(args):
    if args.rollout_only and args.start_stage != "landing":
        raise ValueError("Rollout-only continuation requires landing stage")
    if args.from_parking and (args.start_stage != "runway_climb" or args.rollout_only):
        raise ValueError("Parking start requires the complete departure sequence")
    config = json.loads(args.config.read_text())
    if config.get("mode") != "mission":
        raise ValueError("Requires expiring mission bridge")
    profile = PROFILES[args.profile]
    inv = inventory(args.xplane, include_mission=True, profile=args.profile)
    validate_staged_profile(config, profile, inv, mode="mission")
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
    client = BridgeClient(config)
    retask = MissionRetaskServer(config["socket_path"]+"-retask", config["secret"])
    controller = MissionController(args.start_stage, profile=profile)
    observer = LandingObserver(0., 0., "KMYF 28R", profile=profile)
    survey = None
    ground_stage = None
    ground_start_sim = None
    climb_distance_nm = 0.
    last_climb_sim = None
    if args.from_parking:
        apt = args.xplane / "Global Scenery/Global Airports/Earth nav data/apt.dat"
        survey = read_survey(apt)
        route, points = survey.taxi_route()
        taxi = TaxiCoordinator(route.start, towered=True)
        taxi.load_route(route)
        taxi.authorize_taxi(ClearanceSource.ATC)  # Explicit simulated authority.
        taxi_guide = TaxiGuidance(taxi, route, points, corridor_half_width_m=10.,
                                   profile=profile)
        entry_guide = RunwayEntryGuidance(taxi, survey.entry_geometry(), profile=profile)
        heading, length, _ = survey.runway_frame()
        takeoff = TakeoffGuidance(taxi, runway="27R", runway_heading_true_deg=heading,
                                  runway_length_m=length, field_elevation_ft=388., profile=profile)
        ground_stage = "settle"
        manifest["from_parking"] = True
        manifest["apt_dat_sha256"] = digest(apt)
        manifest["simulated_authority"] = ["KSEE taxi to D8", "KSEE 27R takeoff"]
    recorder = Recorder(args.output, manifest)
    result = {"outcome": "FAIL", "reason": "Setup incomplete"}
    session = secrets.token_hex(16)
    seq = 0
    generation = 0
    samples = 0
    previous_frame = None
    previous_stage = controller.stage
    try:
        retask.__enter__()
        wait_for_ready_snapshot(client, timeout_s=120.)
        status = client.request("fault_pause", reason="KSEE-KMYF mission setup")
        deadline = time.monotonic()+3
        while not status["pause_confirmed"]:
            if time.monotonic()>deadline:
                raise ValueError("Setup pause not confirmed")
            time.sleep(.03)
            status = client.request("status")
        reset = client.request("lab_reset", session=session,
                               **({"checkpoint": "KSEE parking"} if args.from_parking else {}))
        recorder.write("setup", reset)
        snap = wait_for_ready_snapshot(
            client, timeout_s=120.,
            validate=lambda s: (s["session"] == session and s["values"]["paused"] == 1
                                and s["values"]["nav1_frequency_10khz"] == 11195
                                and s["override_state"] is False and s["ap_engaged"] is False))
        controls = {"roll": .0, "pitch": .06, "yaw": .10, "throttle": 1.,
                    "flap": 0., "trim": max(-.6, min(.6, snap["controls"]["trim"])), "brake": 0.}
        if profile.constant_speed_prop:
            controls["prop"] = 1.
        if args.from_parking:
            controls.update(roll=0., pitch=0., yaw=0., throttle=0., brake=.35)
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
                                      sequence=seq, expires_at=time.monotonic()+FRAME_LEASE_S,
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
            retask.apply_pending(controller, snap, recorder)
            samples += 1
            if samples%5 == 0 or ground_stage is not None:
                recorder.write("snapshot", snap)
            if ground_stage is not None:
                if ground_start_sim is None:
                    ground_start_sim = v["sim_time_s"]
                position = survey.local((v["latitude_deg"], v["longitude_deg"]))
                observation = GroundObservation(position.east_m, position.north_m,
                                                v["heading_true_deg"], v["groundspeed_mps"],
                                                bool(v["on_ground"]), bool(v["paused"]))
                if ground_stage == "settle":
                    if v["sim_time_s"]-ground_start_sim > 5:
                        raise ValueError("KSEE parking settle deadline exceeded")
                    if (v["sim_time_s"]-ground_start_sim >= 1.5 and v["on_ground"]
                            and v["groundspeed_mps"] < .5 and v["engine_running"]
                            and v["engine_rpm"] >= 450):
                        ground_stage = "taxi"
                        recorder.write("milestone", {"name": "KSEE taxi began", "frame": snap["frame"]})
                elif ground_stage == "taxi":
                    guidance = taxi_guide.step(observation)
                    if taxi_guide.fault:
                        raise ValueError(taxi_guide.fault)
                    controls = guidance.actuator_frame(snap["controls"]["trim"])
                    if taxi.phase is TaxiPhase.HOLDING_SHORT_DEPARTURE:
                        if v["groundspeed_mps"] > .5:
                            raise ValueError("D8 hold stop not verified")
                        recorder.write("milestone", {"name": "D8 hold short", "frame": snap["frame"]})
                        taxi.authorize_departure_runway("27R", ClearanceSource.ATC, takeoff=True)
                        ground_stage = "lineup"
                elif ground_stage == "lineup":
                    guidance = entry_guide.step(observation)
                    if entry_guide.fault:
                        raise ValueError(entry_guide.fault)
                    controls = guidance.actuator_frame(snap["controls"]["trim"])
                    if entry_guide.phase == "complete":
                        recorder.write("milestone", {"name": "27R lined up", "frame": snap["frame"]})
                        ground_stage = "takeoff"
                else:
                    if last_climb_sim is not None and not v["on_ground"]:
                        climb_distance_nm += v["groundspeed_mps"] * max(0., v["sim_time_s"]-last_climb_sim)/1852.
                    last_climb_sim = v["sim_time_s"]
                    frame = survey._frame(survey.runway_ends["27R"], survey.runway_ends["9L"])
                    along, cross = survey._coordinates(frame, (v["latitude_deg"], v["longitude_deg"]))
                    takeoff_observation = TakeoffObservation(
                        sim_time_s=v["sim_time_s"], along_runway_m=along,
                        cross_runway_m=cross, heading_true_deg=v["heading_true_deg"],
                        kias=v["kias"], groundspeed_mps=v["groundspeed_mps"],
                        on_ground=bool(v["on_ground"]), agl_ft=v["agl_m"]*3.28084,
                        altitude_msl_ft=v["altitude_msl_m"]*3.28084,
                        climb_distance_nm=climb_distance_nm, pitch_deg=v["pitch_deg"],
                        pitch_rate_dps=v["pitch_rate_dps"], roll_deg=v["roll_deg"],
                        engine_rpm=v["engine_rpm"], flap_ratio=v["flap_actual"])
                    guidance = takeoff.step(takeoff_observation)
                    if guidance.intervention_required:
                        raise ValueError("Takeoff intervention: "+guidance.reason)
                    controls = guidance.actuator_frame(snap["controls"]["trim"])
                    if guidance.phase == "climb" and takeoff_observation.agl_ft >= 300:
                        recorder.write("milestone", {"name": "300 ft AGL airborne handoff",
                                                      "frame": snap["frame"],
                                                      "altitude_ft": v["altitude_indicated_ft"]})
                        ground_stage = None
                        controls = controller.step(snap)
            elif args.rollout_only:
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
            else:
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
                print("PROGRESS", json.dumps({"stage": ground_stage or controller.stage,
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
        if retask.thread is not None:
            retask.__exit__(None, None, None)
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
    p.add_argument("--profile", choices=sorted(PROFILES), required=True,
                   help="aircraft profile; C182T tuning is not yet validated")
    p.add_argument("--from-parking", action="store_true")
    a = p.parse_args()
    with ControllerLock():
        return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
