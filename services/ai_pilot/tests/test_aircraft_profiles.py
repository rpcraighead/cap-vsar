"""The profiles carry sourced speeds and refuse combinations that breach Vfe."""
import dataclasses

import pytest

from services.ai_pilot.aircraft_profiles import (AircraftProfile, C172SP, C182T, FlapGate,
                                                  PROFILES, profile_for)


def test_c182t_speeds_match_the_182t_handbook_and_the_built_acf():
    assert (C182T.vr_kias, C182T.vx_kias, C182T.vy_kias) == (55., 65., 80.)
    assert C182T.climb_enroute_kias == 90. and 85 <= C182T.climb_enroute_kias <= 95
    assert 60 <= C182T.final_approach_kias <= 70          # Normal Landing, flaps FULL
    assert 70 <= C182T.approach_clean_kias <= 80 or C182T.approach_clean_kias == 85.
    assert C182T.vfe_kias == ((1/3, 140.), (2/3, 120.), (1., 100.))
    assert C182T.va_kias == 110.
    assert C182T.acf_name == "Cessna_182T_G1000.acf"
    assert C182T.takeoff_flap_ratio == pytest.approx(1/3)
    assert not C182T.tuning_validated and C172SP.tuning_validated


def test_c172_profile_reproduces_the_flown_literals():
    assert (C172SP.vr_kias, C172SP.vx_kias, C172SP.vy_kias) == (55., 62., 74.)
    assert C172SP.threshold_kias == (62., 68.) and C172SP.final_approach_kias == 65.
    assert C172SP.landing_flap_ratio(-2000, 70) == pytest.approx(1/3)
    assert C172SP.landing_flap_ratio(-1200, 70) == pytest.approx(2/3)
    assert C172SP.landing_flap_ratio(-500, 70) == 1.
    assert C172SP.landing_flap_ratio(-500, 90) == pytest.approx(1/3)
    assert C172SP.landing_flap_ratio(-500, 80) == pytest.approx(2/3)


def test_every_profile_selects_flaps_only_below_their_vfe():
    for profile in PROFILES.values():
        for gate in profile.landing_flap_gates[:-1]:
            assert gate.max_kias <= profile.vfe_for(gate.ratio)
        assert profile.ils_final_kias <= profile.vfe_for(profile.ils_flap_ratio)
        assert profile.missed_kias <= profile.vfe_for(profile.missed_flap_ratio)
        assert profile.threshold_kias[0] <= profile.final_approach_kias <= profile.threshold_kias[1]


def test_profile_rejects_flap_gates_above_vfe_and_a_misplaced_final_speed():
    with pytest.raises(ValueError, match="Vfe"):
        dataclasses.replace(C182T, landing_flap_gates=(FlapGate(1/3, 1852., 95.),
                                                       FlapGate(2/3, 926., 125.),
                                                       FlapGate(1., 0., 0.)))
    with pytest.raises(ValueError, match="threshold"):
        dataclasses.replace(C182T, final_approach_kias=75.)
    with pytest.raises(ValueError, match="Vfe"):
        dataclasses.replace(C182T, ils_final_kias=150.)


def test_lookup_by_key_or_aircraft_file():
    assert profile_for("C182T") is C182T
    assert profile_for("Cessna_172SP_G1000.acf") is C172SP
    with pytest.raises(KeyError):
        profile_for("Cessna_208.acf")
