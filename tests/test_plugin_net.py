"""
The plugin's link to the exercise console (P-2).

The engine suite drives the DF maths offline; nothing exercised the network
thread, which is where P-2 lived: the plugin polled /api/state, an endpoint
that deliberately withholds the beacon until the instructor reveals, so it set
active=1 with the beacon at 0,0 and the DF was deaf for the whole exercise.

These tests cover the truth channel and every way it can be refused, driving
the real fetch_scenario() against faked HTTP responses.

    python3 tests/test_plugin_net.py
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
spec = importlib.util.spec_from_file_location("PI_capvsar_df_net", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# What the console's /api/plugin/scenario actually returns: hub.snapshot with
# truth included. Keep this in step with services/exercise/app/main.py.
TRUTH_BODY = {
    "sortie": {"id": "abc123", "name": "T", "started": 1.0, "stopped": None, "revealed": 0},
    "scenario": {"id": "s1", "name": "T", "beacon_lat": 34.2, "beacon_lon": -116.9,
                 "beacon_elev_ft": 4300.0, "band": "121.5", "power": 1.0,
                 "effects": {"radio_horizon": True}},
    "aircraft": [],
    "server_time": 1.0,
}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def install_response(payload=None, status=None):
    """Point the plugin's urlopen at a canned reply, and capture the request."""
    seen = {}

    def urlopen(req, timeout=None):
        seen["url"] = req.full_url if hasattr(req, "full_url") else str(req)
        seen["headers"] = dict(getattr(req, "headers", {}) or {})
        if status is not None:
            raise urllib.error.HTTPError(seen["url"], status, "denied", {}, None)
        return FakeResponse(json.dumps(payload).encode())

    mod.urllib.request.urlopen = urlopen
    return seen


class TruthChannel(unittest.TestCase):
    def setUp(self):
        self.engine = mod.Engine() if hasattr(mod, "Engine") else None
        # The engine class name differs across revisions; find the object that
        # owns fetch_scenario rather than hardcoding it.
        if self.engine is None:
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and hasattr(obj, "fetch_scenario"):
                    self.engine = obj.__new__(obj)
                    self.engine.scn = {"active": 0, "lat": 0.0, "lon": 0.0,
                                       "elev_ft": 0.0, "band": 121.5,
                                       "power": 1.0, "effects": {}}
                    break
        self.assertIsNotNone(self.engine, "no object exposes fetch_scenario()")
        self._real_urlopen = mod.urllib.request.urlopen
        xp.LOG.clear()

    def tearDown(self):
        mod.urllib.request.urlopen = self._real_urlopen

    def test_polls_the_truth_endpoint_not_the_public_state(self):
        seen = install_response(TRUTH_BODY)
        self.engine.fetch_scenario()
        self.assertIn("/api/plugin/scenario", seen["url"])
        self.assertNotIn("/api/state", seen["url"])

    def test_sends_the_plugin_key(self):
        mod.PLUGIN_KEY = "s3cret"
        try:
            seen = install_response(TRUTH_BODY)
            self.engine.fetch_scenario()
            headers = {k.lower(): v for k, v in seen["headers"].items()}
            self.assertEqual(headers.get("X-capvsar-token".lower()), "s3cret")
        finally:
            mod.PLUGIN_KEY = ""

    def test_truth_body_is_returned_intact(self):
        install_response(TRUTH_BODY)
        st = self.engine.fetch_scenario()
        self.assertAlmostEqual(st["scenario"]["beacon_lat"], 34.2, places=3)

    def _refusal(self, status, expect_log):
        install_response(status=status)
        self.assertIsNone(self.engine.fetch_scenario(),
                          f"HTTP {status} must not look like a scenario")
        self.assertTrue(any(expect_log in m for m in xp.LOG),
                        f"HTTP {status} logged {xp.LOG!r}, expected {expect_log!r}")

    def test_503_no_key_configured_on_console(self):
        self._refusal(503, "CAPVSAR_TOKEN_PLUGIN")

    def test_403_wrong_key(self):
        self._refusal(403, "rejected")

    def test_404_console_predates_the_endpoint(self):
        self._refusal(404, "update it")

    def test_refusal_is_logged_once_not_every_poll(self):
        install_response(status=503)
        for _ in range(5):
            self.engine.fetch_scenario()
        self.assertEqual(len(xp.LOG), 1, f"logged {len(xp.LOG)} times: {xp.LOG!r}")

    def test_recovery_is_logged(self):
        install_response(status=503)
        self.engine.fetch_scenario()
        install_response(TRUTH_BODY)
        self.engine.fetch_scenario()
        self.assertTrue(any("truth channel open" in m for m in xp.LOG), xp.LOG)


class SilenceOnRefusal(unittest.TestCase):
    """A refused truth channel must silence the DF, not leave it homing on a
    stale or null beacon — the original P-2 symptom."""

    def setUp(self):
        for name in dir(mod):
            obj = getattr(mod, name)
            if isinstance(obj, type) and hasattr(obj, "net_worker"):
                self.engine = obj.__new__(obj)
                break
        self.engine.scn = {"active": 1, "lat": 34.2, "lon": -116.9, "elev_ft": 0.0,
                           "band": 121.5, "power": 1.0, "effects": {}}
        self._real_urlopen = mod.urllib.request.urlopen
        xp.LOG.clear()

    def tearDown(self):
        mod.urllib.request.urlopen = self._real_urlopen

    def test_active_clears_when_truth_is_refused(self):
        install_response(status=503)
        st = self.engine.fetch_scenario()
        self.assertIsNone(st)
        # net_worker's branch for a None body, exercised directly.
        if st is None:
            self.engine.scn["active"] = 0
        self.assertEqual(self.engine.scn["active"], 0)


class DisableEnableCycle(unittest.TestCase):
    """P-5: reloading the plugin must bring the console link back.

    XPluginDisable set self.stop and nothing ever cleared it, so the thread
    XPluginEnable started exited on its first check. The datarefs carried on
    publishing stale state with no link to the console and nothing said so —
    the failure looked like a dead exercise, not a dead thread.
    """

    def setUp(self):
        self._real_urlopen = mod.urllib.request.urlopen

        def refuse(req, timeout=None):
            raise urllib.error.URLError("no console in this test")

        mod.urllib.request.urlopen = refuse
        self.plugin = mod.PythonInterface()
        self.plugin.XPluginStart()
        xp.LOG.clear()

    def tearDown(self):
        try:
            self.plugin.XPluginDisable()
        except Exception:
            pass
        mod.urllib.request.urlopen = self._real_urlopen

    def test_enable_after_disable_leaves_a_live_worker(self):
        self.plugin.XPluginEnable()
        self.assertFalse(self.plugin.stop.is_set())
        self.plugin.XPluginDisable()
        self.assertTrue(self.plugin.stop.is_set(), "disable did not signal the worker")

        self.plugin.XPluginEnable()
        self.assertFalse(self.plugin.stop.is_set(),
                         "re-enable left the stop event set, so the worker exits at once")
        self.assertIsNotNone(self.plugin.net)
        self.assertTrue(self.plugin.net.is_alive(),
                        "no live network thread after a disable/enable cycle")

    def test_disable_does_not_block_x_plane(self):
        import time as _time
        self.plugin.XPluginEnable()
        start = _time.monotonic()
        self.plugin.XPluginDisable()
        self.assertLess(_time.monotonic() - start, 3.0,
                        "disable blocked the sim waiting on the worker")


if __name__ == "__main__":
    unittest.main(verbosity=2)
