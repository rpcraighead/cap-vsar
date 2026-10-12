"""Pattern geometry in every hemisphere, and the conventions the G1000 work shares (L2-8, L2-13).

The planner's own tests had one datum, in the north-west quadrant. Longitude
signs and the southern hemisphere are where a swapped sine/cosine or a wrong
hemisphere assumption would hide, so each pattern runs at several datums.
"""
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as flight_app  # noqa: E402
from app import (bearing, gc_dist, generate_creeping_line,  # noqa: E402
                 generate_expanding_square, generate_parallel_track)

DATUMS = {
    "north-west (San Diego)": (33.17, -117.0792),
    "south-east (Sydney)": (-33.9, 151.2),
    "south-west (Buenos Aires)": (-34.6, -58.4),
    "north-east (Berlin)": (52.5, 13.4),
    "antimeridian": (10.0, 179.995),
}


def angle_diff(a, b):
    return (a - b + 180) % 360 - 180


class ExpandingSquareEverywhere(unittest.TestCase):
    def test_leg_lengths_and_headings_hold_in_every_hemisphere(self):
        for name, (lat, lon) in DATUMS.items():
            for turn, step in (("right", 90), ("left", -90)):
                with self.subTest(datum=name, turn=turn):
                    pts = generate_expanding_square(lat, lon, 1.0, 8, 30.0, turn)
                    self.assertEqual(pts[0]["identifier"], "DATUM")
                    for i in range(1, len(pts)):
                        a, b = pts[i - 1], pts[i]
                        self.assertAlmostEqual(gc_dist(a["lat"], a["lon"], b["lat"], b["lon"]),
                                               b["leg_dist_nm"], delta=0.01)
                        self.assertAlmostEqual(
                            angle_diff(bearing(a["lat"], a["lon"], b["lat"], b["lon"]),
                                       b["heading_true"]), 0, delta=0.5)
                        self.assertTrue(-180 <= b["lon"] <= 180)
                    # Each leg turns 90 degrees the requested way.
                    for i in range(2, len(pts)):
                        self.assertAlmostEqual(
                            angle_diff(pts[i]["heading_true"], pts[i - 1]["heading_true"]),
                            step, delta=0.2)

    def test_north_then_east_reads_the_same_sign_everywhere(self):
        # Heading 000 then a right turn: latitude rises, then longitude rises
        # (east is +lon on both sides of the prime meridian), in either hemisphere.
        for name, (lat, lon) in DATUMS.items():
            if name == "antimeridian":
                continue
            with self.subTest(datum=name):
                d, s1, s2 = generate_expanding_square(lat, lon, 1.0, 2, 0.0, "right")[:3]
                self.assertGreater(s1["lat"], d["lat"])
                self.assertAlmostEqual(s1["lon"], d["lon"], places=4)
                self.assertGreater(s2["lon"], s1["lon"])


class LeftTurnMagneticHeadings(unittest.TestCase):
    def test_left_turn_heading_mag_is_true_minus_variation(self):
        with patch.object(flight_app, "mag_var", return_value=10.0):      # 10 E
            pts = generate_expanding_square(33.17, -117.0792, 1.0, 4, 0.0, "left")
        self.assertEqual([p["heading_true"] for p in pts], [0.0, 0.0, 270.0, 180.0, 90.0])
        self.assertEqual([p["heading_mag"] for p in pts], [350.0, 350.0, 260.0, 170.0, 80.0])

    def test_west_variation_adds(self):
        with patch.object(flight_app, "mag_var", return_value=-7.5):      # 7.5 W
            pts = generate_expanding_square(33.17, -117.0792, 1.0, 4, 350.0, "left")
        # 350 -> 260 -> 170 -> 80, then plus 7.5
        self.assertEqual([p["heading_mag"] for p in pts[1:]], [357.5, 267.5, 177.5, 87.5])

    def test_real_variation_is_applied_to_every_leg(self):
        pts = generate_expanding_square(33.17, -117.0792, 1.0, 4, 0.0, "left")
        var = flight_app.mag_var(33.17, -117.0792)
        for p in pts[1:]:
            self.assertAlmostEqual(angle_diff(p["heading_true"] - p["heading_mag"], var), 0, delta=1.0)


class ParallelTrackLanesLieToTheRight(unittest.TestCase):
    @staticmethod
    def cross_track(origin, heading, point):
        dist = gc_dist(*origin, point["lat"], point["lon"])
        return dist * math.sin(math.radians(angle_diff(bearing(*origin, point["lat"], point["lon"]), heading)))

    def test_lane_starts_step_right_by_one_spacing(self):
        for name, origin in DATUMS.items():
            if name == "antimeridian":
                continue
            for axis in (0.0, 90.0, 225.0, 310.0):
                with self.subTest(datum=name, axis=axis):
                    pts = generate_parallel_track(*origin, 6.0, 4.0, axis, 1.0)
                    starts = pts[0::2]          # PS01, then each lane's far-end turn
                    lane_points = [pts[0]] + [p for p in pts[1:] if p["leg_dist_nm"] == 1.0]
                    offsets = [self.cross_track(origin, axis, p) for p in lane_points]
                    self.assertTrue(all(o > 0 for o in offsets), (name, axis, offsets))
                    for i, o in enumerate(offsets):
                        self.assertAlmostEqual(o, (i + 0.5) * 1.0, delta=0.03)
                    self.assertEqual(len(starts), 4)

    def test_lanes_alternate_direction(self):
        pts = generate_parallel_track(33.0, -117.0, 6.0, 3.0, 0.0, 1.0)
        lanes = [p["heading_true"] for p in pts[1:] if p["leg_dist_nm"] == 6.0]
        self.assertEqual(lanes, [0.0, 180.0, 0.0])

    def test_api_reports_the_lanes_on_the_right_in_the_south(self):
        flight_app.app.config["TESTING"] = True
        body = flight_app.app.test_client().post("/api/sar/generate-pattern", json={
            "datum": "@-33.9,151.2", "pattern_type": "parallel_track",
            "length_nm": 5, "width_nm": 3, "axis_heading": 0, "spacing_nm": 1}).get_json()
        lons = [p["lon"] for p in body["waypoints"]]
        self.assertEqual(lons[0], min(lons))                      # axis north: right is east
        self.assertGreater(max(lons), lons[0])
        self.assertGreater(body["waypoints"][1]["lat"], body["waypoints"][0]["lat"])


