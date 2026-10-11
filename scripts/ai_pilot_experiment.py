#!/usr/bin/env python3
"""Observe the stock C172 or independently score a recorded cycle.

This first harness has no actuator or simulator-reset commands. Raw traces and
machine inventory live outside Git. The observer cannot qualify flight control.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import os
import secrets
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.ai_pilot.experiment import BridgeClient, Recorder, Scenario, digest, score_trace
from services.ai_pilot.control_ownership import ControllerLock


def inventory(xplane, include_landing=False, include_surface=False):
    aircraft = xplane / "Aircraft/Laminar Research/Cessna 172 SP/Cessna_172SP_G1000.acf"
    plugins = xplane / "Resources/plugins/PythonPlugins"
    def git(*args):
        return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()
    names = (
        "PI_capvsar_flight_control.py", "capvsar_flight_control_core.py",
        "capvsar_flight_control_mapping.py", "capvsar_telemetry.py", "capvsar_qualification.py")
    sources = [ROOT / "xplane" / name for name in names]
    if include_landing:
        sources.append(ROOT / "xplane/capvsar_landing.py")
    if include_surface:
        sources.append(ROOT / "xplane/capvsar_surface.py")
    installed = [plugins / path.name for path in sources]
    return {
        "repository": str(ROOT), "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sources + [Path(__file__), ROOT / "services/ai_pilot/experiment.py"]},
        "installed_bridge_sha256": {p.name: digest(p) if p.exists() else None for p in installed},
        "aircraft": {"path": str(aircraft), "sha256": digest(aircraft)},
        "scenery_packs_sha256": digest(xplane / "Custom Scenery/scenery_packs.ini"),
        "preferences_sha256": {
            name: digest(xplane / "Output/preferences" / name)
            if (xplane / "Output/preferences" / name).exists() else None
            for name in ("X-Plane.prf", "X-Plane Window Positions.prf", "Freeflight.prf")},
        "python": sys.version, "platform": platform.platform(),
        "plugins": sorted(p.name for p in (xplane / "Resources/plugins").iterdir()),
        "python_plugins": sorted(p.name for p in plugins.glob("PI_*.py")),
    }


def stage_observer(destination, qualification_aircraft=None, mode="qualification",
                   runway="KMYF 28R"):
    """Stage an explicit observation or expiring laboratory installation."""
    if qualification_aircraft is not None:
        from xplane.capvsar_qualification import STOCK_NAME, STOCK_SHA256
        qualification_aircraft = qualification_aircraft.resolve()
        if qualification_aircraft.name != STOCK_NAME or digest(qualification_aircraft) != STOCK_SHA256:
            raise ValueError("Qualification requires the pinned stock C172 G1000")
    destination.mkdir(parents=True, exist_ok=False)
    names = ("PI_capvsar_flight_control.py", "capvsar_flight_control_core.py",
             "capvsar_flight_control_mapping.py", "capvsar_telemetry.py", "capvsar_qualification.py")
    extras = (("capvsar_landing.py",) if mode == "landing" else
              ("capvsar_surface.py",) if mode == "surface" else ())
    for name in names + extras:
        shutil.copy2(ROOT / "xplane" / name, destination / name)
    session = secrets.token_hex(16)
    config = {"mode": "observe", "protocol": "atomic-v1", "session": session,
              "secret": secrets.token_hex(32),
              "socket_path": f"/tmp/capvsar-flight-control-{session}.sock"}
    if qualification_aircraft is not None:
        config.update(mode=mode, aircraft_path=str(qualification_aircraft),
                      expires_unix_s=time.time() + (10800 if mode in ("landing", "surface") else 3600))
        if mode == "landing":
            from xplane.capvsar_landing import RUNWAYS
            if runway not in RUNWAYS:
                raise ValueError("Unknown landing runway: " + runway)
            config["runway"] = runway
        if mode == "surface":
            config["parking"] = "KSEE East Transient Parking 12"
    fd = os.open(destination / "capvsar_flight_control_config.json",
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(config, stream, indent=2)
    print(str(destination))


def observe(args):
    config = json.loads(args.config.read_text())
    if config.get("mode") != "observe":
        raise ValueError("This harness requires the read-only observe configuration")
    client = BridgeClient(config)
    with ControllerLock():
        manifest = {"purpose": "telemetry-qualification", "created_utc": datetime.now(timezone.utc).isoformat(),
                    "session": config["session"], "inventory": inventory(args.xplane),
                    "telemetry": client.request("manifest"),
                    "criteria_status": "No flight scoring; read-only readiness trial"}
        inv = manifest["inventory"]
        for name, installed_hash in inv["installed_bridge_sha256"].items():
            if installed_hash != inv["source_sha256"]["xplane/" + name]:
                raise ValueError("Installed bridge differs from tested source: " + name)
        recorder = Recorder(args.output, manifest)
        samples, duplicates, max_age, max_gap = 0, 0, 0.0, 0.0
        previous = None
        end = time.monotonic() + args.seconds
        result = {"outcome": "FAIL"}
        try:
            while time.monotonic() < end:
                snap = client.request("snapshot")
                if (snap["session"] != config["session"] or snap["aircraft"]["path"] != inv["aircraft"]["path"]
                        or snap["aircraft"]["name"] != Scenario().aircraft_name):
                    raise ValueError("Unexpected aircraft or session")
                if snap["age_s"] < 0 or snap["age_s"] > 0.5:
                    raise ValueError("Stale telemetry snapshot")
                if snap["override_state"] is not False:
                    raise ValueError("External control override present during observation")
                if previous:
                    if snap["frame"] == previous["frame"]:
                        duplicates += 1
                        time.sleep(0.02)
                        continue
                    if snap["frame"] < previous["frame"] or snap["wall_time_s"] <= previous["wall_time_s"]:
                        raise ValueError("Snapshot identity regressed")
                    max_gap = max(max_gap, snap["wall_time_s"] - previous["wall_time_s"])
                    if max_gap > 0.5:
                        raise ValueError("Snapshot gap exceeds readiness criterion")
                recorder.write("snapshot", snap)
                samples += 1
                max_age = max(max_age, snap["age_s"])
                previous = snap
                time.sleep(0.08)
            if samples < 10:
                raise ValueError("Insufficient telemetry for readiness trial")
            result = {"outcome": "OBSERVATION_PASS", "samples": samples, "duplicates_skipped": duplicates,
                      "max_age_s": max_age, "max_wall_gap_s": max_gap,
                      "flight_control_qualified": False}
        except BaseException as error:
            result = {"outcome": "FAIL", "reason": str(error), "samples": samples}
            raise
        finally:
            recorder.write("end", result)
            recorder.close()
            print(json.dumps({**result, "trace": str(args.output)}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("observe")
    read.add_argument("--config", type=Path, required=True)
    read.add_argument("--xplane", type=Path, default=Path.home() / "X-Plane 12")
    read.add_argument("--output", type=Path, required=True)
    read.add_argument("--seconds", type=float, default=30)
    score = commands.add_parser("score")
    score.add_argument("trace", type=Path)
    stage = commands.add_parser("stage-observer")
    stage.add_argument("destination", type=Path)
    qualify = commands.add_parser("stage-qualification")
    qualify.add_argument("destination", type=Path)
    qualify.add_argument("--aircraft", type=Path, required=True)
    landing = commands.add_parser("stage-landing")
    landing.add_argument("destination", type=Path)
    landing.add_argument("--aircraft", type=Path, required=True)
    landing.add_argument("--runway", choices=("KMYF 28R", "KSAN 27"), default="KMYF 28R")
    surface = commands.add_parser("stage-surface")
    surface.add_argument("destination", type=Path)
    surface.add_argument("--aircraft", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "observe":
        if not 2 <= args.seconds <= 600:
            parser.error("Observation duration must be 2–600 seconds")
        observe(args)
    elif args.command == "score":
        result = score_trace(args.trace)
        print(json.dumps(result, indent=2))
        return 0 if result["outcome"] == "PASS" else 1
    else:
        stage_observer(args.destination, args.aircraft if args.command in ("stage-qualification", "stage-landing", "stage-surface") else None,
                       mode="landing" if args.command == "stage-landing" else "surface" if args.command == "stage-surface" else "qualification",
                       runway=args.runway if args.command == "stage-landing" else "KMYF 28R")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
