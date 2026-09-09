"""
Exercise console tests: beacon-truth containment and role gates (X-1, X-2, P-2).

The first class here is the regression test the remediation plan asks to be
permanent. The console's whole teaching mechanism is that a crew searches for
a beacon whose position nobody on the exercise net can look up, and three
endpoints used to hand it over on request. Any new endpoint that touches a
scenario or a sortie should be added to LEAK_ENDPOINTS below.

Run:
    python3 -m unittest tests.test_console -v

Needs fastapi + httpx. The container image pins fastapi 0.115.6 / pydantic
2.10.4; nothing here depends on those versions specifically.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "services" / "exercise"))

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("fastapi is not installed in this interpreter")

# A beacon nowhere near the alert position, so a leak is unambiguous.
BEACON = {"lat": 34.2345, "lon": -116.8765, "elev_ft": 4300.0}

INSTRUCTOR, BASE, PLUGIN = "instr-secret", "base-secret", "plugin-secret"


def build_app(db_path=None, **tokens):
    """A console on a throwaway database, with the given tokens configured.

    Pass db_path to reuse an existing file — that is how a restart is
    simulated: build, use, throw the app away, build again on the same file.
    """
    for role in ("INSTRUCTOR", "BASE", "PLUGIN"):
        os.environ.pop(f"CAPVSAR_TOKEN_{role}", None)
    for role, value in tokens.items():
        os.environ[f"CAPVSAR_TOKEN_{role.upper()}"] = value
    if db_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name

    class _Tmp:
        name = db_path
    tmp = _Tmp()
    os.environ["CAPVSAR_DB"] = tmp.name
    for mod in ("app.main", "app.access", "app.radio", "app.propagation", "app"):
        sys.modules.pop(mod, None)
    main = importlib.import_module("app.main")
    # Schema creation lives in the lifespan hook, which TestClient only runs as
    # a context manager. Call it directly so each test gets tables without the
    # seed scenario or the background ticker.
    main.init_db()
    return main, TestClient(main.app), tmp.name


def run_sortie(main, client, *, reveal=False, headers=None):
    """Create a scenario, start a sortie on it, optionally reveal."""
    headers = headers or {}
    r = client.post("/api/scenarios", json={
        "name": "TEST leak check", "notes": "synthetic",
        "beacon_lat": BEACON["lat"], "beacon_lon": BEACON["lon"],
        "beacon_elev_ft": BEACON["elev_ft"], "band": "406", "power": 1.0,
        "alert_lat": 33.0, "alert_lon": -117.5, "alert_radius_nm": 10.0,
    }, headers=headers)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    r = client.post("/api/sorties", json={"scenario_id": sid}, headers=headers)
    assert r.status_code == 200, r.text
    oid = r.json()["id"]
    if reveal:
        assert client.post("/api/sorties/reveal", headers=headers).status_code == 200
    return sid, oid


# Every endpoint that reads scenario or sortie state. Add new ones here.
def leak_endpoints(sid, oid):
    return [
        "/api/state",
        "/api/scenarios",
        "/api/sorties",
        f"/api/sorties/{oid}/track",
        "/api/messages",
        "/api/health",
    ]


def leaks(payload) -> list[str]:
    """Field paths in a response whose value is the beacon position."""
    found = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            for name, truth in (("lat", BEACON["lat"]), ("lon", BEACON["lon"]),
                                ("elev_ft", BEACON["elev_ft"])):
                # ~100 m at this latitude, and exact for the elevation
                if abs(float(node) - truth) < (0.001 if name != "elev_ft" else 0.5):
                    found.append(f"{path} == beacon {name} ({node})")

    walk(payload, "$")
    return found


class TruthContainment(unittest.TestCase):
    """X-1: no endpoint may hand out the beacon before reveal."""

    def setUp(self):
        self.main, self.client, self.db = build_app()

    def tearDown(self):
        os.unlink(self.db)

    def test_no_endpoint_leaks_before_reveal(self):
        sid, oid = run_sortie(self.main, self.client)
        offenders = {}
        for url in leak_endpoints(sid, oid):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            found = leaks(r.json())
            if found:
                offenders[url] = found
        self.assertEqual(offenders, {},
                         f"beacon truth leaked before reveal: {json.dumps(offenders, indent=2)}")

    def test_elevation_is_withheld_too(self):
        """The original fix popped lat/lon and left beacon_elev_ft behind."""
        run_sortie(self.main, self.client)
        sc = self.client.get("/api/state").json()["scenario"]
        self.assertNotIn("beacon_elev_ft", sc)
        self.assertNotIn("beacon_lat", sc)

    def test_scenario_list_withholds_by_default(self):
        run_sortie(self.main, self.client)
        for row in self.client.get("/api/scenarios").json():
            self.assertNotIn("beacon_lat", row)
            self.assertEqual(leaks(row), [])

    def test_track_withholds_until_revealed(self):
        _, oid = run_sortie(self.main, self.client)
        body = self.client.get(f"/api/sorties/{oid}/track").json()
        self.assertIsNone(body["beacon"])
        self.assertFalse(body["revealed"])

    def test_reveal_releases_truth(self):
        _, oid = run_sortie(self.main, self.client, reveal=True)
        state = self.client.get("/api/state").json()
        self.assertAlmostEqual(state["scenario"]["beacon_lat"], BEACON["lat"], places=4)
        track = self.client.get(f"/api/sorties/{oid}/track").json()
        self.assertTrue(track["revealed"])
        self.assertAlmostEqual(track["beacon"]["lat"], BEACON["lat"], places=4)

    def test_alert_position_is_not_treated_as_truth(self):
        """The alert circle is what base staff are given and must survive."""
        run_sortie(self.main, self.client)
        sc = self.client.get("/api/state").json()["scenario"]
        self.assertEqual(sc["alert_lat"], 33.0)
        self.assertEqual(sc["alert_radius_nm"], 10.0)


class TruthUnlock(unittest.TestCase):
    """X-1: a configured instructor token unlocks the definitions endpoint."""

    def setUp(self):
        self.main, self.client, self.db = build_app(instructor=INSTRUCTOR)

    def tearDown(self):
        os.unlink(self.db)

    def test_instructor_token_sees_scenario_truth(self):
        run_sortie(self.main, self.client, headers={"X-CAPVSAR-Token": INSTRUCTOR})
        rows = self.client.get("/api/scenarios",
                               headers={"X-CAPVSAR-Token": INSTRUCTOR}).json()
        self.assertAlmostEqual(rows[-1]["beacon_lat"], BEACON["lat"], places=4)

    def test_wrong_token_does_not(self):
        run_sortie(self.main, self.client, headers={"X-CAPVSAR-Token": INSTRUCTOR})
        rows = self.client.get("/api/scenarios",
                               headers={"X-CAPVSAR-Token": "guess"}).json()
        self.assertNotIn("beacon_lat", rows[-1])

    def test_live_sortie_still_withheld_from_the_map_feed(self):
        """Unlocking definitions must not unlock the running exercise."""
        run_sortie(self.main, self.client, headers={"X-CAPVSAR-Token": INSTRUCTOR})
        sc = self.client.get("/api/state",
                             headers={"X-CAPVSAR-Token": INSTRUCTOR}).json()["scenario"]
        self.assertNotIn("beacon_lat", sc)


class RoleGates(unittest.TestCase):
    """X-2: mutating endpoints require their role once a token is configured."""

    def setUp(self):
        self.main, self.client, self.db = build_app(
            instructor=INSTRUCTOR, base=BASE, plugin=PLUGIN)
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}
        self.base = {"X-CAPVSAR-Token": BASE}

    def tearDown(self):
        os.unlink(self.db)

    def test_instructor_actions_refuse_anonymous_callers(self):
        sid, _ = run_sortie(self.main, self.client, headers=self.instr)
        for method, url, body in [
            ("post", "/api/scenarios", {"name": "x", "beacon_lat": 1.0, "beacon_lon": 2.0}),
            ("delete", f"/api/scenarios/{sid}", None),
            ("post", "/api/sorties", {"scenario_id": sid}),
            ("post", "/api/sorties/stop", None),
            ("post", "/api/sorties/reveal", None),
            ("post", "/api/sorties/effects", {"multipath": True}),
        ]:
            r = getattr(self.client, method)(url, json=body) if body is not None \
                else getattr(self.client, method)(url)
            self.assertEqual(r.status_code, 403, f"{method.upper()} {url} was not gated")

    def test_base_token_cannot_reveal_or_stop(self):
        run_sortie(self.main, self.client, headers=self.instr)
        self.assertEqual(self.client.post("/api/sorties/reveal", headers=self.base).status_code, 403)
        self.assertEqual(self.client.post("/api/sorties/stop", headers=self.base).status_code, 403)

    def test_base_token_can_log_and_message(self):
        run_sortie(self.main, self.client, headers=self.instr)
        r = self.client.post("/api/messages", json={"body": "ops normal"}, headers=self.base)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.post("/api/messages", json={"body": "nope"}).status_code, 403)

    def test_instructor_token_also_satisfies_base(self):
        run_sortie(self.main, self.client, headers=self.instr)
        r = self.client.post("/api/messages", json={"body": "from instructor"},
                             headers=self.instr)
        self.assertEqual(r.status_code, 200)

    def test_position_ingest_needs_the_plugin_key(self):
        run_sortie(self.main, self.client, headers=self.instr)
        pos = {"callsign": "CAP-1", "lat": 33.3, "lon": -117.2, "alt_ft": 5500.0}
        self.assertEqual(self.client.post("/api/positions", json=pos).status_code, 403)
        r = self.client.post("/api/positions", json=pos,
                             headers={"X-CAPVSAR-Token": PLUGIN})
        self.assertEqual(r.status_code, 200)


class PluginTruthChannel(unittest.TestCase):
    """P-2 (server half): the plugin's keyed route to beacon truth."""

    def test_open_when_no_key_configured_is_impossible(self):
        main, client, db = build_app()
        try:
            run_sortie(main, client)
            r = client.get("/api/plugin/scenario")
            self.assertEqual(r.status_code, 503)
        finally:
            os.unlink(db)

    def test_key_serves_truth_before_reveal(self):
        main, client, db = build_app(plugin=PLUGIN)
        try:
            run_sortie(main, client)
            self.assertEqual(client.get("/api/plugin/scenario").status_code, 403)
            self.assertEqual(client.get("/api/plugin/scenario",
                                        headers={"X-CAPVSAR-Token": "wrong"}).status_code, 403)
            body = client.get("/api/plugin/scenario",
                              headers={"X-CAPVSAR-Token": PLUGIN}).json()
            self.assertAlmostEqual(body["scenario"]["beacon_lat"], BEACON["lat"], places=4)
            self.assertAlmostEqual(body["scenario"]["beacon_elev_ft"], BEACON["elev_ft"], places=1)
            # Same shape as /api/state, so the plugin only changes its URL.
            self.assertEqual(set(body), set(client.get("/api/state").json()))
            # ...while the browser feed is still withholding.
            self.assertNotIn("beacon_lat", client.get("/api/state").json()["scenario"])
        finally:
            os.unlink(db)

    def test_payload_carries_every_field_the_plugin_reads(self):
        """Contract test for the seam P-2 broke.

        The plugin's net thread reads these out of the body. If a future
        refactor of snapshot() drops one, the DF degrades quietly in the sim
        rather than failing here — which is exactly how P-2 went unnoticed.
        Keep in step with PI_capvsar_df.py's net_worker().
        """
        main, client, db = build_app(plugin=PLUGIN)
        try:
            run_sortie(main, client)
            body = client.get("/api/plugin/scenario",
                              headers={"X-CAPVSAR-Token": PLUGIN}).json()
            self.assertIn("sortie", body)
            self.assertIn("stopped", body["sortie"])
            for field in ("beacon_lat", "beacon_lon", "beacon_elev_ft",
                          "band", "power", "effects"):
                self.assertIn(field, body["scenario"],
                              f"plugin reads scenario.{field}")
        finally:
            os.unlink(db)

    def test_query_parameter_also_accepted(self):
        """The plugin can pass the key in the URL where a header is awkward."""
        main, client, db = build_app(plugin=PLUGIN)
        try:
            run_sortie(main, client)
            r = client.get(f"/api/plugin/scenario?token={PLUGIN}")
            self.assertEqual(r.status_code, 200)
        finally:
            os.unlink(db)


