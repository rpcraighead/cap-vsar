"""Runway exceptions require phase and position; cruise stays unchanged."""
import pytest

from services.ai_pilot.flight_executive import Phase
from services.ai_pilot.phase_profiles import PhaseProfiles, RunwayCorridor


def profile():
    return PhaseProfiles(
        departure=RunwayCorridor(32.0, -117.0, 500, 0, 140, 0, 35, "test fixture"),
        arrival=RunwayCorridor(33.0, -118.0, 500, 0, 140, 0, 35, "test fixture"))


def observation(**changes):
    state = dict(kias=75, agl_ft=50, altitude_indicated_ft=500,
                 roll_deg=0, age_seconds=0.1, latitude_deg=32.0, longitude_deg=-117.0)
    state.update(changes)
    return state


def test_runway_exception_does_not_widen_cruise_or_other_phases():
    p = profile()
    p.validate_observation(Phase.TAKEOFF, observation())
    for phase in (Phase.CLIMB, Phase.TRANSIT, Phase.SEARCH, Phase.APPROACH, Phase.TEST):
        with pytest.raises(ValueError, match="cruise envelope"):
            p.validate_observation(phase, observation())
        with pytest.raises(ValueError, match="cruise altitude"):
            p.validate_target(phase, 500)


def test_runway_exception_requires_its_corridor_and_sourced_thresholds():
    p = profile()
    with pytest.raises(ValueError, match="corridor"):
        p.validate_observation(Phase.TAKEOFF, observation(latitude_deg=33.0))
    with pytest.raises(ValueError, match="corridor"):
        p.validate_observation(Phase.LAND, observation())
    p.validate_observation(Phase.LAND, observation(latitude_deg=33.0, longitude_deg=-118.0))
    with pytest.raises(ValueError, match="sourced corridor"):
        PhaseProfiles().require_phase(Phase.TAKEOFF)
    with pytest.raises(ValueError, match="Sourced"):
        RunwayCorridor(32, -117, 500, 0, 140, 0, 35, "")


def test_stale_or_missing_position_fails_closed_even_in_runway_phase():
    p = profile()
    with pytest.raises(ValueError, match="missing"):
        p.validate_observation(Phase.TAKEOFF, observation(latitude_deg=None))
    with pytest.raises(ValueError, match="corridor"):
        p.validate_observation(Phase.TAKEOFF, observation(longitude_deg=243.0))
    with pytest.raises(ValueError, match="stale"):
        p.validate_observation(Phase.TAKEOFF, observation(age_seconds=3.0))
