"""Sourced phase envelopes; a runway exception never changes cruise limits."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .flight_executive import Phase
from .maneuvers import Limits


RUNWAY_PHASES = frozenset((Phase.TAKEOFF, Phase.LAND, Phase.ROLLOUT))
CRUISE_PHASES = frozenset((Phase.CLIMB, Phase.TRANSIT, Phase.SEARCH,
                           Phase.APPROACH, Phase.TEST))


@dataclass(frozen=True)
class RunwayCorridor:
    latitude_deg: float
    longitude_deg: float
    radius_m: float
    min_kias: float
    max_kias: float
    min_agl_ft: float
    max_bank_deg: float
    source: str

    def __post_init__(self):
        numbers = (self.latitude_deg, self.longitude_deg, self.radius_m,
                   self.min_kias, self.max_kias, self.min_agl_ft, self.max_bank_deg)
        if (not all(math.isfinite(v) for v in numbers)
                or not -90 <= self.latitude_deg <= 90
                or not -180 <= self.longitude_deg <= 180
                or self.radius_m <= 0 or self.min_kias < 0
                or self.max_kias <= self.min_kias or self.min_agl_ft < 0
                or not 0 < self.max_bank_deg < 90
                or not isinstance(self.source, str) or not self.source.strip()):
            raise ValueError("Sourced runway corridor and envelope required")

    def contains(self, latitude_deg: float, longitude_deg: float) -> bool:
        if (not all(math.isfinite(v) for v in (latitude_deg, longitude_deg))
                or not -90 <= latitude_deg <= 90
                or not -180 <= longitude_deg <= 180):
            return False
        lat1, lat2 = map(math.radians, (self.latitude_deg, latitude_deg))
        dlat = lat2 - lat1
        dlon = math.radians(longitude_deg - self.longitude_deg)
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 6371000.0 * 2 * math.asin(min(1.0, math.sqrt(h))) <= self.radius_m


class PhaseProfiles:
    def __init__(self, *, cruise: Limits = Limits(), departure: RunwayCorridor | None = None,
                 arrival: RunwayCorridor | None = None):
        self.cruise, self.departure, self.arrival = cruise, departure, arrival

    def require_phase(self, phase: Phase):
        if phase == Phase.TAKEOFF and self.departure is None:
            raise ValueError("Takeoff runway envelope lacks a sourced corridor")
        if phase in (Phase.LAND, Phase.ROLLOUT) and self.arrival is None:
            raise ValueError("Landing runway envelope lacks a sourced corridor")

    def validate_target(self, phase: Phase, altitude_indicated_ft: float):
        if phase in CRUISE_PHASES:
            if (type(altitude_indicated_ft) not in (int, float)
                    or not math.isfinite(altitude_indicated_ft)
                    or not self.cruise.min_altitude_ft <= altitude_indicated_ft <= self.cruise.max_altitude_ft):
                raise ValueError("Target outside unchanged cruise altitude envelope")

    def validate_observation(self, phase: Phase, observation: dict):
        """Fail closed on missing, nonfinite, stale, or out-of-phase evidence."""
        if phase not in RUNWAY_PHASES | CRUISE_PHASES:
            return
        self.require_phase(phase)
        fields = ("kias", "agl_ft", "roll_deg", "age_seconds")
        if phase in CRUISE_PHASES:
            fields += ("altitude_indicated_ft",)
        else:
            fields += ("latitude_deg", "longitude_deg")
        if any(type(observation.get(k)) not in (int, float)
               or not math.isfinite(observation[k]) for k in fields):
            raise ValueError("Phase envelope telemetry missing or nonfinite")
        age = observation["age_seconds"]
        if not 0 <= age <= self.cruise.max_age_seconds:
            raise ValueError("Phase envelope telemetry stale")
        if phase in CRUISE_PHASES:
            l = self.cruise
            if not (l.min_altitude_ft <= observation["altitude_indicated_ft"] <= l.max_altitude_ft
                    and observation["agl_ft"] >= l.min_agl_ft
                    and l.min_kias <= observation["kias"] <= l.max_kias
                    and abs(observation["roll_deg"]) <= l.max_bank_deg):
                raise ValueError("Outside unchanged cruise envelope")
            return
        corridor = self.departure if phase == Phase.TAKEOFF else self.arrival
        if not corridor.contains(observation["latitude_deg"], observation["longitude_deg"]):
            raise ValueError("Outside permitted runway corridor")
        if not (corridor.min_kias <= observation["kias"] <= corridor.max_kias
                and observation["agl_ft"] >= corridor.min_agl_ft
                and abs(observation["roll_deg"]) <= corridor.max_bank_deg):
            raise ValueError("Outside sourced runway envelope")
