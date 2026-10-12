"""Deterministic taxi policy for the AI Mission Pilot.

The conversational AI may propose or explain a taxi route.  It does not get to
infer movement authority.  This module owns the durable ground rules that must
survive model changes and ambiguous speech:

* at a towered airport, movement-area taxi and every runway crossing require
  explicit ATC authority;
* a taxi clearance never authorizes entry onto the departure runway;
* runway-crossing authority is specific to one runway and consumed when used;
* uncertainty means stop and request progressive taxi instructions; and
* after landing, the sortie is not complete until the crew taxis back to the
  starting point recorded at the beginning of the session.

Sources: FAA AIM 4-3-18 (Taxiing), 4-3-21 (Exiting the Runway After Landing),
AIM 2-3-5 (Holding Position Markings), and 14 CFR 91.129(i).  This is simulator
policy, not an assertion that the software is approved for real-aircraft use.

The module deliberately emits abstract directives.  An ArduPlane/MAVLink or
X-Plane adapter must translate them into bounded steering, throttle and braking
commands while retaining exclusive control ownership.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Surface(str, Enum):
    APRON = "apron"
    TAXIWAY = "taxiway"
    RUNWAY_CROSSING = "runway_crossing"


class RoutePurpose(str, Enum):
    OUTBOUND = "outbound"
    RETURN = "return"


class ClearanceSource(str, Enum):
    ATC = "atc"
    CREW_TRAFFIC_CHECK = "crew_traffic_check"


class TaxiPhase(str, Enum):
    PARKED = "parked"
    AWAITING_TAXI_CLEARANCE = "awaiting_taxi_clearance"
    TAXIING_OUT = "taxiing_out"
    HOLDING_SHORT_DEPARTURE = "holding_short_departure"
    CLEARED_TO_LINE_UP = "cleared_to_line_up"
    HOLDING_IN_POSITION = "holding_in_position"
    CLEARED_FOR_TAKEOFF = "cleared_for_takeoff"
    AIRBORNE = "airborne"
    RUNWAY_CLEAR_AWAITING_TAXI = "runway_clear_awaiting_taxi"
    TAXIING_RETURN = "taxiing_return"
    HOLDING_FOR_CLARIFICATION = "holding_for_clarification"
    RETURNED_TO_START = "returned_to_start"


@dataclass(frozen=True)
class TaxiLeg:
    start: str
    end: str
    surface: Surface = Surface.TAXIWAY
    runway: str | None = None

    def __post_init__(self) -> None:
        if not self.start.strip() or not self.end.strip():
            raise ValueError("taxi leg endpoints must be named")
        if self.start == self.end:
            raise ValueError("taxi leg must move between distinct points")
        if self.surface is Surface.RUNWAY_CROSSING and not self.runway:
            raise ValueError("runway crossing leg must identify the runway")
        if self.surface is not Surface.RUNWAY_CROSSING and self.runway is not None:
            raise ValueError("only runway crossing legs name a runway")


@dataclass(frozen=True)
class TaxiRoute:
    purpose: RoutePurpose
    legs: tuple[TaxiLeg, ...]

    def __post_init__(self) -> None:
        if not self.legs:
            raise ValueError("taxi route must contain at least one leg")
        for previous, current in zip(self.legs, self.legs[1:]):
            if previous.end != current.start:
                raise ValueError("taxi route legs must be contiguous")

    @property
    def start(self) -> str:
        return self.legs[0].start

    @property
    def destination(self) -> str:
        return self.legs[-1].end


@dataclass(frozen=True)
class TaxiDirective:
    action: str
    reason: str
    next_point: str | None = None
    runway: str | None = None
    request_progressive_taxi: bool = False


class TaxiCoordinator:
    """Own taxi authority and route state for one aircraft/session."""

    def __init__(self, start_point: str, towered: bool):
        if not start_point.strip():
            raise ValueError("starting point must be named")
        self.start_point = start_point
        self.position = start_point
        self.towered = bool(towered)
        self.phase = TaxiPhase.PARKED
        self._route: TaxiRoute | None = None
        self._leg_index = 0
        self._taxi_authorized = False
        self._crossing_runway: str | None = None
        self._departure_runway: str | None = None
        self._departure_action: str | None = None
        self._hold_reason = ""
        self._return_owed = False

    @property
    def route(self) -> TaxiRoute | None:
        return self._route

    def load_route(self, route: TaxiRoute) -> None:
        """Accept an AI/planner route only when it matches the physical session."""
        if route.start != self.position:
            raise ValueError("taxi route must begin at the aircraft's current position")
        if route.purpose is RoutePurpose.OUTBOUND:
            if self._return_owed:
                raise ValueError("return to recorded starting point is still required")
            if self.phase not in (TaxiPhase.PARKED, TaxiPhase.HOLDING_FOR_CLARIFICATION):
                raise ValueError("outbound route is not valid in the current phase")
        else:
            if self.phase not in (
                TaxiPhase.RUNWAY_CLEAR_AWAITING_TAXI,
                TaxiPhase.HOLDING_FOR_CLARIFICATION,
            ):
                raise ValueError("return route requires the aircraft to be clear of the runway")
            if route.destination != self.start_point:
                raise ValueError("return route must end at the recorded starting point")

        self._route = route
        self._leg_index = 0
        self._taxi_authorized = False
        self._crossing_runway = None
        self._hold_reason = ""
        self.phase = TaxiPhase.AWAITING_TAXI_CLEARANCE

    def authorize_taxi(self, source: ClearanceSource) -> None:
        """Record movement authority; it conveys no runway-entry authority."""
        if self.phase is not TaxiPhase.AWAITING_TAXI_CLEARANCE or self._route is None:
            raise ValueError("no taxi route is awaiting authorization")
        self._require_valid_source(source)
        self._taxi_authorized = True
        self.phase = (
            TaxiPhase.TAXIING_OUT
            if self._route.purpose is RoutePurpose.OUTBOUND
            else TaxiPhase.TAXIING_RETURN
        )

    def authorize_runway_crossing(
        self, runway: str, source: ClearanceSource
    ) -> None:
        """Authorize exactly the runway crossing that is immediately ahead."""
        if self.phase not in (TaxiPhase.TAXIING_OUT, TaxiPhase.TAXIING_RETURN):
            raise ValueError("aircraft is not taxiing")
        leg = self._current_leg()
        if leg.surface is not Surface.RUNWAY_CROSSING or leg.runway != runway:
            raise ValueError("authorization does not match the current crossing")
        self._require_valid_source(source)
        self._crossing_runway = runway

    def authorize_departure_runway(
        self,
        runway: str,
        source: ClearanceSource,
        *,
        takeoff: bool = False,
        line_up_and_wait: bool = False,
    ) -> None:
        """Record explicit runway entry authority, distinct from taxi clearance."""
        if self.phase not in (
            TaxiPhase.HOLDING_SHORT_DEPARTURE,
            TaxiPhase.HOLDING_IN_POSITION,
        ):
            raise ValueError("aircraft is not holding short of the departure runway")
        if takeoff == line_up_and_wait:
            raise PermissionError("explicit takeoff or line-up-and-wait authority is required")
        if self.phase is TaxiPhase.HOLDING_IN_POSITION:
            if line_up_and_wait:
                raise ValueError("aircraft is already lined up")
            if self._departure_runway != runway:
                raise ValueError("takeoff clearance runway does not match lined-up runway")
        self._require_valid_source(source)
        self._departure_runway = runway
        self._departure_action = "takeoff" if takeoff else "line_up_and_wait"
        self.phase = (
            TaxiPhase.CLEARED_FOR_TAKEOFF
            if takeoff
            else TaxiPhase.CLEARED_TO_LINE_UP
        )

    def mark_lined_up(self) -> None:
        """Record completion of line-up; the aircraft must still wait for takeoff."""
        if self.phase is not TaxiPhase.CLEARED_TO_LINE_UP:
            raise ValueError("line-up completion was not authorized")
        self._departure_action = None
        self.phase = TaxiPhase.HOLDING_IN_POSITION

    def directive(self) -> TaxiDirective:
        """Return the only ground action presently authorized."""
        if self.phase is TaxiPhase.AWAITING_TAXI_CLEARANCE:
            return TaxiDirective("hold", "awaiting taxi clearance")
        if self.phase is TaxiPhase.HOLDING_FOR_CLARIFICATION:
            return TaxiDirective(
                "hold",
                self._hold_reason or "taxi route uncertain",
                request_progressive_taxi=True,
            )
        if self.phase is TaxiPhase.HOLDING_SHORT_DEPARTURE:
            return TaxiDirective("hold", "departure runway entry is not authorized")
        if self.phase is TaxiPhase.CLEARED_TO_LINE_UP:
            return TaxiDirective(
                "line_up_and_wait",
                "explicit line-up-and-wait authority recorded",
                runway=self._departure_runway,
            )
        if self.phase is TaxiPhase.HOLDING_IN_POSITION:
            return TaxiDirective(
                "hold",
                "lined up; takeoff clearance not received",
                runway=self._departure_runway,
            )
        if self.phase is TaxiPhase.CLEARED_FOR_TAKEOFF:
            return TaxiDirective(
                self._departure_action or "hold",
                "explicit departure runway authority recorded",
                runway=self._departure_runway,
            )
        if self.phase is TaxiPhase.RUNWAY_CLEAR_AWAITING_TAXI:
            return TaxiDirective("hold", "runway clear; awaiting return taxi clearance")
        if self.phase in (TaxiPhase.PARKED, TaxiPhase.RETURNED_TO_START):
            return TaxiDirective("hold", "aircraft parked")
        if self.phase is TaxiPhase.AIRBORNE:
            return TaxiDirective("none", "aircraft airborne")
        if not self._taxi_authorized:
            return TaxiDirective("hold", "taxi movement is not authorized")

        leg = self._current_leg()
        if leg.surface is Surface.RUNWAY_CROSSING:
            if self._crossing_runway != leg.runway:
                return TaxiDirective(
                    "hold",
                    "explicit crossing authorization required for runway %s" % leg.runway,
                    next_point=leg.end,
                    runway=leg.runway,
                )
            return TaxiDirective(
                "cross_runway",
                "specific runway crossing authorization recorded",
                next_point=leg.end,
                runway=leg.runway,
            )
        return TaxiDirective("taxi", "route leg authorized", next_point=leg.end)

    def complete_leg(self) -> None:
        directive = self.directive()
        if directive.action not in ("taxi", "cross_runway"):
            raise PermissionError("current taxi leg is not authorized")
        leg = self._current_leg()
        self.position = leg.end
        if leg.surface is Surface.RUNWAY_CROSSING:
            # FAA runway crossings are issued one runway at a time.  Never let a
            # previous clearance bleed into the next route segment.
            self._crossing_runway = None
        self._leg_index += 1
        if self._route is not None and self._leg_index == len(self._route.legs):
            self._taxi_authorized = False
            if self._route.purpose is RoutePurpose.RETURN:
                self._return_owed = False
            self.phase = (
                TaxiPhase.HOLDING_SHORT_DEPARTURE
                if self._route.purpose is RoutePurpose.OUTBOUND
                else TaxiPhase.RETURNED_TO_START
            )

    def report_route_uncertain(self, reason: str) -> None:
        """Fail closed; the AI must never improvise pavement identity."""
        self._hold_reason = reason.strip() or "taxi route uncertain"
        self._taxi_authorized = False
        self._crossing_runway = None
        self.phase = TaxiPhase.HOLDING_FOR_CLARIFICATION

    def mark_airborne(self) -> None:
        """Record observed flight state; this method does not grant takeoff authority."""
        if self.phase is not TaxiPhase.CLEARED_FOR_TAKEOFF:
            raise PermissionError("airborne transition requires explicit takeoff authority")
        self._route = None
        self._taxi_authorized = False
        self._crossing_runway = None
        self._departure_action = None
        self.phase = TaxiPhase.AIRBORNE

    def mark_landed_and_runway_clear(self, exit_point: str) -> None:
        """Begin the mandatory return only after the whole aircraft is runway-clear."""
        if self.phase is not TaxiPhase.AIRBORNE:
            raise ValueError("landing transition requires an airborne session")
        if not exit_point.strip():
            raise ValueError("runway exit point must be named")
        self.position = exit_point
        self._route = None
        self._taxi_authorized = False
        self._return_owed = True
        self.phase = TaxiPhase.RUNWAY_CLEAR_AWAITING_TAXI

    def _current_leg(self) -> TaxiLeg:
        if self._route is None or self._leg_index >= len(self._route.legs):
            raise ValueError("no current taxi leg")
        return self._route.legs[self._leg_index]

    def _require_valid_source(self, source: ClearanceSource) -> None:
        if self.towered and source is not ClearanceSource.ATC:
            raise PermissionError("towered-airport movement authority must come from ATC")
        if not self.towered and source is not ClearanceSource.CREW_TRAFFIC_CHECK:
            raise PermissionError(
                "untowered movement requires a recorded crew traffic check"
            )
