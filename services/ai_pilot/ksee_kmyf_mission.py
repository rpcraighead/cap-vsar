"""Attended KSEE Mission Bay Two and KMYF ILS 28R guidance.

Waypoints and crossing altitudes are transcribed from the FAA 2610 charts;
the simulator's installed CIFP is older and is checked separately in evidence.
"""
from __future__ import annotations

import math

from .landing_trial import LandingController
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
          "bakel_vector", "mibby", "nesty", "penyy", "ils", "landing",
          "missed_runway", "missed_270", "carif_inbound", "retry_bakel")


def clamp(x, low, high):
    return min(max(x, low), high)


def wrap180(x):
    return (x + 180) % 360 - 180


def bearing_distance(lat, lon, target):
    n = (target[0]-lat)*111132.92
    e = (target[1]-lon)*111412.84*math.cos(math.radians(lat))
    return math.degrees(math.atan2(e, n)) % 360, math.hypot(n, e)/1852


class MissionController:
    def __init__(self, stage="runway_climb"):
        if stage not in STAGES:
            raise ValueError("Unknown mission stage")
        self.stage = stage
        self.last_sim = None
        self.trim = None
        self.alt_i = 0.
        self.power_i = 0.
        self.vvi_lp = None
        self.ils_pitch_i = 0.
        self.landing = LandingController("KMYF 28R")
        self.last_diagnostics = {}
        self.transitions = []

    def _advance(self, new, v):
        self.transitions.append({"from": self.stage, "to": new,
                                 "sim_time_s": v["sim_time_s"],
                                 "lat": v["latitude_deg"], "lon": v["longitude_deg"],
                                 "altitude_ft": v["altitude_indicated_ft"]})
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
        target_true = v["heading_true_deg"]
        target_alt = 5000.
        target_ias = 100.
        distance = None
        if self.stage == "runway_climb":
            target_true = 281.
            target_ias = 74.
            if alt >= 790:
                self._advance("pgy_intercept", v)
        if self.stage == "pgy_intercept":
            target_true = (62.+variation)%360
            target_ias = 74. if alt < 2000 else 85.
            # Cross the PGY R-348 north of the PGY10 fix, allowing turn lead.
            if lon >= -116.9727 and lat >= 32.831:
                self._advance("pgy_inbound", v)
        if self.stage == "pgy_inbound":
            target_true, distance = bearing_distance(lat, lon, PGY10)
            target_ias = 74. if alt < 2000 else 85.
            if distance <= .35 or lat < PGY10[0]:
                self._advance("mzb_inbound", v)
        if self.stage == "mzb_inbound":
            target_true, distance = bearing_distance(lat, lon, MZB)
            target_ias = 74. if alt < 2000 else 85.
            if distance <= .55:
                if alt < 4800:
                    raise ValueError("MZB reached before 5000-foot climb gate")
                self._advance("bakel_vector", v)
        if self.stage == "bakel_vector":
            target_true, distance = bearing_distance(lat, lon, BAKEL)
            target_ias = 100.
            if distance <= .55:
                self._advance("mibby", v)
        if self.stage == "missed_runway":
            target_true = RUNWAY.heading_true_deg
            target_alt, target_ias = 3000., 74.
            if alt >= 1100:
                self._advance("missed_270", v)
        if self.stage == "missed_270":
            target_true = (270.+variation)%360
            target_alt, target_ias = 3500., 74.
            # Pilot-directed simulated vector replaces the published CARIF
            # segment once established in the climb at 3500 ft.
            if alt >= 3500:
                self._advance("retry_bakel", v)
        if self.stage == "carif_inbound":
            target_true, distance = bearing_distance(lat, lon, CARIF)
            target_alt, target_ias = 3000., 95.
            if distance <= .55:
                self._advance("retry_bakel", v)
        if self.stage == "retry_bakel":
            target_true, distance = bearing_distance(lat, lon, BAKEL)
            target_alt, target_ias = 5000., 85. if alt < 4800 else 100.
            if distance <= .55:
                self._advance("mibby", v)
        if self.stage == "mibby":
            target_true, distance = bearing_distance(lat, lon, MIBBY)
            # First pass undershot 4200 by ~80 ft; retain a 100-ft margin.
            target_alt, target_ias = 4300., 100.
            if distance <= .35:
                self._advance("nesty", v)
        if self.stage == "nesty":
            target_true, distance = bearing_distance(lat, lon, NESTY)
            # Keep a 100-ft margin above the charted 3600-ft segment floor;
            # the first descent demonstrated roughly 70 ft of undershoot.
            target_alt, target_ias = 3750., 95.
            if distance <= .35:
                self._advance("penyy", v)
        if self.stage == "penyy":
            target_true, distance = bearing_distance(lat, lon, PENYY)
            target_alt, target_ias = 2650., 90.
            if distance <= .3:
                if v["nav1_frequency_10khz"] != 11195 or not v["nav1_lateral_valid"] or v["nav1_glideslope_flag"]:
                    raise ValueError("ILS signal not established at PENYY")
                self._advance("ils", v)
        if self.stage == "ils":
            along, cross = RUNWAY.coordinates(lat, lon)
            remaining_nm = max(0., -along/1852)
            target_true = RUNWAY.heading_true_deg-clamp(cross*.12, -12., 12.)
            target_alt = RUNWAY.airport_elev_ft + (RUNWAY.aimpoint_m-along)*math.tan(math.radians(3.))*3.28084
            target_ias = 80. if remaining_nm > 3 else 73.
            if remaining_nm <= 1.2:
                if (abs(cross)>90 or abs(v["nav1_hdef_dots"])>1.
                        or abs(v["nav1_vdef_dots"])>1. or v["nav1_glideslope_flag"]):
                    raise ValueError("ILS unstable at 1.2 NM; missed approach required")
                self._advance("landing", v)
        if self.stage == "landing":
            command = self.landing.step(snapshot)
            self.last_diagnostics = {"stage": self.stage, **self.landing.last_commands,
                                     "nav1_hdef_dots": v["nav1_hdef_dots"],
                                     "nav1_vdef_dots": v["nav1_vdef_dots"]}
            return command
        heading_error = wrap180(target_true-v["heading_true_deg"])
        bank_target = clamp(heading_error*1.1, -20., 20.)
        roll = clamp((bank_target-v["roll_deg"])*.020-v["roll_rate_dps"]*.022, -.35, .35)
        if (self.stage in ("runway_climb", "pgy_intercept", "pgy_inbound", "mzb_inbound") and alt < 4800
                or self.stage == "missed_runway"
                or self.stage == "missed_270" and alt < 3450
                or self.stage == "retry_bakel" and alt < 4800):
            target_ias = 74. if alt < 2000 or self.stage.startswith("missed_") else 85.
            pitch_target = clamp(7.+.4*(ias-target_ias), 3., 12.)
            throttle = 1.
        elif self.stage == "ils":
            if not v["nav1_lateral_valid"] or v["nav1_glideslope_flag"]:
                raise ValueError("ILS signal lost on final")
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
            throttle = clamp(.48+speed_error*.02+self.power_i, .05, .75)
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
            trial = .55+speed_error*.020+candidate
            if .12 < trial < 1. or (trial >= 1 and candidate < self.power_i) or (trial <= .12 and candidate > self.power_i):
                self.power_i = candidate
            throttle = clamp(.55+speed_error*.020+self.power_i, .12, 1.)
        pitch = clamp((pitch_target-v["pitch_deg"])*.09-v["pitch_rate_dps"]*.030, -.4, .45)
        self.trim = clamp(self.trim+clamp(pitch*.35*dt, -.06*dt, .06*dt), -.6, .6)
        yaw = clamp(.07*throttle*(100./max(ias, 40.))**2+roll*.25-v["beta_deg"]*.045, -.35, .35)
        flap = (1/3 if self.stage == "ils" and target_ias <= 80 and ias <= 85
                else 1/3 if self.stage == "missed_runway" and v["vvi_fpm"] < 200
                else 0.)
        command = {"roll": roll, "pitch": pitch, "yaw": yaw, "throttle": throttle,
                   "flap": flap, "trim": self.trim, "brake": 0.}
        self.last_diagnostics = {"stage": self.stage, "target_true_deg": target_true,
                                 "target_alt_ft": target_alt, "target_kias": target_ias,
                                 "distance_nm": distance, "heading_error_deg": heading_error,
                                 "nav1_hdef_dots": v["nav1_hdef_dots"],
                                 "nav1_vdef_dots": v["nav1_vdef_dots"],
                                 "target_vvi_fpm": target_vvi if self.stage == "ils" else None,
                                 "filtered_vvi_fpm": self.vvi_lp if self.stage == "ils" else None,
                                 "ils_pitch_i_deg": self.ils_pitch_i if self.stage == "ils" else None}
        return command
