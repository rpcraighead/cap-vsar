"""Terrain guard: the executive's decision about the ground ahead.

Moved here from the squadron-demo script `demo_autopilot.py --guard`
(2026-10-14), where it ran outside the simulator and moved the G1000 autopilot's
altitude target. That script was written after rehearsal 1 flew into the
Ramona/Santa Ysabel ridge: the G1000 plan finished and GPSS held the last
course forever. The numbers below are the ones the demo flew with, and are
engineering values, not validated limits.

This module is pure: it takes the bridge snapshot (with its `terrain` entry from
`xplane/capvsar_terrain.py`) and says what the airplane's owner must do. It
commands nothing. Whoever owns the airplane applies the advice:

* the AI pilot's controllers (DIRECT) take `floor_indicated_ft` as a floor on
  their altitude target and `full_power` on the throttle;
* the GFC 700 owner (`gfc_owner.py`) raises the altitude selection to the floor.

Both owners are subject to the same advice, which is the point: the guard does
not care who is flying.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

FT_PER_M = 3.28084
CLEAR_TARGET_FT = 1500     # climb to put this much air above the highest terrain ahead
CLEAR_TRIGGER_FT = 1000    # least air to keep above the highest ground ahead
CLEAR_URGENT_FT = 500      # climb hard inside this
CEILING_FT = 8500          # terrain needing more than this: turn back, do not climb
STEP_FT = 500
CLIMB_FPM = 500
URGENT_CLIMB_FPM = 700
MARGIN_NM = 2.0            # start the climb this much earlier than the arithmetic says
FULL_POWER_BELOW_FT = 150  # full power while this far under the floor
MAX_TERRAIN_AGE_S = 5.0


@dataclass(frozen=True)
class Advice:
    valid: bool                       # False: no usable terrain data this frame
    floor_indicated_ft: float | None  # None: no floor beyond the mission's own altitude
    climb_fpm: float
    full_power: bool
    turn_back: bool
    reason: str
    clearance_ft: float | None
    ahead_ft: float | None
    return_heading_true: float | None = None


class TerrainGuard:
    """Stateful because the floor has hysteresis: it rises when the ground needs
    it and is released only once the ground ahead is a full step lower."""

    def __init__(self, *, leash=None, ceiling_ft=CEILING_FT, max_climb_fpm=None):
        # leash: (lat, lon, radius_nm) of the area the sortie must stay within.
        # max_climb_fpm: what THIS airplane can sustain (from its measured performance table); the guard
        # then plans with, and orders, no more than that. None keeps the demo's 500/700 fpm.
        self.leash, self.ceiling_ft = leash, ceiling_ft
        self.climb_fpm = CLIMB_FPM if max_climb_fpm is None else max(100., min(CLIMB_FPM, max_climb_fpm))
        self.urgent_fpm = URGENT_CLIMB_FPM if max_climb_fpm is None else max(100., min(URGENT_CLIMB_FPM, max_climb_fpm))
        self.floor_msl = None
        self.last_reason = ""

    def update(self, snapshot) -> Advice:
        v = snapshot["values"]
        terrain = snapshot.get("terrain")
        alt_msl = v["altitude_msl_m"] * FT_PER_M
        offset = v["altitude_indicated_ft"] - alt_msl          # indicated minus true MSL
        turn, why, heading = self._leash(v)
        if (not terrain or not terrain.get("valid")
                or terrain.get("age_s", 0.) > MAX_TERRAIN_AGE_S):
            # Blind. Keep any floor already raised; never invent a descent.
            floor = None if self.floor_msl is None else self.floor_msl + offset
            return Advice(False, floor, 0., False, turn, why or "no terrain data",
                          None, None, heading)

        ahead = max(terrain["ahead_max_ft"], terrain["under_ft"])
        ahead_nm = terrain["ahead_max_nm"]
        clearance = alt_msl - ahead
        gs_nmpm = v["groundspeed_mps"] * 1.94384 / 60.0
        gain = ahead + CLEAR_TRIGGER_FT - alt_msl
        # Climb only when the ground is near enough that the climb must start
        # now: time to gain the height at CLIMB_FPM at this groundspeed, plus a
        # margin. Distant high ground off the search area is not a reason to leave
        # the search altitude.
        need_nm = max(gain, 0.) / self.climb_fpm * gs_nmpm + MARGIN_NM
        want = math.ceil((ahead + CLEAR_TARGET_FT) / STEP_FT) * STEP_FT
        reason = why
        if gain > 0 and ahead_nm <= need_nm and (self.floor_msl is None or want > self.floor_msl):
            self.floor_msl = float(want)
            reason = ("terrain %d ft at %.1f nm, clearance %d ft: floor %d ft"
                      % (ahead, ahead_nm, clearance, want))
        elif self.floor_msl is not None and want < self.floor_msl - STEP_FT:
            self.floor_msl = None
            reason = "terrain %d ft ahead is low again" % ahead
        floor = self.floor_msl
        if floor is not None and floor > self.ceiling_ft and not turn:
            turn, why = True, "terrain needs a floor of %d ft, above the %d ft ceiling" % (
                floor, self.ceiling_ft)
            reason = why
        full_power = floor is not None and alt_msl < floor - FULL_POWER_BELOW_FT
        climb = 0. if floor is None else (self.urgent_fpm if clearance < CLEAR_URGENT_FT
                                          else self.climb_fpm)
        self.last_reason = reason
        return Advice(True, None if floor is None else floor + offset, climb, full_power,
                      turn, reason, clearance, ahead, heading)

    def _leash(self, v):
        if self.leash is None:
            return False, "", None
        lat0, lon0, radius = self.leash
        dn = (lat0 - v["latitude_deg"]) * 60.0
        de = (lon0 - v["longitude_deg"]) * 60.0 * math.cos(math.radians(v["latitude_deg"]))
        dist = math.hypot(dn, de)
        if dist <= radius:
            return False, "", None
        bearing = math.degrees(math.atan2(de, dn)) % 360
        return True, "%.1f nm from the area, beyond the %.0f nm leash" % (dist, radius), bearing

    def apply_to_altitude(self, mission_altitude_ft, advice: Advice) -> float:
        """The altitude an owner must hold: the mission's, or the floor if higher."""
        if advice.floor_indicated_ft is None:
            return mission_altitude_ft
        return max(mission_altitude_ft, advice.floor_indicated_ft)
