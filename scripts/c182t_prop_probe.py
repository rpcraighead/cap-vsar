#!/usr/bin/env python3
"""Does a write to the CAP 487 prop lever land, and does the governor follow it?

NOT YET RUN. Needs a human at the workstation and a running X-Plane with the
CAP 487 loaded and flying (see docs/C182T_AI_PILOT_PROP_2026-10-15.md, "Live
probe"). It writes only the prop lever and the throttle; no control surface.

The p2 sweep (docs/evidence/c182t-2026-10-15/) commanded the lever from 1.0 to
0.5 and read back prop_ratio[0] = 0.0 with a constant ENGN_prop. This script
separates the explanations by trying each write path in turn and reading
the lever, the commanded prop speed and the prop pitch after each one:

  A. UDP DREF to prop_ratio[0]           (what the sweep used)
  B. UDP DREF to prop_ratio_all

and prints whether the readback follows the write (a lever that reads 0.0
after being set to 0.5 is being rewritten each frame by something else, for
example an assigned joystick axis) and whether ENGN_prop moves.

Usage:
    python3 scripts/c182t_prop_probe.py            # prints a table, writes JSON
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

HARNESS = Path.home() / "Projects/g1000-sar/scripts/sim_harness.py"
OUT = Path.home() / ".cache/capvsar/measurements/prop_probe.json"
BASE = "sim/cockpit2/engine/actuators/"
READ = {
    "lever_0": BASE + "prop_ratio[0]",
    "lever_all": BASE + "prop_ratio_all",
    "commanded_prop_rad_s": "sim/flightmodel/engine/ENGN_prop[0]",
    "rpm": "sim/cockpit2/engine/indicators/engine_speed_rpm[0]",
    "pitch_req_deg": BASE + "prop_pitch_deg[0]",
    "pitch_actual_deg": "sim/flightmodel2/engines/prop_pitch_deg[0]",
    "override_prop_pitch": "sim/operation/override/override_prop_pitch",
    "prop_mode": BASE + "prop_mode[0]",
}
PATHS = (("A prop_ratio[0]", BASE + "prop_ratio[0]"),
         ("B prop_ratio_all", BASE + "prop_ratio_all"))
LEVERS = (1.0, 0.5, 0.0, 1.0)


def load_harness():
    spec = importlib.util.spec_from_file_location("sim_harness", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    h = load_harness()
    if not h.ready():
        print("X-Plane is not answering on UDP 49000; start it with the CAP 487 flying.")
        return 2
    rows = []
    for label, ref in PATHS:
        for lever in LEVERS:
            h.dref_set(ref, lever)
            time.sleep(1.0)       # one second to see whether it is rewritten
            early = h.dref_get(list(READ.values()))
            time.sleep(8.0)       # governor lag
            late = h.dref_get(list(READ.values()))
            row = {"path": label, "write": lever,
                   "after_1s": {k: early.get(v) for k, v in READ.items()},
                   "after_9s": {k: late.get(v) for k, v in READ.items()}}
            rows.append(row)
            print("%-18s write %.1f | lever0 %s all %s | ENGN_prop %s | rpm %s | pitch req %s" % (
                label, lever, *(("%.2f" % row["after_9s"][k]) if row["after_9s"][k] is not None else "-"
                                for k in ("lever_0", "lever_all", "commanded_prop_rad_s", "rpm", "pitch_req_deg"))),
                flush=True)
    h.dref_set(BASE + "prop_ratio_all", 1.0)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