class SurvivesAnExercise(unittest.TestCase):
    """C7: the console has to keep running for the length of a sortie.

    X-3 (database work off the audio event loop), X-4 (a restart resumes the
    sortie), X-5 (one wedged console does not stall the rest), X-7 (sortie
    lifecycle).
    """

    def setUp(self):
        self.main, self.client, self.db = build_app()

    def tearDown(self):
        os.unlink(self.db)

    # ---- X-4 ------------------------------------------------------------
    def test_restart_resumes_the_running_sortie(self):
        _, oid = run_sortie(self.main, self.client)
        self.client.post("/api/messages", json={"body": "ops normal CAP-1"})
        # Throw the process away and come back up on the same database. The
        # TestClient context manager runs the real lifespan, so this covers
        # rehydrate() being wired into startup, not just that it works.
        main2, client2, _ = build_app(db_path=self.db)
        with client2:
            self.assertIsNotNone(main2.hub.sortie,
                                 "sortie was orphaned by the restart")
            self.assertEqual(main2.hub.sortie["id"], oid)
            self.assertIsNotNone(main2.hub.scenario)
            self.assertTrue(any(m["body"] == "ops normal CAP-1"
                                for m in client2.get("/api/messages").json()),
                            "messages did not survive the restart")

    def test_restart_does_not_resume_a_stopped_sortie(self):
        run_sortie(self.main, self.client)
        self.client.post("/api/sorties/stop")
        main2, client2, _ = build_app(db_path=self.db)
        with client2:
            self.assertIsNone(main2.hub.sortie)

    # ---- X-7 ------------------------------------------------------------
    def test_starting_a_sortie_closes_the_previous_one(self):
        sid, first = run_sortie(self.main, self.client)
        self.client.post("/api/sorties", json={"scenario_id": sid})
        rows = {r["id"]: r for r in self.client.get("/api/sorties").json()}
        self.assertIsNotNone(rows[first]["stopped"],
                             "the first sortie was left running forever")
        self.assertEqual(sum(1 for r in rows.values() if r["stopped"] is None), 1)

    def test_stopped_sortie_stops_collecting(self):
        _, oid = run_sortie(self.main, self.client)
        self.client.post("/api/sorties/stop")
        self.assertEqual(self.client.post("/api/bearings", json={
            "callsign": "CAP-1", "bearing_true": 90.0}).status_code, 400)
        self.client.post("/api/messages", json={"body": "after the fact"})
        track = self.client.get(f"/api/sorties/{oid}/track").json()
        self.assertEqual([m for m in track["messages"]
                          if m["body"] == "after the fact"], [])

    def test_bearing_accepted_after_the_aircraft_expires_from_the_map(self):
        """A bearing passed over voice is often typed in a minute later."""
        _, oid = run_sortie(self.main, self.client)
        self.client.post("/api/positions", json={
            "callsign": "CAP-1", "lat": 33.4, "lon": -117.1, "alt_ft": 5500.0})
        self.main.hub.aircraft.clear()          # the 30 s expiry, deterministically
        r = self.client.post("/api/bearings",
                             json={"callsign": "CAP-1", "bearing_true": 275.0})
        self.assertEqual(r.status_code, 200, r.text)
        brg = self.client.get(f"/api/sorties/{oid}/track").json()["bearings"][-1]
        self.assertAlmostEqual(brg["lat"], 33.4, places=3)

    def test_track_returns_heading_for_per_aircraft_replay(self):
        """F-3: hdg_true was stored on every position and thrown away by the
        query, so the debrief had to infer heading from consecutive fixes."""
        _, oid = run_sortie(self.main, self.client)
        for cs, hdg in (("CAP-1", 275.0), ("CAP-2", 90.0)):
            self.client.post("/api/positions", json={
                "callsign": cs, "lat": 33.4, "lon": -117.1,
                "alt_ft": 5500.0, "hdg_true": hdg})
        rows = self.client.get(f"/api/sorties/{oid}/track").json()["positions"]
        self.assertTrue(all("hdg_true" in r for r in rows), "hdg_true not returned")
        by_cs = {r["callsign"]: r["hdg_true"] for r in rows}
        self.assertEqual(by_cs, {"CAP-1": 275.0, "CAP-2": 90.0})

    def test_bearing_for_an_unknown_aircraft_is_still_refused(self):
        run_sortie(self.main, self.client)
        r = self.client.post("/api/bearings",
                             json={"callsign": "NOBODY", "bearing_true": 10.0})
        self.assertEqual(r.status_code, 404)

    # ---- X-5 ------------------------------------------------------------
    def test_a_wedged_console_does_not_stall_the_broadcast(self):
        import asyncio

        class Wedged:
            async def send_text(self, _):
                await asyncio.sleep(30)         # never completes

        class Fine:
            def __init__(self):
                self.got = 0

            async def send_text(self, _):
                self.got += 1

        hub = self.main.hub
        wedged, fine = Wedged(), Fine()
        hub.clients = {wedged, fine}
        hub.SEND_TIMEOUT_S = 0.05

        async def go():
            start = asyncio.get_event_loop().time()
            await hub.broadcast({"type": "state"})
            return asyncio.get_event_loop().time() - start

        elapsed = asyncio.run(go())
        self.assertLess(elapsed, 5.0, "broadcast waited on the wedged client")
        self.assertEqual(fine.got, 1, "the healthy console missed the frame")
        self.assertNotIn(wedged, hub.clients, "the wedged client was not dropped")
        self.assertIn(fine, hub.clients, "the healthy client was dropped")

    # ---- X-3 ------------------------------------------------------------
    def test_database_is_in_wal_mode(self):
        import sqlite3
        run_sortie(self.main, self.client)
        c = sqlite3.connect(self.db)
        try:
            self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0].lower(),
                             "wal")
        finally:
            c.close()


