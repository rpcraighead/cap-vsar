#!/usr/bin/env python3
"""Score a single unpaused KSEE parking-to-KMYF runway-stop simulator trace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.score_ksee_kmyf import departure_gradient, read_fragment
from xplane.capvsar_landing import RUNWAYS


def score(path: Path) -> dict:
    fragment = read_fragment(path)
    snaps = fragment["snapshots"]
    with path.open() as stream:
        records = [json.loads(line) for line in stream]
    manifest = records[0]["payload"]
    end = fragment["end"]
    if (manifest.get("from_parking") is not True or
            any(r["kind"] == "intervention" for r in records) or
            end.get("outcome") != "PASS" or not end.get("end", {}).get("status", {}).get("pause_confirmed")):
        raise ValueError("Trace is not a completed uninterrupted parking-to-landing run")
    if any(s["values"]["paused"] for s in snaps):
        raise ValueError("Paused telemetry inside active run")
    sessions = {s["session"] for s in snaps}
    if len(sessions) != 1 or any(b["frame"] <= a["frame"] for a, b in zip(snaps, snaps[1:])):
        raise ValueError("Session or frame sequence changed")
    ground_marks = {m.get("name") for m in fragment["milestones"]}
    if not {"KSEE taxi began", "D8 hold short", "27R lined up",
            "300 ft AGL airborne handoff"}.issubset(ground_marks):
        raise ValueError("Missing surveyed surface/departure milestones")
    gradient = departure_gradient(fragment, {"departure-01": {"snapshots": []},
                                           "departure-02": {"snapshots": []},
                                           "departure-03": {"snapshots": []}})
    transitions = end["transitions"]
    def last_transition(stage):
        return next(m for m in reversed(transitions) if m["to"] == stage)
    minima = {}
    for stage, successor, floor in (("mibby", "nesty", 4200),
                                    ("nesty", "penyy", 3600),
                                    ("penyy", "ils", 2500)):
        start, finish = last_transition(stage), last_transition(successor)
        leg = [s["values"] for s in snaps if start["sim_time_s"] <= s["values"]["sim_time_s"] <= finish["sim_time_s"]]
        if not leg:
            raise ValueError("Missing sampled leg: "+stage)
        minima[stage] = {"floor_ft": floor,
                         "sampled_low_ft": round(min(v["altitude_indicated_ft"] for v in leg), 1),
                         "fix_crossing_ft": round(finish["altitude_ft"], 1)}
    handoff = last_transition("landing")
    handoff_sample = min(snaps, key=lambda s: abs(s["values"]["sim_time_s"]-handoff["sim_time_s"]))["values"]
    runway = RUNWAYS["KMYF 28R"]
    stop = end["end"]["values"]
    stop_along, stop_cross = runway.coordinates(stop["latitude_deg"], stop["longitude_deg"])
    pass_gates = (gradient["lowest_half_nm_gradient_ft_per_nm"] >= 500
                  and all(item["sampled_low_ft"] >= item["floor_ft"] for item in minima.values())
                  and handoff_sample["nav1_frequency_10khz"] == 11195
                  and handoff_sample["nav1_lateral_valid"]
                  and not handoff_sample["nav1_glideslope_flag"]
                  and abs(handoff_sample["nav1_hdef_dots"]) <= 1
                  and abs(handoff_sample["nav1_vdef_dots"]) <= 1
                  and end["last"]["groundspeed_kt"] / 1.94384 <= 1
                  and stop["on_ground"] and stop["groundspeed_mps"] <= 1
                  and stop["toe_brake_left"] == 0 and stop["toe_brake_right"] == 0
                  and abs(stop_cross) <= 5 and stop_along < runway.length_m-100)
    return {"result": "ENGINEERING_PASS_UNINTERRUPTED_TO_STOP" if pass_gates else "GATE_FAIL",
            "trace": {k: fragment[k] for k in ("path", "sha256", "samples")},
            "chart_cycle": manifest["chart_cycle"],
            "sim_cifp_cycle": manifest["sim_cifp_cycle"],
            "surface_milestones": sorted(ground_marks-set([None])),
            "departure_climb": gradient,
            "final_approach_segment_altitudes": minima,
            "ils_handoff": {"sim_time_s": round(handoff["sim_time_s"], 2),
                             "altitude_ft": round(handoff["altitude_ft"], 1),
                             "localizer_dots": round(handoff_sample["nav1_hdef_dots"], 2),
                             "glideslope_dots": round(handoff_sample["nav1_vdef_dots"], 2)},
            "touchdown": end["touchdown"],
            "runway_stop": {"along_m": round(stop_along, 1),
                            "cross_m": round(stop_cross, 1),
                            "groundspeed_mps": round(stop["groundspeed_mps"], 2)},
            "missed_approaches": [t for t in transitions if t["to"] == "missed_runway"],
            "limitations": ["No live ATC or clearance; route authority is simulated.",
                            "Installed navigation cycle 2406 predates FAA chart cycle 2610.",
                            "Visual runway references and ILS audio ident were not machine verified.",
                            "Runway exit and taxi to parking are planned separately."]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = score(args.trace)
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"result": result["result"],
                      "lowest_gradient_ft_per_nm": result["departure_climb"]["lowest_half_nm_gradient_ft_per_nm"],
                      "output": str(args.output)}, indent=2))
    return 0 if result["result"].startswith("ENGINEERING_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
