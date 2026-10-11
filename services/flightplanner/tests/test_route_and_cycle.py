"""L2-7 route labels, L2-9 d-TPP cycle, L2-11 climb interpolation, hard-coded defaults."""
import os
import re
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

PLANNER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLANNER))
os.environ.setdefault("CAPVSAR_PRECACHE_CHARTS", "0")
import app as flight_app  # noqa: E402


class DtppCycle(unittest.TestCase):
    """FAA d-TPP cycles: 28 days, anchored on 2601 = 2026-01-22, NN counts within the year."""

    CASES = {
        date(2026, 1, 22): "2601",
        date(2026, 2, 18): "2601",      # last day of 2601
        date(2026, 2, 19): "2602",
        date(2026, 7, 9): "2607",
        date(2026, 9, 3): "2609",
        date(2026, 9, 30): "2609",
        date(2026, 10, 1): "2610",      # a calendar-month scheme says 2610 too, by luck
        date(2026, 10, 28): "2610",
        date(2026, 10, 29): "2611",
        date(2026, 11, 25): "2611",
        date(2026, 11, 26): "2612",
        date(2026, 12, 23): "2612",
        date(2026, 12, 24): "2613",     # 13th and last cycle of 2026
        date(2026, 12, 31): "2613",
        date(2027, 1, 20): "2613",      # year rolls over inside a cycle: still 2613
        date(2027, 1, 21): "2701",
        date(2026, 1, 21): "2513",      # before the anchor
        date(2026, 1, 1): "2513",
        date(2025, 12, 25): "2513",
        date(2025, 12, 24): "2512",
        date(2025, 1, 23): "2501",
        date(2028, 2, 29): None,        # leap day: only checked for being well-formed
    }

    def test_known_dates(self):
        for day, expected in self.CASES.items():
            with self.subTest(day=day):
                got = flight_app.dtpp_cycle_for(day)
                self.assertRegex(got, r"^\d{4}$")
                if expected:
                    self.assertEqual(got, expected)

    def test_it_is_not_the_calendar_month(self):
        # 2026-09-30 is still cycle 09; 2026-11-30 is cycle 12, not 11.
        self.assertEqual(flight_app.dtpp_cycle_for(date(2026, 11, 30)), "2612")
        self.assertEqual(flight_app.dtpp_cycle_for(date(2026, 3, 1)), "2602")
        self.assertNotEqual(flight_app.dtpp_cycle_for(date(2026, 3, 1)), "2603")

    def test_thirteen_cycles_a_year_in_order(self):
        seen = []
        day = date(2026, 1, 22)
        while day.year == 2026:
            seen.append(flight_app.dtpp_cycle_for(day))
            day = date.fromordinal(day.toordinal() + 28)
        self.assertEqual(seen, [f"26{n:02d}" for n in range(1, 14)])

    def test_every_day_maps_to_a_cycle_that_changes_every_28_days(self):
        day, last, run = date(2026, 1, 22), None, 0
        for _ in range(28 * 20):
            cycle = flight_app.dtpp_cycle_for(day)
            if cycle != last:
                if last is not None:
                    self.assertEqual(run, 28, (day, last, cycle))
                last, run = cycle, 0
            run += 1
            day = date.fromordinal(day.toordinal() + 1)

    def test_uses_the_utc_date(self):
        # 23:30 on the 28th in UTC-8 is already the 29th in UTC.
        late = datetime(2026, 10, 29, 7, 30, tzinfo=timezone.utc)   # 23:30 PST on Oct 28
        with patch.object(flight_app, "get_utc_now", return_value=late):
            self.assertEqual(flight_app.get_dtpp_cycle(), "2611")
        early = datetime(2026, 10, 28, 23, 59, tzinfo=timezone.utc)
        with patch.object(flight_app, "get_utc_now", return_value=early):
            self.assertEqual(flight_app.get_dtpp_cycle(), "2610")


class ClimbInterpolates(unittest.TestCase):
    def test_midpoint_between_rows(self):
        # Table: 0 ft (0 min, 0 gal, 0 nm), 2000 (2, .8, 3), 4000 (5, 1.5, 7).
        c = flight_app.get_climb(0, 3000)
        self.assertAlmostEqual(c["time_minutes"], 3.5)
        self.assertAlmostEqual(c["fuel_gallons"], 1.15)
        self.assertAlmostEqual(c["distance_nm"], 5.0)

    def test_both_ends_interpolate(self):
        c = flight_app.get_climb(1000, 3000)           # 1 min .. 3.5 min
        self.assertAlmostEqual(c["time_minutes"], 2.5)
        self.assertAlmostEqual(c["distance_nm"], 3.5)

    def test_on_a_row_it_still_matches_the_table(self):
        self.assertEqual(flight_app.get_climb(0, 6000)["time_minutes"], 8)
        self.assertEqual(flight_app.get_climb(2000, 8000)["fuel_gallons"], 2.4)

    def test_outside_the_table_holds_the_end_row_and_never_goes_negative(self):
        top = flight_app.get_climb(0, 14000)
        self.assertEqual(flight_app.get_climb(0, 25000), top)
        self.assertEqual(flight_app.get_climb(9000, 3000),
                         {"time_minutes": 0, "fuel_gallons": 0, "distance_nm": 0})
        self.assertEqual(flight_app.get_climb(-300, 0)["time_minutes"], 0)


