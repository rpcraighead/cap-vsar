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
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    # Most tests here are about sorties, effects and retention rather than
    # access control, and they called mutating endpoints with no tokens at all.
    # That worked because enforce() used to fail open. X-11 closed that, so the
    # assumption is now stated instead of inherited: a console built with no
    # tokens is explicitly an open dev console. A test that configures any
    # token gets the strict path, which is what the RBAC and truth-containment
    # tests below rely on.
    os.environ.pop("CAPVSAR_DEV_OPEN", None)
    if not tokens:
        os.environ["CAPVSAR_DEV_OPEN"] = "1"

    if db_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name

    class _Tmp:
        name = db_path
    tmp = _Tmp()
    os.environ["CAPVSAR_DB"] = tmp.name
    # Every app.* module, not a hand-kept list: the console reads its database
    # path and log settings from the environment at import time, so a module
    # left in sys.modules keeps the previous test's database (C15-1 split the
    # console into several of them, and a stale app.settings is invisible
    # until a test mysteriously writes to the wrong file).
    for mod in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
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
            run_sortie(main, client, headers={"X-CAPVSAR-Token": INSTRUCTOR})
            r = client.get("/api/plugin/scenario")
            self.assertEqual(r.status_code, 503)
        finally:
            os.unlink(db)

    def test_key_serves_truth_before_reveal(self):
        main, client, db = build_app(plugin=PLUGIN, instructor=INSTRUCTOR)
        try:
            run_sortie(main, client, headers={"X-CAPVSAR-Token": INSTRUCTOR})
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
        main, client, db = build_app(plugin=PLUGIN, instructor=INSTRUCTOR)
        try:
            run_sortie(main, client, headers={"X-CAPVSAR-Token": INSTRUCTOR})
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
        main, client, db = build_app(plugin=PLUGIN, instructor=INSTRUCTOR)
        try:
            run_sortie(main, client, headers={"X-CAPVSAR-Token": INSTRUCTOR})
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


class EffectsBelongToTheSortie(unittest.TestCase):
    """X-6: an effect toggled mid-exercise must not rewrite the scenario.

    set_effects() merged the posted dict straight into the scenario row, so an
    instructor turning terrain masking off for one demonstration changed the
    scenario definition permanently and every future sortie started with
    masking off. Nobody would notice until a later exercise behaved oddly.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "x6.db")
        self.main, self.client, _ = build_app(db_path=self.db)
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _scenario_row_effects(self, sid):
        with self.main.db() as c:
            row = c.execute("SELECT effects FROM scenarios WHERE id=?",
                            (sid,)).fetchone()
        return json.loads(row["effects"] or "{}")

    def test_changing_effects_leaves_the_scenario_row_untouched(self):
        sid, oid = run_sortie(self.main, self.client, headers=self.instr)
        before = self._scenario_row_effects(sid)
        self.assertTrue(before.get("radio_horizon", True))

        r = self.client.post("/api/sorties/effects",
                             json={"radio_horizon": False,
                                   "terrain_masking": False},
                             headers=self.instr)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["radio_horizon"])

        self.assertEqual(self._scenario_row_effects(sid), before,
                         "the scenario definition was rewritten")

    def test_the_change_is_stored_on_the_sortie(self):
        _, oid = run_sortie(self.main, self.client, headers=self.instr)
        self.client.post("/api/sorties/effects", json={"multipath": True},
                         headers=self.instr)
        with self.main.db() as c:
            row = c.execute("SELECT effects FROM sorties WHERE id=?",
                            (oid,)).fetchone()
        self.assertTrue(json.loads(row["effects"])["multipath"])

    def test_a_later_sortie_starts_from_the_scenario_not_the_last_sortie(self):
        sid, _ = run_sortie(self.main, self.client, headers=self.instr)
        self.client.post("/api/sorties/effects", json={"radio_horizon": False},
                         headers=self.instr)
        r = self.client.post("/api/sorties", json={"scenario_id": sid},
                             headers=self.instr)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(self.main.hub.scenario["effects"]["radio_horizon"],
                        "the new sortie inherited the previous one's effects")

    def test_a_resumed_sortie_keeps_the_effects_it_was_flying(self):
        _, oid = run_sortie(self.main, self.client, headers=self.instr)
        self.client.post("/api/sorties/effects", json={"cone_of_confusion": False},
                         headers=self.instr)
        main2, _, _ = build_app(db_path=self.db)
        main2.rehydrate()
        self.assertFalse(main2.hub.scenario["effects"]["cone_of_confusion"])

    def test_an_unknown_effect_is_rejected_rather_than_stored(self):
        run_sortie(self.main, self.client, headers=self.instr)
        r = self.client.post("/api/sorties/effects",
                             json={"radio_hrizon": False},   # typo
                             headers=self.instr)
        self.assertEqual(r.status_code, 422, r.text)

    def test_effects_out_of_range_are_rejected(self):
        run_sortie(self.main, self.client, headers=self.instr)
        r = self.client.post("/api/sorties/effects",
                             json={"multipath_offset_deg": 900.0},
                             headers=self.instr)
        self.assertEqual(r.status_code, 422, r.text)


class InputIsValidated(unittest.TestCase):
    """X-6: coordinates and sortie bodies were accepted unchecked."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.main, self.client, _ = build_app(
            db_path=os.path.join(self.dir, "x6b.db"))
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_out_of_range_beacon_is_refused(self):
        # A transposed lat/lon pair - the commonest way this goes wrong.
        r = self.client.post("/api/scenarios", json={
            "name": "bad", "beacon_lat": -117.2, "beacon_lon": 33.1,
        }, headers=self.instr)
        self.assertEqual(r.status_code, 422, r.text)

    def test_a_sortie_needs_a_scenario_id(self):
        r = self.client.post("/api/sorties", json={}, headers=self.instr)
        self.assertEqual(r.status_code, 422, r.text)


