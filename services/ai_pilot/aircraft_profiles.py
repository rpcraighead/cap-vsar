"""Aircraft operating profiles for the AI pilot controllers.

The C172 takeoff, landing and KSEE-KMYF mission controllers were flown with
their speeds written as literals. This module is the one place those numbers
live now, with the source of each operational value named, so that the same
control laws can fly the CAP 487 C182T package (built by
`scripts/build_c182t_package.py`) without a second copy of the code
(docs/AI_PILOT_DEVELOPMENT_PLAN.md, "Aircraft and observation profiles").

Two kinds of number are kept apart on purpose:

* **Sourced** values quote a handbook. For the C172 that is the bundled
  X-Plane `X-Plane_C172_Pilot_Operating_Manual.pdf`, which describes the
  simulator aircraft and is not a real aircraft's approved POH. For the C182T
  it is the Cessna 182T NAV III GFC 700 information manual, P/N 182TPHBUS,
  SHA-256 `ba64adab5d6e…3fd2705c`, the document pinned in
  `scripts/c182t_dimension_master.json`.
* **Tuning** values are controller constants adjusted during the C172 trials
  (base throttle positions, flap-selection gates, the observer's acceptance
  windows). They are not performance figures. The C182T copies start from the
  C172 values scaled to the C182T's speeds and carry `tuning_validated=False`
  until a C182T sortie has been flown and scored.

Nothing here is operating guidance for a real aircraft.

The numbers are not in this module any more: each aircraft is a TOML file in `profiles/`, loaded by
`profile_loader`. This module is the dataclass the controllers read, its physical sanity checks, and
the `PROFILES` registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from .performance import PerformanceTable
from .profile_loader import load_profiles


@dataclass(frozen=True)
class FlapGate:
    """Select `ratio` once the aircraft is inside `inside_m` of the threshold
    AND no faster than `max_kias`; until then hold the previous stage. The
    last gate's `inside_m`/`max_kias` are ignored (it is the final stage)."""
    ratio: float
    inside_m: float
    max_kias: float


