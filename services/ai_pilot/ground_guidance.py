"""Bounded taxi actuator guidance behind the TaxiCoordinator's authority gate.

Coordinates are a surveyed/local scenario map in metres, east and north. The
map must be checked against the installed airport and runway/hold-line geometry
before any live use. This module never creates movement authority or a route.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .taxi import TaxiCoordinator, TaxiRoute


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def wrap180(angle: float) -> float:
    return (angle + 180) % 360 - 180


@dataclass(frozen=True)
class TaxiPoint:
    east_m: float
    north_m: float

    def __post_init__(self):
        if not math.isfinite(self.east_m) or not math.isfinite(self.north_m):
            raise ValueError("taxi point coordinates must be finite")


@dataclass(frozen=True)
class GroundObservation:
    east_m: float
    north_m: float
    heading_true_deg: float
    groundspeed_mps: float
    on_ground: bool
    paused: bool

    def __post_init__(self):
        values = (self.east_m, self.north_m, self.heading_true_deg,
                  self.groundspeed_mps)
        if any(not math.isfinite(v) for v in values) or self.groundspeed_mps < 0:
            raise ValueError("ground observation must be finite and nonnegative")


@dataclass(frozen=True)
class GroundCommand:
    yaw: float = 0.
    throttle: float = 0.
    brake: float = 0.
    reason: str = "hold"

    def actuator_frame(self, trim: float = 0.) -> dict[str, float]:
        if not math.isfinite(trim) or not -.6 <= trim <= .6:
            raise ValueError("trim outside taxi trial envelope")
        return {"roll": 0., "pitch": 0., "yaw": self.yaw,
                "throttle": self.throttle, "flap": 0., "trim": trim,
                "brake": self.brake}


class TaxiGuidance:
    """Stop at each named point; never cross a corridor or authority boundary."""

    def __init__(self, coordinator: TaxiCoordinator, route: TaxiRoute,
                 points: dict[str, TaxiPoint], corridor_half_width_m: float = 5.):
        if coordinator.route != route:
            raise ValueError("coordinator must own this route")
        if not 2 <= corridor_half_width_m <= 10:
            raise ValueError("taxi corridor width outside trial envelope")
        if any(leg.start not in points or leg.end not in points
               for leg in route.legs):
            raise ValueError("every taxi route endpoint needs surveyed coordinates")
        if any(not 3 <= math.hypot(points[leg.end].east_m-points[leg.start].east_m,
                                   points[leg.end].north_m-points[leg.start].north_m)
               <= 600 for leg in route.legs):
            raise ValueError("taxi route segment length outside trial envelope")
        self.coordinator = coordinator
        self.route = route
        self.points = dict(points)
        self.corridor_half_width_m = corridor_half_width_m
        self.fault: str | None = None

    def step(self, o: GroundObservation) -> GroundCommand:
        if o.paused:
            return GroundCommand(reason="simulator paused")
        if not o.on_ground:
            self.fault = "taxi controller observed aircraft airborne"
        if o.groundspeed_mps > 8:
            self.fault = "taxi overspeed"
        if self.fault:
            return GroundCommand(brake=.35, reason=self.fault)
        directive = self.coordinator.directive()
        if directive.action not in ("taxi", "cross_runway"):
            return GroundCommand(brake=.35, reason=directive.reason)
        leg = self.coordinator._current_leg()
        a, b = self.points[leg.start], self.points[leg.end]
        dx, dy = b.east_m-a.east_m, b.north_m-a.north_m
        length = math.hypot(dx, dy)
        px, py = o.east_m-a.east_m, o.north_m-a.north_m
        along = (px*dx+py*dy)/length
        cross = (px*dy-py*dx)/length
        remaining = length-along
        if abs(cross) > self.corridor_half_width_m or along < -5 or remaining < -2:
            self.fault = "outside surveyed taxi corridor"
            return GroundCommand(brake=.35, reason=self.fault)
        if remaining <= 2 and o.groundspeed_mps <= .5:
            self.coordinator.complete_leg()
            return GroundCommand(brake=.35, reason="taxi point reached; stop")
        if remaining <= 2:
            return GroundCommand(brake=.35, reason="brake at taxi point")
        desired_speed = min(4., math.sqrt(2*1.0*max(0., remaining-2)))
        if o.groundspeed_mps > desired_speed:
            return GroundCommand(brake=clamp(.12*(o.groundspeed_mps-desired_speed),
                                             .05, .35), reason="decelerate before taxi point")
        target_heading = math.degrees(math.atan2(dx, dy)) % 360
        heading_error = wrap180(target_heading-o.heading_true_deg)
        if abs(heading_error) > 45:
            self.fault = "taxi heading outside capture envelope"
            return GroundCommand(brake=.35, reason=self.fault)
        yaw = clamp(.025*heading_error-.06*cross, -.4, .4)
        throttle = clamp(.07+.05*(desired_speed-o.groundspeed_mps), 0., .22)
        return GroundCommand(yaw=yaw, throttle=throttle,
                             reason=directive.action)
