"""
Fixed radio sites (T31): the Mission Base antenna at Gillespie Field (KSEE)
and the repeater at the Julian VORTAC (JLI), and whether a station can reach
them directly or through the repeater.

Pure-Python checks need no FastAPI; the last class exercises the read-only
route through the console app.
"""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "exercise"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import radio_sites, settings                      # noqa: E402
from app.geo import distance_nm                           # noqa: E402

# Pinned coordinates and where they come from. Sources recorded in
# services/exercise/app/settings.py next to the data.
KSEE = (32.826199, -116.972000, 388.0)     # OurAirports via the planner's aviation_data.db
JLI = (33.140458, -116.585936, 5560.0)     # X-Plane 12 Resources/default data/earth_nav.dat:22664
ESCON = (33.1700, -117.0792)               # settings.SEED beacon position


def default_sites():
    return radio_sites.load_sites(settings.RADIO_SITES)


class SiteData(unittest.TestCase):
    def test_default_exercise_has_base_at_ksee_and_repeater_at_jli(self):
        sites = {s.id: s for s in default_sites()}
        base, rpt = sites["BASE-KSEE"], sites["RPT-JLI"]
        self.assertEqual(base.role, "base_antenna")
        self.assertEqual(rpt.role, "repeater")
        self.assertAlmostEqual(base.lat, KSEE[0], places=5)
        self.assertAlmostEqual(base.lon, KSEE[1], places=5)
        self.assertEqual(base.ground_elev_ft, KSEE[2])
        self.assertAlmostEqual(rpt.lat, JLI[0], places=5)
        self.assertAlmostEqual(rpt.lon, JLI[1], places=5)
        self.assertEqual(rpt.ground_elev_ft, JLI[2])
        self.assertEqual(base.antenna_msl_ft, 388.0 + base.antenna_agl_ft)
        self.assertEqual(rpt.antenna_msl_ft, 5560.0 + rpt.antenna_agl_ft)
        # The sites are where the names say: Julian is about 20 NM east of Gillespie Field.
        self.assertAlmostEqual(distance_nm(base.lat, base.lon, rpt.lat, rpt.lon), 29.0, delta=3.0)

    def test_repeater_pair_follows_the_national_convention(self):
        pair = radio_sites.configured()["repeater_pair"]
        self.assertEqual(pair, {"name": "primary", "input_mhz": 143.550, "output_mhz": 148.125})
        self.assertEqual(radio_sites.repeater_pair("secondary"),
                         {"name": "secondary", "input_mhz": 143.700, "output_mhz": 148.150})
        with self.assertRaises(ValueError):
            radio_sites.repeater_pair("tertiary")

    def test_site_list_is_validated(self):
        good = {"id": "BASE-X", "role": "base_antenna", "lat": 32.8, "lon": -117.0,
                "ground_elev_ft": 100.0, "antenna_agl_ft": 20.0}
        rpt = {**good, "id": "RPT-Y", "role": "repeater"}
        self.assertEqual([s.id for s in radio_sites.load_sites([good, rpt])], ["BASE-X", "RPT-Y"])
        for bad, why in ((
            [rpt], "no base antenna"), ([good, good], "duplicate id"), ([good, {**rpt, "id": "BASE-X"}], "duplicate id"),
            ([{**good, "role": "tower"}], "unknown role"), ([{**good, "lat": 95.0}], "off the globe"),
            ([{**good, "antenna_agl_ft": 900.0}], "antenna too tall"), ([{**good, "lon": float("nan")}], "nan"),
            ([{**good, "extra": 1}], "unknown key"), ([good, {**rpt, "role": "base_antenna"}], "two bases"),
        ):
            with self.assertRaises(ValueError, msg=why):
                radio_sites.load_sites(bad)

    def test_sites_can_come_from_a_json_file_for_another_exercise(self):
        import tempfile
        palomar = {"sites": [
            {"id": "BASE-KCRQ", "role": "base_antenna", "name": "Palomar airport", "lat": 33.1283,
             "lon": -117.28, "ground_elev_ft": 331.0, "antenna_agl_ft": 25.0},
            {"id": "RPT-PALOMAR", "role": "repeater", "name": "Mt. Palomar", "lat": 33.36,
             "lon": -116.86, "ground_elev_ft": 6100.0, "antenna_agl_ft": 60.0}],
            "repeater_pair": "secondary"}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(palomar, handle)
        try:
            os.environ["CAPVSAR_RADIO_SITES"] = handle.name
            cfg = radio_sites.configured()
            self.assertEqual([s.id for s in cfg["sites"]], ["BASE-KCRQ", "RPT-PALOMAR"])
            self.assertEqual(cfg["repeater_pair"]["output_mhz"], 148.150)
        finally:
            os.environ.pop("CAPVSAR_RADIO_SITES", None)
            os.unlink(handle.name)
        self.assertEqual([s.id for s in radio_sites.configured()["sites"]], ["BASE-KSEE", "RPT-JLI"])


