"""Owner-transfer trial scoring, the stager's new mission options, the pattern observer waiver."""
import json
import stat

import pytest

from scripts.ai_pilot_experiment import stage_observer
from services.ai_pilot.owner_trial import OwnerTrialObserver
from services.ai_pilot.search_patterns import PatternObserver, expanding_square
from services.ai_pilot.tests.test_search_patterns import observer_snapshot


def snap(sim, *, alt=4000., heading=90., roll=0., vvi=0., kias=100., frame=None):
    return {"frame": frame if frame is not None else int(sim * 20),
            "aircraft": {"name": "Cessna_182T_G1000.acf"},
            "values": {"sim_time_s": sim, "altitude_indicated_ft": alt, "heading_true_deg": heading,
                       "roll_deg": roll, "vvi_fpm": vvi, "kias": kias, "paused": 0, "on_ground": 0}}


def fly(observer, phase, start, seconds, **fields):
    observer.enter(phase, snap(start))
    t = start
    while t < start + seconds:
        t += .25
        observer.observe(snap(t, **fields))
    return t


def good_trial():
    observer = OwnerTrialObserver(altitude_ft=4000., aircraft_name="Cessna_182T_G1000.acf")
    t = fly(observer, "direct1", 0., 20.)
    observer.enter("gfc", snap(t), heading_target_true=110.)
    for i in range(1, 241):                                   # turn 90 -> 110 and settle
        observer.observe(snap(t + i * .25, heading=min(110., 90. + i * .5), roll=10. if i < 40 else 0.))
    t += 60
    fly(observer, "direct2", t, 20., heading=110.)
    return observer


def test_a_clean_round_trip_passes_and_records_the_capture():
    report = good_trial().report()
    assert report["outcome"] == "PASS" and report["captured"]
    assert set(report["phases"]) == {"direct1", "gfc", "direct2"}
    assert report["phases"]["gfc"]["transient"]["max_bank_deg"] == 10.


def test_a_hand_over_transient_fails_the_trial_and_names_the_phase():
    observer = OwnerTrialObserver(altitude_ft=4000.)
    observer.enter("direct1", snap(0))
    observer.observe(snap(.25))
    observer.enter("gfc", snap(.5), heading_target_true=110.)
    assert observer.observe(snap(.75, alt=3800.)) == "Hand-over transient too large entering gfc"
    assert observer.report()["outcome"] == "FAIL"
    assert observer.observe(snap(1.)) == "Hand-over transient too large entering gfc"   # sticky


@pytest.mark.parametrize("fields,reason", [({"kias": 60.}, "Speed outside band"),
                                           ({"roll": 40.}, "Hand-over transient"),
                                           ({"vvi": 2000.}, "Hand-over transient")])
def test_speed_bank_and_climb_rate_limits(fields, reason):
    observer = OwnerTrialObserver(altitude_ft=4000.)
    observer.enter("gfc", snap(0), heading_target_true=110.)
    assert reason in observer.observe(snap(.25, **fields))


def test_no_capture_is_incomplete_not_a_pass():
    observer = OwnerTrialObserver(altitude_ft=4000.)
    t = fly(observer, "direct1", 0., 10.)
    observer.enter("gfc", snap(t), heading_target_true=150.)
    for i in range(1, 121):
        observer.observe(snap(t + i * .25, heading=95.))
    fly(observer, "direct2", t + 30, 10.)
    report = observer.report()
    assert report["outcome"] == "INCOMPLETE" and "not captured" in report["reason"]


def test_pause_wrong_aircraft_and_gaps_fail():
    observer = OwnerTrialObserver(altitude_ft=4000., aircraft_name="Cessna_172SP_G1000.acf")
    observer.enter("direct1", snap(0))
    assert observer.observe(snap(.25)) == "Wrong aircraft"
    other = OwnerTrialObserver(altitude_ft=4000.)
    other.enter("direct1", snap(0))
    other.observe(snap(.25))
    assert other.observe(snap(3.)) == "Telemetry gap or nonincreasing time"


