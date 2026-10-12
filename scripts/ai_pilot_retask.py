#!/usr/bin/env python3
"""Give the running KSEE–KMYF test pilot a simulated vector without pausing."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.ai_pilot.mission_retask import send_retask


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    sub = p.add_subparsers(dest="kind", required=True)
    direct = sub.add_parser("direct")
    direct.add_argument("fix", choices=["BAKEL"])
    direct.add_argument("--altitude-ft", type=float, required=True)
    heading = sub.add_parser("heading")
    heading.add_argument("heading_mag_deg", type=float)
    heading.add_argument("--altitude-ft", type=float, required=True)
    altitude = sub.add_parser("altitude")
    altitude.add_argument("altitude_ft", type=float)
    args = p.parse_args()
    config = json.loads(args.config.read_text())
    if config.get("mode") != "mission":
        p.error("An active mission configuration is required")
    task = {"kind": args.kind}
    if args.kind == "direct":
        task.update(fix=args.fix, altitude_ft=args.altitude_ft)
    elif args.kind == "heading":
        task.update(heading_mag_deg=args.heading_mag_deg, altitude_ft=args.altitude_ft)
    else:
        task["altitude_ft"] = args.altitude_ft
    result = send_retask(config["socket_path"]+"-retask", config["secret"], task)
    print(json.dumps(result, indent=2))
    return 0 if result.get("accepted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