class CreepingLine(unittest.TestCase):
    def line(self, start, end, **kw):
        return generate_creeping_line(*start, *end, kw.get("width", 4.0), kw.get("spacing", 1.0),
                                      kw.get("legs", 4))

    def test_first_sweep_flies_toward_the_right(self):
        cases = {
            "north, west longitude": ((33.0, -117.0), (33.1, -117.0), +1),      # right = east
            "south, west longitude": ((33.1, -117.0), (33.0, -117.0), -1),      # right = west
            "north, southern hemisphere": ((-34.0, 151.0), (-33.9, 151.0), +1),
            "south, southern hemisphere": ((-33.9, 151.0), (-34.0, 151.0), -1),
        }
        for name, (start, end, east) in cases.items():
            with self.subTest(case=name):
                pts = self.line(start, end)
                cs1, cs2 = pts[0], pts[1]
                self.assertGreater((cs2["lon"] - cs1["lon"]) * east, 0)
                adv = bearing(*start, *end)
                self.assertAlmostEqual(
                    angle_diff(bearing(cs1["lat"], cs1["lon"], cs2["lat"], cs2["lon"]), adv + 90),
                    0, delta=0.5)
                self.assertAlmostEqual(gc_dist(cs1["lat"], cs1["lon"], cs2["lat"], cs2["lon"]),
                                       4.0, delta=0.02)

    def test_sweeps_alternate_and_advance(self):
        pts = self.line((33.0, -117.0), (33.1, -117.0))
        lons = [p["lon"] for p in pts]
        # CS01 left end, CS02 right end, CS03 right end advanced, CS04 left end ...
        self.assertLess(lons[0], lons[1])
        self.assertAlmostEqual(lons[1], lons[2], places=4)
        self.assertGreater(lons[2], lons[3])
        self.assertGreater(pts[2]["lat"], pts[1]["lat"])

    def test_cs01_carries_no_fictitious_leg(self):
        # L2-8: nothing is flown to reach the start, and the heading shown is
        # the first real leg's (CS01 -> CS02), exactly as for PS01.
        for name, origin in DATUMS.items():
            if name == "antimeridian":
                continue
            with self.subTest(datum=name):
                end = (origin[0] + 0.1, origin[1])
                pts = generate_creeping_line(*origin, *end, 4.0, 1.0, 4)
                cs1, cs2 = pts[0], pts[1]
                self.assertEqual(cs1["leg_dist_nm"], 0.0)
                self.assertEqual(cs1["heading_true"], cs2["heading_true"])
                self.assertAlmostEqual(
                    angle_diff(bearing(cs1["lat"], cs1["lon"], cs2["lat"], cs2["lon"]),
                               cs1["heading_true"]), 0, delta=0.5)
        ps1 = generate_parallel_track(33.0, -117.0, 5, 4, 0.0, 1.0)[0]
        self.assertEqual(ps1["leg_dist_nm"], 0.0)

    def test_cs01_in_the_nav_totals(self):
        flight_app.app.config["TESTING"] = True
        body = flight_app.app.test_client().post("/api/sar/generate-pattern", json={
            "datum": "@33.0,-117.0", "pattern_type": "creeping_line",
            "end_lat": 33.1, "end_lon": -117.0, "sweep_width_nm": 4, "spacing_nm": 1}).get_json()
        self.assertEqual(body["waypoints"][0]["leg_dist_nm"], 0.0)
        flown = sum(gc_dist(a["lat"], a["lon"], b["lat"], b["lon"])
                    for a, b in zip(body["waypoints"], body["waypoints"][1:]))
        self.assertAlmostEqual(sum(p["leg_dist_nm"] for p in body["waypoints"]), flown, delta=0.2)


class PatternApiInEveryHemisphere(unittest.TestCase):
    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    def test_all_three_patterns_resolve_negative_coordinates(self):
        for datum in ("@-33.9,151.2", "@33.17,-117.08", "@-34.6,-58.4"):
            for ptype in ("expanding_square", "creeping_line", "parallel_track"):
                with self.subTest(datum=datum, pattern=ptype):
                    r = self.client.post("/api/sar/generate-pattern",
                                         json={"datum": datum, "pattern_type": ptype})
                    self.assertEqual(r.status_code, 200)
                    body = r.get_json()
                    lat, lon = (float(v) for v in datum[1:].split(","))
                    self.assertEqual(body["datum"], {"lat": lat, "lon": lon})
                    for p in body["waypoints"]:
                        self.assertLess(abs(p["lat"] - lat), 1.0)
                        self.assertLess(abs(p["lon"] - lon), 1.0)
                        self.assertEqual(math.copysign(1, p["lat"]), math.copysign(1, lat))


if __name__ == "__main__":
    unittest.main()
