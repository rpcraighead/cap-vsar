"""Planner failures must be visible, not defaulted (L2-1, L2-4, L2-5, L2-6)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as flight_app  # noqa: E402


class Reply:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body


class DatumIsNeverDefaulted(unittest.TestCase):
    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    def post(self, **payload):
        payload.setdefault("pattern_type", "expanding_square")
        return self.client.post("/api/sar/generate-pattern", json=payload)

    def test_an_unknown_identifier_is_an_error_not_ksee(self):
        with patch.object(flight_app, "get_coords", return_value=None):
            r = self.post(datum="KXYZ")
        self.assertEqual(r.status_code, 400)
        self.assertIn("KXYZ", r.get_json()["error"])

    def test_no_datum_at_all_is_an_error(self):
        self.assertEqual(self.post().status_code, 400)

    def test_an_explicit_point_still_works_and_is_range_checked(self):
        ok = self.post(datum_lat=34.0, datum_lon=-118.0)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.get_json()["datum"], {"lat": 34.0, "lon": -118.0})
        self.assertEqual(self.post(datum_lat=91, datum_lon=0).status_code, 400)
        self.assertEqual(self.post(datum_lat="x", datum_lon=0).status_code, 400)

    def test_a_non_string_datum_is_a_400_not_an_html_500(self):
        r = self.post(datum=12)
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.is_json)

    def test_parallel_track_reports_the_box_centre(self):
        r = self.post(datum="@33.0,-117.0", pattern_type="parallel_track",
                      length_nm=10.0, width_nm=4.0, axis_heading=0.0, spacing_nm=1.0)
        body = r.get_json()
        centre, corner = body["search_centre"], body["waypoints"][0]
        self.assertNotAlmostEqual(centre["lat"], corner["lat"], places=3)
        self.assertAlmostEqual(centre["lat"], 33.0 + 5.0 / 60.0, delta=0.01)   # 5 NM north of the corner
        self.assertGreater(centre["lon"], -117.0)                              # box lies to the right

    def test_expanding_square_centre_is_the_datum(self):
        body = self.post(datum="@33.0,-117.0").get_json()
        self.assertEqual(body["search_centre"], {"lat": 33.0, "lon": -117.0})


class WindsAndTerrainAreHonest(unittest.TestCase):
    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    def test_simulated_winds_are_not_planned_on(self):
        with patch.object(flight_app, "fetch_winds_aloft",
                          return_value=flight_app.simulate_winds(33.0, -117.0)):
            r = self.client.post("/api/calculate-route",
                                 json={"departure": "@33.0,-117.0", "destination": "@33.5,-117.0"})
        w = r.get_json()["winds_aloft"]
        self.assertEqual((w["direction"], w["speed"]), (0, 0))
        self.assertFalse(w["available"])
        self.assertTrue(w["simulated"])

    def test_real_winds_are_used(self):
        real = {"station": "GFS", "simulated": False,
                "levels": {6500: {"direction": 270, "speed": 20, "temp": 5}}}
        with patch.object(flight_app, "fetch_winds_aloft", return_value=real):
            r = self.client.post("/api/calculate-route",
                                 json={"departure": "@33.0,-117.0", "destination": "@33.5,-117.0"})
        w = r.get_json()["winds_aloft"]
        self.assertEqual((w["direction"], w["speed"], w["available"]), (270, 20, True))

    def profile(self, get):
        pts = [{"lat": 33.0, "lon": -117.0, "identifier": "A"},
               {"lat": 36.5, "lon": -117.0, "identifier": "B"}]
        with patch.object(flight_app.requests, "get", side_effect=get):
            return self.client.post("/api/terrain-profile",
                                    json={"route_points": pts, "cruise_altitude": 6500}).get_json()

    def test_unreachable_elevation_service_is_not_sea_level(self):
        def down(url, **kw):
            raise OSError("offline")
        body = self.profile(down)
        self.assertFalse(body["terrain_known"])
        self.assertIsNone(body["max_terrain"])
        self.assertIsNone(body["min_clearance"])
        self.assertIsNone(body["vfr_clearance_ok"], "an offline lookup read as adequate")

    def test_known_terrain_still_reports_clearance(self):
        body = self.profile(lambda url, **kw: Reply(200, {"value": 1000.0}))
        self.assertTrue(body["terrain_known"])
        self.assertEqual(body["max_terrain"], 1000)
        # Whether it is adequate is the profile's business (it counts the climb
        # out); what matters here is that a verdict is given when terrain is known.
        self.assertIsNotNone(body["vfr_clearance_ok"])
        self.assertIsNotNone(body["min_clearance"])


class WeatherDegradesVisibly(unittest.TestCase):
    """With every upstream down, the briefing says what is simulated."""

    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    def test_offline_briefing_marks_every_source_simulated(self):
        def down(*a, **kw):
            raise OSError("offline")
        with patch.object(flight_app.requests, "get", side_effect=down):
            r = self.client.post("/api/weather-briefing", json={
                "departure": "@33.0,-117.0", "destination": "@34.0,-117.0", "waypoints": []})
        self.assertEqual(r.status_code, 200)
        briefing = r.get_json()["briefing"]
        for kind in ("metars", "tafs", "notams"):
            self.assertTrue(briefing[kind])
            self.assertTrue(all(item["simulated"] for item in briefing[kind]), kind)
        self.assertTrue(briefing["winds_aloft"]["simulated"])

    def test_offline_route_says_it_was_planned_in_still_air(self):
        def down(*a, **kw):
            raise OSError("offline")
        with patch.object(flight_app.requests, "get", side_effect=down):
            r = self.client.post("/api/calculate-route", json={
                "departure": "@33.0,-117.0", "destination": "@34.0,-117.0"})
        w = r.get_json()["winds_aloft"]
        self.assertFalse(w["available"])
        self.assertIn("still air", w["source"])
        self.assertEqual((w["direction"], w["speed"]), (0, 0))

    def test_a_crash_in_the_briefing_does_not_leak_the_exception(self):
        with patch.object(flight_app, "fetch_metar",
                          side_effect=TypeError("Unknown format code 'f'")):
            r = self.client.post("/api/weather-briefing", json={
                "departure": "@33.0,-117.0", "destination": "@34.0,-117.0"})
        self.assertGreaterEqual(r.status_code, 500)
        self.assertNotIn("format code", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
