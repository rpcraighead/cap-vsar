"""
Exercise console backend hardening, wave C (docs/PROJECT_REVIEW_2026-10-10.md
section 2): X2-3, X2-5, X2-6, X2-7, X2-9, X2-10, X2-11, X2-12 and the
improvements that went with them. The earlier X2 fixes (X2-1, X2-2, X2-4,
X2-8) are in test_console.py and test_radio.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import unittest

from tests.test_console import (BASE, BEACON, INSTRUCTOR, PLUGIN, build_app,
                                run_sortie)

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("httpx is not installed in this interpreter")

SCENARIO = {"name": "hardening", "beacon_lat": 33.1, "beacon_lon": -117.2,
            "band": "121.5"}
JSON = {"Content-Type": "application/json"}


class Base(unittest.TestCase):
    def setUp(self):
        self.main, self.client, self.db = build_app(
            instructor=INSTRUCTOR, base=BASE, plugin=PLUGIN)
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}
        self.base = {"X-CAPVSAR-Token": BASE}
        self.plug = {"X-CAPVSAR-Token": PLUGIN}

    def tearDown(self):
        os.unlink(self.db)

    def post_raw(self, url, raw, headers=None):
        return self.client.post(url, content=raw,
                                headers={**JSON, **(headers or self.instr)})


class ScenarioEffectsAreValidated(Base):
    """X2-3: ScenarioIn.effects used to be dict[str, Any]."""

    def create(self, effects_json):
        return self.post_raw(
            "/api/scenarios",
            '{"name":"x","beacon_lat":33.1,"beacon_lon":-117.2,"effects":%s}'
            % effects_json)

    def test_nan_effect_is_refused(self):
        for raw in ('{"multipath_offset_deg": NaN}',
                    '{"wing_null_max_loss_db": Infinity}',
                    '{"multipath_offset_deg": -Infinity}'):
            self.assertEqual(self.create(raw).status_code, 422, raw)

    def test_unknown_effect_key_is_refused(self):
        self.assertEqual(self.create('{"radio_horizon": true, "typo": 1}')
                         .status_code, 422)

    def test_wrongly_typed_effect_is_refused(self):
        self.assertEqual(self.create('{"radio_horizon": "banana"}').status_code, 422)
        self.assertEqual(self.create('{"multipath_offset_deg": 999}').status_code, 422)

    def test_a_valid_partial_set_is_stored_as_sent(self):
        r = self.create('{"multipath": true, "df_antenna_profile": "c182_belly"}')
        self.assertEqual(r.status_code, 200, r.text)
        row = next(s for s in self.client.get("/api/scenarios", headers=self.instr).json()
                   if s["id"] == r.json()["id"])
        self.assertEqual(row["effects"], {"multipath": True,
                                          "df_antenna_profile": "c182_belly"})

    def test_omitted_effects_get_the_defaults(self):
        r = self.post_raw("/api/scenarios", json.dumps(SCENARIO))
        self.assertEqual(r.status_code, 200, r.text)
        row = next(s for s in self.client.get("/api/scenarios", headers=self.instr).json()
                   if s["id"] == r.json()["id"])
        self.assertEqual(row["effects"], dict(self.main.DEFAULT_EFFECTS))

    def test_a_poisoned_stored_row_cannot_break_the_listing(self):
        """Rows written before this fix may already hold a bare NaN."""
        with self.main.db() as c:
            c.execute("INSERT INTO scenarios (id, name, beacon_lat, beacon_lon,"
                      " effects, created) VALUES ('poison','p',1,2,?,1)",
                      ('{"multipath_offset_deg": NaN, "multipath": true}',))
        r = self.client.get("/api/scenarios", headers=self.instr)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("NaN", r.text)
        poisoned = next(s for s in r.json() if s["id"] == "poison")
        self.assertEqual(poisoned["effects"], {"multipath": True})

    def test_the_hub_refuses_to_send_a_bare_nan(self):
        class Sock:
            async def send_text(self, text):  # pragma: no cover
                raise AssertionError("sent " + text)

        hub = self.main.hub
        hub.clients, hub.truth_clients = {Sock()}, set()
        with self.assertRaises(ValueError):
            asyncio.run(hub.broadcast({"type": "x", "v": float("nan")}))
        hub.aircraft["A1"] = {"callsign": "A1", "t": time.time(), "lat": float("nan")}
        with self.assertRaises(ValueError):
            asyncio.run(hub.broadcast_state())

    def test_the_ticker_survives_a_value_json_cannot_carry(self):
        hub = self.main.hub

        class Sock:
            sent = []
            async def send_text(self, text):
                self.sent.append(text)

        hub.clients, hub.truth_clients = {Sock()}, set()
        hub.aircraft["A1"] = {"callsign": "A1", "t": time.time() + 100,
                              "lat": float("nan")}

        async def run():
            task = asyncio.create_task(self.main.ticker())
            await asyncio.sleep(2.3)
            alive = not task.done()
            task.cancel()
            return alive

        with self.assertLogs("capvsar.console", level="ERROR"):
            self.assertTrue(asyncio.run(run()))
        self.assertEqual(Sock.sent, [])


class PositionDfIsBounded(Base):
    """Improvement 5: PositionIn.df is a whitelist of finite scalars, <= 2 KB."""

    def setUp(self):
        super().setUp()
        run_sortie(self.main, self.client, headers=self.instr)

    def post(self, df):
        return self.client.post("/api/positions", headers=self.plug, json={
            "callsign": "CAP-1", "lat": 33.1, "lon": -117.2, "alt_ft": 5000.0,
            "hdg_true": 90.0, "df": df})

    def test_oversized_df_is_refused(self):
        self.assertEqual(self.post({"note": "x" * 100, "valid": True,
                                    "blob": "y" * 3000}).status_code, 422)
        self.assertEqual(self.post({"valid": True,
                                    **{f"k{i}": i for i in range(400)}}).status_code, 422)

    def test_unknown_keys_are_dropped_not_stored(self):
        r = self.post({"valid": True, "bearing_true": 10.5, "evil": "x", "nested": {"a": 1}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["df"], {"valid": True, "bearing_true": 10.5})
        with self.main.db() as c:
            stored = json.loads(c.execute("SELECT df_json FROM positions").fetchone()[0])
        self.assertEqual(stored, {"valid": True, "bearing_true": 10.5})

    def test_non_finite_and_non_scalar_values_are_refused(self):
        raw = ('{"callsign":"CAP-1","lat":33.1,"lon":-117.2,"alt_ft":5000,'
               '"df":{"bearing_true": NaN}}')
        self.assertEqual(self.post_raw("/api/positions", raw, self.plug).status_code, 422)
        self.assertEqual(self.post({"note": ["a"]}).status_code, 422)

    def test_a_real_plugin_report_is_accepted_whole(self):
        keys = ("valid bearing_rel bearing_true signal distance_nm in_cone blocked"
                " power head_type freq_hz rx_span_hz squelch mode scan mounting"
                " offset_deg rx_open airframe_shadowed airframe_attenuation_db"
                " roll_deg pitch_deg note").split()
        df = {k: 1 for k in keys}
        df.update(valid=True, in_cone=False, blocked=False, note="terrain masked",
                  bearing_true=102.5, signal=0.4231, freq_hz=121_500_000)
        r = self.post(df)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["df"], df)


class SetupIsTyped(Base):
    """X2-12."""

    def setup_body(self, **kw):
        body = {"name": "Ex", "num_aircraft": 1,
                "aircraft": [{"id": "ac-1", "callsign": "CAP 423", "tail": "N1",
                              "df_model": "Becker", "crew": ["pilot", "observer"]}],
                "staff": [{"role": "base", "title": "MRO", "callsign": "MRO 1"}]}
        body.update(kw)
        return body

    def test_a_valid_setup_is_accepted(self):
        r = self.client.post("/api/setup", json=self.setup_body(), headers=self.instr)
        self.assertEqual(r.status_code, 200, r.text)

    def test_plugin_cannot_be_minted_as_a_staff_role(self):
        for role in ("plugin", "instructor", "root"):
            r = self.client.post("/api/setup", headers=self.instr, json=self.setup_body(
                staff=[{"role": role, "title": "x", "callsign": "STAFF 1"}]))
            self.assertEqual(r.status_code, 422, role)
        roles = {row["role"] for row in self.client.get("/api/setup", headers=self.instr)
                 .json()["roster"]}
        self.assertNotIn("plugin", roles)

    def test_a_non_string_callsign_is_a_422_not_a_500(self):
        r = self.client.post("/api/setup", headers=self.instr, json=self.setup_body(
            aircraft=[{"id": "ac-1", "callsign": 423}]))
        self.assertEqual(r.status_code, 422)

    def test_lengths_and_crew_are_capped(self):
        for aircraft in ([{"callsign": "X" * 33}], [{"tail": "T" * 33}],
                         [{"crew": ["pilot", "astronaut"]}],
                         [{"id": "../../etc"}]):
            r = self.client.post("/api/setup", headers=self.instr,
                                 json=self.setup_body(aircraft=aircraft))
            self.assertEqual(r.status_code, 422, aircraft)
        r = self.client.post("/api/setup", headers=self.instr, json=self.setup_body(
            aircraft=[{"callsign": "CAP %d" % (400 + i)} for i in range(33)]))
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
