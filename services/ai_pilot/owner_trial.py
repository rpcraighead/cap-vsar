"""Scoring for the owner-transfer trial: DIRECT -> GFC 700 -> DIRECT.

The trial (`scripts/ai_pilot_owner_trial.py`) holds a heading and altitude under
the AI pilot's controllers, hands the airplane to the GFC 700 for a heading change,
and takes it back. This observer scores what an instructor would watch: how much
the airplane moved at each hand-over, and whether the autopilot captured what it
was given. Criteria are engineering trial values, not CAP standards.
"""
from __future__ import annotations

import math

TRANSIENT_S = 6.0                 # window after each hand-over scored as the transient
CRITERIA = {
    "transient_altitude_ft": 150., "transient_bank_deg": 25., "transient_vvi_fpm": 1200.,
    "kias_band": (70., 130.), "capture_heading_deg": 3., "capture_altitude_ft": 100.,
    "capture_vvi_fpm": 150., "capture_dwell_s": 8., "max_bank_deg": 32.,
}


def wrap180(x):
    return (x + 180.) % 360. - 180.


class OwnerTrialObserver:
    PHASES = ("direct1", "gfc", "direct2")

    def __init__(self, *, altitude_ft, aircraft_name=None, criteria=None):
        self.altitude_ft = altitude_ft
        self.aircraft_name = aircraft_name
        self.criteria = {**CRITERIA, **(criteria or {})}
        self.phase = None
        self.phase_started = {}
        self.stats = {p: self._blank() for p in self.PHASES}
        self.gfc_target_heading = None
        self.captured_since = None
        self.captured = False
        self.failure = None
        self.previous = None

    @staticmethod
    def _blank():
        return {"samples": 0, "transient": {"max_alt_error_ft": 0., "max_bank_deg": 0.,
                                            "max_abs_vvi_fpm": 0.},
                "steady": {"max_alt_error_ft": 0., "max_bank_deg": 0.}}

    def enter(self, phase, snapshot, *, heading_target_true=None):
        if phase not in self.PHASES:
            raise ValueError("Unknown phase")
        self.phase = phase
        self.phase_started[phase] = snapshot["values"]["sim_time_s"]
        if phase == "gfc":
            self.gfc_target_heading = heading_target_true
            self.captured_since = None

    def fail(self, reason):
        if self.failure is None:
            self.failure = reason
        return self.failure

    def observe(self, snapshot):
        if self.failure or self.phase is None:
            return self.failure
        v, c = snapshot["values"], self.criteria
        try:
            sim = v["sim_time_s"]
            if self.aircraft_name and snapshot["aircraft"]["name"] != self.aircraft_name:
                return self.fail("Wrong aircraft")
            numbers = (sim, v["altitude_indicated_ft"], v["kias"], v["roll_deg"], v["vvi_fpm"],
                       v["heading_true_deg"])
            if not all(type(x) in (int, float) and math.isfinite(x) for x in numbers):
                return self.fail("Invalid measured value")
            if self.previous is not None and (sim <= self.previous or sim - self.previous > .5):
                return self.fail("Telemetry gap or nonincreasing time")
            self.previous = sim
            if v["paused"] or v["on_ground"]:
                return self.fail("Pause or ground contact")
            if not c["kias_band"][0] <= v["kias"] <= c["kias_band"][1]:
                return self.fail("Speed outside band in %s" % self.phase)
            stats = self.stats[self.phase]
            stats["samples"] += 1
            alt_error = abs(v["altitude_indicated_ft"] - self.altitude_ft)
            bank = abs(v["roll_deg"])
            if sim - self.phase_started[self.phase] <= TRANSIENT_S:
                t = stats["transient"]
                t["max_alt_error_ft"] = max(t["max_alt_error_ft"], alt_error)
                t["max_bank_deg"] = max(t["max_bank_deg"], bank)
                t["max_abs_vvi_fpm"] = max(t["max_abs_vvi_fpm"], abs(v["vvi_fpm"]))
                if (alt_error > c["transient_altitude_ft"] or bank > c["transient_bank_deg"]
                        or abs(v["vvi_fpm"]) > c["transient_vvi_fpm"]):
                    return self.fail("Hand-over transient too large entering %s" % self.phase)
            else:
                s = stats["steady"]
                s["max_alt_error_ft"] = max(s["max_alt_error_ft"], alt_error)
                s["max_bank_deg"] = max(s["max_bank_deg"], bank)
                if self.phase != "gfc" and alt_error > c["transient_altitude_ft"]:
                    return self.fail("Altitude not held in %s" % self.phase)
                if bank > c["max_bank_deg"]:
                    return self.fail("Bank beyond limit in %s" % self.phase)
            if self.phase == "gfc" and self.gfc_target_heading is not None and not self.captured:
                held = (abs(wrap180(v["heading_true_deg"] - self.gfc_target_heading)) <= c["capture_heading_deg"]
                        and alt_error <= c["capture_altitude_ft"]
                        and abs(v["vvi_fpm"]) <= c["capture_vvi_fpm"])
                if not held:
                    self.captured_since = None
                elif self.captured_since is None:
                    self.captured_since = sim
                elif sim - self.captured_since >= c["capture_dwell_s"]:
                    self.captured = True
        except (KeyError, TypeError) as error:
            return self.fail("Malformed snapshot: %s" % error)
        return None

    def report(self):
        complete = all(self.stats[p]["samples"] for p in self.PHASES)
        outcome = ("FAIL" if self.failure else "PASS" if complete and self.captured else "INCOMPLETE")
        reason = self.failure or (None if outcome == "PASS" else
                                  "heading/altitude not captured by the GFC 700" if complete
                                  else "a phase was not flown")
        return {"outcome": outcome, "reason": reason, "captured": self.captured,
                "phases": self.stats, "criteria": self.criteria}
