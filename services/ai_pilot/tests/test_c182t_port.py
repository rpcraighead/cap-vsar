"""The C172 controllers flown with the C182T profile: takeoff flaps, speeds, observer."""
import math

import pytest

from services.ai_pilot.aircraft_profiles import C172SP, C182T
from services.ai_pilot.ksee_kmyf_mission import MissionController, RUNWAY
from services.ai_pilot.landing_trial import LandingController, LandingObserver
from services.ai_pilot.search_patterns import destination
from services.ai_pilot.takeoff_guidance import TakeoffGuidance, TakeoffObservation
from services.ai_pilot.taxi import (ClearanceSource, RoutePurpose, TaxiCoordinator, TaxiLeg,
                                    TaxiRoute, TaxiPhase)
from services.ai_pilot.tests.test_landing_trial import snapshot as landing_snapshot
from services.ai_pilot.tests.test_ksee_kmyf_mission import snapshot as mission_snapshot


def cleared_taxi():
    taxi = TaxiCoordinator("ramp", towered=True)
    taxi.load_route(TaxiRoute(RoutePurpose.OUTBOUND, (TaxiLeg("ramp", "27R hold short"),)))
    taxi.authorize_taxi(ClearanceSource.ATC)
    taxi.complete_leg()
    assert taxi.phase is TaxiPhase.HOLDING_SHORT_DEPARTURE
    taxi.authorize_departure_runway("27R", ClearanceSource.ATC, takeoff=True)
    return taxi


def observation(**changes):
    values = dict(sim_time_s=0, along_runway_m=10, cross_runway_m=0, heading_true_deg=282,
                  kias=0, groundspeed_mps=0, on_ground=True, agl_ft=0, altitude_msl_ft=388,
                  climb_distance_nm=0, pitch_deg=0, pitch_rate_dps=0, roll_deg=0,
                  engine_rpm=2300, flap_ratio=1/3)
    values.update(changes)
    return TakeoffObservation(**values)


def c182_takeoff():
    return TakeoffGuidance(cleared_taxi(), runway="27R", runway_heading_true_deg=282,
                           runway_length_m=1628, field_elevation_ft=388, profile=C182T)


def test_c182_takeoff_requires_ten_degrees_of_flap_and_carries_it_until_retract_gates():
    pilot = c182_takeoff()
    assert pilot.step(observation(flap_ratio=0.)).throttle == 0   # flaps up is wrong for the 182T
    roll = pilot.step(observation())
    assert (roll.phase, roll.throttle, roll.target_kias) == ("roll", 1., 55.)
    assert roll.flap == pytest.approx(1/3)
    assert roll.actuator_frame(0.)["flap"] == pytest.approx(1/3)
    rotate = pilot.step(observation(sim_time_s=10, kias=56, groundspeed_mps=28, along_runway_m=300))
    assert rotate.phase == "rotate"
    low = pilot.step(observation(sim_time_s=14, kias=72, on_ground=False, agl_ft=60,
                                 altitude_msl_ft=450, along_runway_m=500))
    assert (low.phase, low.target_kias) == ("climb", 65.)
    assert low.flap == pytest.approx(1/3)
    slow_high = pilot.step(observation(sim_time_s=30, kias=66, on_ground=False, agl_ft=320,
                                       altitude_msl_ft=710, climb_distance_nm=.4))
    assert slow_high.flap == pytest.approx(1/3)      # above 300 ft but below 70 KIAS
    retracted = pilot.step(observation(sim_time_s=40, kias=75, on_ground=False, agl_ft=400,
                                       altitude_msl_ft=790, climb_distance_nm=.6))
    assert retracted.flap == 0.
    again_slow = pilot.step(observation(sim_time_s=41, kias=64, on_ground=False, agl_ft=410,
                                        altitude_msl_ft=800, climb_distance_nm=.65))
    assert again_slow.flap == 0.                       # never re-extended
    assert pilot.step(observation(sim_time_s=120, kias=78, on_ground=False, agl_ft=1700,
                                  altitude_msl_ft=2100, climb_distance_nm=3)).target_kias == 80.


def test_c182_rejects_on_its_own_rpm_gate():
    pilot = c182_takeoff()
    pilot.step(observation())
    weak = pilot.step(observation(sim_time_s=6, kias=30, groundspeed_mps=15, engine_rpm=1900))
    assert weak.phase == "rejected"
    c172 = TakeoffGuidance(cleared_taxi(), runway="27R", runway_heading_true_deg=282,
                           runway_length_m=1628, field_elevation_ft=388, profile=C172SP)
    c172.step(observation(flap_ratio=0.))
    assert c172.step(observation(sim_time_s=6, kias=30, groundspeed_mps=15, engine_rpm=1900,
                                 flap_ratio=0.)).phase == "roll"


