"""Run a predeclared, trace-backed sequence of KMYF direct-crosswind landings."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_ledger(path: Path, ledger: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(ledger, indent=2) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--mode", choices=("direct15", "random90"), required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, default=20261010)
    parser.add_argument("--stop-on-fail", action="store_true")
    args = parser.parse_args()
    if args.count < 1:
        parser.error("count must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = args.output_dir / f"{args.label}-ledger.json"
    if ledger_path.exists():
        parser.error(f"ledger already exists: {ledger_path}")
    rng = random.Random(args.seed)
    if args.mode == "direct15":
        plan = [{"wind_speed_kt": 15., "wind_from_offset_deg": -90. if i % 2 == 0 else 90.}
                for i in range(args.count)]
    else:
        plan = [{"wind_speed_kt": round(rng.uniform(4., 15.), 2),
                 "wind_from_offset_deg": rng.choice((-90., 90.))}
                for _ in range(args.count)]
    ledger = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode, "seed": args.seed, "label": args.label,
        "source_sha256": {
            "controller": digest(ROOT / "services/ai_pilot/landing_trial.py"),
            "runner": digest(ROOT / "scripts/ai_pilot_landing.py"),
            "lab": digest(ROOT / "xplane/capvsar_landing.py"),
        },
        "plan": plan, "results": [],
    }
    write_ledger(ledger_path, ledger)
    for i, entry in enumerate(plan, 1):
        trace = args.output_dir / f"{args.label}-{i:02d}.jsonl"
        command = [sys.executable, str(ROOT / "scripts/ai_pilot_landing.py"), "fly",
                   "--config", str(args.config), "--output", str(trace),
                   "--wind-speed-kt", str(entry["wind_speed_kt"]),
                   "--wind-from-offset-deg", str(entry["wind_from_offset_deg"])]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        try:
            report = json.loads(completed.stdout)
            score = report.get("independent_score", {})
        except json.JSONDecodeError:
            score = {"outcome": "ERROR", "reason": completed.stdout[-1000:] or completed.stderr[-1000:]}
        result = {"trial": i, **entry, "exit_code": completed.returncode,
                  "outcome": score.get("outcome"), "reason": score.get("reason"),
                  "threshold": score.get("threshold"), "touchdown": score.get("touchdown"),
                  "last": score.get("last"), "trace": str(trace),
                  "trace_sha256": digest(trace) if trace.exists() else None}
        ledger["results"].append(result)
        write_ledger(ledger_path, ledger)
        print(json.dumps({"trial": i, "wind": entry, "outcome": result["outcome"],
                          "reason": result["reason"], "touchdown": result["touchdown"] and
                          {k: result["touchdown"][k] for k in ("along_m", "cross_m", "pre_touch_pitch_deg")}}),
              flush=True)
        if args.stop_on_fail and result["outcome"] != "PASS":
            return 1
    return 0 if all(r["outcome"] == "PASS" for r in ledger["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
