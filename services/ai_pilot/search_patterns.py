"""CAP search patterns for the AI pilot: geometry and a bounded pattern flyer.

Geometry follows decision D2 shared with the flight planner and the g1000-sar
library (docs/DECISIONS_2026-10-10.md; g1000-sar docs/DESIGN_NOTES.md D2):

* **Expanding square (SS):** DATUM is the centre; legs S, S, 2S, 2S, 3S, 3S ...
  with the first leg along `heading_true` and `turn` right or left; `SSnn` is
  the END of leg nn.
* **Creeping line (CS):** DATUM is the centre of the first sweep; sweeps of
  `width_nm` across `heading_true`, alternating sides, the axis advancing
  `spacing_nm` per sweep; `first_turn` is the side the first sweep flies toward.
* **Parallel track (PS):** DATUM is the first lane's start; lanes of `length_nm`
  along `heading_true`, `spacing_nm` apart on the `turn` side.

Every point is placed from the pattern origin with one great-circle offset,
exactly as g1000-sar `mission.offset()` does, so the three implementations
agree to a few metres at any size. `tests/data/search_pattern_fixtures.json`
is the cross-repo contract and the tests here replay all of it.

`SearchPatternController` flies the waypoints on the primary controls using
the altitude, speed and heading loops lifted from the C172 KSEE-KMYF sortie
(`ksee_kmyf_mission.MissionController`), parametrised by an
`AircraftProfile`. It is an offline-tested controller; it has not flown.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .aircraft_profiles import AircraftProfile, C172SP
from .prop_law import PropLaw

EARTH_NM = 3440.065
M_PER_NM = 1852.


def clamp(x, low, high):
    return min(max(x, low), high)


def wrap180(x):
    return (x + 180) % 360 - 180


def destination(lat, lon, bearing_deg, distance_nm):
    """Great-circle direct solution with longitude wrap (g1000-sar `destination`)."""
    a, b, h = map(math.radians, (lat, lon, bearing_deg))
    d = distance_nm / EARTH_NM
    lat2 = math.asin(math.sin(a) * math.cos(d) + math.cos(a) * math.sin(d) * math.cos(h))
    lon2 = b + math.atan2(math.sin(h) * math.sin(d) * math.cos(a),
                          math.cos(d) - math.sin(a) * math.sin(lat2))
    return math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180


def offset(lat, lon, along_nm, across_nm, heading_deg):
    """The point `along_nm` ahead and `across_nm` to the right of the origin."""
    return destination(lat, lon, heading_deg + math.degrees(math.atan2(across_nm, along_nm)),
                       math.hypot(along_nm, across_nm))


def distance_nm(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    dlat, dlon = b - a, math.radians(lon2 - lon1)
    h = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2
    return EARTH_NM * 2 * math.asin(min(1., math.sqrt(h)))


def bearing_true(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(b)
    y = math.cos(a) * math.sin(b) - math.sin(a) * math.cos(b) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


@dataclass(frozen=True)
class Waypoint:
    name: str
    lat: float
    lon: float

    def __post_init__(self):
        if (not math.isfinite(self.lat) or not math.isfinite(self.lon)
                or not -90 <= self.lat <= 90 or not -180 <= self.lon <= 180
                or not self.name.strip()):
            raise ValueError("waypoint needs a name and a finite position")


def _check(datum_lat, datum_lon, heading_true, spacing_nm, legs, turn, limit=60):
    if not all(math.isfinite(v) for v in (datum_lat, datum_lon, heading_true, spacing_nm)):
        raise ValueError("pattern parameters must be finite")
    if not -90 <= datum_lat <= 90 or not -180 <= datum_lon <= 180:
        raise ValueError("datum outside the globe")
    if not 0.05 <= spacing_nm <= 10:
        raise ValueError("track spacing outside 0.05-10 NM")
    if not isinstance(legs, int) or not 1 <= legs <= limit:
        raise ValueError("legs must be an integer 1..%d" % limit)
    if str(turn).lower() not in ("right", "left"):
        raise ValueError("turn must be 'right' or 'left'")
    return heading_true % 360, 1 if str(turn).lower() == "right" else -1


def expanding_square(datum_lat, datum_lon, heading_true, spacing_nm, legs, turn="right"):
    heading, sign = _check(datum_lat, datum_lon, heading_true, spacing_nm, legs, turn)
    points = [Waypoint("DATUM", datum_lat, datum_lon)]
    along = across = 0.
    for i in range(1, legs + 1):
        length = ((i + 1) // 2) * spacing_nm
        d_along, d_across = ((1, 0), (0, sign), (-1, 0), (0, -sign))[(i - 1) % 4]
        along, across = along + d_along * length, across + d_across * length
        lat, lon = offset(datum_lat, datum_lon, along, across, heading)
        points.append(Waypoint("SS%02d" % i, lat, lon))
    return points


def creeping_line(datum_lat, datum_lon, heading_true, width_nm, spacing_nm, legs,
                  first_turn="right"):
    heading, sign = _check(datum_lat, datum_lon, heading_true, spacing_nm, legs, first_turn)
    if not math.isfinite(width_nm) or not 0.1 <= width_nm <= 40:
        raise ValueError("sweep width outside 0.1-40 NM")
    half = width_nm / 2.

    def at(sweep, side):            # side +1 = the side the first sweep flies toward
        return offset(datum_lat, datum_lon, sweep * spacing_nm, sign * side * half, heading)

    points = [Waypoint("CS01", *at(0, -1)), Waypoint("CS02", *at(0, +1))]
    side = +1
    index = 3
    for sweep in range(1, legs):
        points.append(Waypoint("CS%02d" % index, *at(sweep, side)))
        points.append(Waypoint("CS%02d" % (index + 1), *at(sweep, -side)))
        index += 2
        side = -side
    return points


def parallel_track(datum_lat, datum_lon, heading_true, length_nm, spacing_nm, legs,
                   turn="right"):
    heading, sign = _check(datum_lat, datum_lon, heading_true, spacing_nm, legs, turn)
    if not math.isfinite(length_nm) or not 0.1 <= length_nm <= 60:
        raise ValueError("leg length outside 0.1-60 NM")
    points = [Waypoint("PS01", datum_lat, datum_lon)]
    index = 2
    for lane in range(legs):
        forward = lane % 2 == 0
        end_along = length_nm if forward else 0.
        points.append(Waypoint("PS%02d" % index,
                               *offset(datum_lat, datum_lon, end_along, sign * lane * spacing_nm, heading)))
        index += 1
        if lane < legs - 1:
            points.append(Waypoint("PS%02d" % index,
                                   *offset(datum_lat, datum_lon, end_along,
                                           sign * (lane + 1) * spacing_nm, heading)))
            index += 1
    return points


def track_miles(points):
    return sum(distance_nm(a.lat, a.lon, b.lat, b.lon) for a, b in zip(points, points[1:]))


# ---------------------------------------------------------------------------
# Control laws


class CruiseLaw:
    """Heading, altitude and speed loops of `ksee_kmyf_mission.MissionController`
    (cruise branch), lifted unchanged so a pattern can be flown with the laws
    the C172 sortie of 2026-10-11 used. Gains are tuning values from that
    sortie, not aircraft data; `profile.cruise_base_throttle` is the one
    aircraft-dependent constant."""

    def __init__(self, profile: AircraftProfile):
        self.profile = profile
        self.prop_law = PropLaw(profile)
        self.alt_i = 0.
        self.power_i = 0.
        self.trim = None

    def reset(self):
        self.alt_i = 0.
        self.power_i = 0.

    def frame(self, v, trim_in, target_true, target_alt, target_ias, dt,
              max_bank_deg=20.):
        if self.trim is None:
            self.trim = clamp(trim_in, -.6, .6)
        heading_error = wrap180(target_true - v["heading_true_deg"])
        bank_target = clamp(heading_error * 1.1, -max_bank_deg, max_bank_deg)
        roll = clamp((bank_target - v["roll_deg"]) * .020 - v["roll_rate_dps"] * .022, -.35, .35)
        alt_error = target_alt - v["altitude_indicated_ft"]
        target_vvi = clamp(alt_error * 2., -650., 650.)
        raw_pitch = (target_vvi - v["vvi_fpm"]) * .010 + self.alt_i
        pitch_target = clamp(raw_pitch, -6., 10.)
        candidate = clamp(self.alt_i + alt_error * .0002 * dt * 10., -4., 4.)
        if (-6 < raw_pitch < 10 or (raw_pitch >= 10 and candidate < self.alt_i)
                or (raw_pitch <= -6 and candidate > self.alt_i)):
            self.alt_i = candidate
        speed_error = target_ias - v["kias"]
        base = self.profile.cruise_base_throttle
        candidate = clamp(self.power_i + speed_error * .0015 * dt * 10., -.35, .35)
        trial = base + speed_error * .020 + candidate
        if (.12 < trial < 1. or (trial >= 1 and candidate < self.power_i)
                or (trial <= .12 and candidate > self.power_i)):
            self.power_i = candidate
        throttle = clamp(base + speed_error * .020 + self.power_i, .12, 1.)
        pitch = clamp((pitch_target - v["pitch_deg"]) * .09 - v["pitch_rate_dps"] * .030, -.4, .45)
        self.trim = clamp(self.trim + clamp(pitch * .35 * dt, -.06 * dt, .06 * dt), -.6, .6)
        ias = max(v["kias"], 40.)
        yaw = clamp(.07 * throttle * (100. / ias) ** 2 + roll * .25 - v["beta_deg"] * .045, -.35, .35)
        return (self.prop_law.add_to({"roll": roll, "pitch": pitch, "yaw": yaw, "throttle": throttle,
                                      "flap": 0., "trim": self.trim, "brake": 0.}, v),
                {"heading_error_deg": heading_error, "bank_target_deg": bank_target,
                 "target_vvi_fpm": target_vvi, "pitch_target_deg": pitch_target})


class SearchPatternController:
    """Fly `waypoints` in order at a fixed indicated altitude and speed.

    Lateral guidance tracks the leg from the previous waypoint (or the entry
    position) to the next one: the commanded course is the leg course plus an
    intercept angle proportional to cross-track error. A waypoint is complete
    when the aircraft is inside `capture_nm` of it, or when it has flown far
    enough along the leg that a turn of the pattern's bank angle started now
    ends on the next leg (turn anticipation). At each corner the turn is
    forced in the pattern's own direction, so a 180 degree lane reversal never
    becomes the shortest-way turn of a plain heading loop.

    The controller raises if the aircraft leaves a corridor of `lost_nm` about
    the leg; the caller's bridge handles the pause. It does not watch the
    envelope: the bridge, the observer and the experiment criteria do.
    """

    def __init__(self, waypoints, *, altitude_indicated_ft, kias=None,
                 profile: AircraftProfile = C172SP, capture_nm=.25,
                 bank_deg=20., lost_nm=3.):
        if len(waypoints) < 2:
            raise ValueError("a pattern needs at least two waypoints")
        if any(not isinstance(w, Waypoint) for w in waypoints):
            raise ValueError("waypoints must be Waypoint records")
        if not math.isfinite(altitude_indicated_ft) or not 0 < altitude_indicated_ft < 20000:
            raise ValueError("pattern altitude outside 0-20000 ft")
        self.kias = profile.search_kias if kias is None else kias
        if not profile.envelope_kias[0] <= self.kias <= profile.envelope_kias[1]:
            raise ValueError("pattern speed outside the profile envelope")
        if not .05 <= capture_nm <= 1. or not 10. <= bank_deg <= 30. or not 1. <= lost_nm <= 10.:
            raise ValueError("capture radius, bank or corridor outside the trial envelope")
        self.waypoints = list(waypoints)
        self.altitude_ft = altitude_indicated_ft
        self.profile = profile
        self.capture_nm = capture_nm
        self.bank_deg = bank_deg
        self.lost_nm = lost_nm
        self.law = CruiseLaw(profile)
        self.index = 0
        self.entry = None
        self.last_sim = None
        self.done = False
        self.forced_turn = 0            # +1 right, -1 left while a corner is being turned
        self.transitions = []
        self.last_diagnostics = {}

    # -- geometry helpers in a local flat frame about the aircraft ------------
    @staticmethod
    def _local(lat, lon, target_lat, target_lon):
        north = (target_lat - lat) * 111132.92
        east = (target_lon - lon) * 111412.84 * math.cos(math.radians(lat))
        return east, north

    def _leg(self):
        start = self.entry if self.index == 0 else (self.waypoints[self.index - 1].lat,
                                                    self.waypoints[self.index - 1].lon)
        end = self.waypoints[self.index]
        return start, (end.lat, end.lon)

    def _turn_sign_at(self, index):
        """+1 if the corner at waypoint `index` turns right, -1 left, 0 straight/last."""
        if index + 1 >= len(self.waypoints):
            return 0
        start, end = self._leg_at(index)
        nxt = self.waypoints[index + 1]
        course = bearing_true(start[0], start[1], end[0], end[1])
        next_course = bearing_true(end[0], end[1], nxt.lat, nxt.lon)
        delta = wrap180(next_course - course)
        if abs(delta) < 10:
            return 0
        if abs(abs(delta) - 180) < 1e-6:
            # A straight reversal has no geometric side; take the side the pattern
            # lies on, which is where the waypoint after next sits.
            if index + 2 < len(self.waypoints):
                after = self.waypoints[index + 2]
                e, n = self._local(end[0], end[1], after.lat, after.lon)
                rad = math.radians(course)
                cross = e * math.cos(rad) - n * math.sin(rad)
                return 1 if cross >= 0 else -1
            return 1
        return 1 if delta > 0 else -1

    def _leg_at(self, index):
        start = self.entry if index == 0 else (self.waypoints[index - 1].lat,
                                               self.waypoints[index - 1].lon)
        return start, (self.waypoints[index].lat, self.waypoints[index].lon)

    def step(self, snapshot):
        v = snapshot["values"]
        sim = v["sim_time_s"]
        dt = .04 if self.last_sim is None else clamp(sim - self.last_sim, .005, .15)
        self.last_sim = sim
        lat, lon = v["latitude_deg"], v["longitude_deg"]
        if self.entry is None:
            self.entry = (lat, lon)
        if self.done:
            target_true = self.last_diagnostics.get("course_deg", v["heading_true_deg"])
            frame, diag = self.law.frame(v, snapshot["controls"]["trim"], target_true,
                                         self.altitude_ft, self.kias, dt)
            self.last_diagnostics = {"stage": "complete", "course_deg": target_true, **diag}
            return frame

        start, end = self._leg()
        se, sn = self._local(lat, lon, start[0], start[1])
        ee, en = self._local(lat, lon, end[0], end[1])
        leg_e, leg_n = ee - se, en - sn
        leg_len = math.hypot(leg_e, leg_n)
        course = bearing_true(start[0], start[1], end[0], end[1]) if leg_len > 1 else v["heading_true_deg"]
        # Aircraft is at the local origin: along-track from the start, cross-track (right positive).
        if leg_len > 1:
            ux, uy = leg_e / leg_len, leg_n / leg_len
            along = -(se * ux + sn * uy)
            cross = -(se * uy - sn * ux)
        else:
            along, cross = 0., 0.
        remaining = max(leg_len - along, 0.)
        to_go_nm = math.hypot(ee, en) / M_PER_NM
        if abs(cross) > self.lost_nm * M_PER_NM or along < -self.lost_nm * M_PER_NM:
            raise ValueError("search pattern lost: outside the leg corridor")

        gs = max(v["groundspeed_mps"], 20.)
        radius_m = gs * gs / (9.80665 * math.tan(math.radians(self.bank_deg)))
        turn_sign = self._turn_sign_at(self.index)
        if turn_sign:
            nxt = self.waypoints[self.index + 1]
            next_course = bearing_true(end[0], end[1], nxt.lat, nxt.lon)
            delta = abs(wrap180(next_course - course))
            lead_m = clamp(radius_m * math.tan(math.radians(min(delta, 179.) / 2.)), 0., radius_m)
        else:
            lead_m = 0.
        captured = to_go_nm <= self.capture_nm or (leg_len > 1 and remaining <= lead_m and along > 0)
        if captured:
            self.transitions.append({"waypoint": self.waypoints[self.index].name,
                                     "sim_time_s": sim, "lat": lat, "lon": lon,
                                     "cross_track_m": cross, "distance_nm": to_go_nm})
            self.forced_turn = turn_sign
            self.index += 1
            if self.index >= len(self.waypoints):
                self.done = True
                frame, diag = self.law.frame(v, snapshot["controls"]["trim"], course,
                                             self.altitude_ft, self.kias, dt)
                self.last_diagnostics = {"stage": "complete", "course_deg": course, **diag}
                return frame
            start, end = self._leg()
            course = bearing_true(start[0], start[1], end[0], end[1])
            se, sn = self._local(lat, lon, start[0], start[1])
            ee, en = self._local(lat, lon, end[0], end[1])
            leg_e, leg_n = ee - se, en - sn
            leg_len = math.hypot(leg_e, leg_n)
            ux, uy = leg_e / max(leg_len, 1.), leg_n / max(leg_len, 1.)
            along = -(se * ux + sn * uy)
            cross = -(se * uy - sn * ux)
            to_go_nm = math.hypot(ee, en) / M_PER_NM

        intercept = clamp(-cross * .06, -30., 30.)
        target_true = (course + intercept) % 360
        heading_error = wrap180(target_true - v["heading_true_deg"])
        if self.forced_turn and abs(heading_error) > 100:
            # Keep turning the pattern's way until the new course is within reach.
            heading_error = self.forced_turn * (abs(heading_error) if heading_error * self.forced_turn > 0
                                                else 360 - abs(heading_error))
        elif abs(heading_error) <= 100:
            self.forced_turn = 0
        frame, diag = self.law.frame(v, snapshot["controls"]["trim"],
                                     v["heading_true_deg"] + heading_error,
                                     self.altitude_ft, self.kias, dt, max_bank_deg=self.bank_deg)
        self.last_diagnostics = {"stage": "pattern", "waypoint": self.waypoints[self.index].name,
                                 "index": self.index, "course_deg": course,
                                 "along_m": along, "cross_track_m": cross,
                                 "distance_nm": to_go_nm, "lead_m": lead_m,
                                 "forced_turn": self.forced_turn, "target_true_deg": target_true,
                                 "target_alt_ft": self.altitude_ft, "target_kias": self.kias, **diag}
        return frame


class PatternObserver:
    """Independent scoring of a flown pattern from aircraft snapshots only.

    It never reads the controller's state. A waypoint counts as reached when the
    aircraft passes within `pass_nm` of it, in order. While on the pattern (from
    the first waypoint reached to the last) altitude must stay within
    `altitude_tol_ft` of the assigned altitude, speed inside `kias_band` and bank
    within `max_bank_deg`. Criteria are engineering trial values, not CAP
    standards.
    """

    def __init__(self, waypoints, *, altitude_indicated_ft, pass_nm=.35, altitude_tol_ft=200.,
                 kias_band=(80., 140.), max_bank_deg=32., aircraft_name=None):
        self.waypoints = list(waypoints)
        self.altitude_ft = altitude_indicated_ft
        self.pass_nm = pass_nm
        self.altitude_tol_ft = altitude_tol_ft
        self.kias_band = kias_band
        self.max_bank_deg = max_bank_deg
        self.aircraft_name = aircraft_name
        self.index = 0
        self.closest_nm = float("inf")
        self.reached = []
        self.previous = None
        self.samples = 0
        self.outcome = "INCOMPLETE"
        self.reason = None
        self.max_altitude_error_ft = 0.
        self.max_bank_seen_deg = 0.

    def fail(self, reason):
        self.outcome, self.reason = "FAIL", reason
        return self.report()

    def observe(self, s):
        if self.outcome != "INCOMPLETE":
            return self.report()
        try:
            v = s["values"]
            sim, frame = v["sim_time_s"], s["frame"]
            if self.aircraft_name and s["aircraft"]["name"] != self.aircraft_name:
                return self.fail("Wrong aircraft")
            numbers = (sim, v["latitude_deg"], v["longitude_deg"], v["altitude_indicated_ft"],
                       v["kias"], v["roll_deg"])
            if not all(type(x) in (int, float) and math.isfinite(x) for x in numbers):
                return self.fail("Invalid measured value")
            if self.previous is not None:
                if not (sim > self.previous[0] and frame > self.previous[1]):
                    return self.fail("Nonincreasing telemetry")
                if sim - self.previous[0] > .5:
                    return self.fail("Telemetry gap")
            if v["paused"] or v["on_ground"]:
                return self.fail("Pause or ground contact")
            self.previous = (sim, frame)
            self.samples += 1
            on_pattern = bool(self.reached)
            if on_pattern:
                err = abs(v["altitude_indicated_ft"] - self.altitude_ft)
                self.max_altitude_error_ft = max(self.max_altitude_error_ft, err)
                self.max_bank_seen_deg = max(self.max_bank_seen_deg, abs(v["roll_deg"]))
                if err > self.altitude_tol_ft:
                    return self.fail("Altitude outside tolerance on the pattern")
                if not self.kias_band[0] <= v["kias"] <= self.kias_band[1]:
                    return self.fail("Speed outside band on the pattern")
                if abs(v["roll_deg"]) > self.max_bank_deg:
                    return self.fail("Bank beyond limit on the pattern")
            w = self.waypoints[self.index]
            d = distance_nm(v["latitude_deg"], v["longitude_deg"], w.lat, w.lon)
            self.closest_nm = min(self.closest_nm, d)
            if d <= self.pass_nm:
                self.reached.append({"waypoint": w.name, "sim_time_s": sim, "distance_nm": d,
                                     "altitude_ft": v["altitude_indicated_ft"], "kias": v["kias"]})
                self.index += 1
                self.closest_nm = float("inf")
                if self.index == len(self.waypoints):
                    self.outcome = "PASS"
        except (KeyError, TypeError, ValueError) as error:
            return self.fail("Malformed snapshot: %s" % error)
        return self.report()

    def report(self):
        return {"outcome": self.outcome, "reason": self.reason, "samples": self.samples,
                "reached": list(self.reached), "next_index": self.index,
                "max_altitude_error_ft": self.max_altitude_error_ft,
                "max_bank_deg": self.max_bank_seen_deg}
