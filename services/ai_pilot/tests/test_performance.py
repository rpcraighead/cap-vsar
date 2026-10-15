"""The measured throttle-for-(airspeed, climb rate) table and its use as feed-forward."""
import shutil

import pytest

from services.ai_pilot.aircraft_profiles import C182T
from services.ai_pilot.performance import PerformanceError, PerformanceTable
from services.ai_pilot.profile_loader import PROFILE_DIR, ProfileError, load_profile
from services.ai_pilot.search_patterns import CruiseLaw

HASH = "ab" * 32


def table(points=None, **changes):
    # a plausible airplane: speed rises with throttle, falls as the climb rate rises
    if points is None:
        points = [(t, v, 60. + 90. * t - 0.020 * v) for t in (.4, .6, .8, 1.) for v in (-500., 0., 500.)]
    kw = dict(acf_sha256=HASH, altitude_ft=4000., mass_kg=990., conditions="ISA, calm", evidence="x", points=tuple(points))
    kw.update(changes)
    return PerformanceTable(**kw)


def test_it_inverts_the_measured_map_exactly_at_a_measured_point():
    t = table()
    for throttle, vvi, kias in t.points:
        got, in_range = t.throttle_for(kias, vvi)
        assert got == pytest.approx(throttle, abs=1e-9) and in_range


def test_it_interpolates_between_airspeeds_and_between_climb_rates():
    t = table()
    # level flight at 120 KIAS: 60 + 90 t = 120 -> t = 0.667
    assert t.throttle_for(120., 0.)[0] == pytest.approx(2 / 3, abs=1e-6)
    # a climb needs more power for the same speed: +500 fpm costs 0.02*500/90 = 0.111 of throttle
    assert t.throttle_for(120., 500.)[0] == pytest.approx(2 / 3 + 0.111, abs=2e-3)
    assert t.throttle_for(120., 250.)[0] == pytest.approx(2 / 3 + 0.0556, abs=2e-3)
    assert t.throttle_for(120., -500.)[0] < t.throttle_for(120., 0.)[0]


def test_outside_the_measured_range_it_holds_the_nearest_measurement_and_says_so():
    t = table()
    low, ok = t.throttle_for(40., 0.)
    assert low == pytest.approx(.4) and not ok
    high, ok = t.throttle_for(200., 0.)
    assert high == pytest.approx(1.) and not ok
    steep, ok = t.throttle_for(120., 900.)               # steeper than anything measured
    assert steep == pytest.approx(t.throttle_for(120., 500.)[0]) and not ok


@pytest.mark.parametrize("change,match", [
    ({"acf_sha256": "nothex"}, "SHA-256"), ({"altitude_ft": -1.}, "altitude"), ({"mass_kg": 0.}, "mass"),
    ({"conditions": " "}, "conditions"), ({"evidence": ""}, "evidence"),
])
def test_a_table_must_say_what_it_was_measured_on(change, match):
    with pytest.raises(PerformanceError, match=match):
        table(**change)


def test_a_table_must_be_a_real_map():
    with pytest.raises(PerformanceError, match="at least 2 vertical speeds"):
        table([(t, 0., 60 + 90 * t) for t in (.4, .6, .8)])
    with pytest.raises(PerformanceError, match="throttle points"):
        table([(.4, 0., 96.), (.6, 0., 114.), (.4, 500., 86.), (.6, 500., 104.)])
    with pytest.raises(PerformanceError, match="falls as throttle rises"):
        table([(.4, 0., 100.), (.6, 0., 90.), (.8, 0., 120.), (.4, 500., 90.), (.6, 500., 100.), (.8, 500., 110.)])
    with pytest.raises(PerformanceError, match="duplicate throttle"):
        table([(.4, 0., 96.), (.4, 0., 96.5), (.6, 0., 114.), (.4, 500., 86.), (.6, 500., 104.), (.8, 500., 122.)])


# --- in a profile file ---------------------------------------------------------------------------------

def base_text():
    """The shipped C182T file without its [performance] table, to attach test tables to."""
    return (PROFILE_DIR / "c182t.toml").read_text().split("\n[performance]\n")[0].rstrip("\n") + "\n"


def toml_with_table(tmp_path, points):
    text = base_text()
    block = ('\n[performance]\nacf_sha256 = "%s"\naltitude_ft = 4000.0\nmass_kg = 990.0\n'
             'conditions = "ISA, calm"\nevidence = "docs/evidence/x.json"\npoints = [%s]\n' % (HASH, ", ".join(
                 "[%s, %s, %s]" % p for p in points)))
    path = tmp_path / "x.toml"
    path.write_text(text + block)
    return path


