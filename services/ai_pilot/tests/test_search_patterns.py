"""Pattern geometry against the cross-repo fixture, and a kinematic fly-through."""
import json
import math
from pathlib import Path

import pytest

from services.ai_pilot.aircraft_profiles import C172SP, C182T
from services.ai_pilot.search_patterns import (SearchPatternController, Waypoint, bearing_true,
                                               creeping_line, distance_nm, expanding_square,
                                               parallel_track, track_miles, wrap180)

FIXTURE = Path(__file__).with_name("data") / "search_pattern_fixtures.json"


def generate(case):
    p = case["params"]
    d = p["datum"]
    if case["pattern"] == "expanding_square":
        return expanding_square(d["lat"], d["lon"], p["heading_true"], p["spacing_nm"],
                                p["legs"], p["turn"])
    if case["pattern"] == "parallel":
        return parallel_track(d["lat"], d["lon"], p["heading_true"], p["length_nm"],
                              p["spacing_nm"], p["legs"], p["turn"])
    if case["pattern"] == "creeping_line":
        return creeping_line(d["lat"], d["lon"], p["heading_true"], p["width_nm"],
                             p["spacing_nm"], p["legs"], p["first_turn"])
    raise AssertionError(case["pattern"])


def cases():
    data = json.loads(FIXTURE.read_text())
    return data if isinstance(data, list) else data["cases"]


@pytest.mark.parametrize("case", cases(), ids=lambda c: c["id"])
def test_fixture_names_and_positions_are_reproduced(case):
    points = generate(case)
    assert [w.name for w in points] == case["names"]
    for w, expected in zip(points, case["points"]):
        assert distance_nm(w.lat, w.lon, expected["lat"], expected["lon"]) < 0.003  # < 6 m


def test_expanding_square_leg_lengths_grow_in_pairs_and_turn_the_right_way():
    pts = expanding_square(33.1, -117.3, 0., 1., 6, "right")
    lengths = [distance_nm(a.lat, a.lon, b.lat, b.lon) for a, b in zip(pts, pts[1:])]
    assert lengths == pytest.approx([1, 1, 2, 2, 3, 3], abs=.01)
    courses = [bearing_true(a.lat, a.lon, b.lat, b.lon) for a, b in zip(pts, pts[1:])]
    turns = [wrap180(b - a) for a, b in zip(courses, courses[1:])]
    assert all(abs(t - 90) < 1 for t in turns)
    left = expanding_square(33.1, -117.3, 0., 1., 6, "left")
    courses = [bearing_true(a.lat, a.lon, b.lat, b.lon) for a, b in zip(left, left[1:])]
    assert all(abs(wrap180(b - a) + 90) < 1 for a, b in zip(courses, courses[1:]))


def test_parallel_track_lanes_are_spaced_on_the_turn_side():
    pts = parallel_track(33.1, -117.0, 90., 5., 1., 3, "right")
    assert [w.name for w in pts] == ["PS%02d" % i for i in range(1, 7)]
    assert distance_nm(pts[0].lat, pts[0].lon, pts[1].lat, pts[1].lon) == pytest.approx(5., abs=.01)
    assert abs(wrap180(bearing_true(pts[1].lat, pts[1].lon, pts[2].lat, pts[2].lon) - 180)) < 1
    assert track_miles(pts) == pytest.approx(17., abs=.05)


def test_pattern_parameters_are_bounded():
    with pytest.raises(ValueError):
        expanding_square(33.1, -117.3, 0., 0.01, 4)
    with pytest.raises(ValueError):
        parallel_track(33.1, -117.3, 0., 5., 1., 0)
    with pytest.raises(ValueError):
        creeping_line(33.1, -117.3, 0., 3., 1., 4, first_turn="straight")
    with pytest.raises(ValueError):
        Waypoint("", 0., 0.)


# ---------------------------------------------------------------------------
# A point-mass aircraft: the controller's yoke command sets a roll rate, bank
# sets the turn rate, altitude and speed are held so the lateral law is isolated.