class OperationalHygiene(unittest.TestCase):
    """X-8: retention, pagination, and a healthcheck that means something."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "x8.db")
        self.main, self.client, _ = build_app(db_path=self.db)
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_track_pages_instead_of_returning_everything(self):
        _, oid = run_sortie(self.main, self.client, headers=self.instr)
        with self.main.db() as c:
            for i in range(25):
                c.execute("INSERT INTO positions (sortie_id, callsign, t, lat,"
                          " lon, alt_ft, hdg_true) VALUES (?,?,?,?,?,?,?)",
                          (oid, "CAP-1", 1000.0 + i, 33.0, -117.0, 5500.0, 90.0))
        first = self.client.get(f"/api/sorties/{oid}/track?limit=10").json()
        self.assertEqual(len(first["positions"]), 10)
        self.assertIsNotNone(first["next_since"])
        second = self.client.get(
            f"/api/sorties/{oid}/track?limit=10&since={first['next_since']}").json()
        self.assertEqual(len(second["positions"]), 10)
        self.assertGreater(second["positions"][0]["t"],
                           first["positions"][-1]["t"])
        last = self.client.get(
            f"/api/sorties/{oid}/track?limit=10&since={second['next_since']}").json()
        self.assertEqual(len(last["positions"]), 5)
        self.assertIsNone(last["next_since"], "a short page is the last page")

    def test_track_without_paging_arguments_still_works(self):
        _, oid = run_sortie(self.main, self.client, headers=self.instr)
        r = self.client.get(f"/api/sorties/{oid}/track")
        self.assertEqual(r.status_code, 200)
        self.assertIn("positions", r.json())

    def test_retention_drops_old_positions_but_keeps_the_written_record(self):
        _, old_oid = run_sortie(self.main, self.client, headers=self.instr)
        with self.main.db() as c:
            c.execute("INSERT INTO positions (sortie_id, callsign, t, lat,"
                          " lon, alt_ft, hdg_true) VALUES (?,?,?,?,?,?,?)",
                      (old_oid, "CAP-1", 1.0, 33.0, -117.0, 5500.0, 90.0))
            c.execute("INSERT INTO messages (sortie_id, t, sender, recipient,"
                      " body) VALUES (?,?,?,?,?)",
                      (old_oid, 1.0, "BASE", "CAP-1", "keep me"))
        # The retention window lives in app.settings and is read at call time
        # (C15-1), so that is where a test narrows it.
        settings = sys.modules["app.settings"]
        original = settings.POSITION_RETENTION_SORTIES
        settings.POSITION_RETENTION_SORTIES = 1
        try:
            # A newer sortie pushes the old one out of the window.
            run_sortie(self.main, self.client, headers=self.instr)
            self.main.prune_positions()
        finally:
            settings.POSITION_RETENTION_SORTIES = original
        with self.main.db() as c:
            pos = c.execute("SELECT COUNT(*) n FROM positions WHERE sortie_id=?",
                            (old_oid,)).fetchone()["n"]
            msg = c.execute("SELECT COUNT(*) n FROM messages WHERE sortie_id=?",
                            (old_oid,)).fetchone()["n"]
        self.assertEqual(pos, 0, "old positions were not pruned")
        self.assertEqual(msg, 1, "the written record must survive retention")

    def test_health_reports_the_database(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(r.json()["db"], "ok")

    def test_health_fails_when_the_database_is_unusable(self):
        system = sys.modules["app.routers.system"]
        with patch.object(system, "db",
                          side_effect=sqlite3.OperationalError("unable to open")):
            r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 503)
        self.assertFalse(r.json()["ok"])
        self.assertIn("OperationalError", r.json()["db"])

    def test_the_container_does_not_run_as_root(self):
        dockerfile = (Path(__file__).resolve().parents[1] /
                      "services/exercise/Dockerfile").read_text()
        self.assertRegex(dockerfile, r"(?m)^USER\s+capvsar")
        self.assertIn("useradd", dockerfile)

    def test_the_ticker_is_cancelled_on_shutdown(self):
        source = (Path(__file__).resolve().parents[1] /
                  "services/exercise/app/main.py").read_text()
        self.assertIn("task.cancel()", source)


class Form110OnTheMumbleConsole(unittest.TestCase):
    """F-9: the CAPF-110 log existed only on the retired /radio-legacy page,
    so the console the MRO actually uses could not produce the one document
    the role exists to produce."""

    @classmethod
    def setUpClass(cls):
        static = Path(__file__).resolve().parents[1] / "services/exercise/app/static"
        cls.js = (static / "mission-radio.js").read_text()
        cls.html = (static / "mission-radio.html").read_text()
        cls.legacy = (static / "radio.js").read_text()

    def test_the_log_exists_on_the_new_console(self):
        self.assertIn("commLogBody", self.html)
        self.assertIn("CAP FORM 110", self.html)
        for fn in ("function logEntry", "function renderLog", "function exportLog"):
            self.assertIn(fn, self.js, fn)

    def test_transmissions_are_logged_automatically(self):
        self.assertIn("state.txStarted", self.js)
        self.assertIn("outgoing:true", self.js)
        # ...and received traffic, once per transmission rather than per packet.
        self.assertIn("state.lastLogged", self.js)

    def test_the_export_has_a_date_column(self):
        """The legacy export had time only, so a sortie through 0000Z read as
        though it went backwards."""
        self.assertIn("'DATE'", self.js)
        self.assertIn("slice(0, 10)", self.js)

    def test_the_export_truncates_rather_than_only_padding(self):
        """padEnd does not truncate: one long callsign pushed every column
        after it out of line for the rest of the page."""
        self.assertIn("function pad(", self.js)
        self.assertIn("slice(0, width - 1)", self.js)
        self.assertIn(".padEnd(width", self.js)

    def test_the_blob_url_is_revoked(self):
        self.assertIn("revokeObjectURL", self.js,
                      "every export leaked its blob for the life of the page")

    def test_the_log_never_uses_innerhtml_for_traffic(self):
        """F-6 was the same class of bug in four other views, now escaped in
        ServerStringsAreEscaped. The log must not reintroduce it."""
        body = self.js[self.js.index("function renderLog"):
                       self.js.index("function pad(")]
        self.assertNotIn("innerHTML +=", body)
        self.assertIn("textContent", body)

    def test_typing_in_the_log_does_not_key_the_transmitter(self):
        """The log cells are contenteditable and Space is the PTT key."""
        self.assertIn("[contenteditable]", self.js)


class LegacyConsoleAudio(unittest.TestCase):
    """F-7: two bugs in /radio-legacy, which is still routed."""

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "services/exercise/app/static/radio.js").read_text()
        cls.main = (root / "services/exercise/app/main.py").read_text()

    def test_sender_precedence_no_longer_throws_on_an_absent_sender(self):
        """`a && b || c` parsed as `(a && b) || c`, so an undefined sender
        fell through to c and dereferenced it."""
        self.assertNotIn("if (msg.sender && msg.sender.startsWith('BASE (APX') || "
                         "msg.sender.startsWith('BASE (IC-A'))", self.js)
        self.assertIn("msg.sender && (msg.sender.startsWith('BASE (APX') ||", self.js)

    def test_audio_is_armed_by_a_gesture_not_by_incoming_traffic(self):
        self.assertIn("arm()", self.js)
        self.assertIn("this.armed", self.js)
        # The playback path must not create or resume a context on its own.
        ensure = self.js[self.js.index("  ensureContext()"):
                         self.js.index("  // Motorola P25")]
        self.assertNotIn("new AudioCtx()", ensure)
        self.assertNotIn("resume()", ensure)

    def test_speech_is_gated_too(self):
        speak = self.js[self.js.index("  speak(text, onEnd)"):]
        self.assertIn("this.armed", speak[:600])

    def test_the_legacy_console_is_still_routed(self):
        """F-7 would close with /radio-legacy if it were retired. It is not:
        the airband station it carries has no replacement until F-10."""
        main, client, _ = build_app()
        paths = {getattr(r, "path", None) for r in main.app.routes}
        self.assertIn("/radio-legacy", paths)


class TheConsoleIsSplitUp(unittest.TestCase):
    """C15-1: main.py held the schema, the migrations, the truth filter, the
    role checks, the hub, the retention policy and every route on one page.
    X-3 happened in there, and the CalTopo relay and the IC/AOBD views had
    nowhere obvious to land."""

    APP = Path(__file__).resolve().parents[1] / "services/exercise/app"

    def test_main_is_assembly_not_implementation(self):
        main_src = (self.APP / "main.py").read_text()
        self.assertLess(len(main_src.splitlines()), 260,
                        "main.py is growing back into a monolith")
        # Assembly wires routers up; it does not define routes itself.
        self.assertNotIn("@app.get(", main_src)
        self.assertNotIn("@app.post(", main_src)
        self.assertIn("include_router", main_src)

    def test_the_pieces_exist_and_each_does_one_thing(self):
        for name in ("settings.py", "store.py", "roles.py", "hub.py",
                     "models.py", "geo.py"):
            self.assertTrue((self.APP / name).exists(), name)
        for name in ("scenarios", "sorties", "telemetry", "comms", "system",
                     "auth", "pages"):
            self.assertTrue((self.APP / "routers" / f"{name}.py").exists(), name)

    def test_only_the_store_talks_to_sqlite(self):
        """A route that opens its own connection is how the schema ended up
        spread across a thousand lines in the first place."""
        for path in sorted((self.APP / "routers").glob("*.py")):
            src = path.read_text()
            self.assertNotIn("sqlite3.connect", src, path.name)
            self.assertNotIn("CREATE TABLE", src, path.name)

    def test_the_routes_all_survived_the_split(self):
        """The split must not have dropped an endpoint on the floor."""
        main, _, _ = build_app()
        paths = {getattr(r, "path", None) for r in main.app.routes}
        for path in ("/api/scenarios", "/api/sorties", "/api/sorties/stop",
                     "/api/sorties/reveal", "/api/sorties/effects",
                     "/api/sorties/{oid}/track", "/api/positions",
                     "/api/bearings", "/api/messages", "/api/state",
                     "/api/plugin/scenario", "/api/health", "/api/tile-sources",
                     "/ws", "/login", "/api/auth/login", "/api/auth/me",
                     "/api/auth/logout", "/join/{code}", "/setup", "/api/setup",
                     "/api/setup/reset", "/", "/debrief", "/base", "/radio",
                     "/radio-legacy", "/radio-ca.crt"):
            self.assertIn(path, paths, f"{path} was lost in the split")

    def test_the_names_other_code_imports_still_resolve(self):
        main, _, _ = build_app()
        for name in ("app", "hub", "db", "db_call", "init_db", "rehydrate",
                     "prune_positions", "list_messages", "list_bearings"):
            self.assertTrue(hasattr(main, name), f"app.main.{name} disappeared")


class ServerStringsAreEscaped(unittest.TestCase):
    """F-6: message bodies, senders, bearing notes and callsigns reached
    innerHTML unescaped, and any LAN client can POST all of them. Nothing
    escapes them server-side, so the views must.

    Only values that actually flow into an HTML sink are checked. The same
    fields are used all over these files as object keys and dedup strings,
    where markup is inert.
    """

    VIEWS = ("base.js", "app.js", "debrief.js", "radio.js", "setup.js")
    # Server-controlled string fields. Numbers reach HTML through toFixed()
    # or Math.round(), neither of which can carry markup.
    TAINTED = ("body", "sender", "recipient", "note", "callsign", "name",
               "alert_text", "alert_kind", "id", "points", "distance_nm",
               "channel", "title", "code", "role", "target_url", "tail")
    # A read is safe when wrapped in esc(...) or used as a truthiness test.
    READ = re.compile(r"((?:esc|escapeHtml)\(\s*)?\b[A-Za-z_$][\w$]*(?:\.[\w$]+)*\."
                      r"(" + "|".join(TAINTED) + r")\b(\s*\?)?")
    # bindTooltip renders a string as HTML, so it is an innerHTML sink too.
    SINK = re.compile(r"\.innerHTML\s*\+?=|bindTooltip\(")

    @classmethod
    def setUpClass(cls):
        static = Path(__file__).resolve().parents[1] / "services/exercise/app/static"
        cls.src = {name: (static / name).read_text() for name in cls.VIEWS}

    @classmethod
    def _sink_statements(cls, src):
        """Yield the text of each statement that writes HTML."""
        for m in cls.SINK.finditer(src):
            i, depth = m.end(), 0
            while i < len(src):
                c = src[i]
                if c in "([{":
                    depth += 1
                elif c in ")]}":
                    if depth == 0 and c == ")":
                        break
                    depth -= 1
                elif c == ";" and depth == 0:
                    break
                elif c == "`":
                    i += 1
                    while i < len(src) and src[i] != "`":
                        if src[i] == "\\":
                            i += 1
                        elif src[i:i + 2] == "${":
                            d2 = 0
                            i += 2
                            while i < len(src):
                                if src[i] == "{":
                                    d2 += 1
                                elif src[i] == "}":
                                    if d2 == 0:
                                        break
                                    d2 -= 1
                                i += 1
                        i += 1
                i += 1
            yield src[m.start():i]

    @classmethod
    def _unescaped(cls, src):
        found = []
        for stmt in cls._sink_statements(src):
            for r in cls.READ.finditer(stmt):
                if r.group(1) or r.group(3):
                    continue
                found.append(r.group(0).strip())
        return found

    def test_every_view_defines_an_escape_helper(self):
        for name, src in self.src.items():
            with self.subTest(view=name):
                self.assertTrue("const esc =" in src or "function escapeHtml" in src,
                                f"{name} has no escape helper")
                # The quote matters: two setup.js values sit in attributes.
                for entity in ("&amp;", "&lt;", "&gt;", "&quot;"):
                    self.assertIn(entity, src, f"{name} does not produce {entity}")

    def test_the_shared_helper_also_escapes_the_apostrophe(self):
        for name, src in self.src.items():
            if "const esc =" not in src:
                continue  # radio.js predates the shared helper
            with self.subTest(view=name):
                self.assertIn("&#39;", src)

    def test_no_tainted_field_reaches_an_html_sink_unescaped(self):
        for name, src in self.src.items():
            with self.subTest(view=name):
                raw = self._unescaped(src)
                self.assertEqual(raw, [], f"{name} writes {raw} into HTML unescaped")

    def test_the_check_would_notice_a_regression(self):
        """A detector that cannot fail is worth nothing, so prove it fails."""
        src = self.src["base.js"]
        for original, reverted in (
            ("${esc(x.body)}", "${x.body}"),
            ("bindTooltip(esc(a.callsign)", "bindTooltip(a.callsign"),
            ("+ esc(b.note)", "+ b.note"),
        ):
            with self.subTest(reverted=reverted):
                self.assertIn(original, src, "the fix this test guards has moved")
                self.assertNotEqual([], self._unescaped(src.replace(original, reverted)))


class BearingInteractionPolicy(unittest.TestCase):
    """F-8 review: execute the browser's state decisions under Node."""

    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).resolve().parents[1] /
                      "services/exercise/app/static/base.js").read_text()

    def run_policy(self, expression):
        import subprocess
        start = self.source.index("// BEGIN F-8 BEARING UI POLICY")
        end = self.source.index("// END F-8 BEARING UI POLICY")
        script = self.source[start:end] + \
            f"\nconsole.log(JSON.stringify({expression}));"
        result = subprocess.run(["node", "-e", script], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_callsign_refresh_preserves_the_operator_selection(self):
        current = self.run_policy(
            "(() => { const m=bearingCallsignModel("
            "[{callsign:'CAP-2'},{callsign:'CAP-1'}],'CAP-2');"
            "return {model:m,rebuild:bearingCallsignNeedsRebuild("
            "[{value:'CAP-1',stale:false},{value:'CAP-2',stale:false}],m)}; })()")
        self.assertEqual(current["model"]["selected"], "CAP-2")
        self.assertFalse(current["model"]["stale"])
        self.assertFalse(current["rebuild"],
                         "an unchanged callsign set would collapse an open selector")

        stale = self.run_policy(
            "bearingCallsignModel([{callsign:'CAP-1'}],'CAP-2')")
        self.assertEqual(stale["selected"], "CAP-2")
        self.assertTrue(stale["stale"])
        self.assertEqual(stale["options"], [
            {"value": "CAP-1", "stale": False},
            {"value": "CAP-2", "stale": True},
        ])

    def test_confidence_cut_uses_only_three_latest_bearings_per_aircraft(self):
        rows = "[" + ",".join(
            f"{{callsign:'{callsign}',bearing_true:{bearing}}}"
            for callsign, bearing in (
                ("A", 40), ("A", 30), ("A", 20), ("A", 10),
                ("B", 60), ("B", 50),
            )) + "]"
        result = self.run_policy(
            f"recentBearingsForCut({rows}).map(x=>[x.callsign,x.bearing_true])")
        self.assertEqual(result, [["A", 40], ["A", 30], ["A", 20],
                                  ["B", 60], ["B", 50]])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class InputBounds(unittest.TestCase):
    """FE-8: every request body reached the database unvalidated.

    The one that bit hardest: Pydantic v2 accepts NaN for a float by default
    and Starlette's JSON parser accepts the bare `NaN` literal, so a NaN
    bearing was stored - SQLite writes it as NULL - and base.js then threw on
    `b.bearing_true.toFixed(0)`. Because a reconnecting console replays the
    bearing log, that one row killed the log for the rest of the sortie.
    """

    def setUp(self):
        self.main, self.client, self.db = build_app(
            instructor=INSTRUCTOR, base=BASE, plugin=PLUGIN)
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}
        self.base = {"X-CAPVSAR-Token": BASE}
        self.plug = {"X-CAPVSAR-Token": PLUGIN}
        run_sortie(self.main, self.client, headers=self.instr)
        self.client.post("/api/positions", headers=self.plug, json={
            "callsign": "CAP-1", "lat": 33.1, "lon": -117.2,
            "alt_ft": 5500.0, "hdg_true": 90.0})

    def tearDown(self):
        os.unlink(self.db)

    def post_bearing(self, **kw):
        body = {"callsign": "CAP-1", "bearing_true": 45.0}
        body.update(kw)
        return self.client.post("/api/bearings", json=body, headers=self.base)

    def test_a_nan_bearing_is_refused(self):
        # Sent as raw bytes: `NaN` is not valid JSON, but Python's json module
        # (and therefore Starlette) accepts the literal, which is how it ever
        # reached the model.
        r = self.client.post(
            "/api/bearings",
            headers={**self.base, "content-type": "application/json"},
            content=b'{"callsign":"CAP-1","bearing_true":NaN}')
        self.assertEqual(r.status_code, 422, "a NaN bearing was accepted")
        self.assertEqual(self.client.get("/api/bearings", headers=self.base).json(), [],
                         "a NaN bearing reached the log and will break it on replay")

    def test_out_of_range_bearings_are_refused(self):
        # A compass bearing is [0, 360). 360 is 0 and belongs to the next lap.
        for value in (360.0, -1.0, 720.0):
            with self.subTest(bearing=value):
                self.assertEqual(self.post_bearing(bearing_true=value).status_code, 422)

    def test_an_infinite_bearing_is_refused(self):
        # Raw bytes again: httpx will not serialise Infinity either, so this
        # can only be sent the way a hand-rolled client would send it.
        r = self.client.post(
            "/api/bearings",
            headers={**self.base, "content-type": "application/json"},
            content=b'{"callsign":"CAP-1","bearing_true":Infinity}')
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.client.get("/api/bearings", headers=self.base).json(), [])

    def test_a_normal_bearing_still_works(self):
        self.assertEqual(self.post_bearing(bearing_true=359.9).status_code, 200)

    def test_position_bounds(self):
        bad = [{"lat": 91.0}, {"lat": -91.0}, {"lon": 181.0}, {"hdg_true": 360.0},
               {"hdg_true": -1.0}, {"alt_ft": 100000.0}, {"callsign": "x"},
               {"callsign": "no/slashes"}]
        for override in bad:
            with self.subTest(**override):
                body = {"callsign": "CAP-1", "lat": 33.0, "lon": -117.0,
                        "alt_ft": 5000.0, "hdg_true": 10.0}
                body.update(override)
                r = self.client.post("/api/positions", json=body, headers=self.plug)
                self.assertEqual(r.status_code, 422, f"accepted {override}")

    def test_oversized_text_is_refused(self):
        self.assertEqual(self.post_bearing(note="x" * 501).status_code, 422)
        self.assertEqual(self.client.post(
            "/api/messages", json={"body": "y" * 2001}, headers=self.base).status_code, 422)
        self.assertEqual(self.client.post(
            "/api/messages", json={"body": ""}, headers=self.base).status_code, 422)

    def test_a_base_caller_cannot_sign_a_message_as_the_instructor(self):
        r = self.client.post("/api/messages", headers=self.base,
                             json={"body": "all aircraft return", "sender": "INSTRUCTOR"})
        self.assertEqual(r.status_code, 200)
        sent = self.client.get("/api/messages", headers=self.base).json()[-1]
        self.assertNotEqual(sent["sender"], "INSTRUCTOR",
                            "a base client signed a message as the instructor")


