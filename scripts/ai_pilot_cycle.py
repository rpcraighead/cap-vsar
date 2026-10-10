#!/usr/bin/env python3
"""Bounded stock-C172 qualification runner; every attempt produces evidence."""
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
from services.ai_pilot.experiment import BridgeClient, CycleObserver, Recorder, Scenario, digest, score_trace
from services.ai_pilot.snapshot_controller import SnapshotController
from scripts.ai_pilot_experiment import inventory


def run(args):
    config = json.loads(args.config.read_text())
    if config.get("mode") != "qualification":
        raise ValueError("Requires an expiring stock-C172 qualification installation")
    client = BridgeClient(config)
    scenario = Scenario()
    inv = inventory(args.xplane)
    inv["controller_sha256"] = {name: digest(ROOT / "services/ai_pilot" / name)
                                 for name in ("snapshot_controller.py", "direct_backend.py")}
    inv["runner_sha256"] = digest(Path(__file__))
    manifest = {"purpose": "fault-probe" if args.fault_probe else "scored-cycle", "created_utc": datetime.now(timezone.utc).isoformat(),
                "scenario": scenario.manifest(), "inventory": inv,
                "entry": {"heading_offset": args.heading_offset, "altitude_offset": args.altitude_offset,
                          "speed_offset": args.speed_offset}, "qualification_only": True}
    recorder = Recorder(args.output, manifest)
    observer = CycleObserver(scenario)
    result = {"outcome": "FAIL", "reason": "Setup incomplete"}
    seq = 0
    session = secrets.token_hex(16)
    generation = 0
    def frame(controls):
        nonlocal seq
        seq += 1
        return dict(session=session, generation=generation, sequence=seq,
                    expires_at=time.monotonic() + .18, controls=controls)
    try:
        for name, value in inv["installed_bridge_sha256"].items():
            if value != inv["source_sha256"]["xplane/" + name]:
                raise ValueError("Installed bridge mismatch: " + name)
        client.request("fault_pause", reason="Qualification setup between trials")
        deadline = time.monotonic() + 3
        while not client.request("status")["pause_confirmed"]:
            if time.monotonic() > deadline:
                raise ValueError("Setup pause not confirmed")
            time.sleep(.05)
        reset = client.request("lab_reset", session=session, **manifest["entry"])
        recorder.write("setup", reset)
        deadline = time.monotonic() + 15
        while True:
            try:
                s = client.request("snapshot")
                v = s["values"]
                ready = (s["session"] == session and v["paused"] == 1
                         and all(abs(v[f"local_{axis}_m"] - value) < 1
                                 for axis, value in zip("xyz", reset["local_position_m"]))
                         and abs(v["payload_kg"] - 170) < 1 and abs(v["fuel_kg"] - 100) < 1
                         and v["wind_mps"] < .5 and v["sim_speed"] in (0, 1)
                         and s["override_state"] is False and s["ap_engaged"] is False)
                recorder.write("setup_snapshot", s)
                if ready:
                    break
            except (RuntimeError, OSError):
                pass
            if time.monotonic() > deadline:
                raise ValueError("Reset readiness not established in 15 seconds")
            time.sleep(.1)
        controls = dict(s["controls"])
        client.request("submit_frame", **frame(controls))
        prepared = client.request("prepare", owner="DIRECT", session=session, expected_generation=0)
        generation = prepared["generation"]
        client.request("submit_frame", **frame(controls))
        client.request("activate", session=session, generation=generation)
        client.request("lab_resume")
        controller = SnapshotController(config["aircraft_path"], session)
        started = time.monotonic()
        deadline = started + scenario.wall_deadline_s
        previous_frame = None
        while time.monotonic() < deadline:
            response = client.request("exchange", **frame(controls))
            if response["bridge"]["state"] != "ACTIVE":
                raise ValueError("Bridge lost active authority")
            s = response["snapshot"]
            if s is None or s["frame"] == previous_frame:
                time.sleep(.01)
                continue
            if s["values"]["paused"] and time.monotonic() - started < .2:
                continue
            previous_frame = s["frame"]
            if observer.samples == 0 and s["values"]["kias"] < 80 and time.monotonic() - started < 2:
                recorder.write("setup_snapshot", s)
                time.sleep(.02)
                continue
            recorder.write("snapshot", s)
            report = observer.observe(s)
            if report["outcome"] != "INCOMPLETE":
                result = report
                break
            if args.fault_probe and report["phase"] == "maneuver":
                recorder.write("intervention", {"expected_probe": args.fault_probe})
                if args.fault_probe == "loss":
                    time.sleep(.35)  # No heartbeat or candidate frames.
                    status = client.request("status")
                    state = client.request("snapshot")
                    assert status["retired"] and status["pause_confirmed"]
                    assert state["override_state"] is False and state["values"]["paused"] == 1
                else:
                    status = client.request("human_takeover", reason="Qualification takeover injection")
                    state = client.request("snapshot")
                    assert status["retired"] and status["state"] == "MANUAL"
                    assert state["override_state"] is False and state["ap_engaged"] is False
                try:
                    client.request("submit_frame", **frame(controls))
                except RuntimeError as error:
                    rejection = str(error)
                else:
                    raise ValueError("Retired writer was accepted")
                result = {"outcome": "PROBE_PASS", "probe": args.fault_probe,
                          "bridge": status, "snapshot": state, "retired_rejection": rejection}
                break
            if not s["values"]["engine_running"] or s["values"]["wind_mps"] > .5:
                raise ValueError("Engine or fixed-weather readiness lost")
            controls = controller.step(s, observer.target, time.monotonic())
            recorder.write("command", {"source_frame": s["frame"], "target": observer.target,
                                        "controls": controls, "diagnostics": controller.backend.last_commands})
            time.sleep(.055)
        else:
            raise ValueError("Trial wall deadline exceeded")
    except BaseException as error:
        recorder.write("intervention", {"error": type(error).__name__, "reason": str(error)})
        result = {"outcome": "FAIL", "reason": str(error), "observer": observer.report()}
    finally:
        try:
            status = client.request("fault_pause", reason="Qualification trial ended")
            pause_deadline = time.monotonic() + 2
            while not status["pause_confirmed"] and time.monotonic() < pause_deadline:
                time.sleep(.03)
                status = client.request("status")
            result["end_bridge"] = status
            if not status["pause_confirmed"]:
                raise RuntimeError("Final pause not confirmed")
        except Exception as error:
            result["containment_error"] = str(error)
            recorder.write("intervention", {"containment_error": str(error)})
            result["outcome"] = "FAIL"
        recorder.write("end", result)
        recorder.close()
    measured = score_trace(args.output) if not args.fault_probe else {"outcome": "NOT_A_SCORED_FLIGHT"}
    summary = ({k: result.get(k) for k in ("outcome", "probe", "reason", "end_bridge")}
               if args.fault_probe else result)
    print(json.dumps({"runner": summary, "independent_score": measured, "trace": str(args.output)}, indent=2))
    return 0 if measured["outcome"] == "PASS" or result["outcome"] == "PROBE_PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--xplane", type=Path, default=Path.home() / "X-Plane 12")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--heading-offset", type=float, default=0)
    parser.add_argument("--altitude-offset", type=float, default=0)
    parser.add_argument("--speed-offset", type=float, default=0)
    parser.add_argument("--fault-probe", choices=("loss", "takeover"))
    args = parser.parse_args()
    with ControllerLock():
        return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
