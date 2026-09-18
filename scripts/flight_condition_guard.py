#!/usr/bin/env python3
"""Refuse to measure an aeroplane that is not flying the condition you think.

Read-only. Written after a C2 attempt spun into the sea while a mixture sweep
recorded eleven tidy rows of 0.0 HP and concluded "peak power at mixture 0.80".
The engine had stopped before the first row. Nothing in that loop asked whether
the aircraft was still flying.

That is the same failure as a capture taken while paused, and as reading mass
from a paused m_total: a loop that produces confident numbers about a situation
that does not exist. The fix is the same in all three - check the state, and
refuse rather than report.

Use it around any measurement loop:

    guard = ConditionGuard(client, alt_ft=7000, alt_tol_ft=500, min_kias=70)
    for step in sweep:
        guard.check()          # raises ConditionLost if the aeroplane departed
        ...
"""
from __future__ import annotations


class ConditionLost(RuntimeError):
    """The aircraft is no longer in the condition being measured."""


class ConditionGuard:
    #: X-Plane array datarefs. Reading these WITHOUT the index returns a silent
    #: 0.0, which once reported a dead engine at full throttle.
    RPM = "sim/cockpit2/engine/indicators/prop_speed_rpm[0]"
    RUNNING = "sim/flightmodel/engine/ENGN_running[0]"
    CRASHED = "sim/flightmodel2/misc/has_crashed"
    ALT = "sim/flightmodel/position/elevation"
    KIAS = "sim/flightmodel/position/indicated_airspeed"
    ROLL = "sim/flightmodel/position/phi"
    PITCH = "sim/flightmodel/position/theta"
    M_PER_FT = 0.3048

    def __init__(self, client, alt_ft=None, alt_tol_ft=750.0, min_kias=55.0,
                 max_roll_deg=45.0, max_pitch_deg=30.0, require_engine=True):
        self.client = client
        self.alt_ft = alt_ft
        self.alt_tol_ft = alt_tol_ft
        self.min_kias = min_kias
        self.max_roll_deg = max_roll_deg
        self.max_pitch_deg = max_pitch_deg
        self.require_engine = require_engine
        for ref in (self.RPM, self.RUNNING, self.CRASHED, self.ALT,
                    self.KIAS, self.ROLL, self.PITCH):
            client.subscribe_dref(ref, 5)

    def state(self) -> dict:
        cache = self.client.get_all_cached()
        return {
            "crashed": cache.get(self.CRASHED),
            "running": cache.get(self.RUNNING),
            "rpm": cache.get(self.RPM),
            "alt_ft": (cache.get(self.ALT) or 0.0) / self.M_PER_FT,
            "kias": cache.get(self.KIAS),
            "roll": cache.get(self.ROLL),
            "pitch": cache.get(self.PITCH),
        }

    def faults(self) -> list:
        s = self.state()
        bad = []
        if s["crashed"]:
            bad.append("the aircraft has CRASHED")
        if s["kias"] is not None and s["kias"] < self.min_kias:
            bad.append("airspeed %.0f KIAS below %.0f" % (s["kias"], self.min_kias))
        if s["roll"] is not None and abs(s["roll"]) > self.max_roll_deg:
            bad.append("roll %.0f deg beyond %.0f" % (s["roll"], self.max_roll_deg))
        if s["pitch"] is not None and abs(s["pitch"]) > self.max_pitch_deg:
            bad.append("pitch %.0f deg beyond %.0f" % (s["pitch"], self.max_pitch_deg))
        if self.require_engine:
            # RPM is the honest one: ENGN_running can lag, and an engine turning
            # zero at full throttle is what the sweep failed to notice.
            if s["rpm"] is not None and s["rpm"] < 100:
                bad.append("engine stopped (%.0f RPM)" % s["rpm"])
        if self.alt_ft is not None and abs(s["alt_ft"] - self.alt_ft) > self.alt_tol_ft:
            bad.append("altitude %.0f ft is %.0f ft from the %.0f ft condition"
                       % (s["alt_ft"], s["alt_ft"] - self.alt_ft, self.alt_ft))
        return bad

    def check(self) -> None:
        bad = self.faults()
        if bad:
            raise ConditionLost("; ".join(bad))
