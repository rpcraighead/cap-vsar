"""Attended KSEE Mission Bay Two and KMYF ILS 28R guidance.

Waypoints and crossing altitudes are transcribed from the FAA 2610 charts;
the simulator's installed CIFP is older and is checked separately in evidence.
"""
from __future__ import annotations

import math

from .aircraft_profiles import AircraftProfile
from .landing_trial import LandingController
from .prop_law import PropLaw
from xplane.capvsar_landing import RUNWAYS

PGY10 = (32.778216667, -116.972158333)
MZB = (32.782208333, -117.225422222)
BAKEL = (32.776838889, -116.844377778)
MIBBY = (32.716422222, -116.887075000)
NESTY = (32.739716667, -116.945883333)
PENYY = (32.769802778, -117.021991667)
CARIF = (33.038597222, -117.332705556)
RUNWAY = RUNWAYS["KMYF 28R"]
STAGES = ("runway_climb", "pgy_intercept", "pgy_inbound", "mzb_inbound",
          "bakel_vector", "vector_heading", "mibby", "nesty", "penyy", "ils", "landing",
          "missed_runway", "missed_270", "carif_inbound", "retry_bakel")
# Stages where a governed prop may leave full forward (level, established
# cruise). Climb-out, the approach and every go-around fly it full forward.
CRUISE_PROP_STAGES = ("pgy_inbound", "mzb_inbound", "bakel_vector", "vector_heading",
                      "carif_inbound", "retry_bakel")


def clamp(x, low, high):
    return min(max(x, low), high)


def wrap180(x):
    return (x + 180) % 360 - 180


def bearing_distance(lat, lon, target):
    n = (target[0]-lat)*111132.92
    e = (target[1]-lon)*111412.84*math.cos(math.radians(lat))
    return math.degrees(math.atan2(e, n)) % 360, math.hypot(n, e)/1852


