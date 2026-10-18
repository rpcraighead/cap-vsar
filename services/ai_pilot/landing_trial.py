"""Bounded landing controller and independent engineering observer.

Flown on the stock C172 (the default `AircraftProfile`); the C182T profile
supplies that aircraft's speeds and acceptance windows to the same laws.
"""
from __future__ import annotations

import math

from .aircraft_profiles import AircraftProfile
from .prop_law import FULL
from xplane.capvsar_landing import GLIDEPATH_AIMPOINT_M, RUNWAYS

# The unflared glidepath intersects 25 ft beyond the displaced threshold.
TOUCHDOWN_MIN_M = GLIDEPATH_AIMPOINT_M
TOUCHDOWN_MAX_M = GLIDEPATH_AIMPOINT_M + 400. * .3048


def clamp(x, a, b):
    return min(max(x, a), b)


def wrap180(x):
    return (x + 180) % 360 - 180


class LandingController:
    def __init__(self, runway="KMYF 28R", *, profile: AircraftProfile):
        self.runway = RUNWAYS[runway]
        self.profile = profile
        self.start_sim = None
        self.last_sim = None
        self.last_throttle = profile.approach_base_throttle - .04
        self.power_i = 0.
        self.speed_pitch_i = 0.
        self.trim = None
        self.phase = "approach"
        self.touchdown_sim = None
        self.flare_started_sim = None
        self.flare_entry_pitch = None
        self.last_pitch_target = None
        self.last_commands = {}
        self.last_cross = None
        self.cross_rate_mps = 0.
        self.last_heading = None
        self.heading_rate_dps = 0.
        self.heading_i = 0.
        self.last_vvi = None
        self.vvi_rate_fpmps = 0.
        self.last_air_roll = 0.
        self.touchdown_aileron = 0.

    def step(self, snapshot):
        runway_coordinates = self.runway.coordinates
        HEADING_TRUE_DEG = self.runway.heading_true_deg
        GLIDEPATH_AIMPOINT_M = self.runway.aimpoint_m
        AIRPORT_ELEV_FT = self.runway.airport_elev_ft
        v = snapshot["values"]
        sim = v["sim_time_s"]
        if self.start_sim is None:
            self.start_sim = sim
        dt = .05 if self.last_sim is None else clamp(sim - self.last_sim, .005, .15)
        self.last_sim = sim
        along, cross = runway_coordinates(v["latitude_deg"], v["longitude_deg"])
        if self.last_cross is not None:
            raw_cross_rate = clamp((cross - self.last_cross) / dt, -15., 15.)
            alpha = clamp(dt / .5, 0., 1.)
            self.cross_rate_mps += alpha * (raw_cross_rate - self.cross_rate_mps)
        self.last_cross = cross
        if self.last_heading is not None:
            raw_heading_rate = clamp(wrap180(v["heading_true_deg"] - self.last_heading) / dt,
                                     -30., 30.)
            self.heading_rate_dps += clamp(dt / .3, 0., 1.) * (raw_heading_rate - self.heading_rate_dps)
        self.last_heading = v["heading_true_deg"]
        if self.last_vvi is not None:
            raw_vvi_rate = clamp((v["vvi_fpm"] - self.last_vvi) / dt, -500., 500.)
            self.vvi_rate_fpmps += clamp(dt / .5, 0., 1.) * (raw_vvi_rate - self.vvi_rate_fpmps)
        self.last_vvi = v["vvi_fpm"]
        left_crosswind_mps = (v["wind_mps"] *
                              math.sin(math.radians(wrap180(HEADING_TRUE_DEG -
                                                          v["wind_from_true_deg"]))))
        crosswind = abs(left_crosswind_mps) > .5
        agl_ft = v["agl_m"] * 3.28084
        gs_kt = v["groundspeed_mps"] * 1.94384
        if v["on_ground"]:
            if self.touchdown_sim is None:
                self.touchdown_sim = sim
                self.touchdown_aileron = self.last_air_roll
            self.phase = "rollout"
        elif agl_ft < self.profile.flare_start_agl_ft and along > -50:
            if self.flare_started_sim is None:
                self.flare_started_sim = sim
                self.flare_entry_pitch = self.last_pitch_target if self.last_pitch_target is not None else v["pitch_deg"]
            self.phase = "flare"
        elif self.phase != "flare":
            self.phase = "approach"

        if self.phase == "rollout":
            # Carry the airborne rudder bias briefly through wheel contact,
            # then shed it as nosewheel steering takes over.
            self.heading_i *= max(0., 1. - dt / 1.5)
            # Brake only after main gear contact and some nosewheel-settling time.
            # Toe-brake readback now confirms effective C182T braking, so the
            # earlier .32 ramp is sufficient and keeps the C172 path moderate.
            brake = clamp((sim - self.touchdown_sim - .7) / 2., 0., .32)
            if gs_kt < 4:
                brake = .25
            heading_error = wrap180(HEADING_TRUE_DEG - v["heading_true_deg"])
            if crosswind:
                # At taxi speed beta is dominated by the crosswind and
                # becomes a poor steering signal. Keep the nosewheel/rudder
                # on runway heading while holding aileron into wind.
                yaw = clamp(heading_error * .05 - self.heading_rate_dps * .015
                            + self.heading_i - cross * .015
                            - self.cross_rate_mps * .020, -.55, .55)
            else:
                yaw = clamp(heading_error * .02 - cross * .010
                            - v["beta_deg"] * .015, -.25, .25)
            if crosswind:
                # Keep the touchdown input continuous. As speed falls, the
                # ailerons lose authority, so progressively increase input
                # into the wind rather than stepping it at wheel contact.
                windward = -1. if left_crosswind_mps > 0 else 1.
                entry = clamp(windward * self.touchdown_aileron, .04, .30)
                slow_fraction = clamp((55. - gs_kt) / 53., 0., 1.)
                rollout_roll = windward * (entry + (.30 - entry) * slow_fraction)
            else:
                rollout_roll = clamp(-v["roll_deg"] * .015, -.2, .2)
            controls = {"roll": rollout_roll,
                        "pitch": .08, "yaw": yaw, "throttle": 0., "flap": 1.,
                        "trim": clamp(snapshot["controls"]["trim"], -.6, .6), "brake": brake}
        else:
            # Flap stages by distance and speed from the profile (C172: 10 deg,
            # 20 by 1 NM, 30 by 0.5 NM; the C182T package shares the detents).
            flap = self.profile.landing_flap_ratio(along, v["kias"])
            target_speed = (self.profile.final_approach_kias
                            + self.profile.final_speed_add_kias * clamp((-along - 900.) / 900., 0., 1.))
            # Runway cross-track is positive to the RIGHT. A left
            # displacement therefore needs a positive (right) heading change.
            if crosswind:
                # Wing-low slip: aileron into wind holds ground track and
                # centerline; rudder independently aligns the fuselage with
                # the runway through flare, contact and rollout.
                # The stock C172 needs less right bank for a wind from the
                # right: excess bank increases slip and rudder demand there.
                wind_bank_gain = 1.05 if left_crosswind_mps >= 0 else .85
                cross_bank_gain = .60 if left_crosswind_mps >= 0 else .50
                bank_target = clamp(-left_crosswind_mps * wind_bank_gain - cross * cross_bank_gain
                                    - self.cross_rate_mps * 1.8, -10., 10.)
                roll = clamp((bank_target - v["roll_deg"]) * .035
                             - v["roll_rate_dps"] * .022, -.3, .3)
                heading_error = wrap180(HEADING_TRUE_DEG - v["heading_true_deg"])
            else:
                heading_target = HEADING_TRUE_DEG - clamp(cross * .15, -8., 8.)
                heading_error = wrap180(heading_target - v["heading_true_deg"])
                bank_target = clamp(heading_error * 1.1, -12., 12.)
                roll = clamp((bank_target - v["roll_deg"]) * .020
                             - v["roll_rate_dps"] * .022, -.3, .3)
            if self.phase == "approach":
                # Continue the 3-degree line over the physical threshold.
                # Its zero-height intersection is the specified aimpoint.
                target_alt_ft = (AIRPORT_ELEV_FT +
                                 (GLIDEPATH_AIMPOINT_M - along) *
                                 math.tan(math.radians(3.)) * 3.28084)
                alt_error_ft = target_alt_ft - v["altitude_msl_m"] * 3.28084
                desired_vvi = clamp(-390. + alt_error_ft * 2., -750., 0.)
                speed_error = target_speed - v["kias"]
                if sim - self.start_sim < 2.:
                    # Indicated airspeed warms up from zero after a paused
                    # reposition. Truth TAS is already near 70 kt; hold the
                    # reset controls until the instrument settles.
                    pitch_target = v["pitch_deg"]
                    throttle = self.profile.approach_base_throttle - .04
                else:
                    # Pilot technique: pitch for indicated airspeed, power for
                    # the glidepath. Above path => reduce power. The vertical
                    # speed term anticipates the path response without asking
                    # the elevator to chase an altitude error.
                    candidate_speed_i = clamp(self.speed_pitch_i - speed_error * .015 * dt,
                                              -3., 3.)
                    raw_pitch = 2. - speed_error * 1.0 + candidate_speed_i
                    if (-5. < raw_pitch < 8. or
                            (raw_pitch <= -5. and candidate_speed_i > self.speed_pitch_i) or
                            (raw_pitch >= 8. and candidate_speed_i < self.speed_pitch_i)):
                        self.speed_pitch_i = candidate_speed_i
                    pitch_target = clamp(2. - speed_error * 1.0 + self.speed_pitch_i, -5., 8.)
                    candidate_i = clamp(self.power_i + alt_error_ft * .00016 * dt, -.25, .25)
                    base = self.profile.approach_base_throttle
                    raw_power = (base + alt_error_ft * .004
                                 + (desired_vvi - v["vvi_fpm"]) * .0001 + candidate_i)
                    if (0. < raw_power < .65 or
                            (raw_power >= .65 and candidate_i < self.power_i) or
                            (raw_power <= 0. and candidate_i > self.power_i)):
                        self.power_i = candidate_i
                    raw_power = clamp(base + alt_error_ft * .004
                                      + (desired_vvi - v["vvi_fpm"]) * .0001 + self.power_i,
                                      0., .65)
                    throttle = clamp(raw_power, self.last_throttle - .25 * dt,
                                     self.last_throttle + .25 * dt)
                self.last_throttle = throttle
            else:
                # Ease the pitch transition so the initial flare does not
                # balloon. Reduce power promptly but at a bounded rate; the
                # old slow power ramp held approach power as pitch increased.
                target_alt_ft = AIRPORT_ELEV_FT
                alt_error_ft = target_alt_ft - v["altitude_msl_m"] * 3.28084
                desired_vvi = clamp(-120. - agl_ft * 5., -300., -100.)
                progress = clamp((sim - self.flare_started_sim) / 4.5, 0., 1.)
                blend = progress * progress * (3. - 2. * progress)
                # The last ~two seconds start around 10 ft AGL in these
                # trials. Keep increasing the nose-up request as the ground
                # approaches instead of holding a nearly flat attitude.
                late_flare = clamp((10. - agl_ft) / 10., 0., 1.)
                flare_pitch = clamp(5.5 + (desired_vvi - v["vvi_fpm"]) * .020
                                    - clamp(self.vvi_rate_fpmps, 0., 250.) * .015
                                    + 4.5 * late_flare, 0., 12.)
                pitch_target = (1. - blend) * self.flare_entry_pitch + blend * flare_pitch
                target_power = clamp(.10 * (agl_ft / 50.), 0., .10)
                throttle = clamp(target_power, self.last_throttle - .24 * dt,
                                 self.last_throttle + .24 * dt)
                self.last_throttle = throttle
            self.last_pitch_target = pitch_target
            pitch = clamp((pitch_target - v["pitch_deg"]) * .11
                          - v["pitch_rate_dps"] * .030, -.4,
                          .45 if self.phase == "flare" else .4)
            if self.trim is None:
                self.trim = clamp(snapshot["controls"]["trim"], -.6, .6)
            if self.phase == "approach":
                change = clamp(pitch * .35 * dt, -.06 * dt, .06 * dt)
                self.trim = clamp(self.trim + change, -.6, .6)
            elif self.trim < -.10:
                # Speed-on-pitch approach trim is nose-down. Unload it slowly
                # during the flare so the yoke can keep raising the nose.
                self.trim = min(-.10, self.trim + .06 * dt)
            if crosswind:
                self.heading_i = clamp(self.heading_i + heading_error * .012 * dt,
                                       -.50, .50)
                # A wing-low landing intentionally carries sideslip. Rudder
                # follows runway heading; beta must not cancel that command.
                yaw = clamp(heading_error * .070 - self.heading_rate_dps * .018
                            + self.heading_i
                            + left_crosswind_mps * .025
                            + .07 * throttle * (100. / max(v["kias"], 40.)) ** 2,
                            -1., .75)
            else:
                yaw = clamp(.07 * throttle * (100. / max(v["kias"], 40.)) ** 2
                            + roll * .25 - v["beta_deg"] * .045, -.3, .3)
            controls = {"roll": roll, "pitch": pitch, "yaw": yaw,
                        "throttle": throttle, "flap": flap,
                        "trim": self.trim, "brake": 0.}
            self.last_air_roll = roll
        if self.profile.constant_speed_prop:
            controls["prop"] = FULL     # prop high for landing and any go-around
        self.last_commands = {"phase": self.phase, "along_m": along, "cross_m": cross,
                              "agl_ft": agl_ft, "groundspeed_kt": gs_kt,
                              "target_kias": target_speed if self.phase != "rollout" else 0.,
                              "flap_command": controls["flap"],
                              "left_crosswind_mps": left_crosswind_mps,
                              "cross_rate_mps": self.cross_rate_mps,
                              "heading_error_deg": wrap180(HEADING_TRUE_DEG - v["heading_true_deg"]),
                              "target_altitude_ft": target_alt_ft if self.phase != "rollout" else None,
                              "desired_vvi_fpm": desired_vvi if self.phase != "rollout" else None}
        return controls