class BeaconChannel(unittest.TestCase):
    """B-5: a 406 scenario has to be able to name the exact channel.

    Without it the engine assumes 406.025, which a Becker in Emergency mode
    always hears - so the Becker-vs-RT-600 coverage difference, the reason both
    heads exist, could not be staged from the console at all.
    """

    def setUp(self):
        self.main, self.client, self.db = build_app(instructor=INSTRUCTOR, plugin=PLUGIN)
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}

    def tearDown(self):
        os.unlink(self.db)

    def make(self, **kw):
        body = {"name": "chan", "beacon_lat": 33.0, "beacon_lon": -117.0,
                "band": "406"}
        body.update(kw)
        return self.client.post("/api/scenarios", json=body, headers=self.instr)

    def test_a_channel_on_the_grid_is_accepted_and_kept(self):
        r = self.make(beacon_freq_hz=406_037_000)
        self.assertEqual(r.status_code, 200, r.text)
        row = [s for s in self.client.get("/api/scenarios", headers=self.instr).json()
               if s["id"] == r.json()["id"]][0]
        self.assertEqual(row["beacon_freq_hz"], 406_037_000)

    def test_off_grid_channels_are_refused(self):
        for hz in (406_038_000, 406_021_000, 406_079_000):
            with self.subTest(hz=hz):
                self.assertEqual(self.make(beacon_freq_hz=hz).status_code, 422)

    def test_the_frequency_must_match_the_band(self):
        self.assertEqual(self.make(band="121.5", beacon_freq_hz=406_037_000).status_code, 422)
        self.assertEqual(self.make(band="121.5", beacon_freq_hz=121_500_000).status_code, 200)

    def test_it_is_optional(self):
        self.assertEqual(self.make().status_code, 200)

    def test_the_plugin_receives_it(self):
        sid = self.make(beacon_freq_hz=406_037_000).json()["id"]
        self.client.post("/api/sorties", json={"scenario_id": sid}, headers=self.instr)
        body = self.client.get("/api/plugin/scenario",
                               headers={"X-CAPVSAR-Token": PLUGIN}).json()
        self.assertEqual(body["scenario"]["beacon_freq_hz"], 406_037_000)


