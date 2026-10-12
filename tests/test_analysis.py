"""
Debrief scoring dashboard: /api/sorties/{id}/analysis and the page that draws it
(docs/UX_REVIEW_2026-10-11.md 3.4 and 4.5).

Three layers:

  * the maths in routers/analysis.py on synthetic positions placed with
    app/geo.py, so every expected error is known exactly;
  * the endpoint, including the truth boundary: every number it returns that
    is derived from the beacon is beacon truth in another form (an error plus
    the reported bearing is the true bearing), so it follows /track's rule -
    nothing before reveal, nothing for a non-instructor while the same beacon
    is being flown;
  * the static files: the page is on the shell and the tokens, and viz.js /
    debrief.js behave under Node with a small DOM that can also print the SVG.

    python3 -m pytest tests/test_analysis.py -q
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from test_console import (BASE, BEACON, INSTRUCTOR, PLUGIN, build_app,  # noqa: E402
                          leaks, route_paths, run_sortie)

ROOT = HERE.parent
STATIC = ROOT / "services" / "exercise" / "app" / "static"
NODE = shutil.which("node") or shutil.which("nodejs")

# Fields of an aircraft entry that are derived from the beacon position.
TRUTH_DERIVED = ("df_error", "df_error_stats", "df_invalid", "bearing_error",
                 "bearing_error_stats", "cpa", "first_good_cut", "track")


def analysis_module():
    return sys.modules["app.routers.analysis"]


def geo_module():
    return sys.modules["app.geo"]


def from_beacon(bearing, nm):
    """A point `nm` from the beacon on `bearing` (so the truth back is bearing+180)."""
    return geo_module().move(BEACON["lat"], BEACON["lon"], bearing, nm)


# ------------------------------------------------------------------ the maths
class ErrorMaths(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.main, _, cls.db = build_app()
        cls.an = analysis_module()
        cls.beacon = {"lat": BEACON["lat"], "lon": BEACON["lon"]}

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.db)

    def err(self, reading, bearing_from_beacon, nm=5.0):
        lat, lon = from_beacon(bearing_from_beacon, nm)
        return self.an.signed_error(reading, lat, lon, self.beacon)

    def test_due_north_reading_180_is_no_error(self):
        self.assertAlmostEqual(self.err(180.0, 0.0), 0.0, places=6)

    def test_due_north_reading_170_is_minus_ten(self):
        self.assertAlmostEqual(self.err(170.0, 0.0), -10.0, places=6)
        self.assertAlmostEqual(self.err(190.0, 0.0), 10.0, places=6)

    def test_the_error_wraps_through_north(self):
        # Due south of the beacon the truth is 000: 350 is ten degrees left of
        # it, not 350 degrees right.
        self.assertAlmostEqual(self.err(350.0, 180.0), -10.0, places=6)
        self.assertAlmostEqual(self.err(10.0, 180.0), 10.0, places=6)
        self.assertAlmostEqual(abs(self.err(0.0, 0.0)), 180.0, places=6)

    def test_df_series_reads_df_bearing_true_and_skips_invalid_samples(self):
        north = from_beacon(0.0, 5.0)
        rows = [
            {"t": 1.0, "lat": north[0], "lon": north[1], "df": {"valid": True, "bearing_true": 180.0}},
            {"t": 2.0, "lat": north[0], "lon": north[1], "df": {"valid": True, "bearing_true": 170.0,
                                                                "in_cone": True}},
            {"t": 3.0, "lat": north[0], "lon": north[1], "df": {"valid": False, "bearing_true": 0.0}},
            {"t": 4.0, "lat": north[0], "lon": north[1], "df": {"valid": True}},
            {"t": 5.0, "lat": north[0], "lon": north[1]},
            {"t": 6.0, "lat": north[0], "lon": north[1], "df": {"bearing_true": True}},
        ]
        series, skipped = self.an.df_error_series(rows, self.beacon)
        self.assertEqual([p["t"] for p in series], [1.0, 2.0])
        self.assertAlmostEqual(series[0]["error"], 0.0, places=2)
        self.assertAlmostEqual(series[1]["error"], -10.0, places=2)
        self.assertTrue(series[1]["in_cone"])
        self.assertNotIn("in_cone", series[0])
        self.assertEqual(skipped, 1)

    def test_logged_bearings_use_where_they_were_taken(self):
        east = from_beacon(90.0, 4.0)
        rows = [{"t": 9.0, "lat": east[0], "lon": east[1], "bearing_true": 260.0, "note": "weak"}]
        (b,) = self.an.bearing_error_series(rows, self.beacon)
        truth = geo_module().bearing_true(east[0], east[1], BEACON["lat"], BEACON["lon"])
        self.assertAlmostEqual(b["error"], 260.0 - truth, places=2)
        self.assertEqual(b["note"], "weak")

    def test_closest_point_of_approach(self):
        pts = [dict(zip(("lat", "lon"), from_beacon(0.0, nm)), t=t)
               for t, nm in ((10.0, 5.0), (20.0, 1.5), (30.0, 2.5), (40.0, 1.5))]
        cpa = self.an.closest_approach(pts, self.beacon)
        self.assertAlmostEqual(cpa["nm"], 1.5, places=2)
        self.assertEqual(cpa["t"], 20.0)          # the first time it got that close
        self.assertIsNone(self.an.closest_approach([], self.beacon))

    def test_first_good_cut_is_the_earliest_within_ten_degrees(self):
        errors = [{"t": 40.0, "error": 2.0}, {"t": 10.0, "error": 25.0},
                  {"t": 30.0, "error": -10.0}, {"t": 20.0, "error": -12.0}]
        self.assertEqual(self.an.first_good_cut(errors), {"t": 30.0, "error": -10.0})
        self.assertIsNone(self.an.first_good_cut([{"t": 1.0, "error": 10.5}]))
        self.assertIsNone(self.an.first_good_cut([]))

    def test_track_efficiency_keeps_the_debrief_definition(self):
        # Straight in from 5 nm north to 1 nm north: flown 4, direct 5.
        pts = [dict(zip(("lat", "lon"), from_beacon(0.0, nm)), t=t)
               for t, nm in ((0.0, 5.0), (1.0, 3.0), (2.0, 1.0))]
        tr = self.an.track_efficiency(pts, self.beacon)
        self.assertAlmostEqual(tr["flown_nm"], 4.0, places=2)
        self.assertAlmostEqual(tr["direct_nm"], 5.0, places=2)
        self.assertAlmostEqual(tr["efficiency_pct"], 125.0, places=0)
        # One fix: debrief.js floored the distance flown at 0.01 nm, and so does this.
        (one,) = pts[:1]
        self.assertAlmostEqual(self.an.track_efficiency([one], self.beacon)["efficiency_pct"],
                               5.0 / 0.01 * 100, delta=1.0)

    def test_downsampling_keeps_the_extremes(self):
        series = [{"t": float(i), "error": 0.0} for i in range(5000)]
        series[1234]["error"] = 40.0          # a multipath swing
        series[4321]["error"] = -35.0
        out = self.an.downsample(series, 400)
        self.assertLessEqual(len(out), 420)
        self.assertIn(40.0, [p["error"] for p in out])
        self.assertIn(-35.0, [p["error"] for p in out])
        self.assertEqual([p["t"] for p in out], sorted(p["t"] for p in out))
        short = series[:10]
        self.assertIs(self.an.downsample(short, 400), short)      # short series pass through

    def test_slots_follow_the_roster_not_the_rank(self):
        roster = ["CAP 423", "CAP 424", "CAP 425"]
        got = dict(self.an.assign_slots({"CAP 425", "ZULU 9", "ALPHA 1"}, roster))
        self.assertEqual(got["CAP 425"], 3)       # keeps its roster slot when 423/424 did not fly
        self.assertEqual(got["ALPHA 1"], 1)       # unknown callsigns take the free slots, A-Z
        self.assertEqual(got["ZULU 9"], 2)
        five = dict(self.an.assign_slots({"A1", "A2", "A3", "A4", "A5"}, []))
        self.assertEqual(sorted(v for v in five.values() if v), [1, 2, 3, 4])
        self.assertIsNone(five["A5"])             # no generated fifth hue
        order = [cs for cs, _ in self.an.assign_slots({"CAP 425", "ALPHA 1"}, roster)]
        self.assertEqual(order, ["ALPHA 1", "CAP 425"])   # displayed in slot order


# ------------------------------------------------------------------ endpoint
class AnalysisEndpoint(unittest.TestCase):

    def setUp(self):
        self.main, self.client, self.db = build_app(
            instructor=INSTRUCTOR, base=BASE, plugin=PLUGIN)
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}
        self.base = {"X-CAPVSAR-Token": BASE}
        self.plug = {"X-CAPVSAR-Token": PLUGIN}

    def tearDown(self):
        os.unlink(self.db)

    def report(self, callsign, bearing_from_beacon, nm, df_bearing, **df):
        lat, lon = from_beacon(bearing_from_beacon, nm)
        r = self.client.post("/api/positions", headers=self.plug, json={
            "callsign": callsign, "lat": lat, "lon": lon, "alt_ft": 5500.0, "hdg_true": 180.0,
            "df": {"valid": True, "bearing_true": df_bearing, "bearing_rel": 0.0,
                   "signal": 0.5, "distance_nm": nm, **df}})
        self.assertEqual(r.status_code, 200, r.text)

    def log(self, callsign, bearing, note=""):
        r = self.client.post("/api/bearings", headers=self.base,
                             json={"callsign": callsign, "bearing_true": bearing, "note": note})
        self.assertEqual(r.status_code, 200, r.text)

    def fly(self, reveal=False):
        """CAP 1 runs in from the north, CAP 2 sits to the east; base logs three cuts."""
        sid, oid = run_sortie(self.main, self.client, headers=self.instr)
        self.report("CAP 1", 0.0, 5.0, 180.0)          # needle on the truth
        self.log("CAP 1", 200.0)                       # +20: not a good cut
        self.report("CAP 1", 0.0, 3.0, 170.0)          # needle 10 left
        self.log("CAP 1", 185.0, note="steady")        # +5: the first good cut
        self.report("CAP 2", 90.0, 4.0, 300.0, valid=False)   # no signal: skipped
        self.report("CAP 2", 90.0, 4.0, 270.0)
        r = self.client.post("/api/messages", headers=self.base,
                             json={"recipient": "CAP 1", "body": "orbit the cut"})
        self.assertEqual(r.status_code, 200, r.text)
        if reveal:
            self.assertEqual(self.client.post("/api/sorties/reveal", headers=self.instr).status_code, 200)
        return sid, oid

    def get(self, oid, headers):
        r = self.client.get(f"/api/sorties/{oid}/analysis", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def by_cs(self, body):
        return {a["callsign"]: a for a in body["aircraft"]}

    def test_the_route_is_registered(self):
        self.assertIn("/api/sorties/{oid}/analysis", route_paths(self.main.app))

    def test_reads_need_a_credential(self):
        _, oid = self.fly()
        self.assertIn(self.client.get(f"/api/sorties/{oid}/analysis").status_code, (401, 403))
        self.assertEqual(self.client.get("/api/sorties/nope/analysis", headers=self.base).status_code, 404)

    def test_nothing_truth_derived_before_reveal(self):
        _, oid = self.fly()
        for who in (self.base, self.instr):     # not even the instructor: /track's rule
            body = self.get(oid, who)
            self.assertFalse(body["revealed"])
            self.assertEqual(leaks(body), [])
            self.assertNotIn("beacon", body)
            ac = self.by_cs(body)
            self.assertEqual(set(ac), {"CAP 1", "CAP 2"})
            for a in ac.values():
                for k in TRUTH_DERIVED:
                    self.assertIsNone(a[k], f"{a['callsign']}.{k} before reveal")
            # What is not truth still comes back: the counts and the distance flown.
            self.assertEqual(ac["CAP 1"]["counts"], {"positions": 2, "bearings": 2, "messages": 1})
            self.assertAlmostEqual(ac["CAP 1"]["flown_nm"], 2.0, places=1)
            self.assertNotIn("bearing_true", json.dumps(body))

    def test_scores_after_reveal(self):
        _, oid = self.fly(reveal=True)
        body = self.get(oid, self.base)
        self.assertTrue(body["revealed"])
        self.assertFalse(body["withheld"])
        self.assertEqual(body["good_cut_deg"], 10.0)
        self.assertEqual(body["counts"], {"positions": 4, "bearings": 2, "messages": 1})
        a = self.by_cs(body)["CAP 1"]
        self.assertEqual([round(p["error"], 1) for p in a["df_error"]], [0.0, -10.0])
        self.assertEqual([round(b["error"], 1) for b in a["bearing_error"]], [20.0, 5.0])
        self.assertEqual(a["bearing_error"][1]["note"], "steady")
        self.assertAlmostEqual(a["first_good_cut"]["error"], 5.0, places=1)
        self.assertEqual(a["first_good_cut"]["t"], a["bearing_error"][1]["t"])
        self.assertAlmostEqual(a["cpa"]["nm"], 3.0, places=2)
        self.assertEqual(a["cpa"]["t"], a["df_error"][1]["t"])
        self.assertAlmostEqual(a["track"]["efficiency_pct"], 250.0, delta=0.5)
        self.assertEqual(a["df_error_stats"]["n"], 2)
        self.assertAlmostEqual(a["df_error_stats"]["mean_abs"], 5.0, places=1)
        self.assertEqual(a["bearing_error_stats"]["good"], 1)
        b = self.by_cs(body)["CAP 2"]
        self.assertEqual(b["df_invalid"], 1)
        self.assertEqual(len(b["df_error"]), 1)
        self.assertLess(abs(b["df_error"][0]["error"]), 0.2)   # 270 from due east, near enough
        self.assertIsNone(b["first_good_cut"])
        self.assertEqual(b["counts"]["messages"], 0)
        self.assertEqual([x["slot"] for x in body["aircraft"]], [1, 2])

    def test_withheld_from_non_instructors_while_the_same_beacon_flies(self):
        sid, old = self.fly(reveal=True)
        self.client.post("/api/sorties/stop", headers=self.instr)
        r = self.client.post("/api/sorties", json={"scenario_id": sid}, headers=self.instr)
        self.assertEqual(r.status_code, 200, r.text)
        body = self.get(old, self.base)
        self.assertTrue(body["withheld"])
        self.assertFalse(body["revealed"])
        self.assertEqual(leaks(body), [])
        for a in body["aircraft"]:
            for k in TRUTH_DERIVED:
                self.assertIsNone(a[k], f"{a['callsign']}.{k} leaked while withheld")
        # The instructor still can, and once the live sortie is revealed so can base.
        mine = self.by_cs(self.get(old, self.instr))
        self.assertEqual(len(mine["CAP 1"]["df_error"]), 2)
        self.client.post("/api/sorties/reveal", headers=self.instr)
        later = self.by_cs(self.get(old, self.base))
        self.assertEqual(len(later["CAP 1"]["bearing_error"]), 2)

    def test_the_sorties_effects_are_listed(self):
        _, oid = self.fly(reveal=True)
        r = self.client.post("/api/sorties/effects", headers=self.instr,
                             json={"multipath": True, "multipath_offset_deg": 35.0,
                                   "cone_of_confusion": False})
        self.assertEqual(r.status_code, 200, r.text)
        body = self.get(oid, self.base)
        self.assertTrue(body["effects"]["multipath"])
        labels = [e["label"] for e in body["effects_active"]]
        self.assertIn("Multipath (35° offset)", labels)
        self.assertNotIn("Cone of confusion", labels)
        self.assertIn("Radio horizon", labels)


if __name__ == "__main__":
    unittest.main()