def test_c182_landing_schedule_and_speeds():
    c = LandingController("KMYF 28R", profile=C182T)
    far = c.step(landing_snapshot(-2500, gs_kt=100., agl_ft=400.))
    assert far["flap"] == pytest.approx(1/3)
    assert c.last_commands["target_kias"] == pytest.approx(73.)
    mid = c.step(landing_snapshot(-1200, gs_kt=82., agl_ft=200., sim=1.1, frame=2))
    assert mid["flap"] == pytest.approx(2/3)
    short = c.step(landing_snapshot(-500, gs_kt=80., agl_ft=90., sim=1.2, frame=3))
    assert short["flap"] == 1.
    assert c.last_commands["target_kias"] == pytest.approx(68.)
    fast = LandingController("KMYF 28R", profile=C182T)
    assert fast.step(landing_snapshot(-500, gs_kt=96., agl_ft=90.))["flap"] == pytest.approx(1/3)


def c182_landing_snapshot(along, **kw):
    s = landing_snapshot(along, **kw)
    s["aircraft"] = {"name": "Cessna_182T_G1000.acf", "path": "/sim/cap487"}
    return s


def test_c182_observer_insists_on_the_182_and_its_threshold_window():
    wrong = LandingObserver(profile=C182T)
    assert wrong.observe(landing_snapshot(-2000))["reason"] == "Wrong aircraft"
    o = LandingObserver(profile=C182T)
    for i, (along, flap) in enumerate(((-2000, 1/3), (-1300, 2/3), (-500, 1.), (-50, 1.)), 1):
        report = o.observe(c182_landing_snapshot(along, flap=flap, agl_ft=50, gs_kt=70, pitch_deg=6.,
                                                 sim=1. + .1 * (i - 1), frame=i))
        assert report["outcome"] == "INCOMPLETE"
    assert "38deg" in o.flap_stages
    assert o.observe(c182_landing_snapshot(2, flap=1., agl_ft=40, gs_kt=70, pitch_deg=6.,
                                           sim=1.5, frame=5))["outcome"] == "INCOMPLETE"
    slow = LandingObserver(profile=C182T)
    for i, (along, flap) in enumerate(((-2000, 1/3), (-1300, 2/3), (-500, 1.)), 1):
        slow.observe(c182_landing_snapshot(along, flap=flap, agl_ft=50, gs_kt=70, pitch_deg=6.,
                                           sim=1. + .1 * (i - 1), frame=i))
    report = slow.observe(c182_landing_snapshot(2, flap=1., agl_ft=40, gs_kt=62, pitch_deg=6.,
                                                sim=1.4, frame=4))
    assert report["reason"] == "Threshold height or final speed outside window"


def test_c182_mission_speeds_follow_the_profile():
    m = MissionController(profile=C182T)
    m.step(mission_snapshot())
    assert m.last_diagnostics["target_kias"] == 80.
    m.step(mission_snapshot(sim_time_s=10.1, altitude_indicated_ft=790.))
    assert m.stage == "pgy_intercept" and m.last_diagnostics["target_kias"] == 80.
    m.step(mission_snapshot(sim_time_s=10.2, altitude_indicated_ft=2500.))
    assert m.last_diagnostics["target_kias"] == 90.
    vector = MissionController("bakel_vector", profile=C182T)
    vector.step(mission_snapshot(altitude_indicated_ft=5000.))
    assert vector.last_diagnostics["target_kias"] == 110.
    far = MissionController("ils", profile=C182T)
    far.step(mission_snapshot(latitude_deg=32.76774, longitude_deg=-117.0166,
                              altitude_indicated_ft=2600., heading_true_deg=295., heading_mag_deg=284.,
                              kias=86., pitch_deg=0., vvi_fpm=-400.))
    assert far.last_diagnostics["target_kias"] == 85.
    lat, lon = destination(*RUNWAY.threshold, (RUNWAY.heading_true_deg + 180) % 360, 1.6)
    near = MissionController("ils", profile=C182T)
    frame = near.step(mission_snapshot(latitude_deg=lat, longitude_deg=lon, altitude_indicated_ft=900.,
                                       heading_true_deg=295., heading_mag_deg=284., kias=84.,
                                       pitch_deg=0., vvi_fpm=-400.))
    assert near.last_diagnostics["target_kias"] == 80.
    assert frame["flap"] == pytest.approx(1/3)
    missed = MissionController("missed_runway", profile=C182T)
    frame = missed.step(mission_snapshot(altitude_indicated_ft=600., vvi_fpm=100.))
    assert missed.last_diagnostics["target_kias"] == 70.
    assert frame["flap"] == pytest.approx(2/3)
    c172 = MissionController("missed_runway", profile=C172SP)
    assert c172.step(mission_snapshot(altitude_indicated_ft=600., vvi_fpm=100.))["flap"] == pytest.approx(1/3)