class DFTelemetryIsRecorded(unittest.TestCase):
    """V2-5: the track held where the aircraft was, never what the DF showed."""

    def setUp(self):
        self.main, self.client, self.db = build_app(
            instructor=INSTRUCTOR, base=BASE, plugin=PLUGIN)
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}
        self.plug = {"X-CAPVSAR-Token": PLUGIN}

    def tearDown(self):
        os.unlink(self.db)

    def report(self):
        self.client.post("/api/positions", headers=self.plug, json={
            "callsign": "CAP-1", "lat": 33.1, "lon": -117.2, "alt_ft": 5500.0,
            "hdg_true": 90.0,
            "df": {"valid": True, "bearing_rel": 12.5, "bearing_true": 102.5,
                   "signal": 0.42, "distance_nm": 9.2, "in_cone": False}})

    def test_it_is_stored_and_returned_after_reveal(self):
        _, oid = run_sortie(self.main, self.client, reveal=True, headers=self.instr)
        self.report()
        track = self.client.get(f"/api/sorties/{oid}/track", headers=self.instr).json()
        self.assertTrue(track["positions"], "no positions recorded")
        self.assertEqual(track["positions"][-1]["df"]["bearing_true"], 102.5)

    def test_it_is_withheld_before_reveal(self):
        _, oid = run_sortie(self.main, self.client, headers=self.instr)
        self.report()
        track = self.client.get(f"/api/sorties/{oid}/track").json()
        self.assertTrue(track["positions"])
        # bearing_true + distance_nm from a known position IS the beacon.
        for point in track["positions"]:
            self.assertNotIn("df", point, "DF telemetry leaked before reveal")
        self.assertIsNone(track["beacon"])


class ConnectionPragmas(unittest.TestCase):
    """FE-9: `synchronous` is per-connection; only journal_mode persists."""

    def setUp(self):
        self.main, self.client, self.db = build_app()

    def tearDown(self):
        os.unlink(self.db)

    def test_every_connection_is_wal_and_normal(self):
        with self.main.db() as c:
            self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(c.execute("PRAGMA synchronous").fetchone()[0], 1,
                             "connection reverted to FULL: every commit fsyncs")
