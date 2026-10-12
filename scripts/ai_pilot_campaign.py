#!/usr/bin/env python3
"""Run and independently report a frozen C172 qualification campaign."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.ai_pilot.experiment import digest, score_trace

ENTRIES = ROOT / "services/ai_pilot/qualification_entries.json"
CHANNEL_LIMITS = {"roll": (-.35, .35), "pitch": (-.4, .4), "yaw": (-.35, .35),
                  "throttle": (.15, 1.0), "flap": (0.0, 0.0), "trim": (-.6, .6)}


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def plan() -> list[dict]:
    declared = json.loads(ENTRIES.read_text())
    if declared["schema"] != "capvsar.qualification-entries.v1" or declared["baseline_repetitions"] != 10:
        raise ValueError("Unexpected qualification plan")
    disturbed = declared["disturbed_entries"]
    if len(disturbed) != 10 or len({item["name"] for item in disturbed}) != 10:
        raise ValueError("Expected ten distinct disturbed entries")
    zero = {"heading_offset": 0, "altitude_offset": 0, "speed_offset": 0}
    return [{"name": f"baseline_{n:02d}", **zero} for n in range(1, 11)] + disturbed


def run(args) -> int:
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.config.read_text())
    if config.get("mode") != "qualification":
        raise ValueError("Fresh qualification configuration required")
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip()
    if dirty:
        raise ValueError("Commit the frozen source before running the campaign")
    frozen = {str(p.relative_to(ROOT)): digest(p) for p in
              [Path(__file__), ROOT / "scripts/ai_pilot_cycle.py",
               ROOT / "services/ai_pilot/experiment.py", ROOT / "services/ai_pilot/snapshot_controller.py",
               ROOT / "services/ai_pilot/direct_backend.py", ENTRIES]}
    ledger = {"schema": "capvsar.ai-pilot-campaign.v1", "created_utc": datetime.now(timezone.utc).isoformat(),
              "commit": head, "source_sha256": frozen, "plan_sha256": digest(ENTRIES),
              "aircraft_path": config["aircraft_path"], "attempts": []}
    save(directory / "campaign.json", ledger)
    for entry in plan():
        if any(digest(ROOT / name) != value for name, value in frozen.items()):
            raise RuntimeError("Frozen source changed during campaign")
        name = entry["name"]
        trace = directory / f"{name}.jsonl"
        command = [sys.executable, str(ROOT / "scripts/ai_pilot_cycle.py"),
                   "--config", str(args.config), "--output", str(trace)]
        for field in ("heading", "altitude", "speed"):
            command.extend([f"--{field}-offset", str(entry[f"{field}_offset"])])
        with (directory / f"{name}.stdout.txt").open("x") as output:
            try:
                proc = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                      timeout=args.process_timeout_s, check=False)
                exit_code, startup_error = proc.returncode, None
            except (OSError, subprocess.TimeoutExpired) as error:
                exit_code, startup_error = None, f"{type(error).__name__}: {error}"
                output.write(startup_error + "\n")
        score = score_trace(trace) if trace.is_file() else {"outcome": "NO_TRACE", "reason": startup_error or "Runner exited before trace creation"}
        attempt = {"name": name, "entry": entry, "exit_code": exit_code,
                   "startup_error": startup_error, "trace": trace.name if trace.is_file() else None,
                   "trace_sha256": digest(trace) if trace.is_file() else None,
                   "independent_score": score}
        ledger["attempts"].append(attempt)
        save(directory / "campaign.json", ledger)
        print(f"{name}: {score['outcome']} (exit {exit_code})", flush=True)
    ledger["finished_utc"] = datetime.now(timezone.utc).isoformat()
    save(directory / "campaign.json", ledger)
    return 0 if all(a["independent_score"]["outcome"] == "PASS" and a["exit_code"] == 0
                    for a in ledger["attempts"]) else 1


def trace_metrics(path: Path) -> dict:
    score = score_trace(path)
    snapshots, commands, interventions, end = [], [], [], None
    with path.open() as stream:
        for line in stream:
            record = json.loads(line)
            kind, payload = record["kind"], record["payload"]
            if kind == "snapshot": snapshots.append(payload)
            elif kind == "command": commands.append(payload["controls"])
            elif kind == "intervention": interventions.append(payload)
            elif kind == "end": end = payload
    gaps = [b["wall_time_s"] - a["wall_time_s"] for a, b in zip(snapshots, snapshots[1:])]
    phase_names = ("establish", "maneuver", "recover")
    transitions = score.get("transitions", [])
    capture = {}
    if snapshots:
        start = snapshots[0]["values"]["sim_time_s"]
        for index, transition in enumerate(transitions):
            capture[phase_names[index]] = round(transition["sim_time_s"] - start, 3)
    errors = {name: {"heading_max_deg": 0.0, "altitude_max_ft": 0.0, "airspeed_max_kt": 0.0}
              for name in phase_names}
    phase = 0
    for snapshot in snapshots:
        while phase < len(transitions) and snapshot["frame"] > transitions[phase]["frame"]:
            phase += 1
        if phase >= 3: break
        v = snapshot["values"]
        target_heading = 110 if phase == 1 else 90
        e = errors[phase_names[phase]]
        e["heading_max_deg"] = max(e["heading_max_deg"], abs((v["heading_mag_deg"] - target_heading + 180) % 360 - 180))
        e["altitude_max_ft"] = max(e["altitude_max_ft"], abs(v["altitude_indicated_ft"] - 4500))
        e["airspeed_max_kt"] = max(e["airspeed_max_kt"], abs(v["kias"] - 100))
    saturated = {channel: 0 for channel in CHANNEL_LIMITS}
    for command in commands:
        for channel, (lo, hi) in CHANNEL_LIMITS.items():
            if channel != "flap" and (math.isclose(command[channel], lo, abs_tol=1e-4)
                                      or math.isclose(command[channel], hi, abs_tol=1e-4)):
                saturated[channel] += 1
    bridge = (end or {}).get("end_bridge") or {}
    return {"score": score, "samples": len(snapshots), "capture_elapsed_sim_s": capture,
            "tracking_max_by_phase": errors, "max_telemetry_wall_gap_s": max(gaps, default=None),
            "saturation_frames": saturated, "command_frames": len(commands),
            "interventions": interventions,
            "terminal": {"runner_outcome": (end or {}).get("outcome"), "bridge_state": bridge.get("state"),
                         "owner": bridge.get("owner"), "pause_confirmed": bridge.get("pause_confirmed"),
                         "retired": bridge.get("retired")}}


def report(args) -> int:
    directory = args.directory.resolve()
    ledger = json.loads((directory / "campaign.json").read_text())
    expected = plan()
    if ledger["schema"] != "capvsar.ai-pilot-campaign.v1": raise ValueError("Wrong ledger schema")
    results = []
    for index, entry in enumerate(expected):
        if index >= len(ledger["attempts"]):
            results.append({"name": entry["name"], "outcome": "NOT_RUN"})
            continue
        attempt = ledger["attempts"][index]
        if attempt["entry"] != entry: raise ValueError("Attempt differs from declared plan")
        result = {"name": entry["name"], "entry": entry, "exit_code": attempt["exit_code"]}
        if attempt["trace"]:
            trace = directory / attempt["trace"]
            if digest(trace) != attempt["trace_sha256"]: raise ValueError("Trace hash changed: " + trace.name)
            result.update(trace_metrics(trace))
            result["outcome"] = result["score"]["outcome"]
            result["trace_sha256"] = attempt["trace_sha256"]
        else:
            result["outcome"] = "NO_TRACE"
            result["startup_error"] = attempt["startup_error"]
        results.append(result)
    passed = sum(r["outcome"] == "PASS" and r.get("exit_code") == 0 and
                 r.get("terminal", {}).get("pause_confirmed") is True for r in results)
    summary = {"schema": "capvsar.ai-pilot-campaign-report.v1", "commit": ledger["commit"],
               "plan_sha256": ledger["plan_sha256"], "attempts": len(ledger["attempts"]),
               "passed_with_confirmed_pause": passed, "required": len(expected),
               "outcome": "PASS" if passed == len(expected) else "FAIL", "results": results}
    save(directory / "report.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    return 0 if summary["outcome"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--config", type=Path, required=True)
    run_parser.add_argument("--directory", type=Path, required=True)
    run_parser.add_argument("--process-timeout-s", type=int, default=620)
    report_parser = commands.add_parser("report")
    report_parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    return run(args) if args.command == "run" else report(args)


if __name__ == "__main__":
    raise SystemExit(main())