class MissionController:
    def __init__(self, stage="runway_climb", *, profile: AircraftProfile):
        if stage not in STAGES:
            raise ValueError("Unknown mission stage")
        self.stage = stage
        self.profile = profile
        self.last_sim = None
        self.trim = None
        self.alt_i = 0.
        self.power_i = 0.
        self.vvi_lp = None
        self.ils_pitch_i = 0.
        self.landing = LandingController("KMYF 28R", profile=profile)
        self.prop_law = PropLaw(profile)
        self.last_diagnostics = {}
        self.transitions = []
        self.vector_heading_mag = None
        self.vector_alt_ft = None
        self.missed_turn_alt_ft = 1100.

    def retask(self, task, snapshot):
        """Apply a bounded simulated vector on a live telemetry frame."""
        v = snapshot["values"]
        alt = v["altitude_indicated_ft"]
        if (v["paused"] or v["on_ground"] or alt < 3000 or
                self.stage not in ("pgy_inbound", "mzb_inbound", "bakel_vector",
                                   "retry_bakel", "vector_heading")):
            raise ValueError("Retask requires an airborne en-route segment above 3000 ft")
        if not isinstance(task, dict) or type(task.get("kind")) is not str:
            raise ValueError("Invalid retask request")
        kind = task["kind"]
        if kind == "direct":
            if set(task) != {"kind", "fix", "altitude_ft"} or task["fix"] != "BAKEL":
                raise ValueError("Only explicit direct BAKEL with altitude is supported")
            target_alt = task["altitude_ft"]
            if type(target_alt) not in (int, float) or not math.isfinite(target_alt) or not 4200 <= target_alt <= 6000:
                raise ValueError("Direct BAKEL altitude outside 4200–6000 ft")
            self.vector_heading_mag = None
            self.vector_alt_ft = float(target_alt)
            self._advance("retry_bakel", v)
        elif kind == "heading":
            if set(task) != {"kind", "heading_mag_deg", "altitude_ft"}:
                raise ValueError("Heading vector requires heading and altitude")
            heading, target_alt = task["heading_mag_deg"], task["altitude_ft"]
            if (type(heading) not in (int, float) or not math.isfinite(heading) or not 0 <= heading < 360
                    or type(target_alt) not in (int, float) or not math.isfinite(target_alt)
                    or not 4200 <= target_alt <= 6000):
                raise ValueError("Heading or altitude outside vector bounds")
            self.vector_heading_mag = float(heading)
            self.vector_alt_ft = float(target_alt)
            self._advance("vector_heading", v)
        elif kind == "altitude":
            if set(task) != {"kind", "altitude_ft"}:
                raise ValueError("Altitude request has unexpected fields")
            target_alt = task["altitude_ft"]
            if type(target_alt) not in (int, float) or not math.isfinite(target_alt) or not 4200 <= target_alt <= 6000:
                raise ValueError("Altitude outside 4200–6000 ft")
            self.vector_alt_ft = float(target_alt)
        else:
            raise ValueError("Unknown retask kind")
        return {"kind": kind, "stage": self.stage, "heading_mag_deg": self.vector_heading_mag,
                "altitude_ft": self.vector_alt_ft, "sim_time_s": v["sim_time_s"]}

    def _advance(self, new, v, reason=None):
        transition = {"from": self.stage, "to": new,
                                 "sim_time_s": v["sim_time_s"],
                                 "lat": v["latitude_deg"], "lon": v["longitude_deg"],
                                 "altitude_ft": v["altitude_indicated_ft"]}
        if reason is not None:
            transition["reason"] = reason
        self.transitions.append(transition)
        if new == "missed_runway":
            self.missed_turn_alt_ft = max(1100., v["altitude_indicated_ft"]+200.)
        self.stage = new
        self.alt_i = 0.
        self.power_i = 0.

    def step(self, snapshot):
        v = snapshot["values"]
        sim = v["sim_time_s"]
        dt = .04 if self.last_sim is None else clamp(sim-self.last_sim, .005, .15)
        self.last_sim = sim
        lat, lon = v["latitude_deg"], v["longitude_deg"]
        alt, ias = v["altitude_indicated_ft"], v["kias"]
        if self.trim is None:
            self.trim = clamp(snapshot["controls"]["trim"], -.6, .6)
        variation = wrap180(v["heading_true_deg"]-v["heading_mag_deg"])
        p = self.profile
        climb_ias = p.vy_kias if alt < 2000 else p.climb_enroute_kias
        target_true = v["heading_true_deg"]
        target_alt = 5000.
        target_ias = p.cruise_kias
        distance = None
        if self.stage == "runway_climb":
            target_true = 281.
            target_ias = p.vy_kias
            if alt >= 790:
                self._advance("pgy_intercept", v)
        if self.stage == "pgy_intercept":
            target_true = (62.+variation)%360
            target_ias = climb_ias
            # Cross the PGY R-348 north of the PGY10 fix, allowing turn lead.
            if lon >= -116.9727 and lat >= 32.831:
                self._advance("pgy_inbound", v)
        if self.stage == "pgy_inbound":
            target_true, distance = bearing_distance(lat, lon, PGY10)
            target_ias = climb_ias
            if distance <= .35 or lat < PGY10[0]:
                self._advance("mzb_inbound", v)
        if self.stage == "mzb_inbound":
            target_true, distance = bearing_distance(lat, lon, MZB)
            target_ias = climb_ias
            if distance <= .55:
                if alt < 4800:
                    raise ValueError("MZB reached before 5000-foot climb gate")
                self._advance("bakel_vector", v)
        if self.stage == "bakel_vector":
            target_true, distance = bearing_distance(lat, lon, BAKEL)
            target_ias = p.cruise_kias
            if distance <= .55:
                self._advance("mibby", v)
        if self.stage == "vector_heading":
            target_true = (self.vector_heading_mag+variation)%360
            target_ias = p.cruise_kias
        if self.stage == "missed_runway":
            target_true = RUNWAY.heading_true_deg
            target_alt, target_ias = max(3000., self.missed_turn_alt_ft), p.missed_kias
            if alt >= self.missed_turn_alt_ft:
                self._advance("missed_270", v)
        if self.stage == "missed_270":
            target_true = (270.+variation)%360
            target_alt, target_ias = 3500., p.vy_kias
            # Pilot-directed simulated vector replaces the published CARIF
            # segment once established in the climb at 3500 ft.
            if alt >= 3500:
                self._advance("retry_bakel", v)
        if self.stage == "carif_inbound":
            target_true, distance = bearing_distance(lat, lon, CARIF)
            target_alt, target_ias = 3000., p.approach_intermediate_kias
            if distance <= .55:
                self._advance("retry_bakel", v)
        if self.stage == "retry_bakel":
            target_true, distance = bearing_distance(lat, lon, BAKEL)
            target_alt, target_ias = 5000., p.climb_enroute_kias if alt < 4800 else p.cruise_kias
            if distance <= .55:
                self.vector_alt_ft = None
                self._advance("mibby", v)
        if self.stage == "mibby":
            target_true, distance = bearing_distance(lat, lon, MIBBY)
            # First pass undershot 4200 by ~80 ft; retain a 100-ft margin.
            target_alt, target_ias = 4300., p.approach_initial_kias
            if distance <= .35:
                self._advance("nesty", v)
        if self.stage == "nesty":
            target_true, distance = bearing_distance(lat, lon, NESTY)
            # Keep a 100-ft margin above the charted 3600-ft segment floor;
            # the first descent demonstrated roughly 70 ft of undershoot.
            target_alt, target_ias = 3750., p.approach_intermediate_kias
            if distance <= .35:
                self._advance("penyy", v)
        if self.stage == "penyy":
            target_true, distance = bearing_distance(lat, lon, PENYY)
            target_alt, target_ias = 2650., p.approach_intermediate_kias-5.
            if distance <= .3:
                if v["nav1_frequency_10khz"] != 11195 or not v["nav1_lateral_valid"] or v["nav1_glideslope_flag"]:
                    self._advance("missed_runway", v, "ILS signal not established at PENYY")
                    return self.step(snapshot)
                self._advance("ils", v)
        if self.stage == "ils":
            if not v["nav1_lateral_valid"] or v["nav1_glideslope_flag"]:
                self._advance("missed_runway", v, "ILS signal lost on final")
                return self.step(snapshot)
            along, cross = RUNWAY.coordinates(lat, lon)
            remaining_nm = max(0., -along/1852)
            target_true = RUNWAY.heading_true_deg-clamp(cross*.12, -12., 12.)
            target_alt = RUNWAY.airport_elev_ft + (RUNWAY.aimpoint_m-along)*math.tan(math.radians(3.))*3.28084
            target_ias = p.approach_clean_kias if remaining_nm > 3 else p.ils_final_kias
            if remaining_nm <= 1.2:
                if (abs(cross)>90 or abs(v["nav1_hdef_dots"])>1.
                        or abs(v["nav1_vdef_dots"])>1. or v["nav1_glideslope_flag"]):
                    self._advance("missed_runway", v, "ILS unstable at 1.2 NM")
                    return self.step(snapshot)
                self._advance("landing", v)
        if self.stage == "landing":
            command = self.landing.step(snapshot)
            self.last_diagnostics = {"stage": self.stage, **self.landing.last_commands,
                                     "nav1_hdef_dots": v["nav1_hdef_dots"],
                                     "nav1_vdef_dots": v["nav1_vdef_dots"]}
            return command
        if self.vector_alt_ft is not None and self.stage in ("pgy_inbound", "mzb_inbound", "vector_heading", "retry_bakel", "bakel_vector"):
            target_alt = self.vector_alt_ft
        heading_error = wrap180(target_true-v["heading_true_deg"])
        bank_target = clamp(heading_error*1.1, -20., 20.)
        roll = clamp((bank_target-v["roll_deg"])*.020-v["roll_rate_dps"]*.022, -.35, .35)
        if (self.stage in ("runway_climb", "pgy_intercept", "pgy_inbound", "mzb_inbound") and alt < 4800
                or self.stage == "missed_runway"
                or self.stage == "missed_270" and alt < 3450
                or self.stage == "retry_bakel" and alt < 4800):
            target_ias = (p.missed_kias if self.stage == "missed_runway"
                          else p.vy_kias if alt < 2000 or self.stage.startswith("missed_")
                          else p.climb_enroute_kias)
            # The first KSEE sortie drifted to 79–80 KIAS near 1,800 ft,
            # yielding a 493 ft/NM half-mile window. Hold the stock C172
            # nearer its 74-KIAS Vy with more speed-error pitch authority.
            pitch_target = clamp(8.+.8*(ias-target_ias), 3., 12.)
            throttle = 1.
        elif self.stage == "ils":
            # Glideslope deviation is the primary vertical guidance. In this
            # X-Plane instrument positive vdef is ABOVE the beam, established
            # by correlating the recorded aircraft altitude and geometry.
            nominal_sink = -v["groundspeed_mps"]*math.tan(math.radians(3.))*196.8504
            target_vvi = clamp(nominal_sink-clamp(v["nav1_vdef_dots"], -2.5, 2.5)*90., -750., -250.)
            if self.vvi_lp is None:
                self.vvi_lp = v["vvi_fpm"]
            self.vvi_lp += clamp(dt/2., 0., 1.)*(v["vvi_fpm"]-self.vvi_lp)
            vvi_error = target_vvi-self.vvi_lp
            candidate_i = clamp(self.ils_pitch_i+vvi_error*.0004*dt, -3., 3.)
            raw_pitch = -2.+vvi_error*.006+candidate_i
            if -6 < raw_pitch < 6 or (raw_pitch <= -6 and candidate_i > self.ils_pitch_i) or (raw_pitch >= 6 and candidate_i < self.ils_pitch_i):
                self.ils_pitch_i = candidate_i
            pitch_target = clamp(-2.+vvi_error*.006+self.ils_pitch_i, -6., 6.)
            speed_error = target_ias-ias
            self.power_i = clamp(self.power_i+speed_error*.001*dt*10., -.3, .3)
            throttle = clamp(p.ils_base_throttle+speed_error*.02+self.power_i, .05, .75)
        else:
            alt_error = target_alt-alt
            target_vvi = clamp(alt_error*2., -650., 650.)
            raw_pitch = (target_vvi-v["vvi_fpm"])*.010+self.alt_i
            pitch_target = clamp(raw_pitch, -6., 10.)
            candidate = clamp(self.alt_i+alt_error*.0002*dt*10., -4., 4.)
            if -6 < raw_pitch < 10 or (raw_pitch >= 10 and candidate < self.alt_i) or (raw_pitch <= -6 and candidate > self.alt_i):
                self.alt_i = candidate
            speed_error = target_ias-ias
            candidate = clamp(self.power_i+speed_error*.0015*dt*10., -.35, .35)
            trial = p.cruise_base_throttle+speed_error*.020+candidate
            if .12 < trial < 1. or (trial >= 1 and candidate < self.power_i) or (trial <= .12 and candidate > self.power_i):
                self.power_i = candidate
            throttle = clamp(p.cruise_base_throttle+speed_error*.020+self.power_i, .12, 1.)
        pitch = clamp((pitch_target-v["pitch_deg"])*.09-v["pitch_rate_dps"]*.030, -.4, .45)
        self.trim = clamp(self.trim+clamp(pitch*.35*dt, -.06*dt, .06*dt), -.6, .6)
        yaw = clamp(.07*throttle*(100./max(ias, 40.))**2+roll*.25-v["beta_deg"]*.045, -.35, .35)
        flap = (p.ils_flap_ratio if self.stage == "ils" and target_ias <= p.ils_final_kias and ias <= p.ils_final_kias+5
                else p.missed_flap_ratio if self.stage == "missed_runway" and v["vvi_fpm"] < 200
                else 0.)
        command = {"roll": roll, "pitch": pitch, "yaw": yaw, "throttle": throttle,
                   "flap": flap, "trim": self.trim, "brake": 0.}
        self.prop_law.add_to(command, v, allow_cruise=self.stage in CRUISE_PROP_STAGES)
        self.last_diagnostics = {"stage": self.stage, "target_true_deg": target_true,
                                 "target_alt_ft": target_alt, "target_kias": target_ias,
                                 "distance_nm": distance, "heading_error_deg": heading_error,
                                 "nav1_hdef_dots": v["nav1_hdef_dots"],
                                 "nav1_vdef_dots": v["nav1_vdef_dots"],
                                 "target_vvi_fpm": target_vvi if self.stage == "ils" else None,
                                 "filtered_vvi_fpm": self.vvi_lp if self.stage == "ils" else None,
                                 "ils_pitch_i_deg": self.ils_pitch_i if self.stage == "ils" else None}
        return command
