"""
Engine robustness against what the console actually sends (S-5).

The engine suite drives the DF maths with well-formed scenarios. These tests
drive it with the scenarios a real console produces: nullable fields, a
scenario swapped underneath a tick, a reply that will not parse.

Every case here fails on the pre-S-5 engine.

    python3 -m pytest tests/test_engine_robustness.py
"""
import importlib.util
import io
import json
import os
import sys
import unittest
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xp  # the stub

PLUGIN = os.path.abspath(os.path.join(HERE, "..", "xplane", "PI_capvsar_df.py"))
spec = importlib.util.spec_from_file_location("PI_capvsar_df_robust", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def started_engine():
    """A fully started engine, with its datarefs registered in the stub.

    This is what makes the accessor tests real: they call the very read/write
    callbacks XPluginStart handed to X-Plane, out of xp.REFS, rather than a
    reimplementation of them in the test.
    """
    xp.REFS.clear()
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, type) and hasattr(obj, "XPluginStart"):
            e = obj()
            e.XPluginStart()
            return e
    raise AssertionError("no engine class found")


def read_int(name):
    return xp.REFS[name]["readInt"](None)


def write_int(name, value):
    xp.REFS[name]["writeInt"](None, value)


def engine():
    """A bare engine, as the network-thread tests build one."""
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, type) and hasattr(obj, "fetch_scenario"):
            e = obj.__new__(obj)
            e.scn = {"active": 0, "lat": 0.0, "lon": 0.0, "elev_ft": 0.0,
                     "band": 121.5, "power": 1.0, "effects": {}}
            return e
    raise AssertionError("no engine class found")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def respond(body, raw=None):
    def urlopen(req, timeout=None):
        return FakeResponse(raw if raw is not None else json.dumps(body).encode())
    mod.urllib.request.urlopen = urlopen


def truth(**scenario):
    sc = {"id": "s1", "name": "T", "beacon_lat": 34.2, "beacon_lon": -116.9,
          "beacon_elev_ft": 4300.0, "band": "121.5", "power": 1.0, "effects": {}}
    sc.update(scenario)
    return {"sortie": {"id": "a", "name": "T", "started": 1.0, "stopped": None,
                       "revealed": 0},
            "scenario": sc, "aircraft": [], "server_time": 1.0}


class NullableFields(unittest.TestCase):
    """V2-8: the console's own model types several of these `| None`.

    A null reaching a dataref read callback raises inside X-Plane, which
    returns 0 for the accessor. For `cap/df/error_code` that is not a benign
    zero - 0 is E0 NO RECEIVER, so an empty field made the Becker report a hard
    receiver fault. A null in the `cs` block instead raises one level up in
    compute(), where it is caught and logged four times a second while every
    dataref stays frozen at its last value.
    """

    def setUp(self):
        self.e = engine()
        self._real = mod.urllib.request.urlopen
        xp.LOG.clear()

    def tearDown(self):
        mod.urllib.request.urlopen = self._real

    def test_as_int_coerces_like_as_float(self):
        self.assertEqual(mod.as_int(None, -1), -1)
        self.assertEqual(mod.as_int("not a number", -1), -1)
        self.assertEqual(mod.as_int("7"), 7)
        self.assertEqual(mod.as_int(7.9), 7)

    def test_null_error_code_reads_as_no_error_not_E0(self):
        e = started_engine()
        e.scn = dict(e.scn, effects={"error_code": None})
        # The real accessor X-Plane would call.
        self.assertEqual(read_int("cap/df/error_code"), mod.ERR_NONE)
        self.assertNotEqual(read_int("cap/df/error_code"), 0,
                            "0 is E0 NO RECEIVER, not 'healthy'")

    def test_absent_error_code_reads_as_no_error(self):
        e = started_engine()
        e.scn = dict(e.scn, effects={})
        self.assertEqual(read_int("cap/df/error_code"), mod.ERR_NONE)

    def test_a_real_error_code_still_reaches_the_panel(self):
        e = started_engine()
        e.scn = dict(e.scn, effects={"error_code": 7})
        self.assertEqual(read_int("cap/df/error_code"), 7)

    def test_null_cs_fields_do_not_raise(self):
        self.e.scn = dict(
            self.e.scn, active=1, lat=34.2, lon=-116.9,
            cs={"protocol": None, "country": None, "hex15": None,
                "has_position": True, "lat": None, "lon": None},
            effects={})
        # load_decode is the method that used bare int()/float() on these.
        self.e.panel_seen = False
        self.e.mode = 0
        self.e.load_decode()
        self.assertEqual(self.e.cs_protocol, 2)      # STANDARD default
        self.assertEqual(self.e.cs_country, 366)     # United States default
        self.assertEqual(self.e.cs_lat, 34.2)        # falls back to the beacon
        self.assertEqual(self.e.cs_lon, -116.9)

    def test_null_effects_do_not_break_the_scenario_poll(self):
        respond(truth(effects={"multipath_offset_deg": None,
                               "antenna_offset_deg": None,
                               "mounting": None,
                               "error_code": None}))
        self.e.poll_scenario_once()
        self.assertEqual(self.e.scn["active"], 1)
        self.assertEqual(mod.as_float(self.e.scn["effects"]["multipath_offset_deg"], 40.0),
                         40.0)