class LandingObserver:
    """Scores measured runway position, touchdown, braking and complete stop."""
    def __init__(self, wind_speed_kt=0., wind_from_offset_deg=0., runway="KMYF 28R",
                 *, profile: AircraftProfile):
        self.runway = RUNWAYS[runway]
        self.profile = profile
        self.wind_speed_kt = wind_speed_kt
        self.wind_from_true_deg = (self.runway.heading_true_deg + wind_from_offset_deg) % 360.
        self.wind_side = (-1 if wind_from_offset_deg < -1 else
                          1 if wind_from_offset_deg > 1 else 0)
        self.previous = None
        self.first_sim = None
        self.session = None
        self.aircraft = None
        self.samples = 0
        self.touchdown = None
        self.last_air_pitch_deg = None
        self.last_air_heading_deg = None
        self.last_air_roll_deg = None
        self.threshold = None
        self.flap_stages = set()
        self.max_brake = 0.
        self.brake_readback_max = [0., 0.]
        self.rollout_decelerations = []
        self.last_rollout_speed = None
        self.braked_samples = 0
        self.flare_aileron_samples = 0
        self.rollout_aileron_samples = 0
        self.flare_low_agl_ft = None
        self.max_flare_rebound_ft = 0.
        self.max_rollout_heading_error_deg = 0.
        self.outcome = "INCOMPLETE"
        self.reason = None
        self.last = None

    def fail(self, reason):
        self.outcome, self.reason = "FAIL", reason
        return self.report()

    def observe(self, s):
        if self.outcome != "INCOMPLETE":
            return self.report()
        runway_coordinates = self.runway.coordinates
        HEADING_TRUE_DEG = self.runway.heading_true_deg
        RUNWAY_LENGTH_M = self.runway.length_m
        TOUCHDOWN_MIN_M = self.runway.aimpoint_m
        TOUCHDOWN_MAX_M = TOUCHDOWN_MIN_M + 400. * .3048
        try:
            v, c = s["values"], s["controls"]
            wind_from = v.get("wind_from_true_deg", HEADING_TRUE_DEG if not self.wind_speed_kt else None)
            sim, wall, frame = v["sim_time_s"], s["wall_time_s"], s["frame"]
            if s["schema"] != "capvsar.telemetry.v1" or s["phase"] != "after_flight_model":
                return self.fail("Invalid snapshot provenance")
            if s["aircraft"]["name"] != self.profile.acf_name:
                return self.fail("Wrong aircraft")
            numbers = (sim, wall, v["latitude_deg"], v["longitude_deg"], v["agl_m"],
                       v["kias"], v["groundspeed_mps"], v["vvi_fpm"],
                       v["roll_deg"], v["pitch_deg"], v["brake_left"], v["brake_right"])
            numbers += (v["heading_true_deg"], v["wind_mps"], wind_from)
            if not all(type(x) in (int, float) and math.isfinite(x) for x in numbers):
                return self.fail("Invalid measured value")
            if self.previous:
                old_sim, old_wall, old_frame = self.previous
                if not (sim > old_sim and wall > old_wall and frame > old_frame):
                    return self.fail("Nonincreasing telemetry")
                if sim - old_sim > .25 or wall - old_wall > .5:
                    return self.fail("Telemetry gap")
            else:
                self.session, self.aircraft = s["session"], s["aircraft"]
                self.first_sim = sim
            if s["session"] != self.session or s["aircraft"] != self.aircraft:
                return self.fail("Aircraft or session changed")
            if v["paused"] or s["override_state"] is not True or s["ap_engaged"] is not False:
                return self.fail("Authority or pause changed")
            self.previous = sim, wall, frame
            self.samples += 1
            along, cross = runway_coordinates(v["latitude_deg"], v["longitude_deg"])
            gs_kt = v["groundspeed_mps"] * 1.94384
            agl_ft = v["agl_m"] * 3.28084
            self.last = {"sim_time_s": sim, "along_m": along, "cross_m": cross,
                         "agl_ft": agl_ft, "kias": v["kias"], "groundspeed_kt": gs_kt}
            if sim - self.first_sim > 6:
                expected = self.wind_speed_kt * .514444
                speed_ok = (v["wind_mps"] <= .5 if not self.wind_speed_kt else
                            expected * .5 <= v["wind_mps"] <= expected + 1.5)
                direction_ok = (not self.wind_speed_kt or
                                abs(wrap180(wind_from - self.wind_from_true_deg)) <= 6)
                if not speed_ok or not direction_ok:
                    return self.fail("Measured wind outside trial setting")
            if not v["on_ground"] and agl_ft < 17.5 and along > -50:
                self.flare_low_agl_ft = (agl_ft if self.flare_low_agl_ft is None else
                                         min(self.flare_low_agl_ft, agl_ft))
                self.max_flare_rebound_ft = max(self.max_flare_rebound_ft,
                                                agl_ft - self.flare_low_agl_ft)
                if self.max_flare_rebound_ft > 1.5:
                    return self.fail("Flare balloon exceeded 1.5 ft")
                if self.wind_speed_kt and self.wind_side * c["roll"] > .01:
                    self.flare_aileron_samples += 1
            actual_flap = v["flap_actual"]
            stage1, stage2, stage3 = self.profile.flap_stage_names
            if along < -1852 and .25 <= actual_flap <= .42:
                self.flap_stages.add(stage1)
            if -1852 <= along < -926 and .58 <= actual_flap <= .75:
                self.flap_stages.add(stage2)
            if -926 <= along <= 0 and actual_flap >= .90:
                self.flap_stages.add(stage3)
            if self.threshold is None and along >= 0:
                self.threshold = {**self.last, "flap_actual": actual_flap}
                low_kias, high_kias = self.profile.threshold_kias
                if not 20 <= agl_ft <= 85 or not low_kias <= v["kias"] <= high_kias:
                    return self.fail("Threshold height or final speed outside window")
                if actual_flap < .9 or self.flap_stages != {stage1, stage2, stage3}:
                    return self.fail("Flap schedule not observed")
            if abs(cross) > 80 or along < -2450 or along > RUNWAY_LENGTH_M + 10:
                return self.fail("Left landing corridor")
            if abs(v["roll_deg"]) > 25 or abs(v["pitch_deg"]) > 18:
                return self.fail("Excessive attitude")
            # X-Plane consumes brake_add during the flight model, so the
            # after-model dataref is normally zero. Score the simulator-side
            # readback taken immediately after the bridge wrote both brakes,
            # then use the independent groundspeed trace for stopping effect.
            a = s["actuator_readback"]
            if (a["bridge_state"] != "ACTIVE" or type(a["frame_sequence"]) is not int
                    or not 0 <= wall - a["wall_time_s"] <= .2):
                return self.fail("Stale or invalid native brake readback")
            brake = max(a["brake_left"], a["brake_right"])
            self.max_brake = max(self.max_brake, brake)
            self.brake_readback_max = [max(old, float(new)) for old, new in
                                       zip(self.brake_readback_max,
                                           (a["brake_left"], a["brake_right"]))]
            if (brake > .351 or abs(a["brake_left"] - a["brake_right"]) > .02
                    or (not v["on_ground"] and brake > .02)):
                return self.fail("Brake limit, symmetry or airborne braking violated")
            if self.touchdown is None and v["on_ground"]:
                self.touchdown = {**self.last, "vvi_fpm": v["vvi_fpm"], "frame": frame,
                                  "pre_touch_pitch_deg": self.last_air_pitch_deg,
                                  "pre_touch_heading_deg": self.last_air_heading_deg,
                                  "pre_touch_roll_deg": self.last_air_roll_deg,
                                  "wind_mps": v["wind_mps"],
                                  "wind_from_true_deg": wind_from}
                pitch_low, pitch_high = self.profile.touchdown_pitch_deg
                if (not TOUCHDOWN_MIN_M <= along <= TOUCHDOWN_MAX_M or abs(cross) > 4
                        or gs_kt > self.profile.touchdown_max_groundspeed_kt
                        or v["vvi_fpm"] < -600 or self.last_air_pitch_deg is None
                        or not pitch_low <= self.last_air_pitch_deg <= pitch_high):
                    return self.fail("Touchdown outside acceptance window")
                if (self.wind_speed_kt and self.wind_side and
                    (self.last_air_heading_deg is None or
                     abs(wrap180(HEADING_TRUE_DEG - self.last_air_heading_deg)) > 3 or
                     self.last_air_roll_deg is None or
                     self.wind_side * self.last_air_roll_deg <= 0 or
                     self.flare_aileron_samples < 10)):
                    return self.fail("Crosswind touchdown alignment not demonstrated")
            elif not v["on_ground"]:
                self.last_air_pitch_deg = v["pitch_deg"]
                self.last_air_heading_deg = v["heading_true_deg"]
                self.last_air_roll_deg = v["roll_deg"]
            if self.touchdown is not None:
                if v["on_ground"]:
                    if self.last_rollout_speed is not None:
                        old_sim, old_speed = self.last_rollout_speed
                        dt = sim - old_sim
                        if dt > 0 and brake >= .15:
                            deceleration = (old_speed - v["groundspeed_mps"]) / dt
                            if deceleration > 0:
                                self.rollout_decelerations.append(deceleration)
                    self.last_rollout_speed = (sim, v["groundspeed_mps"])
                if not v["on_ground"] and agl_ft > 3:
                    return self.fail("Bounced above 3 ft")
                if brake >= .15:
                    self.braked_samples += 1
                if self.wind_speed_kt and self.wind_side and v["on_ground"]:
                    if self.wind_side * c["roll"] > .01:
                        self.rollout_aileron_samples += 1
                    self.max_rollout_heading_error_deg = max(
                        self.max_rollout_heading_error_deg,
                        abs(wrap180(HEADING_TRUE_DEG - v["heading_true_deg"])))
                    if self.max_rollout_heading_error_deg > 5:
                        return self.fail("Crosswind rollout runway alignment lost")
                if v["on_ground"] and gs_kt <= 2:
                    if along > RUNWAY_LENGTH_M - 100 or abs(cross) > 4:
                        return self.fail("Stopped outside runway stop window")
                    if self.braked_samples < 10 or self.max_brake > .351:
                        return self.fail("Moderate braking not demonstrated")
                    if self.wind_speed_kt and self.wind_side and self.rollout_aileron_samples < 10:
                        return self.fail("Into-wind aileron not held through rollout")
                    self.outcome = "PASS"
        except (KeyError, TypeError, ValueError) as exc:
            return self.fail("Malformed landing snapshot: %s" % exc)
        return self.report()

    def report(self):
        ordered = sorted(self.rollout_decelerations)
        p90 = ordered[min(len(ordered)-1, int(.9*len(ordered)))] if ordered else None
        median = (ordered[len(ordered)//2] if len(ordered) % 2 else
                  (ordered[len(ordered)//2-1] + ordered[len(ordered)//2]) / 2
                  if ordered else None)
        return {"outcome": self.outcome, "reason": self.reason, "samples": self.samples,
                "threshold": self.threshold, "touchdown": self.touchdown, "last": self.last,
                "flap_stages": sorted(self.flap_stages),
                "max_brake": self.max_brake, "braked_samples": self.braked_samples,
                "brake_readback_max": {"left": self.brake_readback_max[0],
                                        "right": self.brake_readback_max[1]},
                "rollout_deceleration_mps2": {
                    "median": median,
                    "p90": p90, "samples": len(ordered)},
                "max_flare_rebound_ft": self.max_flare_rebound_ft,
                "flare_aileron_samples": self.flare_aileron_samples,
                "rollout_aileron_samples": self.rollout_aileron_samples,
                "max_rollout_heading_error_deg": self.max_rollout_heading_error_deg}