def test_pattern_observer_waives_altitude_only_while_the_terrain_floor_is_held_and_says_so():
    waypoints = expanding_square(32.7, -117.3, 0., 1., 3, "right")
    observer = PatternObserver(waypoints, altitude_indicated_ft=2000.)
    observer.observe(observer_snapshot(.1, waypoints[0].lat, waypoints[0].lon, alt=2000., frame=1))
    assert observer.reached
    far = (waypoints[1].lat + .2, waypoints[1].lon)
    observer.terrain_override = True
    assert observer.observe(observer_snapshot(.2, *far, alt=2600., frame=2))["outcome"] == "INCOMPLETE"
    assert observer.report()["terrain_override_samples"] == 1
    observer.terrain_override = False
    assert observer.observe(observer_snapshot(.3, *far, alt=2600., frame=3))["reason"] == \
        "Altitude outside tolerance on the pattern"


def test_stage_mission_installs_terrain_gfc_and_the_fence(tmp_path):
    aircraft = tmp_path / "Cessna_182T_G1000.acf"
    aircraft.write_text("built package fixture")
    out = tmp_path / "stage"
    stage_observer(out, aircraft, mode="mission")
    config = json.loads((out / "capvsar_flight_control_config.json").read_text())
    assert config["mode"] == "mission" and config["terrain_lookahead"] is True
    assert config["gfc_owner"] is True and config["terrain_backstop_ft"] == 200
    assert (out / "capvsar_terrain.py").is_file() and (out / "capvsar_mission.py").is_file()
    assert stat.S_IMODE((out / "capvsar_flight_control_config.json").stat().st_mode) == 0o600
    off = tmp_path / "stage_no_fence"
    stage_observer(off, aircraft, mode="mission", terrain_backstop_ft=None)
    assert "terrain_backstop_ft" not in json.loads((off / "capvsar_flight_control_config.json").read_text())
    # only the mission lab gets the GFC owner and terrain scan
    surface = tmp_path / "surface"
    stage_observer(surface, aircraft, mode="surface")
    plain = json.loads((surface / "capvsar_flight_control_config.json").read_text())
    assert "gfc_owner" not in plain and "terrain_lookahead" not in plain


def test_terrain_floor_waives_only_the_altitude_criteria_and_is_counted():
    observer = OwnerTrialObserver(altitude_ft=4000.)
    observer.enter("gfc", snap(0), heading_target_true=110.)
    observer.terrain_override = True
    observer.altitude_ft = 5500.                      # the floor the guard raised
    t = 0.
    for _ in range(40):
        t += .25
        assert observer.observe(snap(t, alt=5480.)) is None       # near the floor: fine
    assert observer.report()["terrain_override_samples"] == 40
    assert observer.observe(snap(t + .25, alt=5480., roll=40.)).startswith("Hand-over transient") \
        or observer.failure                                          # bank is never waived
    clean = OwnerTrialObserver(altitude_ft=4000.)
    clean.enter("gfc", snap(0), heading_target_true=110.)
    assert clean.observe(snap(.25, alt=3700.)) == "Hand-over transient too large entering gfc"
    assert clean.report()["terrain_override_samples"] == 0


def test_the_adopted_first_phase_is_recorded_not_limited_but_later_hand_overs_still_are():
    observer = OwnerTrialObserver(altitude_ft=4000.)
    observer.enter("direct1", snap(0))
    assert observer.observe(snap(.25, vvi=1500., alt=3900.)) is None      # the air start was still climbing
    assert observer.report()["phases"]["direct1"]["transient"]["max_abs_vvi_fpm"] == 1500.
    observer.enter("gfc", snap(.5), heading_target_true=110.)
    assert observer.observe(snap(.75, vvi=1500.)).startswith("Hand-over transient")
