#!/usr/bin/env python3
"""Derive reviewable KSEE–KMYF flight metrics from the attended raw fragments."""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xplane.capvsar_landing import RUNWAYS

NAMES = (
    "departure-01", "departure-02", "departure-03", "departure-04",
    "approach-01", "approach-02", "approach-03", "approach-04",
    "ils-final-01", "ils-final-02", "ils-final-03",
    "missed-01", "missed-02", "missed-03", "retry-bakel",
    "retry-mibby", "retry-nesty", "retry-penyy", "retry-ils",
    "retry-ils-filtered", "retry-ils-integral", "retry-landing", "retry-rollout",
)
RUNWAY = RUNWAYS["KMYF 28R"]


def read_fragment(path):
    h = hashlib.sha256()
    snaps, milestones, end = [], [], None
    with path.open("rb") as stream:
        for line in stream:
            h.update(line)
            record = json.loads(line)
            if record["kind"] == "snapshot":
                snaps.append(record["payload"])
            elif record["kind"] == "milestone":
                milestones.append(record["payload"])
            elif record["kind"] == "end":
                end = record["payload"]
    if not snaps or end is None:
        raise ValueError("Incomplete flight fragment: " + str(path))
    return {"path": str(path), "sha256": h.hexdigest(), "samples": len(snaps),
            "snapshots": snaps, "milestones": milestones, "end": end}


def coords(snapshot):
    v = snapshot["values"]
    return RUNWAY.coordinates(v["latitude_deg"], v["longitude_deg"])


def obs(snapshot):
    v = snapshot["values"]
    return {"sim_time_s": round(v["sim_time_s"], 2),
            "altitude_indicated_ft": round(v["altitude_indicated_ft"], 1),
            "kias": round(v["kias"], 1),
            "localizer_dots": round(v["nav1_hdef_dots"], 2),
            "glideslope_dots": round(v["nav1_vdef_dots"], 2),
            "dme_nm": round(v["nav1_dme_nm"], 2)}


def crossing(fragment):
    marks = fragment["milestones"]
    if len(marks) != 1:
        raise ValueError("Expected exactly one fix crossing: " + fragment["path"])
    return round(marks[0]["altitude_ft"], 1)


def departure_gradient(takeoff, d):
    samples = takeoff["snapshots"] + [s for name in ("departure-01", "departure-02", "departure-03")
                                      for s in d[name]["snapshots"]]
    samples.sort(key=lambda s: s["values"]["sim_time_s"])
    start = next(i for i, s in enumerate(samples)
                 if s["values"]["latitude_deg"] > 32.826
                 and s["values"]["on_ground"] == 0
                 and s["values"]["kias"] >= 60
                 and s["values"]["agl_m"] < 2)
    samples = samples[start:]
    distance, altitude = [0.], [samples[0]["values"]["altitude_indicated_ft"]]
    for prior, current in zip(samples, samples[1:]):
        p, v = prior["values"], current["values"]
        north = (v["latitude_deg"]-p["latitude_deg"])*111132.92
        east = ((v["longitude_deg"]-p["longitude_deg"])*111412.84
                * math.cos(math.radians(v["latitude_deg"])))
        distance.append(distance[-1]+math.hypot(north, east)/1852.)
        altitude.append(v["altitude_indicated_ft"])
    top = next(i for i, a in enumerate(altitude) if a >= 2000)
    low = (float("inf"), None)
    for i in range(top):
        if distance[i] < .5:
            continue
        left = distance[i]-.5
        j = bisect.bisect_left(distance, left)
        fraction = ((left-distance[j-1])/(distance[j]-distance[j-1])
                    if j and distance[j] > distance[j-1] else 0.)
        earlier_alt = (altitude[j-1]+fraction*(altitude[j]-altitude[j-1])
                       if j else altitude[0])
        gradient = (altitude[i]-earlier_alt)/.5
        if gradient < low[0]:
            low = gradient, altitude[i]
    return {"takeoff_trace": {k: takeoff[k] for k in ("path", "sha256", "samples")},
            "distance_to_2000_ft_nm": round(distance[top], 3),
            "cumulative_gradient_ft_per_nm": round((altitude[top]-altitude[0])/distance[top], 1),
            "lowest_half_nm_gradient_ft_per_nm": round(low[0], 1),
            "altitude_at_lowest_window_ft": round(low[1], 1),
            "published_minimum_ft_per_nm": 500,
            "qualification": "NOT_DEMONSTRATED" if low[0] < 500 else "SAMPLED_GRADIENT_MET"}


