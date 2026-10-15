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


# --- bumpless hand-back ---------------------------------------------------------

def level_values(kias, alt=4000., vvi=650.):
    return {"sim_time_s": 100., "on_ground": 0, "agl_m": 800., "kias": kias, "flap_actual": 0.,
            "vvi_fpm": vvi, "heading_true_deg": 90., "roll_deg": 0., "roll_rate_dps": 0.,
            "altitude_indicated_ft": alt, "pitch_deg": 5., "pitch_rate_dps": 0., "beta_deg": 0.}


def test_a_fresh_cruise_law_handed_a_climbing_airplane_does_not_cut_the_power():
    from services.ai_pilot.aircraft_profiles import C182T
    from services.ai_pilot.search_patterns import CruiseLaw
    v = level_values(119.)
    unchanged, _ = CruiseLaw(C182T).frame(v, 0., 90., 6000., 100., .05)
    assert unchanged["throttle"] < .2                      # the 2026-10-15 ESCON finding: idle for 8 s
    law = CruiseLaw(C182T, adopt_slew_kt_s=2.0)
    first, _ = law.frame(v, 0., 90., 6000., 100., .05, throttle_in=1.0)
    assert first["throttle"] > .8                          # starts where the pilot left it
    assert law.ias_cmd == pytest.approx(119., abs=.2)      # and the speed command from the measured speed
    for _ in range(100):                                   # 5 s later the command has slewed ~10 kt
        law.frame(v, 0., 90., 6000., 100., .05, throttle_in=1.0)
    assert law.ias_cmd == pytest.approx(109., abs=1.)
    law.reset()
    assert law.ias_cmd is None and not law.seeded


def test_without_adopt_slew_the_law_is_the_lifted_one():
    from services.ai_pilot.aircraft_profiles import C182T
    from services.ai_pilot.search_patterns import CruiseLaw
    v = level_values(119.)
    a, _ = CruiseLaw(C182T).frame(v, 0., 90., 6000., 100., .05)
    b, _ = CruiseLaw(C182T).frame(v, 0., 90., 6000., 100., .05, throttle_in=1.0)
    assert a == b                                          # throttle_in is ignored unless adopting


# --- widened geofence -------------------------------------------------------------

def test_extra_airborne_boxes_are_validated_and_extend_only_this_session():
    from xplane.capvsar_mission import AIRBORNE_BOXES, checked_extra_boxes, in_airborne_region
    east = (33.0, 33.35, -116.85, -116.70)
    assert not in_airborne_region(33.2, -116.78)
    assert in_airborne_region(33.2, -116.78, AIRBORNE_BOXES + checked_extra_boxes([east]))
    assert checked_extra_boxes(None) == ()
    for bad in ([33.0, 33.35, -116.85], [33.0, 33.35, -116.85, "x"], [31.0, 33.0, -117.0, -116.0],
                [33.5, 33.0, -117.0, -116.0], [33.0, 33.4, -119.0, -116.0]):
        with pytest.raises(ValueError):
            checked_extra_boxes([bad])


def test_stage_mission_records_a_widened_fence_only_when_asked(tmp_path):
    aircraft = tmp_path / "Cessna_182T_G1000.acf"
    aircraft.write_text("built package fixture")
    plain = tmp_path / "plain"
    stage_observer(plain, aircraft, mode="mission")
    assert "extra_airborne_boxes" not in json.loads((plain / "capvsar_flight_control_config.json").read_text())
    wide = tmp_path / "wide"
    stage_observer(wide, aircraft, mode="mission", extra_boxes=[(33.0, 33.35, -116.85, -116.70)])
    assert json.loads((wide / "capvsar_flight_control_config.json").read_text())["extra_airborne_boxes"] == \
        [[33.0, 33.35, -116.85, -116.7]]
    with pytest.raises(ValueError, match="outside the Southern California"):
        stage_observer(tmp_path / "bad", aircraft, mode="mission", extra_boxes=[(10., 11., 0., 1.)])


def test_a_hand_back_may_ease_down_to_the_target_speed_but_not_undershoot_it():
    """ESCON run 4, 2026-10-15: handed 119.6 KIAS mid-climb with a 100 KIAS target, the AI pilot's law
    fell to 90.0 KIAS (a power cut). Run 5, with the slower ramp, eased to 104.6 and held."""
    def fly(speeds):
        observer = OwnerTrialObserver(altitude_ft=4000., speed_target_kias=100.)
        observer.enter("direct1", snap(0, kias=119.6))
        observer.enter("direct2", snap(0.25, kias=119.6))
        result, t = None, .25
        for kias in speeds:
            t += .5
            observer.terrain_override = True            # climbing under the guard's floor
            result = observer.observe(snap(t, kias=kias, alt=4000.))
            if result:
                break
        return observer, result
    ok, result = fly([119., 117., 114., 111., 108., 105., 103., 101., 100.])
    assert result is None and ok.report()["phases"]["direct2"]["min_kias_after_handback"] == 100.
    bad, result = fly([118., 112., 104., 98., 94.])
    assert result.startswith("Speed undershot after the hand-back: 94 KIAS")
    # with no target the entry speed is the reference
    plain = OwnerTrialObserver(altitude_ft=4000.)
    plain.enter("direct2", snap(0, kias=110.))
    assert plain.observe(snap(.25, kias=106., alt=4000.)) is None            # 110 - 5 = 105
    assert plain.observe(snap(.5, kias=104., alt=4000.)).startswith("Speed undershot")