class OfflineAssets(unittest.TestCase):
    """F-1: the map views must not need the internet.

    A mission base often has none. Leaflet used to load from unpkg, and when it
    failed the view was not merely map-less: base.js threw on the missing `L`
    before opening its WebSocket, so the status board and bearing log went with
    it. These check the vendored copy is actually reachable at the path the
    pages ask for, and that no remote asset creeps back in.
    """

    VIEWS = ("/", "/base", "/debrief")

    def setUp(self):
        self.main, self.client, self.db = build_app()

    def tearDown(self):
        os.unlink(self.db)

    def test_views_load_no_remote_scripts_or_stylesheets(self):
        import re
        pattern = re.compile(
            r'<(?:script[^>]*\bsrc|link[^>]*\bhref)\s*=\s*"(https?://[^"]+)"',
            re.I)
        for view in self.VIEWS:
            html = self.client.get(view).text
            self.assertEqual(pattern.findall(html), [],
                             f"{view} pulls an asset from the internet")

    def test_vendored_leaflet_is_served(self):
        for asset, sig in (("/static/vendor/leaflet/leaflet.js", b"Leaflet"),
                           ("/static/vendor/leaflet/leaflet.css", b".leaflet")):
            r = self.client.get(asset)
            self.assertEqual(r.status_code, 200, asset)
            self.assertIn(sig, r.content)

    def test_leaflet_css_images_resolve(self):
        """leaflet.css asks for images/ relative to itself; 404s there are the
        classic broken-vendoring symptom."""
        for img in ("marker-icon.png", "marker-shadow.png", "layers.png"):
            r = self.client.get(f"/static/vendor/leaflet/images/{img}")
            self.assertEqual(r.status_code, 200, img)


