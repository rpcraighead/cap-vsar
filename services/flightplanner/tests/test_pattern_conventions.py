"""D2: the planner and the g1000-sar library agree on names and positions.

tests/data/search_pattern_fixtures.json is generated in g1000-sar
(scripts/make_pattern_fixtures.py) and copied here byte for byte. Each case is
the library's answer for one datum-based mission. The planner's generators take
boxes and start/end points, so the case is first run through the front-end
conversions in app.py (parallel_inputs_from_datum, creeping_inputs_from_datum)
and the result must match the library's names and positions to tolerance_m.
"""
import json
import math
import os
import sys
import unittest
from pathlib import Path

PLANNER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLANNER))
os.environ.setdefault("CAPVSAR_PRECACHE_CHARTS", "0")
import app as flight_app  # noqa: E402
from app import (creeping_datum_from_endpoints, creeping_inputs_from_datum,  # noqa: E402
                 destination_point, gc_dist, generate_creeping_line,
                 generate_expanding_square, generate_parallel_track,
                 parallel_datum_from_box, parallel_inputs_from_datum)

FIXTURE = json.loads((PLANNER / "tests" / "data" / "search_pattern_fixtures.json").read_text())
NM_M = 1852.0


def planner_points(case):
    """Run one fixture case through the conversion and the planner's generator."""
    p = case["params"]
    d = p["datum"]
    hdg, spacing, legs = p["heading_true"], p["spacing_nm"], p["legs"]
    if case["pattern"] == "expanding_square":
        return generate_expanding_square(d["lat"], d["lon"], spacing, legs, hdg, p.get("turn", "right"))
    if case["pattern"] == "parallel":
        box = parallel_inputs_from_datum(d["lat"], d["lon"], hdg, spacing, legs, p["turn"])
        return generate_parallel_track(box["corner_lat"], box["corner_lon"], p["length_nm"],
                                       box["width_nm"], box["axis_heading"], spacing, box["turn"])
    ends = creeping_inputs_from_datum(d["lat"], d["lon"], hdg, spacing, legs)
    return generate_creeping_line(ends["start_lat"], ends["start_lon"], ends["end_lat"], ends["end_lon"],
                                  p["width_nm"], spacing, max_legs=legs, first_turn=p["first_turn"])