def fly(controller, lat, lon, heading, kias=100., dt=.2, max_s=5400.):
    gs = kias * .514444
    roll = roll_rate = 0.
    t = 0.
    samples = []
    while t < max_s and not controller.done:
        snapshot = {"values": {"sim_time_s": t, "latitude_deg": lat, "longitude_deg": lon,
                               "heading_true_deg": heading % 360, "altitude_indicated_ft": 1500.,
                               "kias": kias, "vvi_fpm": 0., "pitch_deg": 2., "pitch_rate_dps": 0.,
                               "roll_deg": roll, "roll_rate_dps": roll_rate, "beta_deg": 0.,
                               "groundspeed_mps": gs},
                    "controls": {"trim": 0.}}
        frame = controller.step(snapshot)
        assert set(frame) == {"roll", "pitch", "yaw", "throttle", "flap", "trim", "brake"}
        # Roll rate follows the yoke through a half-second lag, as an airframe does;
        # an instantaneous response would alias against the rate-damping term.
        roll_rate += (max(-40., min(40., frame["roll"] * 90.)) - roll_rate) * min(1., dt / .5)
        roll = max(-45., min(45., roll + roll_rate * dt))
        heading = (heading + math.degrees(9.80665 * math.tan(math.radians(roll)) / gs) * dt) % 360
        lat += gs * dt * math.cos(math.radians(heading)) / 111132.92
        lon += gs * dt * math.sin(math.radians(heading)) / (111412.84 * math.cos(math.radians(lat)))
        t += dt
        samples.append((t, lat, lon, heading, roll, dict(controller.last_diagnostics)))
    return samples


def closest_approach_nm(samples, waypoint):
    return min(distance_nm(lat, lon, waypoint.lat, waypoint.lon) for _, lat, lon, _, _, _ in samples)


def signed_heading_changes(samples, transitions):
    """Net heading change between successive waypoint captures."""
    times = [tr["sim_time_s"] for tr in transitions]
    changes = []
    for start, end in zip(times, times[1:]):
        total = 0.
        previous = None
        for t, _, _, heading, _, _ in samples:
            if start <= t <= end:
                if previous is not None:
                    total += wrap180(heading - previous)
                previous = heading
        changes.append(total)
    return changes


def expected_corner_turns(points):
    courses = [bearing_true(a.lat, a.lon, b.lat, b.lon) for a, b in zip(points, points[1:])]
    return [0.] + [wrap180(b - a) for a, b in zip(courses, courses[1:])]


def test_parallel_track_is_flown_in_order_with_right_turns_and_small_cross_track():
    pts = parallel_track(33.10, -117.00, 25., 4., 1., 4, "right")
    controller = SearchPatternController(pts, altitude_indicated_ft=1500., profile=C182T)
    samples = fly(controller, 33.085, -117.01, 25., kias=controller.kias)
    assert controller.done
    assert [tr["waypoint"] for tr in controller.transitions] == [w.name for w in pts]
    for w in pts:
        assert closest_approach_nm(samples, w) < .35
    # Lanes alternate direction while the cross-steps all go to the turn side, so
    # a right-handed parallel track turns right, right, left, left, right ...
    # Each corner must be turned the way the geometry says, never the long way round.
    changes = signed_heading_changes(samples, controller.transitions)
    assert expected_corner_turns(pts)[1:] == pytest.approx(changes[1:], abs=30.)
    settled = [abs(d["cross_track_m"]) for _, _, _, _, _, d in samples
               if d.get("stage") == "pattern" and d["index"] >= 2 and not d["forced_turn"]
               and d["along_m"] > 1200 and d["distance_nm"] * 1852 > d["lead_m"] + 300]
    assert settled and max(settled) < 120.


def test_expanding_square_turns_left_when_asked():
    pts = expanding_square(33.10, -117.30, 0., 1., 6, "left")
    controller = SearchPatternController(pts, altitude_indicated_ft=1200., profile=C172SP)
    samples = fly(controller, 33.09, -117.30, 0., kias=controller.kias)
    assert controller.done
    assert len(controller.transitions) == len(pts)
    changes = signed_heading_changes(samples, controller.transitions)
    assert all(-120 < c < -60 for c in changes[1:]), changes
    assert expected_corner_turns(pts)[1:] == pytest.approx(changes[1:], abs=30.)