class NamedRoutePoints(unittest.TestCase):
    """L2-7: the nav log keeps DATUM and the pattern's names; they match the .fms."""

    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    def pattern(self, **extra):
        payload = {"datum": "@33.0,-117.0", "pattern_type": "expanding_square", "num_legs": 4}
        payload.update(extra)
        return self.client.post("/api/sar/generate-pattern", json=payload).get_json()

    @staticmethod
    def route_tokens(pattern):
        # What app.js builds in "Apply to Route".
        return [f"{p['identifier']}=@{p['lat']:.5f},{p['lon']:.5f}" for p in pattern["waypoints"]]

    def calc(self, tokens):
        with patch.object(flight_app, "fetch_winds_aloft", return_value=flight_app.simulate_winds(33.0, -117.0)):
            return self.client.post("/api/calculate-route", json={
                "departure": "@32.9,-117.0", "destination": "@33.2,-117.1",
                "waypoints": tokens}).get_json()

    def test_a_named_point_keeps_its_name(self):
        body = self.calc(["DATUM=@33.0,-117.0", "@33.1,-117.0"])
        self.assertTrue(body["success"], body)
        self.assertEqual([p["identifier"] for p in body["route_points"]],
                         ["USR1", "DATUM", "USR2", "USR3"])

    def test_nav_log_carries_the_leg_that_defines_the_square(self):
        pattern = self.pattern()
        body = self.calc(self.route_tokens(pattern))
        self.assertTrue(body["success"], body)
        legs = [(s["from"], s["to"]) for s in body["segments"]]
        self.assertIn(("DATUM", "SS01"), legs)
        self.assertIn(("SS01", "SS02"), legs)
        self.assertNotIn("USR", " ".join(a + b for a, b in legs[1:-1]))

    def test_nav_log_and_fms_use_the_same_names(self):
        pattern = self.pattern(num_legs=6)
        body = self.calc(self.route_tokens(pattern))
        nav_names = [p["identifier"] for p in body["route_points"][1:-1]]
        airport = {"latitude": 32.8, "longitude": -117.0, "elevation": 388}
        with patch.object(flight_app, "get_airport", return_value=airport):
            fms = self.client.post("/api/sar/export-fms",
                                   json={"waypoints": pattern["waypoints"]}).get_json()["content"]
        fms_names = [line.split()[1] for line in fms.splitlines() if line.startswith("28 ")]
        self.assertEqual(nav_names, fms_names)
        self.assertEqual(nav_names[0], "DATUM")

    def test_names_are_reduced_to_the_fms_character_set_and_length(self):
        body = self.calc(["ss 01!=@33.0,-117.0"])
        self.assertEqual(body["route_points"][1]["identifier"], "SS_01")
        body = self.calc(["ABCDEFGHIJKLMNOP=@33.0,-117.0"])
        self.assertEqual(body["route_points"][1]["identifier"], "ABCDEFGHIJKL")

    def test_only_coordinate_points_can_be_named(self):
        body = self.calc(["FAKE=KSEE"])
        self.assertFalse(body["success"])
        self.assertIn("FAKE=KSEE", body["error"])

    def test_apply_to_route_in_the_page_keeps_datum(self):
        js = (PLANNER / "static" / "js" / "app.js").read_text(encoding="utf-8")
        apply_block = js[js.index("sar-btn-apply"):js.index("sar-btn-fms")]
        self.assertNotIn("'DATUM'", apply_block)
        self.assertIn("=${at}", apply_block)


class DefaultsAreNotScatteredLiterals(unittest.TestCase):
    def setUp(self):
        flight_app.app.config["TESTING"] = True
        self.client = flight_app.app.test_client()

    def test_export_fms_default_airport_is_the_constant(self):
        seen = []

        def fake(ident):
            seen.append(ident)
            return {"latitude": 32.8, "longitude": -117.0, "elevation": 388}
        with patch.object(flight_app, "DEFAULT_AIRPORT", "KCRQ"), \
                patch.object(flight_app, "get_airport", side_effect=fake):
            r = self.client.post("/api/sar/export-fms", json={"waypoints": []})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(seen, ["KCRQ", "KCRQ"])
        self.assertEqual(r.get_json()["filename"], "KCRQ_KCRQ_SAR.fms")

    def test_environment_variable_overrides_it(self):
        with patch.dict(os.environ, {"CAPVSAR_DEFAULT_AIRPORT": " kpsp "}):
            self.assertEqual(flight_app._env_setting("CAPVSAR_DEFAULT_AIRPORT", "KSEE", upper=True), "KPSP")
        with patch.dict(os.environ, {"CAPVSAR_DEFAULT_AIRPORT": ""}):
            self.assertEqual(flight_app._env_setting("CAPVSAR_DEFAULT_AIRPORT", "KSEE", upper=True), "KSEE")

    def test_page_hands_the_default_to_the_script(self):
        with patch.object(flight_app, "DEFAULT_AIRPORT", "KCRQ"), \
                patch.object(flight_app, "DEFAULT_DATUM", "@32.0,-116.0"):
            html = self.client.get("/").get_data(as_text=True)
        self.assertIn('data-default-airport="KCRQ"', html)
        self.assertIn('value="@32.0,-116.0"', html)

    def test_no_literal_default_airport_or_console_host_in_the_script(self):
        js = (PLANNER / "static" / "js" / "app.js").read_text(encoding="utf-8")
        code = re.sub(r"//[^\n]*", "", js)
        self.assertNotRegex(code, r"['\"]KSEE['\"]")
        self.assertNotIn("ms01", js.lower())

    def test_template_has_no_hard_coded_datum_prefill(self):
        html = (PLANNER / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('value="@33.1700,-117.0792"', html)


if __name__ == "__main__":
    unittest.main()
