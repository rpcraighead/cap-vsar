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
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math


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
    tuning_validated: bool = False
    sources: dict = field(default_factory=dict)

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


C172SP = AircraftProfile(
    key="C172SP",
    acf_name="Cessna_172SP_G1000.acf",
    display_name="X-Plane 12 stock Cessna 172SP G1000",
    vr_kias=55., vx_kias=62., vy_kias=74., climb_enroute_kias=85.,
    cruise_kias=100., approach_initial_kias=100., approach_intermediate_kias=95.,
    approach_clean_kias=80., ils_final_kias=73., final_approach_kias=65.,
    missed_kias=74., vfe_kias=((1/3, 110.), (1., 85.)), va_kias=105.,
    takeoff_flap_ratio=0., flap_retract_kias=70., flap_retract_agl_ft=300.,
    search_kias=90.,
    tuning_validated=True,
    sources={
        "vr/vx/vy": "bundled X-Plane_C172_Pilot_Operating_Manual.pdf: rotate 55, Vx 62, Vy 74 KIAS "
                    "(docs/C172_KSEE_KMYF_IFR_TRIAL.md)",
        "vfe/va": "same manual: flaps 10 deg 110 KIAS, 10-30 deg 85 KIAS; Va 105 KIAS at 2550 lb",
        "other speeds": "controller values flown on the 2026-10-11 KSEE-KMYF sortie "
                        "(services/ai_pilot/ksee_kmyf_mission.py, landing_trial.py)",
        "tuning": "C172 trials 2026-10-10/11; the 62-68 KIAS threshold window and 5-7 deg "
                  "touchdown pitch are LandingObserver engineering criteria",
    },
)


C182T = AircraftProfile(
    key="C182T",
    acf_name="Cessna_182T_G1000.acf",
    display_name="CAP 487 Cessna 182T NAV III (local prototype package)",
    # POH Section 4, Normal Takeoff: flaps UP-20 deg (10 deg preferred), lift
    # nosewheel at 50-60 KIAS, climb 70 KIAS (flaps 20) / 80 KIAS (flaps up).
    vr_kias=55.,
    # POH Section 4 / Section 5: Vx 65 KIAS and Vy 80 KIAS at sea level.
    vx_kias=65., vy_kias=80.,
    # POH Section 4, Enroute Climb: 85-95 KIAS at 23 in.hg / 2400 RPM.
    climb_enroute_kias=90.,
    # Exercise cruise: the README's FLC exercise target; inside the 55-80 %
    # power band of POH Section 4 Cruise and the 90-140 KIAS exercise envelope.
    cruise_kias=110.,
    approach_initial_kias=100., approach_intermediate_kias=95.,
    # POH Section 4, Normal Landing: 70-80 KIAS flaps up; flaps 10 deg below
    # 140, 10-20 deg below 120, 20-FULL below 100; 60-70 KIAS flaps FULL.
    approach_clean_kias=85., ils_final_kias=80., final_approach_kias=68.,
    # POH Section 4, Balked Landing: full power, flaps 20 deg, 55 KIAS, retract
    # slowly after a safe altitude and 70 KIAS. 70 KIAS (the flaps-20 climb
    # speed of Normal Takeoff) is used for the controller's missed-approach
    # climb rather than 55, which is an obstacle-clearance speed.
    missed_kias=70.,
    # POH Section 2, Figure 2-1: Vfe 140 (up-10), 120 (10-20), 100 (20-FULL).
    vfe_kias=((1/3, 140.), (2/3, 120.), (1., 100.)),
    # POH Section 2: Va 110 KIAS at 3100 lb.
    va_kias=110.,
    # Normal takeoff with 10 deg, retracted above 70 KIAS (POH Short Field
    # Takeoff item 9) once clear of the runway environment.
    takeoff_flap_ratio=1/3, flap_retract_kias=70., flap_retract_agl_ft=300.,
    # CAP visual search speed for the 182 (training value, not a POH figure).
    search_kias=100.,
    # --- tuning: C172 values moved up by the final-approach speed difference ---
    final_speed_add_kias=5.,
    threshold_kias=(64., 72.),
    landing_flap_gates=(FlapGate(1/3, 1852., 95.), FlapGate(2/3, 926., 85.),
                        FlapGate(1., 0., 0.)),
    flap_stage_names=("10deg", "20deg", "38deg"),
    touchdown_pitch_deg=(5., 8.),
    touchdown_max_groundspeed_kt=80.,
    missed_flap_ratio=2/3, ils_flap_ratio=1/3,
    min_roll_rpm=2000.,
    # The C172 taxi law, unchanged; the IO-540's idle thrust and the governed
    # propeller will move it (measure on the first taxi-only trial).
    taxi_base_throttle=.16, taxi_speed_gain=.08, taxi_max_throttle=.28,
    cruise_base_throttle=.55, ils_base_throttle=.48, approach_base_throttle=.28,
    envelope_kias=(80., 140.),
    tuning_validated=False,
    sources={
        "handbook": "Cessna 182T NAV III GFC 700 AFCS information manual, P/N 182TPHBUS, "
                    "SHA-256 ba64adab5d6ed543f73b330f24301e72fdaba4f729c3661075fa55173fd2705c",
        "vr": "Section 4 Normal Takeoff: lift nosewheel at 50-60 KIAS (55 used)",
        "vx/vy": "Section 4 Maximum Performance Climb: 80 KIAS SL; Section 5 Vx 65 KIAS SL",
        "climb_enroute": "Section 4 Enroute Climb: 85-95 KIAS",
        "landing": "Section 4 Normal Landing: 70-80 KIAS flaps up, 60-70 KIAS flaps FULL",
        "missed": "Section 4 Balked Landing: flaps 20, 55 KIAS; retract above 70 KIAS",
        "vfe/va": "Section 2 Figure 2-1",
        "acf": "scripts/build_c182t_package.py ACF_PATCHES: Vs 51, Vso 41, Vx 65, Vy 80, "
               "Vfe 140/100, Vno 140, Vne 175; flap detents 10/20/38 deg",
        "tuning": "NOT VALIDATED: base throttles, flap gates, threshold window and touchdown "
                  "pitch are the C172 criteria shifted to the C182T speeds; see "
                  "docs/C182T_AI_PILOT_PORT_2026-10-11.md",
    },
)


PROFILES = {C172SP.key: C172SP, C182T.key: C182T}


def profile_for(key_or_acf: str) -> AircraftProfile:
    """Look a profile up by key (`C182T`) or by aircraft file name."""
    for profile in PROFILES.values():
        if key_or_acf in (profile.key, profile.acf_name):
            return profile
    raise KeyError("no aircraft profile for %r" % key_or_acf)