@dataclass(frozen=True)
class AircraftProfile:
    key: str
    acf_name: str                       # the aircraft file the observers insist on
    display_name: str
    # --- sourced operating speeds (KIAS) ---
    vr_kias: float                      # nosewheel lift-off / rotation
    vx_kias: float                      # best angle, sea level
    vy_kias: float                      # best rate, sea level
    climb_enroute_kias: float           # normal enroute climb
    cruise_kias: float                  # exercise cruise / vector speed
    approach_initial_kias: float        # first approach segment, clean
    approach_intermediate_kias: float   # intermediate segment, clean
    approach_clean_kias: float          # final segment outside 3 NM, clean
    ils_final_kias: float               # inside 3 NM, first flap stage
    final_approach_kias: float          # short final, landing flaps
    missed_kias: float                  # balked landing climb
    vfe_kias: tuple[tuple[float, float], ...]   # (flap ratio, Vfe) per stage
    va_kias: float                      # manoeuvring speed at max weight
    takeoff_flap_ratio: float           # flap handle ratio for a normal takeoff
    flap_retract_kias: float            # retract takeoff flaps above this speed
    flap_retract_agl_ft: float          # ... and above this height
    search_kias: float                  # grid/track search speed
    # --- tuning (controller constants, not handbook values) ---
    final_speed_add_kias: float = 5.    # extra speed beyond ~0.5 NM final
    threshold_kias: tuple[float, float] = (62., 68.)
    landing_flap_gates: tuple[FlapGate, ...] = (FlapGate(1/3, 1852., 85.),
                                                 FlapGate(2/3, 926., 75.),
                                                 FlapGate(1., 0., 0.))
    flap_stage_names: tuple[str, str, str] = ("10deg", "20deg", "30deg")
    touchdown_pitch_deg: tuple[float, float] = (5., 7.)
    touchdown_max_groundspeed_kt: float = 78.
    missed_flap_ratio: float = 1/3
    ils_flap_ratio: float = 1/3
    min_roll_rpm: float = 1800.         # engine must exceed this 5 s into the roll
    # taxi throttle law: base + gain * (target - groundspeed), clamped to [0, max]
    taxi_base_throttle: float = .16
    taxi_speed_gain: float = .08
    taxi_max_throttle: float = .28
    cruise_base_throttle: float = .55
    ils_base_throttle: float = .48
    approach_base_throttle: float = .28
    envelope_kias: tuple[float, float] = (80., 140.)
    # Constant-speed propeller (the C172 package is fixed pitch and has no lever).
    # `prop_cruise_ratio` is the lever setting used in level cruise; every other
    # phase flies the lever full forward (takeoff, climb, approach, balked landing).
    constant_speed_prop: bool = False
    prop_cruise_ratio: float = 1.
    tuning_validated: bool = False
    sources: dict = field(default_factory=dict)
    # Measured throttle-for-(airspeed, vertical speed) table; None means "not measured", and the
    # controllers then fall back to their base-throttle law (profiles/README.md, [performance]).
    performance: "PerformanceTable | None" = None

    def __post_init__(self):
        speeds = (self.vr_kias, self.vx_kias, self.vy_kias, self.climb_enroute_kias,
                  self.cruise_kias, self.approach_initial_kias,
                  self.approach_intermediate_kias, self.approach_clean_kias,
                  self.ils_final_kias, self.final_approach_kias, self.missed_kias,
                  self.va_kias, self.flap_retract_kias, self.search_kias)
        if any(not math.isfinite(s) or s <= 0 for s in speeds):
            raise ValueError("profile speeds must be positive and finite")
        if not 0 <= self.takeoff_flap_ratio <= 1:
            raise ValueError("takeoff flap ratio outside 0..1")
        if self.threshold_kias[0] >= self.threshold_kias[1]:
            raise ValueError("threshold speed window inverted")
        if not self.threshold_kias[0] <= self.final_approach_kias <= self.threshold_kias[1]:
            raise ValueError("final approach speed must sit inside the threshold window")
        for gate in self.landing_flap_gates:
            if not 0 < gate.ratio <= 1:
                raise ValueError("flap gate ratio outside 0..1")
            if gate.max_kias > self.vfe_for(gate.ratio):
                raise ValueError("flap gate %.2f would select flaps above Vfe" % gate.ratio)
        if not 0.5 <= self.prop_cruise_ratio <= 1.:
            raise ValueError("prop cruise ratio outside the bridge's 0.5..1 authority")
        if self.prop_cruise_ratio != 1. and not self.constant_speed_prop:
            raise ValueError("a fixed-pitch aircraft has no prop cruise setting")
        if self.landing_flap_gates[-1].ratio != 1.:
            raise ValueError("the last landing flap gate must be full flaps")
        if self.ils_final_kias > self.vfe_for(self.ils_flap_ratio):
            raise ValueError("ILS final speed exceeds Vfe for the ILS flap stage")
        if self.missed_kias > self.vfe_for(self.missed_flap_ratio):
            raise ValueError("missed approach speed exceeds Vfe for its flap stage")
        if (self.takeoff_flap_ratio
                and self.flap_retract_kias > self.vfe_for(self.takeoff_flap_ratio)):
            raise ValueError("takeoff flaps would be carried above Vfe")

    def taxi_throttle(self, target_mps: float, groundspeed_mps: float) -> float:
        return min(max(self.taxi_base_throttle
                       + self.taxi_speed_gain * (target_mps - groundspeed_mps), 0.),
                   self.taxi_max_throttle)

    def vfe_for(self, ratio: float) -> float:
        """Vfe of the smallest handbook stage at or above `ratio`."""
        for stage, vfe in self.vfe_kias:
            if ratio <= stage + 1e-9:
                return vfe
        return self.vfe_kias[-1][1]

    def landing_flap_ratio(self, along_m: float, kias: float) -> float:
        """The landing-flap stage for a position `along_m` from the threshold
        (negative before it) at `kias`. Earlier stages are held until the next
        gate is both inside its distance and below its speed."""
        for gate in self.landing_flap_gates[:-1]:
            if along_m < -gate.inside_m or kias > gate.max_kias:
                return gate.ratio
        return self.landing_flap_gates[-1].ratio


# The profiles themselves are data: services/ai_pilot/profiles/<aircraft>.toml, loaded and validated by
# profile_loader (schema and how to add an aircraft: profiles/README.md). They were Python literals in this
# module until 2026-10-15; services/ai_pilot/tests/golden_profiles.py keeps those literals and the
# migration test asserts the files load to profiles equal to them.
PROFILES = load_profiles()
C172SP = PROFILES["C172SP"]
C182T = PROFILES["C182T"]


def profile_for(key_or_acf: str) -> AircraftProfile:
    """Look a profile up by key (`C182T`) or by aircraft file name."""
    for profile in PROFILES.values():
        if key_or_acf in (profile.key, profile.acf_name):
            return profile
    raise KeyError("no aircraft profile for %r" % key_or_acf)
