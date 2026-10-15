#!/usr/bin/env python3
"""Attended owner-transfer trial: AI pilot -> GFC 700 -> AI pilot (CAP 487 C182T or C172).

NOT YET FLOWN. Needs a person at the workstation (see docs/GFC700_SECOND_OWNER_2026-10-15.md).

Adopts a PAUSED airborne aircraft inside the mission bridge's region (the same
setup as ai_pilot_pattern.py), then:

  direct1  the AI pilot's CruiseLaw holds heading and altitude                (--direct-s)
  gfc      the bridge hands the airplane to the GFC 700, which turns `--turn-deg`
           and holds altitude, under the terrain guard                         (--gfc-s)
  direct2  the bridge takes the airplane back; a FRESH CruiseLaw holds the new
           heading and altitude                                                (--direct-s)

and scores both hand-overs and the autopilot's capture with OwnerTrialObserver.
Every actuator frame still goes through the expiring, authenticated mission
bridge; any fault pauses the simulator and releases the overrides.

Usage:
    python3 scripts/ai_pilot_owner_trial.py --config <PythonPlugins>/capvsar_flight_control_config.json \
        --output ~/.cache/capvsar/ai-pilot/owner_trial_c182.jsonl --profile C182T
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
from services.ai_pilot.gfc_owner import GfcOwner
from services.ai_pilot.owner_trial import OwnerTrialObserver
from services.ai_pilot.search_patterns import CruiseLaw
from services.ai_pilot.terrain_guard import TerrainGuard
from xplane.capvsar_mission import AIRBORNE_MAX_ALTITUDE_FT
from scripts.ai_pilot_experiment import inventory

CHANNELS = ("roll", "pitch", "yaw", "throttle", "flap", "trim", "brake")
# Slow on purpose. At 2.0 kt/s the first live hand-back mid-climb (ESCON run 4, 2026-10-15) still
# dropped to 90 KIAS: the loop chased a deceleration the climbing airplane could not follow, cut
# power to idle and wound the integrator down. Handed 119.6 KIAS, the command now takes ~50 s to
# reach the 100 KIAS target, so power eases off instead of being cut.
ADOPT_SLEW_KT_S = 0.4


def clamp(x, low, high):
    return max(low, min(high, x))


class Hold:
    """Heading and altitude hold on the primary controls (the AI pilot's cruise law)."""

    def __init__(self, profile, target_true, target_alt, kias, adopt_slew_kt_s=None):
        # Bumpless: the airplane is handed over flying at its own speed and power, so the
        # speed command starts there and the throttle starts where the pilot left it.
        self.law, self.profile = CruiseLaw(profile, adopt_slew_kt_s=adopt_slew_kt_s or ADOPT_SLEW_KT_S), profile
        self.target_true, self.target_alt, self.kias = target_true, target_alt, kias
        self.last_sim = None
        self.trim = None

    def frame(self, snap):
        v = snap["values"]
        sim = v["sim_time_s"]
        dt = .05 if self.last_sim is None else clamp(sim - self.last_sim, .005, .25)
        self.last_sim = sim
        frame, _ = self.law.frame(v, snap["controls"]["trim"], self.target_true, self.target_alt,
                                  self.kias, dt, throttle_in=snap["controls"].get("throttle"))
        return frame


def first_frame(snap, profile):
    """A complete first frame from the measured airplane: neutral yoke, measured power and trim."""
    m = snap["controls"]
    controls = {"roll": 0., "pitch": 0., "yaw": 0.,
                "throttle": clamp(m.get("throttle", .6), .2, 1.), "flap": 0.,
                "trim": clamp(m["trim"], -.6, .6), "brake": 0.}
    if profile.constant_speed_prop:
        controls["prop"] = clamp(m.get("prop", 1.), .5, 1.)
    return controls


def run(args):
    config = json.loads(args.config.read_text())
    if config.get("mode") != "mission" or not config.get("gfc_owner"):
        raise ValueError("Requires a mission session staged with gfc_owner (current stage-mission)")
    profile = PROFILES[args.profile]
    channels = CHANNELS + (("prop",) if profile.constant_speed_prop else ())
    inv = inventory(args.xplane, include_mission=True, profile=args.profile)
    for name, installed in inv["installed_bridge_sha256"].items():
        if installed != inv["source_sha256"]["xplane/" + name]:
            raise ValueError("Installed mission bridge mismatch: " + name)
    inv["runner_sha256"] = digest(Path(__file__))
    manifest = {"purpose": "owner transfer trial: AI pilot -> GFC 700 -> AI pilot",
                "created_utc": datetime.now(timezone.utc).isoformat(), "inventory": inv,
                "parameters": {k: getattr(args, k) for k in ("turn_deg", "direct_s", "gfc_s", "kias")},
                "simulated_clearance": "Self-assigned; no ATC service"}
    recorder = Recorder(args.output, manifest)
    client = BridgeClient(config)
    owner = GfcOwner(client)
    guard = TerrainGuard(ceiling_ft=AIRBORNE_MAX_ALTITUDE_FT - 500)
    observer = OwnerTrialObserver(altitude_ft=0., aircraft_name=profile.acf_name,
                                  require_capture=not args.handback_in_climb,
                                  speed_target_kias=args.kias or profile.search_kias)
    kias = args.kias or profile.search_kias
    result = {"outcome": "FAIL", "reason": "Setup incomplete"}
    guard_log = {}
    session = secrets.token_hex(16)
    samples = 0
    try:
        status = client.request("fault_pause", reason="owner trial setup")
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
                raise ValueError("Readiness not confirmed")
            time.sleep(.1)
        v0 = snap["values"]
        altitude = round(v0["altitude_indicated_ft"] / 10.) * 10.
        observer.altitude_ft = altitude
        hold = Hold(profile, v0["heading_true_deg"], altitude, kias, args.adopt_slew)
        controls = first_frame(snap, profile)
        started = client.request("lab_start", session=session, controls=controls,
                                 snapshot_frame=snap["frame"], snapshot_wall_time_s=snap["wall_time_s"])
        if started["state"] != "ACTIVE":
            raise ValueError("Start not active")
        generation, seq = started["generation"], started["frame_sequence"]
        start_wall = time.monotonic()

        def direct_phase(name, seconds):
            nonlocal seq, samples, snap
            phase_start, previous = None, None
            observer.enter(name, snap)
            while True:
                if time.monotonic() - start_wall > args.max_wall_s:
                    raise ValueError("Wall deadline exceeded")
                seq += 1
                reply = client.request("exchange", session=client_session[0], generation=generation,
                                       sequence=seq, expires_at=time.monotonic() + .18,
                                       controls=frame_now[0])
                if reply["bridge"]["state"] != "ACTIVE":
                    raise ValueError("Bridge lost authority in %s" % name)
                snap = reply["snapshot"]
                if snap is None or snap["frame"] == previous:
                    time.sleep(.005)
                    continue
                previous = snap["frame"]
                if snap["values"]["paused"]:
                    if time.monotonic() - start_wall < .2:
                        continue
                    raise ValueError("Simulator paused in " + name)
                samples += 1
                bad = observer.observe(snap)
                if bad:
                    raise ValueError(bad)
                if samples % 5 == 0:
                    recorder.write("snapshot", {**snap, "trial_phase": name})
                sim = snap["values"]["sim_time_s"]
                phase_start = sim if phase_start is None else phase_start
                if sim - phase_start >= seconds:
                    return
                advice = apply_guard(snap)
                if advice is not None and advice.turn_back:
                    raise ValueError("Terrain guard: " + advice.reason)
                hold.target_alt = observer.altitude_ft
                frame_now[0] = {k: float(v) for k, v in hold.frame(snap).items() if k in channels}

        snapshot_owner = ["DIRECT"]
        guard_log = {"events": 0, "max_floor_ft": None, "min_clearance_ft": None, "said": "",
                     "min_agl_ft": None, "closest": None, "crest": None}

        def apply_guard(snapshot, advice=None):
            """The executive's terrain guard, applied to whoever owns the airplane: the
            observer scores against the floor-adjusted altitude and waives only altitude.
            Pass the advice already computed this frame (GfcOwner.step does); the guard is
            stateful and a second update would swallow the event that raised the floor."""
            advice = advice or guard.update(snapshot)
            target = guard.apply_to_altitude(altitude, advice)
            observer.altitude_ft = target
            observer.terrain_override = target > altitude
            if advice.floor_indicated_ft is not None:
                top = guard_log["max_floor_ft"]
                guard_log["max_floor_ft"] = advice.floor_indicated_ft if top is None else max(top, advice.floor_indicated_ft)
            if advice.clearance_ft is not None:
                low = guard_log["min_clearance_ft"]
                guard_log["min_clearance_ft"] = advice.clearance_ft if low is None else min(low, advice.clearance_ft)
            terrain = snapshot.get("terrain")
            if terrain and terrain.get("under_valid"):
                agl = snapshot["values"]["altitude_msl_m"] / .3048 - terrain["under_ft"]
                low = guard_log["min_agl_ft"]
                guard_log["min_agl_ft"] = agl if low is None else min(low, agl)
            if terrain and terrain.get("under_valid"):
                # The highest ground the airplane actually flew over, and how high it was there.
                if guard_log["crest"] is None or terrain["under_ft"] > guard_log["crest"]["ground_ft"]:
                    guard_log["crest"] = {"ground_ft": terrain["under_ft"],
                                          "altitude_msl_ft": snapshot["values"]["altitude_msl_m"] / .3048,
                                          "lat": snapshot["values"]["latitude_deg"],
                                          "lon": snapshot["values"]["longitude_deg"],
                                          "owner": snapshot_owner[0]}
            if terrain and terrain.get("valid") and terrain["ahead_max_nm"] <= 1.5:
                # Over or nearly over the highest ground in the scan: the crossing itself.
                clearance = snapshot["values"]["altitude_msl_m"] / .3048 - terrain["ahead_max_ft"]
                if guard_log["closest"] is None or clearance < guard_log["closest"]["clearance_ft"]:
                    guard_log["closest"] = {"clearance_ft": clearance, "ground_ft": terrain["ahead_max_ft"],
                                            "ground_nm": terrain["ahead_max_nm"],
                                            "lon": snapshot["values"]["longitude_deg"],
                                            "lat": snapshot["values"]["latitude_deg"],
                                            "owner": snapshot_owner[0]}
            if advice.reason and advice.reason != guard_log["said"]:
                guard_log["said"] = advice.reason
                guard_log["events"] += 1
                print("GUARD", advice.reason, flush=True)
                recorder.write("guard", {"frame": snapshot["frame"], "reason": advice.reason,
                                         "floor_ft": advice.floor_indicated_ft})
            return advice

        client_session, frame_now = [session], [controls]
        direct_phase("direct1", args.direct_s)

        # ---- DIRECT -> GFC 700 -------------------------------------------------
        v = snap["values"]
        target_true = (v["heading_true_deg"] + args.turn_deg) % 360
        target_mag = (v["heading_mag_deg"] + args.turn_deg) % 360
        observer.enter("gfc", snap, heading_target_true=target_true)
        snapshot_owner[0] = "GFC700"
        owner.engage(heading_mag=target_mag, altitude_ft=altitude)
        recorder.write("handover", {"to": "GFC700", "frame": snap["frame"], "heading_mag": target_mag,
                                    "altitude_ft": altitude})
        gfc_start, previous, climb_since = None, None, None
        while True:
            if time.monotonic() - start_wall > args.max_wall_s:
                raise ValueError("Wall deadline exceeded")
            snap = client.request("snapshot")
            if snap["frame"] == previous:
                time.sleep(.005)
                continue
            previous = snap["frame"]
            samples += 1
            bad = observer.observe(snap)
            if bad:
                raise ValueError(bad)
            advice = owner.step(snap, heading_mag=target_mag, altitude_ft=altitude, guard=guard)
            advice = apply_guard(snap, advice)
            if advice is not None and advice.turn_back:
                raise ValueError("Terrain guard: " + advice.reason)
            if samples % 5 == 0:
                recorder.write("snapshot", {**snap, "trial_phase": "gfc"})
            sim = snap["values"]["sim_time_s"]
            gfc_start = sim if gfc_start is None else gfc_start
            if args.handback_in_climb:
                # Take the airplane back part-way up the guard's climb, at climb speed and power:
                # the case the bumpless hand-back exists for.
                if observer.terrain_override and snap["values"]["vvi_fpm"] > 500:
                    climb_since = sim if climb_since is None else climb_since
                    if sim - climb_since >= args.handback_in_climb:
                        break
            elif sim - gfc_start >= args.gfc_s and observer.captured:
                break
            if sim - gfc_start >= args.gfc_s * 2:
                raise ValueError("GFC 700 did not capture the heading and altitude")

        # ---- GFC 700 -> DIRECT -------------------------------------------------
        controls = first_frame(snap, profile)
        new_session, generation, seq = owner.hand_back(controls)
        client_session[0], frame_now[0] = new_session, controls
        snapshot_owner[0] = "DIRECT"
        recorder.write("handover", {"to": "DIRECT", "session": new_session})
        v = snap["values"]
        hold = Hold(profile, v["heading_true_deg"], observer.altitude_ft, kias, args.adopt_slew)   # fresh integrators
        direct_phase("direct2", args.direct2_s or args.direct_s)
        result = {**observer.report(), "samples": samples, "terrain_guard": guard_log}
    except BaseException as error:
        result = {**observer.report(), "outcome": "FAIL", "reason": str(error) or type(error).__name__,
                  "samples": samples, "terrain_guard": guard_log}
        recorder.write("intervention", result)
    finally:
        try:
            status = client.request("fault_pause", reason="owner trial ended")
            deadline = time.monotonic() + 2
            while not status["pause_confirmed"] and time.monotonic() < deadline:
                time.sleep(.03)
                status = client.request("status")
            end = client.request("snapshot")
            result["end"] = {"status": status, "values": end["values"]}
            # A fault pauses the simulator and releases the actuator overrides. It does NOT drop
            # the autopilot: if the GFC 700 owns the airplane it keeps flying it when the sim is
            # un-paused, which is safer than free flight (ARDUPLANE_TRIAL F1).
            result["end_autopilot_engaged"] = end["ap_engaged"]
            if not status["pause_confirmed"] or end["override_state"] is not False:
                result["outcome"] = "FAIL"
                result["containment_error"] = "Pause/override release not confirmed"
        except Exception as error:
            result["outcome"] = "FAIL"
            result["containment_error"] = str(error)
        recorder.write("end", result)
        recorder.close()
    print("RESULT", json.dumps({k: result.get(k) for k in ("outcome", "reason", "samples", "captured")}
                               | {"trace": str(args.output)}), flush=True)
    print(json.dumps(result.get("phases"), indent=1), flush=True)
    return 0 if result["outcome"] == "PASS" else 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--xplane", type=Path, default=Path.home() / "X-Plane 12")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--profile", choices=sorted(PROFILES), default="C182T")
    p.add_argument("--turn-deg", type=float, default=20.)
    p.add_argument("--direct-s", type=float, default=60.)
    p.add_argument("--gfc-s", type=float, default=90.)
    p.add_argument("--handback-in-climb", type=float, default=None, metavar="SECONDS",
                   help="end the GFC 700 phase this many seconds into the guard's climb, mid-climb, "
                        "instead of waiting for capture at level")
    p.add_argument("--adopt-slew", type=float, default=None, metavar="KT_PER_S",
                   help="speed-command slew after a hand-back (default %.1f); the A/B knob for the "
                        "performance-table feed-forward" % ADOPT_SLEW_KT_S)
    p.add_argument("--direct2-s", type=float, default=None,
                   help="length of the final AI-pilot phase (default: --direct-s)")
    p.add_argument("--kias", type=float, default=None)
    p.add_argument("--max-wall-s", type=float, default=900.)
    a = p.parse_args()
    if not 5 <= abs(a.turn_deg) <= 60:
        p.error("turn must be 5-60 degrees")
    with ControllerLock():
        return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