def test_creeping_line_completes_and_holds_the_final_course():
    pts = creeping_line(33.10, -117.00, 90., 3., 1., 4, "right")
    controller = SearchPatternController(pts, altitude_indicated_ft=1500., profile=C182T)
    samples = fly(controller, 33.08, -117.02, 60., kias=controller.kias)
    assert controller.done
    assert [tr["waypoint"] for tr in controller.transitions] == [w.name for w in pts]
    frame = controller.step({"values": samples[-1][5] and {
        "sim_time_s": samples[-1][0] + .2, "latitude_deg": samples[-1][1],
        "longitude_deg": samples[-1][2], "heading_true_deg": samples[-1][3],
        "altitude_indicated_ft": 1500., "kias": 100., "vvi_fpm": 0., "pitch_deg": 2.,
        "pitch_rate_dps": 0., "roll_deg": 0., "roll_rate_dps": 0., "beta_deg": 0.,
        "groundspeed_mps": 51.}, "controls": {"trim": 0.}})
    assert controller.last_diagnostics["stage"] == "complete"
    assert abs(frame["roll"]) < .1


def test_controller_refuses_out_of_envelope_speed_and_lost_pattern():
    pts = parallel_track(33.10, -117.00, 90., 3., 1., 2)
    with pytest.raises(ValueError, match="envelope"):
        SearchPatternController(pts, altitude_indicated_ft=1500., kias=60.)
    controller = SearchPatternController(pts, altitude_indicated_ft=1500.)
    far = {"values": {"sim_time_s": 0., "latitude_deg": 33.10, "longitude_deg": -117.00,
                      "heading_true_deg": 90., "altitude_indicated_ft": 1500., "kias": 90.,
                      "vvi_fpm": 0., "pitch_deg": 2., "pitch_rate_dps": 0., "roll_deg": 0.,
                      "roll_rate_dps": 0., "beta_deg": 0., "groundspeed_mps": 46.},
           "controls": {"trim": 0.}}
    controller.step(far)
    far["values"].update(sim_time_s=1., latitude_deg=33.30)
    with pytest.raises(ValueError, match="lost"):
        controller.step(far)


def observer_snapshot(t, lat, lon, alt=1500., kias=100., roll=0., frame=None, paused=0):
    return {"frame": frame if frame is not None else int(t * 10) + 1,
            "aircraft": {"name": "Cessna_182T_G1000.acf"},
            "values": {"sim_time_s": t, "latitude_deg": lat, "longitude_deg": lon,
                       "altitude_indicated_ft": alt, "kias": kias, "roll_deg": roll,
                       "paused": paused, "on_ground": 0}}


def test_observer_scores_a_fly_through_independently():
    from services.ai_pilot.search_patterns import PatternObserver
    pts = expanding_square(33.10, -117.30, 0., 1., 4, "right")
    controller = SearchPatternController(pts, altitude_indicated_ft=1500., profile=C182T)
    samples = fly(controller, 33.09, -117.30, 0., kias=controller.kias)
    observer = PatternObserver(pts, altitude_indicated_ft=1500., aircraft_name="Cessna_182T_G1000.acf")
    report = None
    for i, (t, lat, lon, _, roll, _) in enumerate(samples):
        report = observer.observe(observer_snapshot(t, lat, lon, roll=roll, frame=i + 1))
    assert report["outcome"] == "PASS", report
    assert [r["waypoint"] for r in report["reached"]] == [w.name for w in pts]


def test_observer_fails_altitude_excursion_and_wrong_aircraft():
    from services.ai_pilot.search_patterns import PatternObserver
    pts = expanding_square(33.10, -117.30, 0., 1., 2)
    o = PatternObserver(pts, altitude_indicated_ft=1500.)
    o.observe(observer_snapshot(1., pts[0].lat, pts[0].lon))
    assert o.observe(observer_snapshot(1.1, pts[0].lat + .001, pts[0].lon, alt=1750.))["reason"] == \
        "Altitude outside tolerance on the pattern"
    wrong = PatternObserver(pts, altitude_indicated_ft=1500., aircraft_name="Cessna_172SP_G1000.acf")
    assert wrong.observe(observer_snapshot(1., 33., -117.))["reason"] == "Wrong aircraft"
