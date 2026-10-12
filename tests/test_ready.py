"""The Ready room (docs/UX_REVIEW_2026-10-11.md §4.3, docs/DECISIONS_2026-10-11.md D5)."""
import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_console import INSTRUCTOR, PLUGIN, build_app, leaks, run_sortie  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class ReadyRoom(unittest.TestCase):
    def setUp(self):
        self.main, self.client, self.db = build_app(instructor=INSTRUCTOR, plugin=PLUGIN)
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}
        self.plug = {"X-CAPVSAR-Token": PLUGIN}
        r = self.client.post("/api/setup", headers=self.instr, json={
            "exercise_name": "Ready test",
            "aircraft": [{"callsign": "CAP 487", "crew": ["pilot", "observer"]},
                         {"callsign": "CAP 423", "crew": ["observer"]}],
            "staff": [{"role": "base", "title": "Mission Radio Operator 1"}]})
        self.assertEqual(r.status_code, 200, r.text)
        self.roster = r.json()["roster"]

    def tearDown(self):
        os.unlink(self.db)

    def code(self, prefix):
        return next(x["code"] for x in self.roster if x["code"].startswith(prefix + "-"))

    def login(self, prefix):
        from fastapi.testclient import TestClient
        # The session cookie is Secure, so the client must look like HTTPS.
        c = TestClient(self.main.app, base_url="https://testserver")
        r = c.post("/api/auth/login", json={"code": self.code(prefix)})
        self.assertEqual(r.status_code, 200, r.text)
        return c

    def test_seats_are_derived_from_the_roster(self):
        st = self.client.get("/api/ready", headers=self.instr).json()
        seats = {(s["seat"], s["callsign"]) for s in st["seats"]}
        self.assertIn(("director", "INSTRUCTOR"), seats)
        self.assertIn(("pilot", "CAP 487"), seats)
        self.assertIn(("observer", "CAP 487"), seats)
        self.assertIn(("observer", "CAP 423"), seats)
        self.assertIn(("mro", "BASE 1"), seats)
        self.assertEqual(st["summary"]["total"], len([s for s in st["seats"] if s["seat"] != "station"]))
        slots = {s["callsign"]: s["ac_slot"] for s in st["seats"] if s["kind"] == "aircraft"}
        self.assertEqual(slots, {"CAP 487": 1, "CAP 423": 2})      # roster order is the colour slot

    def test_a_reporting_station_and_powered_head_light_the_aircraft_checks(self):
        run_sortie(self.main, self.client, headers=self.instr)
        before = self.client.get("/api/ready", headers=self.instr).json()
        obs = next(s for s in before["seats"] if s["seat"] == "observer" and s["callsign"] == "CAP 487")
        self.assertEqual(obs["checks"]["station"], "pending")
        r = self.client.post("/api/positions", headers=self.plug, json={
            "callsign": "CAP487", "lat": 33.1, "lon": -117.2, "alt_ft": 5500.0, "hdg_true": 90.0,
            "df": {"valid": False, "head_type": 1, "power": 1}})
        self.assertEqual(r.status_code, 200, r.text)
        after = self.client.get("/api/ready", headers=self.instr).json()
        obs = next(s for s in after["seats"] if s["seat"] == "observer" and s["callsign"] == "CAP 487")
        self.assertEqual(obs["checks"]["station"], "ok")
        self.assertEqual(obs["checks"]["df_head"], "ok")
        pilot = next(s for s in after["seats"] if s["seat"] == "pilot" and s["callsign"] == "CAP 487")
        self.assertEqual(pilot["checks"]["station"], "ok")
        self.assertNotIn("df_head", pilot["checks"])
        other = next(s for s in after["seats"] if s["callsign"] == "CAP 423")
        self.assertEqual(other["checks"]["station"], "pending")

    def test_a_stale_station_is_said_so(self):
        run_sortie(self.main, self.client, headers=self.instr)
        self.client.post("/api/positions", headers=self.plug, json={
            "callsign": "CAP487", "lat": 33.1, "lon": -117.2, "alt_ft": 5500.0, "hdg_true": 90.0})
        self.main.hub.aircraft["CAP487"]["t"] = time.time() - 25
        st = self.client.get("/api/ready", headers=self.instr).json()
        pilot = next(s for s in st["seats"] if s["seat"] == "pilot" and s["callsign"] == "CAP 487")
        self.assertEqual(pilot["status"], "stale")
        self.assertEqual(pilot["checks"]["station"], "bad")

    def test_a_participant_can_attest_and_becomes_joined(self):
        c = self.login("OBS-487")
        st = c.get("/api/ready").json()
        self.assertEqual(st["me"]["callsign"], "CAP 487")
        r = c.post("/api/ready/check", json={"check": "briefing", "ok": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c.post("/api/ready/check", json={"check": "hack", "ok": True}).status_code, 422)
        st = c.get("/api/ready").json()
        me = next(s for s in st["seats"] if s["seat"] == "observer" and s["callsign"] == "CAP 487")
        self.assertEqual(me["checks"]["joined"], "ok")
        self.assertEqual(me["checks"]["briefing"], "ok")
        self.assertIn(me["status"], ("joined", "on_net"))

    def test_the_socket_registers_presence_with_its_page(self):
        c = self.login("PLT-487")
        # The socket handshake carries the session as a Bearer header here;
        # in a browser the cookie does the same job.
        sid = c.cookies.get("capvsar_session")
        self.assertTrue(sid)
        with c.websocket_connect("/ws?page=ready", headers={"Authorization": f"Bearer {sid}"}) as ws:
            ws.receive_json()
            st = self.client.get("/api/ready", headers=self.instr).json()
            pilot = next(s for s in st["seats"] if s["seat"] == "pilot" and s["callsign"] == "CAP 487")
            self.assertEqual(pilot["page"], "ready")
            self.assertEqual(pilot["checks"]["joined"], "ok")

    def test_ready_needs_a_credential_and_never_carries_truth(self):
        self.assertIn(self.client.get("/api/ready").status_code, (401, 403))
        run_sortie(self.main, self.client, headers=self.instr)
        for who in (self.login("OBS-487"), self.login("MRO-1")):
            body = who.get("/api/ready").json()
            self.assertEqual(leaks(body), [], "beacon truth in the Ready room")
            self.assertNotIn("notes", body["scenario"])
            self.assertIn("alert_text", body["scenario"])

    def test_the_page_is_served_on_the_shell(self):
        html = (ROOT / "services/exercise/app/static/ready.html").read_text()
        for asset in ("/static/tokens.css", "/static/shell.css", "/static/shell.js", "/static/ready.js"):
            self.assertIn(asset, html)
        self.assertIn('<header id="shell">', html)
        js = (ROOT / "services/exercise/app/static/ready.js").read_text()
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("insertAdjacentHTML", js)
        self.assertEqual(self.client.get("/ready", headers=self.instr).status_code, 200)

    def test_seat_of_reads_old_rows(self):
        access = __import__("app.access", fromlist=["seat_of"])
        self.assertEqual(access.seat_of({"role": "base", "title": "Mission Radio Operator 2"}), "mro")
        self.assertEqual(access.seat_of({"role": "base", "title": "Air Operations Branch Director"}), "aobd")
        self.assertEqual(access.seat_of({"role": "base", "title": "Staff Member 1"}), "base")
        self.assertEqual(access.seat_of({"role": "aircrew", "title": "CAP 423 SAR Mission Pilot"}), "pilot")
        self.assertEqual(access.seat_of({"role": "aircrew", "title": "CAP 423 Mission Observer"}), "observer")
        self.assertEqual(access.seat_of({"role": "ground_team", "title": "UDF 1"}), "udf")
        self.assertEqual(access.seat_of({"role": "evaluator", "title": "SET"}), "evaluator")
        self.assertEqual(access.seat_of({"role": "aircrew", "seat": "scanner", "title": "x"}), "scanner")


if __name__ == "__main__":
    unittest.main()
