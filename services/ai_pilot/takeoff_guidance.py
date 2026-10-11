"""Offline stock-C172 runway roll and initial-climb controller.

This controller is deliberately not wired to the live X-Plane bridge yet. A
surveyed runway frame, independent telemetry and a takeoff-mode bridge profile
are prerequisites for live control. Speeds come from the bundled X-Plane C172
pilot operating manual; the KSEE 27R climb-gradient gate is from FAA MZB2.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .taxi import TaxiCoordinator, TaxiPhase


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def wrap180(angle: float) -> float:
    return (angle + 180) % 360 - 180


@dataclass(frozen=True)
class TakeoffObservation:
    sim_time_s: float
    along_runway_m: float
    cross_runway_m: float
    heading_true_deg: float
    kias: float
    groundspeed_mps: float
    on_ground: bool
    agl_ft: float
    altitude_msl_ft: float
    climb_distance_nm: float
    pitch_deg: float
    pitch_rate_dps: float
    roll_deg: float
    engine_rpm: float
    flap_ratio: float
    paused: bool = False

    def __post_init__(self):
        numbers = (self.sim_time_s, self.along_runway_m, self.cross_runway_m,
                   self.heading_true_deg, self.kias, self.groundspeed_mps,
                   self.agl_ft, self.altitude_msl_ft, self.climb_distance_nm,
                   self.pitch_deg, self.pitch_rate_dps, self.roll_deg,
                   self.engine_rpm, self.flap_ratio)
        if any(not math.isfinite(x) for x in numbers):
            raise ValueError("takeoff observation must be finite")
        if min(self.kias, self.groundspeed_mps, self.agl_ft,
               self.climb_distance_nm, self.engine_rpm, self.flap_ratio) < 0:
            raise ValueError("takeoff observation has a negative physical quantity")


@dataclass(frozen=True)
class TakeoffCommand:
    roll: float = 0.
    pitch: float = 0.
    yaw: float = 0.
    throttle: float = 0.
    brake: float = 0.
    target_kias: float = 0.
    phase: str = "hold"
    reason: str = "hold"
    intervention_required: bool = False

    def actuator_frame(self, trim: float = 0.) -> dict[str, float]:
        if not math.isfinite(trim) or not -.6 <= trim <= .6:
            raise ValueError("trim outside takeoff trial envelope")
        return {"roll": self.roll, "pitch": self.pitch, "yaw": self.yaw,
                "throttle": self.throttle, "flap": 0., "trim": trim,
                "brake": self.brake}


class TakeoffGuidance:
    VR_KIAS = 55.
    VX_KIAS = 62.
    VY_KIAS = 74.
    MIN_GRADIENT_FT_PER_NM = 500.

    def __init__(self, taxi: TaxiCoordinator, *, runway: str,
                 runway_heading_true_deg: float, runway_length_m: float,
                 field_elevation_ft: float):
        if not runway.strip() or not math.isfinite(runway_heading_true_deg):
            raise ValueError("surveyed runway identification and heading required")
        if not 500 <= runway_length_m <= 4000:
            raise ValueError("runway length outside trial envelope")
        if not math.isfinite(field_elevation_ft):
            raise ValueError("field elevation must be finite")
        self.taxi = taxi
        self.runway = runway
        self.heading_true_deg = runway_heading_true_deg % 360
        self.runway_length_m = runway_length_m
        self.field_elevation_ft = field_elevation_ft
        self.phase = "hold"
        self.roll_start_s: float | None = None
        self.reason = "awaiting explicit takeoff authority"
        self.gradient_deficit = False

    def step(self, o: TakeoffObservation) -> TakeoffCommand:
        if o.paused:
            return TakeoffCommand(phase=self.phase, reason="simulator paused")
        if self.phase == "rejected":
            return TakeoffCommand(brake=1., phase="rejected", reason=self.reason,
                                  intervention_required=True)
        if self.phase == "hold":
            directive = self.taxi.directive()
            if (self.taxi.phase is not TaxiPhase.CLEARED_FOR_TAKEOFF
                    or directive.action != "takeoff" or directive.runway != self.runway):
                return TakeoffCommand(brake=.35, reason="takeoff clearance required")
            heading_error = wrap180(self.heading_true_deg-o.heading_true_deg)
            if (not o.on_ground or o.kias > 5 or o.groundspeed_mps > 3
                    or abs(o.cross_runway_m) > 3 or abs(heading_error) > 5
                    or not 0 <= o.along_runway_m <= self.runway_length_m-500
                    or o.flap_ratio > .05):
                return TakeoffCommand(brake=.35, reason="runway alignment or configuration invalid")
            self.phase = "roll"
            self.roll_start_s = o.sim_time_s
        if self.phase in ("roll", "rotate"):
            if not o.on_ground and o.agl_ft >= 4:
                self.taxi.mark_airborne()
                self.phase = "climb"
            else:
                if (abs(o.cross_runway_m) > 10
                        or abs(wrap180(self.heading_true_deg-o.heading_true_deg)) > 15
                        or o.along_runway_m > self.runway_length_m-100
                        or (o.sim_time_s-self.roll_start_s > 5 and o.engine_rpm < 1800)
                        or (o.sim_time_s-self.roll_start_s > 20 and o.kias < 25)):
                    self.phase = "rejected"
                    self.reason = "runway, engine, or acceleration gate failed"
                    return TakeoffCommand(brake=1., phase="rejected", reason=self.reason,
                                          intervention_required=True)
                if o.kias >= self.VR_KIAS:
                    self.phase = "rotate"
                heading_error = wrap180(self.heading_true_deg-o.heading_true_deg)
                yaw = clamp(.025*heading_error-.02*o.cross_runway_m, -.35, .35)
                target_pitch = 7. if self.phase == "rotate" else 1.
                pitch = clamp(.09*(target_pitch-o.pitch_deg)-.025*o.pitch_rate_dps,
                              -.2, .45)
                return TakeoffCommand(pitch=pitch, yaw=yaw, throttle=1.,
                                      target_kias=self.VR_KIAS, phase=self.phase,
                                      reason="runway roll and rotation")
        if self.phase == "climb":
            if o.on_ground and o.agl_ft < 2:
                self.phase = "rejected"
                self.reason = "aircraft returned to runway after liftoff"
                return TakeoffCommand(brake=1., phase="rejected", reason=self.reason,
                                      intervention_required=True)
            target = self.VX_KIAS if o.altitude_msl_ft < 2000 else self.VY_KIAS
            if .3 <= o.climb_distance_nm and o.altitude_msl_ft < 2000:
                achieved = (o.altitude_msl_ft-self.field_elevation_ft) / o.climb_distance_nm
                self.gradient_deficit |= achieved < self.MIN_GRADIENT_FT_PER_NM
            target_pitch = clamp(7.+.7*(target-o.kias), 2., 12.)
            pitch = clamp(.09*(target_pitch-o.pitch_deg)-.025*o.pitch_rate_dps,
                          -.25, .4)
            return TakeoffCommand(pitch=pitch, throttle=1., target_kias=target,
                                  phase="climb", reason="initial climb",
                                  intervention_required=self.gradient_deficit)
        raise AssertionError("unreachable takeoff state")