class F4Backfill(unittest.TestCase):
    """F-4: reconnecting base consoles recover missed persisted traffic."""

    def setUp(self):
        self.main, self.client, self.db = build_app()
        self.sid, self.oid = 'f4scenario', 'f4sortie'
        self.main._exec(
            'INSERT INTO scenarios (id, name, beacon_lat, beacon_lon, effects, created)'
            ' VALUES (?,?,?,?,?,?)',
            (self.sid, 'F-4 test', 33.17, -117.0792, '{}', 900.0))
        self.main._exec(
            'INSERT INTO sorties (id, scenario_id, name, started) VALUES (?,?,?,?)',
            (self.oid, self.sid, 'F-4 test', 900.0))
        self.main.hub.sortie = {
            'id': self.oid, 'scenario_id': self.sid, 'name': 'F-4 test',
            'started': 900.0, 'stopped': None, 'revealed': 0}

    def tearDown(self):
        os.unlink(self.db)

    def test_messages_since_reads_sqlite_instead_of_hub_memory(self):
        for when, body in ((1000.0, 'first'), (1001.0, 'missed')):
            self.main._exec(
                'INSERT INTO messages (sortie_id, t, sender, recipient, body)'
                ' VALUES (?,?,?,?,?)',
                (self.oid, when, 'MISSION BASE', 'ALL', body))
        self.main.hub.messages.clear()

        rows = self.main.list_messages(since=1000.0)
        self.assertEqual([r['body'] for r in rows], ['missed'])
        self.assertEqual(rows[0]['type'], 'message')

    def test_bearings_since_returns_only_missed_rows(self):
        for when, bearing in ((2000.0, 90.0), (2001.0, 120.0)):
            self.main._exec(
                'INSERT INTO bearings (sortie_id, callsign, t, lat, lon,'
                ' bearing_true, note) VALUES (?,?,?,?,?,?,?)',
                (self.oid, 'CAP-1', when, 33.4, -117.1, bearing, ''))

        rows = self.main.list_bearings(since=2000.0)
        self.assertEqual([r['bearing_true'] for r in rows], [120.0])
        self.assertEqual(rows[0]['type'], 'bearing')

    def test_backfill_survives_a_console_restart(self):
        self.main._exec(
            'INSERT INTO messages (sortie_id, t, sender, recipient, body)'
            ' VALUES (?,?,?,?,?)',
            (self.oid, 3000.0, 'MISSION BASE', 'ALL', 'persisted message'))
        self.main._exec(
            'INSERT INTO bearings (sortie_id, callsign, t, lat, lon,'
            ' bearing_true, note) VALUES (?,?,?,?,?,?,?)',
            (self.oid, 'CAP-1', 3000.0, 33.4, -117.1, 275.0, ''))

        main2, client2, _ = build_app(db_path=self.db)
        main2.rehydrate()
        self.assertEqual(main2.list_messages(since=0.0)[-1]['body'],
                         'persisted message')
        self.assertEqual(main2.list_bearings(since=0.0)[-1]['bearing_true'],
                         275.0)

    def test_base_client_backfills_on_every_websocket_open(self):
        source = (Path(__file__).resolve().parents[1] /
                  'services/exercise/app/static/base.js').read_text()
        self.assertIn('/api/messages?since=', source)
        self.assertIn('/api/bearings?since=', source)
        self.assertRegex(source, r'ws\.onopen\s*=.*backfill')


if __name__ == "__main__":
    unittest.main(verbosity=2)