# A synthetic landscape: flat 300 ft country (below the Gillespie Field
# antenna, so the valley floor itself never blocks the base) with a 7,000 ft
# ridge running north-south 2-8 NM east of Julian. No scenery is needed offline.
def ridge_east_of_jli(lat, lon):
    return 7000.0 if -116.55 < lon < -116.45 else 300.0


# ...and a second ridge, 6,000 ft, between the search area and Gillespie Field,
# but only north of 33.03 N, so it stands between an aircraft near Julian and
# the base while the repeater's own link to the base passes south of it.
def ridge_between_search_area_and_base(lat, lon):
    if -116.82 < lon < -116.78 and lat > 33.03:
        return 6000.0
    return ridge_east_of_jli(lat, lon)


NEAR_JULIAN = (33.140, -116.750, 4500.0)        # 8 NM west of JLI at 4,500 ft MSL
BEHIND_RIDGE = (33.140, -116.350, 3000.0)       # 12 NM east of JLI, low, behind the ridge


class Reach(unittest.TestCase):
    def setUp(self):
        self.sites = default_sites()
        self.base = next(s for s in self.sites if s.id == "BASE-KSEE")
        self.rpt = next(s for s in self.sites if s.id == "RPT-JLI")

    def test_radio_horizon_is_the_two_ended_rule_the_engine_uses(self):
        from app.propagation import radio_horizon_nm
        p = radio_sites.path(*NEAR_JULIAN, self.rpt)
        self.assertEqual(p["horizon_nm"], round(radio_horizon_nm(4500.0, self.rpt.antenna_msl_ft), 1))
        self.assertFalse(p["terrain_checked"])
        self.assertTrue(p["within_horizon"] and p["reachable"])

    def test_a_station_beyond_the_horizon_is_out_of_reach_unless_the_effect_is_off(self):
        far = (30.0, -116.972, 50.0)            # 170 NM south, on the deck
        p = radio_sites.path(*far, self.base)
        self.assertFalse(p["within_horizon"] or p["reachable"])
        self.assertTrue(radio_sites.path(*far, self.base, radio_horizon=False)["reachable"])

    def test_an_aircraft_at_4500_ft_near_julian_has_repeater_coverage(self):
        p = radio_sites.path(*NEAR_JULIAN, self.rpt, terrain_ft=ridge_east_of_jli)
        self.assertTrue(p["terrain_checked"])
        self.assertFalse(p["terrain_blocked"])
        self.assertTrue(p["reachable"])
        self.assertGreater(p["clearance_ft"], 2000)

    def test_a_low_aircraft_behind_the_ridge_east_of_julian_does_not(self):
        p = radio_sites.path(*BEHIND_RIDGE, self.rpt, terrain_ft=ridge_east_of_jli)
        self.assertTrue(p["within_horizon"], "the horizon alone would allow it")
        self.assertTrue(p["terrain_blocked"])
        self.assertLess(p["clearance_ft"], 0)
        self.assertFalse(p["reachable"])

    def test_the_repeater_reaches_the_base_over_the_synthetic_country(self):
        link = radio_sites.site_link(self.rpt, self.base, terrain_ft=ridge_between_search_area_and_base)
        self.assertEqual((link["from"], link["to"]), ("RPT-JLI", "BASE-KSEE"))
        self.assertTrue(link["reachable"])
        self.assertFalse(link["terrain_blocked"])

    def test_routing_direct_then_via_repeater_then_out_of_range(self):
        # Flat-ish country: the aircraft near Julian reaches Gillespie Field directly.
        direct = radio_sites.route(*NEAR_JULIAN, self.sites, terrain_ft=ridge_east_of_jli)
        self.assertEqual((direct["path"], direct["via"]), ("direct", None))
        self.assertEqual(direct["heard"], "heard direct at Mission Base, Gillespie Field (KSEE)")
        # A ridge between the search area and the base: the same aircraft is
        # heard through the Julian repeater, whose fixed link clears the ridge.
        via = radio_sites.route(*NEAR_JULIAN, self.sites, terrain_ft=ridge_between_search_area_and_base)
        self.assertEqual((via["path"], via["via"]), ("repeater", "RPT-JLI"))
        self.assertEqual(via["heard"], "heard via Julian (JLI VORTAC) repeater")
        self.assertTrue(via["paths"]["BASE-KSEE"]["terrain_blocked"])
        # Low and east of the ridge: neither the base nor the repeater hears it.
        none = radio_sites.route(*BEHIND_RIDGE, self.sites, terrain_ft=ridge_east_of_jli)
        self.assertEqual((none["path"], none["via"]), ("none", None))
        self.assertEqual(none["heard"], "out of range of base and repeater")

    def test_escon_search_block_is_heard_direct_without_terrain(self):
        for alt in (4500.0, 5500.0):
            r = radio_sites.route(ESCON[0], ESCON[1], alt, self.sites)
            self.assertEqual(r["path"], "direct", alt)
            self.assertFalse(r["paths"]["BASE-KSEE"]["terrain_checked"])

    def test_unloaded_terrain_counts_as_clear_like_the_engine(self):
        p = radio_sites.path(*BEHIND_RIDGE, self.rpt, terrain_ft=lambda lat, lon: None)
        self.assertTrue(p["terrain_checked"] and p["reachable"])
        self.assertIsNone(p["clearance_ft"])

    def test_sampling_follows_the_engine_constants(self):
        self.assertEqual(radio_sites.los_sample_count(1.0), 24)
        self.assertEqual(radio_sites.los_sample_count(10.0), 40)
        self.assertEqual(radio_sites.los_sample_count(100.0), 96)
        self.assertAlmostEqual(radio_sites.earth_bulge_ft(30.0, 0.5), 149.0, delta=2.0)