def test_a_profile_file_can_carry_a_performance_table(tmp_path):
    points = [(t, v, 60. + 90. * t - 0.020 * v) for t in (.4, .6, .8, 1.) for v in (-500., 0., 500.)]
    profile = load_profile(toml_with_table(tmp_path, points))
    assert profile.performance is not None and profile.performance.acf_sha256 == HASH
    assert profile.performance.throttle_for(120., 0.)[0] == pytest.approx(2 / 3, abs=1e-6)
    assert C182T.performance is not None and len(C182T.performance.acf_sha256) == 64   # the shipped, measured table


def test_a_malformed_performance_table_in_a_file_is_a_profile_error(tmp_path):
    with pytest.raises(ProfileError, match="at least 2 vertical speeds"):
        load_profile(toml_with_table(tmp_path, [(.4, 0., 96.), (.6, 0., 114.), (.8, 0., 132.)]))
    bad = tmp_path / "bad.toml"
    bad.write_text(base_text() + '\n[performance]\nacf_sha256 = "x"\n')
    with pytest.raises(ProfileError, match=r"\[performance\] needs exactly"):
        load_profile(bad)


# --- feed-forward in the cruise law -------------------------------------------------------------------------

def level_values(kias, alt=4000., vvi=0.):
    return {"sim_time_s": 100., "on_ground": 0, "agl_m": 800., "kias": kias, "flap_actual": 0.,
            "vvi_fpm": vvi, "heading_true_deg": 90., "roll_deg": 0., "roll_rate_dps": 0.,
            "altitude_indicated_ft": alt, "pitch_deg": 2., "pitch_rate_dps": 0., "beta_deg": 0.}


def test_with_a_table_the_law_starts_from_the_throttle_the_airplane_needs():
    from dataclasses import replace
    profile = replace(C182T, performance=table())
    _, level = CruiseLaw(profile).frame(level_values(100., alt=4000.), 0., 90., 4000., 100., .05)
    frame, climb = CruiseLaw(profile).frame(level_values(100., alt=3800.), 0., 90., 4000., 100., .05)
    # 200 ft below the target the law asks for a 400 fpm climb; the table says that costs power
    assert climb["target_vvi_fpm"] == pytest.approx(400.)
    assert climb["feed_forward_in_table"] and level["feed_forward_in_table"]
    assert climb["feed_forward_throttle"] == pytest.approx(level["feed_forward_throttle"] + 0.020 * 400 / 90, abs=2e-3)
    assert frame["throttle"] > CruiseLaw(profile).frame(level_values(100., alt=4000.), 0., 90., 4000., 100., .05)[0]["throttle"]
    # without a table: the law exactly as flown
    old, old_diag = CruiseLaw(replace(C182T, performance=None)).frame(level_values(100., alt=3800.), 0., 90., 4000., 100., .05)
    assert old_diag["feed_forward_throttle"] is None and old["throttle"] == pytest.approx(.55 + 0.0, abs=.2)


# --- the sweep -> profile converter ---------------------------------------------------------------------------

def sweep_log():
    points = []
    for t in (.5, .6, .7, .8):
        for v in (400., 0., -400.):
            kias = 60. + 90. * t - 0.020 * v
            points.append({"throttle": t, "target_vvi_fpm": v, "outcome": "settled", "kias": kias, "alt": 3900. + 50 * t,
                           "mass": 990., "cowl": .5})
    points.append({"throttle": .5, "target_vvi_fpm": 800., "outcome": "low_speed", "kias": 74., "alt": 4000.,
                   "mass": 990., "cowl": .5})
    return {"profile": "C182T", "acf_sha256": HASH, "altitude_ft": 4000., "points": points,
            "conditions": "ISA, calm, full rich, prop full forward, flaps up, autopilot holding vertical speed"}


def test_the_converter_keeps_only_settled_points_and_the_block_round_trips_through_the_loader(tmp_path):
    from scripts.perf_table_to_toml import build, render
    built, dropped = build(sweep_log(), "docs/evidence/x.json")
    assert len(built.points) == 12 and len(dropped) == 1 and dropped[0]["outcome"] == "low_speed"
    assert built.altitude_ft == 3932 and built.mass_kg == 990.0       # mean of the settled points
    text = base_text() + "\n" + render(built)
    path = tmp_path / "x.toml"
    path.write_text(text)
    loaded = load_profile(path).performance
    assert sorted(loaded.points) == sorted(built.points) and loaded.acf_sha256 == HASH   # rendered grouped by climb rate
    for throttle, vvi, kias in built.points:
        assert loaded.throttle_for(kias, vvi)[0] == pytest.approx(throttle, abs=1e-9)
