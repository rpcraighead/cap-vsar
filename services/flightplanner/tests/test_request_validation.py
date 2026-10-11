"""L2-3 and L2-2: bad input is a JSON 400, never an HTML 500, and the .fms cap holds."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as flight_app  # noqa: E402

LEAK_MARKERS = ("Traceback", "Unknown format code", "could not convert",
                "invalid literal", "object has no attribute", "NoneType")

GOOD_POINTS = [{"identifier": "A", "lat": 33.0, "lon": -117.0},
               {"identifier": "B", "lat": 33.5, "lon": -117.0}]


class NumHelper(unittest.TestCase):
    def test_default_when_absent(self):
        self.assertEqual(flight_app._num({}, "x", 7, 0, 10), 7)

    def test_accepts_numbers_and_numeric_text(self):
        self.assertEqual(flight_app._num({"x": 3}, "x", 0, 0, 10), 3)
        self.assertEqual(flight_app._num({"x": "2.5"}, "x", 0, 0, 10), 2.5)

    def test_rejects_what_is_not_a_finite_number(self):
        for bad in ("abc", "", None, True, [1], {"a": 1}, "nan", float("inf"), "1e999"):
            with self.subTest(bad=bad), self.assertRaises(flight_app.RequestError) as ctx:
                flight_app._num({"x": bad}, "x", 0, -1e9, 1e9)
            self.assertIn("x must be", str(ctx.exception))

    def test_range_is_refused_or_clamped(self):
        with self.assertRaises(flight_app.RequestError):
            flight_app._num({"x": 11}, "x", 0, 0, 10)
        self.assertEqual(flight_app._num({"x": 11}, "x", 0, 0, 10, clamp=True), 10)
        self.assertEqual(flight_app._num({"x": -3}, "x", 0, 0, 10, clamp=True), 0)

    def test_integer(self):
        self.assertEqual(flight_app._num({"x": "4"}, "x", 0, 0, 10, integer=True), 4)
        with self.assertRaises(flight_app.RequestError):
            flight_app._num({"x": 4.5}, "x", 0, 0, 10, integer=True)


class EveryPostRouteAnswersJson(unittest.TestCase):
    """Malformed numbers and wrong types on every POST route."""

    ROUTES = {
        "/api/calculate-route": [
            {"departure": "@33,-117", "destination": "@34,-117", "cruise_altitude": "abc"},
            {"departure": "@33,-117", "destination": "@34,-117", "rpm": None},
            {"departure": "@33,-117", "destination": "@34,-117", "manifold_pressure": "x"},
            {"departure": "@33,-117", "destination": "@34,-117", "reserve_minutes": [1]},
            {"departure": 5, "destination": "@34,-117"},
            {"departure": "@33,-117", "destination": "@34,-117", "waypoints": "KSEE"},
            {"departure": "@33,-117", "destination": "@34,-117", "waypoints": [1, 2]},
        ],
        "/api/weather-briefing": [
            {"departure": 5}, {"waypoints": {"a": 1}}, {"waypoints": [None]},
        ],
        "/api/performance/takeoff": [
            {"weight": "heavy"}, {"pressure_altitude": None}, {"temperature": [1]},
            {"headwind": "nan"},
        ],
        "/api/performance/landing": [
            {"pressure_altitude": "x"}, {"temperature": {}}, {"headwind": True},
        ],
        "/api/weight-balance": [
            {"pilot_weight": "abc"}, {"fuel_gallons": None}, {"baggage_weight": [1]},
            {"empty_weight": "x"}, {"empty_moment": "inf"},
        ],
        "/api/terrain-profile": [
            {"route_points": "x"}, {"route_points": [1, 2]},
            {"route_points": [{"lat": "a", "lon": 1}, {"lat": 2, "lon": 3}]},
            {"route_points": GOOD_POINTS, "cruise_altitude": "abc"},
            {"route_points": [{"lat": 1}, {"lat": 2, "lon": 3}]},
        ],
        "/api/sar/generate-pattern": [
            {"datum": "@33,-117", "spacing_nm": "abc"},
            {"datum": "@33,-117", "num_legs": None},
            {"datum": "@33,-117", "initial_heading": "north"},
            {"datum": "@33,-117", "turn_direction": 5},
            {"datum": "@33,-117", "turn_direction": "sideways"},
            {"datum": "@33,-117", "pattern_type": ["x"]},
            {"datum": "@33,-117", "pattern_type": "creeping_line", "end_lat": "x"},
            {"datum": "@33,-117", "pattern_type": "creeping_line", "sweep_width_nm": [1]},
            {"datum": "@33,-117", "pattern_type": "parallel_track", "length_nm": "x"},
            {"datum": "@33,-117", "pattern_type": "parallel_track", "width_nm": None},
            {"datum": "@33,-117", "pattern_type": "parallel_track", "axis_heading": "x"},
            {"datum_lat": "x", "datum_lon": 1},
            {"datum_lat": 1, "datum_lon": float("nan")},
        ],
        "/api/sar/export-fms": [
            {"waypoints": "x"}, {"waypoints": [1]},
            {"waypoints": [{"lat": "abc", "lon": -117.0}]},
            {"waypoints": [{"lat": 33.0, "lon": None}]},
            {"waypoints": [{"lat": 33.0}]},
            {"waypoints": [{"lat": 33.0, "lon": -117.0, "identifier": 5}]},
            {"altitude": "high", "waypoints": []},
            {"departure": 5, "waypoints": []},
        ],
        "/api/sar/export-vsar": [
            {"waypoints": [{"lat": "x", "lon": 1}]}, {"pattern_type": 5},
        ],
        "/api/update-database": [{"anything": "x"}],
    }
    SHAPES = [[], "text", 5, None]

    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    def check(self, path, response, what):
        self.assertTrue(response.is_json, f"{path} {what}: answered {response.content_type}")
        body = response.get_json()
        self.assertIs(body.get("success"), False, f"{path} {what}: {body}")
        self.assertGreaterEqual(response.status_code, 400, f"{path} {what}")
        self.assertLess(response.status_code, 500, f"{path} {what}: {body}")
        for marker in LEAK_MARKERS:
            self.assertNotIn(marker, body.get("error", ""), f"{path} {what}")

    def test_malformed_values(self):
        for path, bodies in self.ROUTES.items():
            for payload in bodies:
                with self.subTest(path=path, payload=payload):
                    r = self.client.post(path, json=payload,
                                         headers={"Origin": "http://localhost"})
                    self.check(path, r, json.dumps(payload, default=str)[:80])

    def test_body_that_is_not_an_object(self):
        for path in self.ROUTES:
            for shape in self.SHAPES:
                with self.subTest(path=path, shape=shape):
                    r = self.client.post(path, data=json.dumps(shape),
                                         content_type="application/json",
                                         headers={"Origin": "http://localhost"})
                    self.check(path, r, f"body {shape!r}")

    def test_body_that_is_not_json(self):
        for path in self.ROUTES:
            with self.subTest(path=path):
                r = self.client.post(path, data="not json at all",
                                     content_type="text/plain",
                                     headers={"Origin": "http://localhost"})
                self.check(path, r, "plain text body")

    def test_the_old_export_fms_crash_is_a_400_naming_the_field(self):
        r = self.client.post("/api/sar/export-fms",
                             json={"waypoints": [{"lat": "abc", "lon": -117.0}]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("lat", r.get_json()["error"])


class ExportVsarValidation(unittest.TestCase):
    """The console push, once past authentication, rejects bad points as JSON."""

    def test_bad_points_are_a_400_not_a_crash(self):
        flight_app.app.config["TESTING"] = True
        client = flight_app.app.test_client()
        flight_app._vsar_export_attempts.clear()
        bodies = [{"waypoints": [{"lat": "x", "lon": 1}]},
                  {"waypoints": [1, 2]},
                  {"waypoints": [{"lat": 1, "lon": 1}], "search_centre": {"lat": "x", "lon": 1}},
                  {"waypoints": [{"lat": 1, "lon": 1}], "callsign": 5},
                  {"waypoints": "x"}]
        with patch.object(flight_app, "_request_security_error", return_value=None):
            for payload in bodies:
                flight_app._vsar_export_attempts.clear()
                with self.subTest(payload=payload):
                    r = client.post("/api/sar/export-vsar", json=payload)
                    self.assertEqual(r.status_code, 400)
                    self.assertTrue(r.is_json)


class ErrorHandler(unittest.TestCase):
    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    def test_http_errors_under_api_are_json_and_keep_their_status(self):
        r = self.client.get("/api/no-such-thing")
        self.assertEqual((r.status_code, r.is_json), (404, True))
        self.assertIs(r.get_json()["success"], False)
        r = self.client.get("/api/calculate-route")           # POST-only
        self.assertEqual((r.status_code, r.is_json), (405, True))
        self.assertIn("POST", r.headers.get("Allow", ""))

    def test_pages_keep_the_ordinary_html_error(self):
        r = self.client.get("/no-such-page")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.is_json)

    def test_an_unexpected_exception_is_a_json_500_without_the_python_text(self):
        boom = TypeError("Unknown format code 'f' for object of type 'str'")
        with patch.object(flight_app, "fetch_winds_aloft", side_effect=boom), \
                patch.object(flight_app.app.logger, "exception") as log:
            r = self.client.post("/api/calculate-route",
                                 json={"departure": "@33,-117", "destination": "@34,-117"})
        self.assertEqual(r.status_code, 500)
        self.assertTrue(r.is_json)
        self.assertIs(r.get_json()["success"], False)
        self.assertNotIn("format code", r.get_json()["error"])
        log.assert_called_once()            # the cause is logged, not shown

    def test_a_sloppy_endpoint_added_later_is_still_covered(self):
        with patch.dict(flight_app.app.view_functions, {"perf_to": lambda: 1 / 0}):
            r = self.client.post("/api/performance/takeoff", json={})
        self.assertEqual(r.status_code, 500)
        self.assertTrue(r.is_json)
        self.assertNotIn("division", r.get_json()["error"])


class FmsWaypointCap(unittest.TestCase):
    """L2-2: 99 is the G1000 flight-plan size; X-Plane's real limit is unverified."""

    AIRPORT = {"latitude": 32.8, "longitude": -117.0, "elevation": 388}

    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    @staticmethod
    def points(n):
        return [{"identifier": f"P{i:03d}", "lat": 33.0 + i * 0.001, "lon": -117.0}
                for i in range(n)]

    def test_the_cap_is_a_named_constant_of_99(self):
        self.assertEqual(flight_app.MAX_FMS_WAYPOINTS, 99)

    def test_export_accepts_exactly_the_limit(self):
        with patch.object(flight_app, "get_airport", return_value=self.AIRPORT):
            r = self.client.post("/api/sar/export-fms", json={"waypoints": self.points(99)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["content"].count("\n28 "), 99)

    def test_export_refuses_one_more_and_says_how_to_fix_it(self):
        with patch.object(flight_app, "get_airport", return_value=self.AIRPORT):
            r = self.client.post("/api/sar/export-fms", json={"waypoints": self.points(100)})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertNotIn("content", body)
        self.assertIn("100", body["error"])
        self.assertIn("99", body["error"])
        self.assertIn("split", body["error"].lower())

    def test_the_generator_enforces_it_too(self):
        with patch.object(flight_app, "get_airport", return_value=self.AIRPORT):
            flight_app.generate_xplane_fms_content("KSEE", "KSEE", self.points(99))
            with self.assertRaises(ValueError):
                flight_app.generate_xplane_fms_content("KSEE", "KSEE", self.points(100))

    def pattern(self, **extra):
        payload = {"datum": "@33.0,-117.0", "pattern_type": "parallel_track"}
        payload.update(extra)
        return self.client.post("/api/sar/generate-pattern", json=payload).get_json()

    def test_generate_pattern_says_when_it_would_not_fit(self):
        big = self.pattern(length_nm=5, width_nm=50, spacing_nm=0.5)     # 100 lanes, 200 points
        self.assertTrue(big["success"])
        self.assertEqual(big["fms_waypoint_count"], len(big["waypoints"]))
        self.assertGreater(big["fms_waypoint_count"], 99)
        self.assertTrue(big["exceeds_fms_limit"])
        self.assertEqual(big["fms_waypoint_limit"], 99)
        self.assertTrue(big["warnings"])
        self.assertIn("split", big["warnings"][0].lower())

    def test_a_pattern_that_fits_carries_no_warning(self):
        small = self.pattern(length_nm=5, width_nm=4, spacing_nm=1)
        self.assertFalse(small["exceeds_fms_limit"])
        self.assertEqual(small["warnings"], [])

    def test_boundary_of_the_generate_pattern_flag(self):
        # expanding square: 1 datum + legs points
        ok = self.client.post("/api/sar/generate-pattern",
                              json={"datum": "@33,-117", "num_legs": 40}).get_json()
        self.assertEqual(ok["fms_waypoint_count"], 41)
        self.assertFalse(ok["exceeds_fms_limit"])


if __name__ == "__main__":
    unittest.main()
