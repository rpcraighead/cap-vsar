#!/usr/bin/env python3
"""Turn a perf_table_sweep.py JSON into the `[performance]` table of an aircraft profile.

Only points that SETTLED are used: a point abandoned at the envelope edge (below 75 or above 138 KIAS) or
one that timed out without the airspeed settling says nothing about steady flight. Each point is labelled
with the vertical speed the autopilot was asked to hold, and its airspeed is the mean of the last eight
seconds. The table is validated by the same code that loads it (monotonic, enough points, tagged with the
aircraft-file hash), and `--write` replaces any existing `[performance]` table in the profile file.

Usage:
    python3 scripts/perf_table_to_toml.py ~/.cache/capvsar/measurements/perf_table_C182T_t1.json \
        --evidence docs/evidence/c182t-2026-10-15/perf_table_C182T_t1.json --write
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.ai_pilot.performance import PerformanceTable      # noqa: E402
from services.ai_pilot.profile_loader import PROFILE_DIR, load_profile   # noqa: E402

PROFILE_FILES = {"C172SP": "c172sp.toml", "C182T": "c182t.toml"}


def build(log, evidence):
    points = [(p["throttle"], p["target_vvi_fpm"], round(p["kias"], 1))
              for p in log["points"] if p["outcome"] == "settled"]
    mass = [p["mass"] for p in log["points"]]
    points_full = [p for p in log["points"] if p["outcome"] == "settled"]
    table = PerformanceTable(
        acf_sha256=log["acf_sha256"],
        altitude_ft=round(sum(p["alt"] for p in points_full) / len(points_full)), mass_kg=round(sum(mass) / len(mass), 1),
        conditions=log["conditions"] + "; mean cowl-flap ratio %.2f (left as the air start set it)" % (
            sum(p["cowl"] for p in log["points"]) / len(log["points"])),
        evidence=evidence, points=tuple(points))
    return table, [p for p in log["points"] if p["outcome"] != "settled"]


def render(table):
    rows = []
    for vvi, row in table.rows().items():
        rows.append("# %+.0f fpm\n" % vvi + "\n".join("  [%s, %s, %s]," % (repr(t), repr(vvi), repr(k)) for t, k in row))
    return ('[performance]\n'
            '# MEASURED, not handbook: the airspeed that settles at a fixed throttle with the autopilot holding a\n'
            '# vertical speed (scripts/perf_table_sweep.py), prop full forward. Valid only for the aircraft file,\n'
            '# loading and altitude below; re-measure when the aircraft file changes (A-1 will move it).\n'
            'acf_sha256 = "%s"\naltitude_ft = %s\nmass_kg = %s\nconditions = "%s"\nevidence = "%s"\n'
            '# [throttle, vertical speed fpm, settled KIAS]\npoints = [\n%s\n]\n'
            % (table.acf_sha256, repr(float(table.altitude_ft)), repr(float(table.mass_kg)),
               table.conditions.replace('"', "'"), table.evidence, "\n".join(rows)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sweep", type=Path)
    ap.add_argument("--evidence", required=True, help="repo path where the raw sweep JSON is kept")
    ap.add_argument("--write", action="store_true", help="replace [performance] in the profile file")
    args = ap.parse_args(argv)
    log = json.loads(args.sweep.read_text())
    table, dropped = build(log, args.evidence)
    block = render(table)
    print(block)
    for p in dropped:
        print("# not used: throttle %.2f vvi %+.0f %s (%.1f KIAS)" % (p["throttle"], p["target_vvi_fpm"], p["outcome"], p["kias"]))
    if args.write:
        path = PROFILE_DIR / PROFILE_FILES[log["profile"]]
        text = path.read_text()
        text = re.split(r"\n\[performance\]\n", text)[0].rstrip("\n") + "\n\n" + block
        path.write_text(text)
        load_profile(path)           # must still load
        print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