class SitesRoute(unittest.TestCase):
    def setUp(self):
        from test_setup_auth import build_app
        self.main, self.client, self.db = build_app(instructor="instr-token-" + "x" * 16)
        self.headers = {"X-CAPVSAR-Token": "instr-token-" + "x" * 16}

    def tearDown(self):
        os.unlink(self.db)

    def test_sites_route_describes_the_exercise_and_routes_a_position(self):
        r = self.client.get("/api/radio/sites", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual([s["id"] for s in body["sites"]], ["BASE-KSEE", "RPT-JLI"])
        self.assertEqual(body["repeater_pair"]["output_mhz"], 148.125)
        self.assertEqual(body["links"][0]["from"], "RPT-JLI")
        self.assertTrue(body["links"][0]["reachable"])
        r = self.client.get("/api/radio/sites", params={"lat": ESCON[0], "lon": ESCON[1], "alt_ft": 4500},
                            headers=self.headers)
        self.assertEqual(r.json()["route"]["path"], "direct")
        self.assertEqual(self.client.get("/api/radio/sites", params={"lat": 1, "lon": 2},
                                         headers=self.headers).status_code, 400)
        self.assertEqual(self.client.get("/api/radio/sites", params={"lat": 1, "lon": 200, "alt_ft": 1},
                                         headers=self.headers).status_code, 400)

    def test_sites_route_needs_a_role(self):
        self.assertIn(self.client.get("/api/radio/sites").status_code, (401, 403, 503))


if __name__ == "__main__":
    unittest.main()