class CircularMean(unittest.TestCase):
    """EN-10: `% 360.0` on a small negative float returns 360.0, and the
    faceplates render that as `<360>` instead of `000`."""

    def test_350_and_10_average_to_zero_not_360(self):
        self.assertEqual(mod.circular_mean([350.0, 10.0]), 0.0)

    def test_359_and_1_average_to_zero(self):
        self.assertEqual(mod.circular_mean([359.0, 1.0]), 0.0)

    def test_ordinary_averages_are_untouched(self):
        self.assertAlmostEqual(mod.circular_mean([90.0, 110.0]), 100.0, places=6)
        self.assertAlmostEqual(mod.circular_mean([10.0]), 10.0, places=6)

    def test_never_returns_360(self):
        for a in range(0, 360, 7):
            for d in (1, 3, 11):
                m = mod.circular_mean([(a - d) % 360.0, (a + d) % 360.0])
                self.assertLess(m, 360.0)
                self.assertGreaterEqual(m, 0.0)


class ScenarioSwapIsAtomic(unittest.TestCase):
    """EN-4: the network thread used to mutate the dict the flight loop reads.

    A swap landing between the loop's `s["lat"]` and `s["lon"]` produced one
    tick with an old latitude and a new longitude - a beacon somewhere between
    the two, which then entered the averaging window and dragged the needle for
    up to six seconds.
    """

    def setUp(self):
        self.e = engine()
        self._real = mod.urllib.request.urlopen
        xp.LOG.clear()

    def tearDown(self):
        mod.urllib.request.urlopen = self._real

    def test_poll_rebinds_rather_than_mutating(self):
        before = self.e.scn
        respond(truth())
        self.e.poll_scenario_once()
        self.assertIsNot(self.e.scn, before,
                         "scn was mutated in place; a flight-loop tick can see half a swap")
        self.assertEqual(before["active"], 0, "the old dict was modified")

    def test_a_reader_holding_the_old_dict_sees_a_whole_scenario(self):
        respond(truth(beacon_lat=1.0, beacon_lon=2.0))
        self.e.poll_scenario_once()
        held = self.e.scn                      # what a tick captured
        respond(truth(beacon_lat=50.0, beacon_lon=60.0))
        self.e.poll_scenario_once()            # swap underneath it
        self.assertEqual((held["lat"], held["lon"]), (1.0, 2.0),
                         "the captured scenario changed underneath the reader")
        self.assertEqual((self.e.scn["lat"], self.e.scn["lon"]), (50.0, 60.0))

    def test_every_branch_rebinds(self):
        for body in (truth(),
                     {"sortie": {"stopped": 1.0}, "scenario": {}},          # not running
                     {"sortie": {"id": "a", "stopped": None},               # running, no beacon
                      "scenario": {"effects": {"radio_horizon": True}}}):
            respond(body)
            before = self.e.scn
            self.e.poll_scenario_once()
            self.assertIsNot(self.e.scn, before, f"branch did not rebind: {body}")


class MalformedReplies(unittest.TestCase):
    """EN-12: a console that answers with something unparseable left the DF
    homing on the previous beacon with nothing in the log."""

    def setUp(self):
        self.e = engine()
        self._real = mod.urllib.request.urlopen
        xp.LOG.clear()

    def tearDown(self):
        mod.urllib.request.urlopen = self._real

    def test_previous_scenario_survives_a_bad_reply(self):
        respond(truth(beacon_lat=12.0, beacon_lon=-34.0))
        self.e.poll_scenario_once()
        respond(None, raw=b"<html>gateway timeout</html>")
        self.e.poll_scenario_once()
        self.assertEqual((self.e.scn["lat"], self.e.scn["lon"]), (12.0, -34.0))

    def test_bad_reply_is_logged_once_then_rate_limited(self):
        respond(None, raw=b"not json")
        for _ in range(5):
            self.e.poll_scenario_once()
        self.e.drain_log()
        complaints = [m for m in xp.LOG if "scenario poll failed" in m]
        self.assertEqual(len(complaints), 1, f"logged {complaints}")

    def test_unreachable_console_stays_silent(self):
        def boom(req, timeout=None):
            raise urllib.error.URLError("connection refused")
        mod.urllib.request.urlopen = boom
        for _ in range(3):
            self.e.poll_scenario_once()
        self.e.drain_log()
        self.assertEqual([m for m in xp.LOG if "scenario poll failed" in m], [],
                         "an offline console is expected and must not be logged")


class ScanHold(unittest.TestCase):
    """EN-11: the held scan frequency survived a scan off/on cycle, so
    re-enabling scan resumed on a frequency the crew had tuned away from."""

    def test_turning_scan_off_drops_the_held_frequency(self):
        e = started_engine()
        write_int("cap/df/scan_enable", 1)
        e.scan_hold_hz = 121_500_000          # scan settled on a frequency
        write_int("cap/df/scan_enable", 0)    # crew turns scan off
        self.assertIsNone(e.scan_hold_hz,
                          "a stale scan frequency survived scan being turned off")

    def test_turning_scan_on_does_not_clear_anything(self):
        e = started_engine()
        e.scan_hold_hz = 243_000_000
        write_int("cap/df/scan_enable", 1)
        self.assertEqual(e.scan_hold_hz, 243_000_000)

    def test_the_write_still_lands(self):
        e = started_engine()
        write_int("cap/df/scan_enable", 1)
        self.assertEqual(e.scan_enable, 1)
        self.assertTrue(e.panel_seen, "writing a panel input must set panel_seen")


if __name__ == "__main__":
    unittest.main()