def api_points(client, case):
    """The same case through POST /api/sar/generate-pattern (the box/endpoint front end)."""
    p = case["params"]
    d = p["datum"]
    hdg, spacing, legs = p["heading_true"], p["spacing_nm"], p["legs"]
    if case["pattern"] == "expanding_square":
        body = {"pattern_type": "expanding_square", "datum_lat": d["lat"], "datum_lon": d["lon"],
                "spacing_nm": spacing, "num_legs": legs, "initial_heading": hdg,
                "turn_direction": p["turn"]}
    elif case["pattern"] == "parallel":
        box = parallel_inputs_from_datum(d["lat"], d["lon"], hdg, spacing, legs, p["turn"])
        body = {"pattern_type": "parallel_track", "datum_lat": box["corner_lat"],
                "datum_lon": box["corner_lon"], "length_nm": p["length_nm"],
                "width_nm": box["width_nm"], "axis_heading": hdg, "spacing_nm": spacing,
                "turn_direction": p["turn"]}
    else:
        ends = creeping_inputs_from_datum(d["lat"], d["lon"], hdg, spacing, legs)
        body = {"pattern_type": "creeping_line", "datum_lat": ends["start_lat"],
                "datum_lon": ends["start_lon"], "end_lat": ends["end_lat"], "end_lon": ends["end_lon"],
                "sweep_width_nm": p["width_nm"], "spacing_nm": spacing, "num_legs": legs,
                "first_turn": p["first_turn"]}
    r = client.post("/api/sar/generate-pattern", json=body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


class FixtureFile(unittest.TestCase):
    def test_fixture_is_the_one_from_g1000_sar(self):
        self.assertEqual(FIXTURE["version"], 1)
        self.assertEqual(FIXTURE["tolerance_m"], 25)
        self.assertEqual(len(FIXTURE["cases"]), 24)
        kinds = {}
        for case in FIXTURE["cases"]:
            kinds[case["pattern"]] = kinds.get(case["pattern"], 0) + 1
        self.assertEqual(kinds, {"expanding_square": 12, "parallel": 6, "creeping_line": 6})


class PlannerMatchesTheLibrary(unittest.TestCase):
    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    def assert_case(self, case, points):
        tol = FIXTURE["tolerance_m"]
        self.assertEqual([p["identifier"] for p in points], case["names"], case["id"])
        self.assertEqual(len(points), len(case["points"]), case["id"])
        for i, (got, want) in enumerate(zip(points, case["points"])):
            err = gc_dist(got["lat"], got["lon"], want["lat"], want["lon"]) * NM_M
            self.assertLessEqual(err, tol, f"{case['id']} {case['names'][i]}: {err:.1f} m off")

    def test_generators_through_the_conversions(self):
        for case in FIXTURE["cases"]:
            with self.subTest(case=case["id"]):
                self.assert_case(case, planner_points(case))

    def test_api_through_the_conversions(self):
        for case in FIXTURE["cases"]:
            with self.subTest(case=case["id"]):
                self.assert_case(case, api_points(self.client, case)["waypoints"])


class ConversionsAreExactInverses(unittest.TestCase):
    def test_parallel_round_trip(self):
        for turn in ("right", "left"):
            for legs, spacing in ((1, 1.0), (4, 0.5), (7, 0.1), (30, 1.5)):
                with self.subTest(turn=turn, legs=legs, spacing=spacing):
                    box = parallel_inputs_from_datum(33.1, -117.0, 40.0, spacing, legs, turn)
                    lat, lon, n = parallel_datum_from_box(box["corner_lat"], box["corner_lon"],
                                                          box["width_nm"], 40.0, spacing, turn)
                    self.assertEqual(n, legs)
                    self.assertLess(gc_dist(lat, lon, 33.1, -117.0) * NM_M, 1.0)

    def test_parallel_lane_count_is_not_fooled_by_floating_point(self):
        # 3 * 0.1 / 0.1 is 3.0000000000000004 in floating point.
        self.assertEqual(flight_app.parallel_lane_count(3 * 0.1, 0.1), 3)
        self.assertEqual(flight_app.parallel_lane_count(4.1, 1.0), 5)
        self.assertEqual(flight_app.parallel_lane_count(0.4, 1.0), 1)

    def test_creeping_round_trip(self):
        for heading in (0, 25, 270):
            for legs, spacing in ((1, 1.0), (2, 0.5), (9, 1.5), (60, 0.5)):
                with self.subTest(heading=heading, legs=legs, spacing=spacing):
                    e = creeping_inputs_from_datum(-33.9, 151.2, heading, spacing, legs)
                    lat, lon, hdg, n = creeping_datum_from_endpoints(
                        e["start_lat"], e["start_lon"], e["end_lat"], e["end_lon"], spacing)
                    self.assertEqual(n, legs)
                    self.assertLess(gc_dist(lat, lon, -33.9, 151.2) * NM_M, 1.0)
                    self.assertAlmostEqual((hdg - heading + 180) % 360 - 180, 0, delta=0.1)

    def test_the_half_spacing_inset_is_what_makes_it_match(self):
        # Guard on the fixture test itself: with the inset dropped the planner
        # is a half spacing (~900 m at 1 NM) away from the library.
        case = next(c for c in FIXTURE["cases"] if c["id"] == "ps-right-h025-l6-west")
        p = case["params"]
        d = p["datum"]
        wrong = generate_parallel_track(d["lat"], d["lon"], p["length_nm"], p["legs"] * p["spacing_nm"],
                                        p["heading_true"], p["spacing_nm"], "right")
        want = case["points"][0]
        self.assertGreater(gc_dist(wrong[0]["lat"], wrong[0]["lon"], want["lat"], want["lon"]) * NM_M, 100)


class NewParameters(unittest.TestCase):
    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    def post(self, **kw):
        kw.setdefault("datum", "@33.0,-117.0")
        return self.client.post("/api/sar/generate-pattern", json=kw)

    def test_defaults_are_unchanged(self):
        a = generate_parallel_track(33.0, -117.0, 5, 4, 0.0, 1.0)
        b = generate_parallel_track(33.0, -117.0, 5, 4, 0.0, 1.0, "right")
        self.assertEqual(a, b)
        c = generate_creeping_line(33.0, -117.0, 33.1, -117.0, 4.0, 1.0, 4)
        d = generate_creeping_line(33.0, -117.0, 33.1, -117.0, 4.0, 1.0, 4, "right")
        self.assertEqual(c, d)
        self.assertLess(c[0]["lon"], c[1]["lon"])             # CS01 left end, CS02 right end

    def test_left_parallel_track_lies_left_of_the_axis(self):
        pts = generate_parallel_track(33.0, -117.0, 5, 4, 0.0, 1.0, "left")
        self.assertTrue(all(p["lon"] < -117.0 for p in pts))   # axis north: left is west
        self.assertEqual(len(pts), 8)

    def test_left_first_turn_mirrors_the_creeping_line(self):
        r = generate_creeping_line(33.0, -117.0, 33.1, -117.0, 4.0, 1.0, 4, "right")
        l = generate_creeping_line(33.0, -117.0, 33.1, -117.0, 4.0, 1.0, 4, "left")
        self.assertGreater(l[0]["lon"], l[1]["lon"])           # CS01 right end, CS02 left end
        for a, b in zip(r, l):
            self.assertEqual(a["identifier"], b["identifier"])
            self.assertAlmostEqual(a["lat"], b["lat"], places=5)
            self.assertAlmostEqual(a["lon"] + b["lon"], -234.0, places=3)   # mirrored about -117
        self.assertEqual(l[0]["heading_true"], l[1]["heading_true"])
        self.assertAlmostEqual(l[1]["heading_true"], 270.0, delta=0.5)

    def test_api_takes_turn_and_first_turn_and_rejects_nonsense(self):
        self.assertEqual(self.post(pattern_type="parallel_track", turn_direction="left").status_code, 200)
        self.assertEqual(self.post(pattern_type="creeping_line", first_turn="left").status_code, 200)
        self.assertEqual(self.post(pattern_type="creeping_line", first_turn="up").status_code, 400)
        self.assertEqual(self.post(pattern_type="creeping_line", first_turn=3).status_code, 400)

    def test_leg_caps(self):
        self.assertEqual(flight_app.MAX_PATTERN_LEGS, 60)
        sq = self.post(num_legs=60).get_json()
        self.assertEqual(len(sq["waypoints"]), 61)
        self.assertEqual(len(self.post(num_legs=500).get_json()["waypoints"]), 61)   # clamped
        cs = self.post(pattern_type="creeping_line", end_lat=33.6, end_lon=-117.0,
                       spacing_nm=1, num_legs=40).get_json()
        sweeps = math.ceil(gc_dist(33.0, -117.0, 33.6, -117.0))
        self.assertEqual(len(cs["waypoints"]), 2 * sweeps)      # was capped at 12 sweeps
        self.assertGreater(sweeps, 12)
        self.assertFalse(cs["coverage_truncated"])
        html = (PLANNER / "templates" / "index.html").read_text()
        self.assertIn('id="sar-ss-legs" value="8" step="2" min="4" max="60"', html)


class SearchCentre(unittest.TestCase):
    """D2.7: the console anchors on the middle of the search area, whatever the pattern."""

    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    @staticmethod
    def offset(lat, lon, along, across, heading):
        return flight_app.local_offset(lat, lon, along, across, heading)

    def expected_centre(self, case):
        p = case["params"]
        d, h, s, n = p["datum"], p["heading_true"], p["spacing_nm"], p["legs"]
        if case["pattern"] == "expanding_square":
            return d["lat"], d["lon"]
        if case["pattern"] == "parallel":                       # middle of the box
            side = 1 if p["turn"] == "right" else -1
            return self.offset(d["lat"], d["lon"], p["length_nm"] / 2, side * (n - 1) * s / 2, h)
        return self.offset(d["lat"], d["lon"], (n - 1) * s / 2, 0, h)   # middle of the sweeps

    def test_search_centre_is_the_middle_of_the_area_for_every_fixture(self):
        for case in FIXTURE["cases"]:
            with self.subTest(case=case["id"]):
                body = api_points(self.client, case)
                want = self.expected_centre(case)
                got = body["search_centre"]
                err = gc_dist(got["lat"], got["lon"], want[0], want[1]) * NM_M
                self.assertLessEqual(err, FIXTURE["tolerance_m"], f"{err:.1f} m")

    def test_parallel_centre_is_not_the_corner_or_the_first_lane(self):
        case = next(c for c in FIXTURE["cases"] if c["id"] == "ps-right-h270-l5")
        body = api_points(self.client, case)
        first = body["waypoints"][0]
        c = body["search_centre"]
        self.assertGreater(gc_dist(c["lat"], c["lon"], first["lat"], first["lon"]) * NM_M, 1000)


if __name__ == "__main__":
    unittest.main()
