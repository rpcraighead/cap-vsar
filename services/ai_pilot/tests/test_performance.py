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
    with pytest.raises(PerformanceError, match="at least 3 vertical speeds"):
        table([(t, v, 60 + 90 * t - .02 * v) for t in (.4, .6, .8, 1.) for v in (0., 500.)])
    with pytest.raises(PerformanceError, match="throttle points; needs 2"):
        table([(t, 0., 60 + 90 * t) for t in (.4, .6, .8, 1.)] + [(t, 500., 50 + 90 * t) for t in (.6, 1.)]
              + [(1., -500., 150.)])
    with pytest.raises(PerformanceError, match="too thin"):
        table([(t, v, 60 + 90 * t - .02 * v) for t in (.6, 1.) for v in (-500., 0., 500.)])
    with pytest.raises(PerformanceError, match="falls as throttle rises"):
        table([(.4, 0., 100.), (.6, 0., 90.), (.8, 0., 120.), (.4, 500., 90.), (.6, 500., 100.), (.8, 500., 110.)]
              + [(t, -500., 70. + 90. * t) for t in (.4, .6, .8)])
    with pytest.raises(PerformanceError, match="duplicate throttle"):
        table([(.4, 0., 96.), (.4, 0., 96.5), (.6, 0., 114.), (.4, 500., 86.), (.6, 500., 104.), (.8, 500., 122.)]
              + [(t, -500., 70. + 90. * t) for t in (.4, .6, .8)])


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
    with pytest.raises(ProfileError, match="at least 3 vertical speeds"):
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


# --- what climb the airplane can actually hold --------------------------------------------------------------------

def weak_table():
    """An underpowered airplane: full throttle holds 105 KIAS level but only 80 KIAS in a 400 fpm climb."""
    rows = {-400.: (110., 118., 124.), 0.: (88., 96., 105.), 400.: (62., 71., 80.)}     # speeds at throttle .6/.8/1.0
    return table([(t, v, k) for v, ks in rows.items() for t, k in zip((.6, .8, 1.), ks)])


def test_sustainable_climb_is_read_from_the_full_throttle_row_without_extrapolating():
    t = weak_table()
    assert t.sustainable_vvi(80.) == pytest.approx(400.)          # holds a 400 fpm climb at 80 KIAS, no more is measured
    assert t.sustainable_vvi(70.) == pytest.approx(400.)          # slower: still the best measured, not extrapolated
    assert t.sustainable_vvi(92.5) == pytest.approx(200., abs=1.)  # between the level row (105) and the climb row (80)
    assert t.sustainable_vvi(110.) <= 0.                           # faster than level full throttle holds: no climb
    assert table().sustainable_vvi(100.) == pytest.approx(500.)    # the strong synthetic airplane: its best row
    # only rows measured at (nearly) full throttle count
    partial = table([(t_, v, 60 + 90 * t_ - .02 * v) for t_ in (.4, .6, .8) for v in (-500., 0., 500.)])
    assert partial.sustainable_vvi(90.) is None


def test_an_edge_climb_row_may_have_only_two_points():
    pts = [(t, v, 60. + 90. * t - 0.02 * v) for t in (.4, .6, .8, 1.) for v in (-500., 0.)] + [(.9, 400., 81.), (1., 400., 101.)]
    assert max(len(r) for r in table(pts).rows().values()) >= 3
    t = table(pts)
    assert t.throttle_for(91., 400.)[0] == pytest.approx(.95, abs=.01)


def test_the_cruise_law_will_not_ask_for_a_climb_the_airplane_cannot_hold():
    from dataclasses import replace
    weak = replace(C182T, performance=weak_table())
    strong = replace(C182T, performance=table())
    # 200 ft low: the law wants +400 fpm. The strong airplane (measured to 500 fpm) can; the weak one cannot.
    for profile, capped in ((weak, True), (strong, False)):
        _, diag = CruiseLaw(profile).frame(level_values(90., alt=3800.), 0., 90., 4000., 90., .05)
        assert diag["climb_capped"] is capped
    _, weak_diag = CruiseLaw(weak).frame(level_values(90., alt=3800.), 0., 90., 4000., 90., .05)
    assert 0. < weak_diag["target_vvi_fpm"] < 300.
    _, none_diag = CruiseLaw(replace(C182T, performance=None)).frame(level_values(90., alt=2000.), 0., 90., 4000., 90., .05)
    assert none_diag["target_vvi_fpm"] == 650. and none_diag["climb_capped"] is False   # as flown
    # descents are never capped
    _, down = CruiseLaw(weak).frame(level_values(90., alt=6000.), 0., 90., 4000., 90., .05)
    assert down["target_vvi_fpm"] == -650.


def test_the_profile_reports_the_climb_it_may_ask_for():
    from dataclasses import replace
    assert replace(C182T, performance=None).sustainable_climb_fpm() is None
    assert C182T.sustainable_climb_fpm() == pytest.approx(0.85 * 700.)          # the measured CAP 487 table
    weak = replace(C182T, performance=weak_table(), climb_enroute_kias=80.)
    assert weak.sustainable_climb_fpm() == pytest.approx(0.85 * 400.)


def test_the_terrain_guard_plans_and_orders_only_the_climb_the_airplane_can_hold():
    from services.ai_pilot.tests.test_terrain_guard import snapshot, terrain
    from services.ai_pilot.terrain_guard import TerrainGuard
    normal = TerrainGuard().update(snapshot(4000., terrain(5200., 5.)))
    assert normal.climb_fpm == 700                                  # below the ground: the demo's urgent rate
    weak = TerrainGuard(max_climb_fpm=300.)
    advice = weak.update(snapshot(4000., terrain(5200., 5.)))
    assert advice.climb_fpm == 300
    # a slower climber has to start earlier: 5.0 nm is too far for the strong airplane to need the floor yet
    far = snapshot(4000., terrain(4700., 8.))
    assert TerrainGuard().update(far).floor_indicated_ft is None
    assert TerrainGuard(max_climb_fpm=200.).update(far).floor_indicated_ft is not None
