"""Bounded D8-to-27R line-up guidance after specific runway authority."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .ground_guidance import GroundCommand, GroundObservation, TaxiPoint, clamp, wrap180
from .taxi import TaxiCoordinator, TaxiPhase


@dataclass(frozen=True)
class RunwayEntryGeometry:
    hold: TaxiPoint
    centerline_entry: TaxiPoint
    lineup: TaxiPoint
    heading_true_deg: float
    runway_width_m: float

    def __post_init__(self):
        if not math.isfinite(self.heading_true_deg) or not 25 <= self.runway_width_m <= 70:
            raise ValueError("runway geometry outside trial envelope")
        if not 25 <= math.hypot(self.centerline_entry.east_m-self.hold.east_m,
                                self.centerline_entry.north_m-self.hold.north_m) <= 100:
            raise ValueError("hold-to-centerline geometry invalid")
        if not 15 <= math.hypot(self.lineup.east_m-self.centerline_entry.east_m,
                                self.lineup.north_m-self.centerline_entry.north_m) <= 80:
            raise ValueError("line-up segment geometry invalid")


class RunwayEntryGuidance:
    def __init__(self, taxi: TaxiCoordinator, geometry: RunwayEntryGeometry,
                 runway: str = "27R"):
        self.taxi = taxi
        self.geometry = geometry
        self.runway = runway
        self.phase = "hold"
        self.fault: str | None = None

    def step(self, o: GroundObservation) -> GroundCommand:
        if o.paused:
            return GroundCommand(reason="simulator paused")
        if not o.on_ground or o.groundspeed_mps > 5:
            self.fault = "runway entry flight-state or speed fault"
        if self.fault:
            return GroundCommand(brake=.35, reason=self.fault)
        directive = self.taxi.directive()
        if self.phase == "complete":
            return GroundCommand(brake=.35, reason="lined up on 27R")
        if directive.action not in ("line_up_and_wait", "takeoff") or directive.runway != self.runway:
            return GroundCommand(brake=.35, reason="specific 27R entry authority required")
        p = TaxiPoint(o.east_m, o.north_m)
        if self.phase == "hold":
            if math.hypot(p.east_m-self.geometry.hold.east_m,
                          p.north_m-self.geometry.hold.north_m) > 4:
                self.fault = "aircraft not at surveyed D8 hold"
                return GroundCommand(brake=.35, reason=self.fault)
            self.phase = "enter"
        target = self.geometry.centerline_entry if self.phase == "enter" else self.geometry.lineup
        distance = math.hypot(target.east_m-p.east_m, target.north_m-p.north_m)
        if self.phase == "enter" and distance <= 5 and o.groundspeed_mps <= 1.5:
            self.phase = "lineup"
            target = self.geometry.lineup
            distance = math.hypot(target.east_m-p.east_m, target.north_m-p.north_m)
        if self.phase == "lineup":
            start = self.geometry.centerline_entry
            de = p.east_m-start.east_m
            dn = p.north_m-start.north_m
            cross = (de*math.cos(math.radians(self.geometry.heading_true_deg))
                     - dn*math.sin(math.radians(self.geometry.heading_true_deg)))
            if abs(cross) > self.geometry.runway_width_m/2-2:
                self.fault = "outside 27R runway width"
                return GroundCommand(brake=.35, reason=self.fault)
            heading_error = abs(wrap180(self.geometry.heading_true_deg-o.heading_true_deg))
            if distance <= 3 and o.groundspeed_mps <= .5 and heading_error <= 5:
                if self.taxi.phase is TaxiPhase.CLEARED_TO_LINE_UP:
                    self.taxi.mark_lined_up()
                self.phase = "complete"
                return GroundCommand(brake=.35, reason="27R lineup complete")
        else:
            a, b = self.geometry.hold, self.geometry.centerline_entry
            dx, dy = b.east_m-a.east_m, b.north_m-a.north_m
            cross = ((p.east_m-a.east_m)*dy-(p.north_m-a.north_m)*dx)/math.hypot(dx, dy)
            if abs(cross) > 8 or distance > 110:
                self.fault = "outside surveyed D8 runway entry corridor"
                return GroundCommand(brake=.35, reason=self.fault)
        if distance <= 3:
            return GroundCommand(brake=.35, reason="brake at 27R lineup point")
        desired_heading = math.degrees(math.atan2(target.east_m-p.east_m,
                                                  target.north_m-p.north_m)) % 360
        if self.phase == "enter" and distance < 12:
            corner = wrap180(self.geometry.heading_true_deg-desired_heading)
            desired_heading = (desired_heading + clamp((12-distance)/10, 0., 1.)*corner) % 360
        error = wrap180(desired_heading-o.heading_true_deg)
        if abs(error) > 115:
            self.fault = "runway entry heading outside capture"
            return GroundCommand(brake=.35, reason=self.fault)
        speed = min(2., math.sqrt(max(0., 2*(distance-3))))
        if abs(error) > 45:
            speed = min(speed, 1.)
        if o.groundspeed_mps > speed + .3:
            return GroundCommand(brake=clamp(.12*(o.groundspeed_mps-speed), .05, .35),
                                 reason="slow for 27R line-up")
        yaw = clamp(.025*error, -1., 1.)
        throttle = clamp(.16+.08*(speed-o.groundspeed_mps), 0., .28)
        return GroundCommand(yaw=yaw, throttle=throttle, reason=self.phase)