def score(directory):
    d = {name: read_fragment(directory / ("ksee-kmyf-" + name + ".jsonl")) for name in NAMES}
    takeoff = read_fragment(directory / "ksee_parking_to_takeoff_20261011_trial2.jsonl")
    landing = d["retry-landing"]["snapshots"]
    threshold = next(s for s in landing if coords(s)[0] >= 0)
    touchdown_pair = next((landing[i-1], landing[i]) for i in range(1, len(landing))
                          if not landing[i-1]["values"]["on_ground"] and landing[i]["values"]["on_ground"])
    pre, touch = touchdown_pair
    stop = d["retry-rollout"]["end"]["end"]
    stop_v = stop["values"]
    first_mibby = d["approach-02"]
    second_legs = {name: d["retry-"+name] for name in ("mibby", "nesty", "penyy")}
    minima = {name: {"charted_floor_ft": floor,
                     "sampled_minimum_ft": round(min(s["values"]["altitude_indicated_ft"] for s in fragment["snapshots"]), 1),
                     "fix_crossing_ft": crossing(fragment)}
              for name, floor, fragment in (("MIBBY", 4200, second_legs["mibby"]),
                                             ("NESTY", 3600, second_legs["nesty"]),
                                             ("PENYY", 2500, second_legs["penyy"]))}
    for name, item in minima.items():
        if item["sampled_minimum_ft"] < item["charted_floor_ft"]:
            raise ValueError(name + " sampled below charted floor on second approach")
    if (abs(d["retry-ils-integral"]["snapshots"][-1]["values"]["nav1_hdef_dots"]) > 1
            or abs(d["retry-ils-integral"]["snapshots"][-1]["values"]["nav1_vdef_dots"]) > 1):
        raise ValueError("Second ILS handoff outside one-dot gate")
    th_along, th_cross = coords(threshold)
    td_along, td_cross = coords(touch)
    stop_along, stop_cross = RUNWAY.coordinates(stop_v["latitude_deg"], stop_v["longitude_deg"])
    if not (RUNWAY.aimpoint_m <= td_along <= RUNWAY.aimpoint_m+400*.3048
            and abs(td_cross) <= 4 and stop_v["on_ground"] == 1
            and stop_v["groundspeed_mps"] <= 1 and stop_along < RUNWAY.length_m-100
            and stop["status"]["pause_confirmed"]):
        raise ValueError("Touchdown, stop or containment gate failed")
    return {
        "date": "2026-10-11", "aircraft": "stock X-Plane 12 Cessna_172SP_G1000.acf",
        "result": "OBSERVED_LANDING_AND_STOP_WITH_ROLLOUT_BRIDGE_RESTART",
        "chart_cycle": "FAA 2610", "sim_navigation_cycle": "2406",
        "authority": "attended direct control; simulated vectors; no live ATC",
        "departure_climb": departure_gradient(takeoff, d),
        "first_approach": {"MIBBY_sampled_minimum_ft": round(min(s["values"]["altitude_indicated_ft"] for s in first_mibby["snapshots"]), 1),
                           "MIBBY_crossing_ft": crossing(first_mibby),
                           "outcome": "ALTITUDE_CONSTRAINT_MISS_AND_UNSTABLE_ILS_GO_AROUND"},
        "missed_approach": {"runway_climb_turn_at_ft": crossing(d["missed-01"]),
                             "pilot_vector": "direct BAKEL during climb near 3450 ft; level at 5000 ft"},
        "second_approach": {"BAKEL_crossing_ft": crossing(d["retry-bakel"]),
                            "charted_segment_altitudes": minima,
                            "PENYY_nav1": obs(d["retry-penyy"]["snapshots"][-1]),
                            "ILS_landing_handoff": obs(d["retry-ils-integral"]["snapshots"][-1])},
        "landing": {"threshold": {"along_m": round(th_along, 1), "cross_m": round(th_cross, 1),
                                  "agl_ft": round(threshold["values"]["agl_m"]*3.28084, 1),
                                  "kias": round(threshold["values"]["kias"], 1)},
                    "touchdown": {"along_m": round(td_along, 1), "cross_m": round(td_cross, 1),
                                  "kias": round(touch["values"]["kias"], 1),
                                  "vertical_speed_fpm": round(touch["values"]["vvi_fpm"], 1),
                                  "pre_touch_pitch_deg": round(pre["values"]["pitch_deg"], 1)},
                    "stop": {"along_m": round(stop_along, 1), "cross_m": round(stop_cross, 1),
                             "groundspeed_mps": round(stop_v["groundspeed_mps"], 2),
                             "paused": bool(stop_v["paused"]),
                             "bridge_state": stop["status"]["state"],
                             "toe_brakes_released": stop_v["toe_brake_left"] == 0 and stop_v["toe_brake_right"] == 0}},
        "limitations": ["First approach crossed below the MIBBY segment altitude and was flown to a go-around.",
                        "The lowest sampled half-NM climb-gradient window to 2000 ft was below the published 500 ft/NM minimum; departure gradient is not qualified.",
                        "The second approach used the simulator's ILS signal without G1000 flight-plan sequencing or live ATC.",
                        "The flight-control bridge paused during rollout at 40 KIAS because its airborne speed guard applied on the ground; rollout resumed from the same paused position after a guard fix.",
                        "Raw traces are sampled fragments across attended pause/restart boundaries; this is not an uninterrupted qualification replay.",
                        "Runway sighting/visual references and radio-ident audio were not machine verified."],
        "fragments": {name: {k: f[k] for k in ("path", "sha256", "samples")}
                      for name, f in d.items()},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = score(a.directory)
    a.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"result": result["result"], "landing": result["landing"],
                      "output": str(a.output)}, indent=2))


if __name__ == "__main__":
    main()
