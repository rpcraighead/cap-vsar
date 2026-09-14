"""
Exercise Setup and Role-Based Access Control (RBAC) tests.

Validates:
- Setup configuration and roster persistence
- Participant code generation and authentication (/api/auth/login, /api/auth/me, /api/auth/logout)
- Direct QR code / link join flow (/join/{code})
- Role-gated route enforcement for instructor, base, aircrew, and ground team roles
- Beacon truth containment under session-based RBAC
- Vendored offline asset compliance for setup and login pages
"""
from __future__ import annotations

import importlib
import json
import os
import re
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


def build_app(db_path=None, *, auth_token=None, dev_open=False, **tokens):
    """Build a console app for testing.

    auth_token presents that value as the X-CAPVSAR-Token header on every
    request, which is how a script or an operator authenticates. dev_open
    starts the console in the explicitly-unauthenticated mode X-11 introduced;
    it is cleared otherwise so one test cannot open the console for the next.
    """
    for role in ("INSTRUCTOR", "BASE", "PLUGIN"):
        os.environ.pop(f"CAPVSAR_TOKEN_{role}", None)
    for role, value in tokens.items():
        os.environ[f"CAPVSAR_TOKEN_{role.upper()}"] = value
    os.environ.pop("CAPVSAR_DEV_OPEN", None)
    if dev_open:
        os.environ["CAPVSAR_DEV_OPEN"] = "1"
    if db_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name

    os.environ["CAPVSAR_DB"] = db_path
    # Every app.* module, not a hand-kept list: the console reads its database
    # path and log settings from the environment at import time, so a module
    # left in sys.modules keeps the previous test's database (C15-1 split the
    # console into several of them, and a stale app.settings is invisible
    # until a test mysteriously writes to the wrong file).
    for mod in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        sys.modules.pop(mod, None)
    main = importlib.import_module("app.main")
    main.init_db()
    headers = {"X-CAPVSAR-Token": auth_token} if auth_token else None
    return main, TestClient(main.app, headers=headers, base_url="https://testserver"), db_path


def credential(label):
    from app import access
    return next(row["code"] for row in access.get_roster()
                if row["code"].rsplit("-", 1)[0] == label)


def confirm_badge(client, label):
    url = "/join/" + credential(label)
    page = client.get(url)
    assert page.status_code == 200
    assert "capvsar_session" not in page.cookies
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    return client.post(url, data={"csrf": csrf}, follow_redirects=False)


class SetupPersistenceTests(unittest.TestCase):
    """Exercise setup schema, saving, roster generation, and resetting."""

    def setUp(self):
        # Setup is instructor-gated. These tests used to run with no tokens at
        # all and passed only because enforce() failed open (X-11); they now
        # authenticate the way an operator does.
        self.main, self.client, self.db = build_app(
            instructor="token-instructor", auth_token="token-instructor")

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_default_setup_returns_defaults(self):
        r = self.client.get("/api/setup")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["num_aircraft"], 1)
        self.assertTrue(len(data["config"]["aircraft"]) >= 1)
        # Default database seeds 5 standard roster participants (INSTR-1, PLT-423, OBS-423, MRO-1, UDF-1)
        self.assertEqual(len(data["roster"]), 5)
        codes = [entry["code"].rsplit("-", 1)[0] for entry in data["roster"]]
        self.assertIn("INSTR-1", codes)
        self.assertIn("OBS-423", codes)

    def test_save_setup_persists_fleet_and_roster(self):
        payload = {
            "name": "Test SAR Ops",
            "num_aircraft": 2,
            "aircraft": [
                {
                    "id": "ac-1",
                    "tail": "CAP 487",
                    "callsign": "CAP 423",
                    "df_model": "RHOTHETA RT-600",
                    "crew": ["pilot", "observer", "scanner"]
                },
                {
                    "id": "ac-2",
                    "tail": "N99885",
                    "callsign": "CAP 415",
                    "df_model": "Becker SAR-DF 517",
                    "crew": ["pilot", "observer"]
                }
            ],
            "staff": [
                {"role": "base", "title": "Mission Radio Operator 1", "callsign": "MRO 1"},
                {"role": "base", "title": "Mission Radio Operator 2", "callsign": "MRO 2"},
                {"role": "ground_team", "title": "Ground Search Team 1", "callsign": "UDF 1"}
            ]
        }

        r = self.client.post("/api/setup", json=payload)
        self.assertEqual(r.status_code, 200)
        saved = r.json()
        self.assertEqual(saved["name"], "Test SAR Ops")
        self.assertEqual(saved["num_aircraft"], 2)

        # Expected roster: 1 instructor + (3 ac-1 crew) + (2 ac-2 crew) + (3 staff) = 9
        self.assertEqual(len(saved["roster"]), 9)

        # Verify through GET /api/setup
        r2 = self.client.get("/api/setup")
        self.assertEqual(r2.status_code, 200)
        data2 = r2.json()
        codes = {entry["code"].rsplit("-", 1)[0]: entry for entry in data2["roster"]}
        self.assertIn("INSTR-1", codes)
        self.assertEqual(codes["INSTR-1"]["role"], "instructor")
        self.assertIn("PLT-423", codes)
        self.assertEqual(codes["PLT-423"]["aircraft_id"], "ac-1")
        self.assertIn("OBS-415", codes)
        self.assertEqual(codes["OBS-415"]["aircraft_id"], "ac-2")
        self.assertIn("MRO-1", codes)
        self.assertEqual(codes["MRO-1"]["role"], "base")
        self.assertIn("UDF-3", codes)
        self.assertEqual(codes["UDF-3"]["role"], "ground_team")

    def test_setup_reset_restores_standard_roster(self):
        # First save custom 2-aircraft setup
        self.client.post("/api/setup", json={
            "name": "Custom",
            "num_aircraft": 2,
            "aircraft": [
                {"id": "ac-1", "tail": "N1", "callsign": "CAP 1", "crew": ["pilot"]},
                {"id": "ac-2", "tail": "N2", "callsign": "CAP 2", "crew": ["pilot"]}
            ],
            "staff": []
        })
        r1 = self.client.get("/api/setup")
        self.assertEqual(r1.json()["num_aircraft"], 2)

        # Reset
        reset_resp = self.client.post("/api/setup/reset")
        self.assertEqual(reset_resp.status_code, 200)
        data = reset_resp.json()
        self.assertEqual(data["num_aircraft"], 1)
        # Default has 1 instructor + 3 crew + 2 staff = 6
        self.assertEqual(len(data["roster"]), 6)


class AuthenticationAndSessionTests(unittest.TestCase):
    """Login, session cookies, /api/auth/me, and logout."""

    def setUp(self):
        self.main, self.client, self.db = build_app()
        self.client.post("/api/setup", json={
            "name": "Auth Test",
            "num_aircraft": 1,
            "aircraft": [
                {
                    "id": "ac-1",
                    "tail": "CAP 487",
                    "callsign": "CAP 423",
                    "df_model": "RT-600",
                    "crew": ["pilot", "observer"]
                }
            ],
            "staff": [
                {"role": "base", "title": "Mission Radio Operator 1", "callsign": "MRO 1"}
            ]
        })

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_login_invalid_code_fails(self):
        r = self.client.post("/api/auth/login", json={"code": "INVALID-CODE"})
        self.assertEqual(r.status_code, 401)
        self.assertIn("Invalid participant access code", r.json()["detail"])

    def test_login_valid_code_sets_cookie_and_returns_session(self):
        r = self.client.post("/api/auth/login", json={"code": credential("OBS-423")})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["user"]["role"], "aircrew")
        self.assertEqual(data["user"]["callsign"], "CAP 423")
        self.assertNotIn("session_id", data)
        self.assertIn("Secure", r.headers["set-cookie"])
        self.assertIn("HttpOnly", r.headers["set-cookie"])
        self.assertIn("capvsar_session", r.cookies)

    def test_auth_me_with_session_cookie(self):
        login_res = self.client.post("/api/auth/login", json={"code": credential("INSTR-1")})
        self.assertEqual(login_res.status_code, 200)

        # TestClient automatically maintains cookies across calls
        me_res = self.client.get("/api/auth/me")
        self.assertEqual(me_res.status_code, 200)
        data = me_res.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["role"], "instructor")
        self.assertIn("Exercise Director", data["title"])

    def test_auth_me_with_bearer_token(self):
        login_res = self.client.post("/api/auth/login", json={"code": credential("MRO-1")})
        sess_id = login_res.cookies["capvsar_session"]

        # Create fresh client without cookies
        c2 = TestClient(self.main.app, base_url="https://testserver")
        r = c2.get("/api/auth/me", headers={"Authorization": f"Bearer {sess_id}"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["authenticated"])
        self.assertEqual(r.json()["role"], "base")

    def test_logout_clears_session(self):
        # Configure instructor token so unauthenticated requests report False
        os.environ["CAPVSAR_TOKEN_INSTRUCTOR"] = "test-instr"
        self.client.post("/api/auth/login", json={"code": credential("INSTR-1")})
        self.assertTrue(self.client.get("/api/auth/me").json()["authenticated"])

        logout_res = self.client.post("/api/auth/logout")
        self.assertEqual(logout_res.status_code, 200)

        # After logout, session is gone
        self.assertFalse(self.client.get("/api/auth/me").json()["authenticated"])


class JoinRouteTests(unittest.TestCase):
    """Direct scannable QR code link /join/{code} handling."""

    def setUp(self):
        self.main, self.client, self.db = build_app()
        self.client.post("/api/setup", json={
            "name": "Join Route Test",
            "num_aircraft": 1,
            "aircraft": [
                {
                    "id": "ac-1",
                    "tail": "CAP 487",
                    "callsign": "CAP 423",
                    "df_model": "RT-600",
                    "crew": ["pilot"]
                }
            ],
            "staff": [
                {"role": "base", "title": "Mission Radio Operator 1", "callsign": "MRO 1"}
            ]
        })

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_join_invalid_code_redirects_to_login(self):
        r = self.client.get("/join/NONEXISTENT", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login?error=invalid_code", r.headers["location"])

    def test_join_instructor_code_sets_cookie_and_redirects(self):
        r = confirm_badge(self.client, "INSTR-1")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/")
        self.assertIn("capvsar_session", r.cookies)

        # Followed request confirms instructor auth
        r_me = self.client.get("/api/auth/me")
        self.assertEqual(r_me.json()["role"], "instructor")

    def test_join_aircrew_code_redirects_to_base(self):
        r = confirm_badge(self.client, "PLT-423")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/base")
        self.assertIn("capvsar_session", r.cookies)

    def test_join_base_code_redirects_to_base(self):
        r = confirm_badge(self.client, "MRO-1")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/base")
        self.assertIn("capvsar_session", r.cookies)


class RBACRouteEnforcementTests(unittest.TestCase):
    """RBAC checks across views and mutating API endpoints."""

    def setUp(self):
        self.main, self.client, self.db = build_app(
            instructor="token-instructor",
            base="token-base",
            plugin="token-plugin"
        )
        self.client.post("/api/setup", json={
            "name": "RBAC Test",
            "num_aircraft": 1,
            "aircraft": [
                {
                    "id": "ac-1",
                    "tail": "CAP 487",
                    "callsign": "CAP 423",
                    "df_model": "RT-600",
                    "crew": ["pilot", "observer"]
                }
            ],
            "staff": [
                {"role": "base", "title": "Mission Radio Operator 1", "callsign": "MRO 1"}
            ]
        }, headers={"X-CAPVSAR-Token": "token-instructor"})

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_anonymous_browser_on_portal_redirects_to_login(self):
        c = TestClient(self.main.app, base_url="https://testserver")
        r = c.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["location"], "/login?next=/")

    def test_anonymous_browser_on_setup_redirects_to_login(self):
        c = TestClient(self.main.app, base_url="https://testserver")
        r = c.get("/setup", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["location"], "/login?next=/setup")

    def test_aircrew_cannot_access_setup(self):
        c = TestClient(self.main.app, base_url="https://testserver")
        c.post("/api/auth/login", json={"code": credential("PLT-423")})
        r = c.get("/setup", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login?error=instructor_required", r.headers["location"])

    def test_aircrew_cannot_access_console(self):
        c = TestClient(self.main.app, base_url="https://testserver")
        c.post("/api/auth/login", json={"code": credential("PLT-423")})
        r = c.get("/instructor", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login?error=instructor_required", r.headers["location"])

    def test_instructor_session_can_access_portal_setup_and_console(self):
        c = TestClient(self.main.app, base_url="https://testserver")
        c.post("/api/auth/login", json={"code": credential("INSTR-1")})
        r_setup = c.get("/setup")
        self.assertEqual(r_setup.status_code, 200)
        self.assertIn("Exercise & Fleet Setup", r_setup.text)

        r_portal = c.get("/")
        self.assertEqual(r_portal.status_code, 200)
        self.assertIn('href="/planner/"', r_portal.text)
        self.assertIn('href="/instructor"', r_portal.text)

        r_console = c.get("/instructor")
        self.assertEqual(r_console.status_code, 200)
        self.assertIn("Exercise Console", r_console.text)

    def test_aircrew_portal_lists_only_role_appropriate_stations(self):
        c = TestClient(self.main.app, base_url="https://testserver")
        c.post("/api/auth/login", json={"code": credential("PLT-423")})
        r = c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('href="/planner/"', r.text)
        self.assertIn('href="/base"', r.text)
        self.assertNotIn('href="/instructor"', r.text)
        self.assertNotIn('href="/setup"', r.text)

    def test_base_session_can_access_base_view(self):
        c = TestClient(self.main.app, base_url="https://testserver")
        c.post("/api/auth/login", json={"code": credential("MRO-1")})
        r_base = c.get("/base")
        self.assertEqual(r_base.status_code, 200)
        self.assertIn("Mission Base", r_base.text)

    def test_aircrew_session_can_access_base_view(self):
        c = TestClient(self.main.app, base_url="https://testserver")
        c.post("/api/auth/login", json={"code": credential("PLT-423")})
        r_base = c.get("/base")
        self.assertEqual(r_base.status_code, 200)

    def test_aircrew_session_cannot_mutate_scenarios_or_sorties(self):
        c = TestClient(self.main.app, base_url="https://testserver")
        c.post("/api/auth/login", json={"code": credential("PLT-423")})

        r_scen = c.post("/api/scenarios", json={"name": "hacked", "beacon_lat": 33.0, "beacon_lon": -117.0})
        self.assertEqual(r_scen.status_code, 403)

        r_stop = c.post("/api/sorties/stop")
        self.assertEqual(r_stop.status_code, 403)

        r_reveal = c.post("/api/sorties/reveal")
        self.assertEqual(r_reveal.status_code, 403)

    def test_base_session_can_post_messages_and_bearings(self):
        c_base = TestClient(self.main.app, base_url="https://testserver")
        c_base.post("/api/auth/login", json={"code": credential("MRO-1")})

        # First create scenario and sortie via instructor
        c_instr = TestClient(self.main.app, base_url="https://testserver")
        c_instr.post("/api/auth/login", json={"code": credential("INSTR-1")})
        sc_res = c_instr.post("/api/scenarios", json={
            "name": "Ops Test", "beacon_lat": 33.1, "beacon_lon": -117.1,
            "beacon_elev_ft": 1000.0, "band": "121.5", "power": 1.0
        })
        sid = sc_res.json()["id"]
        c_instr.post("/api/sorties", json={"scenario_id": sid})

        # Post message as base
        r_msg = c_base.post("/api/messages", json={"recipient": "ALL", "body": "Base check"})
        self.assertEqual(r_msg.status_code, 200)


class OfflineAssetComplianceTests(unittest.TestCase):
    """Offline asset compliance on new setup and login views."""

    def setUp(self):
        self.main, self.client, self.db = build_app()

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_setup_and_login_load_no_remote_assets(self):
        pattern = re.compile(
            r'<(?:script[^>]*\bsrc|link[^>]*\bhref)\s*=\s*"(https?://[^"]+)"',
            re.I
        )
        for path in ("/setup", "/login"):
            html = self.client.get(path).text
            remote = pattern.findall(html)
            self.assertEqual(remote, [], f"{path} requests remote assets: {remote}")

    def test_vendored_qrcode_is_served(self):
        r = self.client.get("/static/vendor/qrcode.min.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"QRCode", r.content)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class BackdoorCodeTests(unittest.TestCase):
    """X-10: the literal codes ADMIN and INSTRUCTOR must not mint a session.

    authenticate_code() used to treat those two strings as valid whenever
    CAPVSAR_TOKEN_INSTRUCTOR was set, checking only that the token existed and
    never comparing the caller's input to it. GET /join/ADMIN was therefore an
    unauthenticated URL that produced an Exercise Director session, and since
    instructor satisfies every other role it also defeated the X-1 truth gate.
    """

    def setUp(self):
        self.main, self.client, self.db = build_app(
            instructor="token-instructor",
            base="token-base",
            plugin="token-plugin",
        )
        self.client.post("/api/setup", json={
            "exercise_name": "Backdoor Test",
            "aircraft": [{"tail": "CAP 487", "callsign": "CAP 423",
                          "df_model": "RT-600", "crew": ["pilot"]}],
            "staff": [{"role": "base", "title": "MRO 1", "callsign": "MRO 1"}],
        })

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_join_admin_does_not_create_a_session(self):
        for code in ("ADMIN", "INSTRUCTOR", "admin", "Instructor"):
            with self.subTest(code=code):
                client = type(self.client)(self.main.app)
                r = client.get(f"/join/{code}", follow_redirects=False)
                self.assertEqual(r.status_code, 302, f"{code} should be refused")
                self.assertIn("error=invalid_code", r.headers["location"],
                              f"{code} was accepted as a participant code")
                self.assertNotIn("capvsar_session", r.cookies,
                                 f"{code} minted a session cookie")

    def test_login_with_admin_code_is_rejected(self):
        for code in ("ADMIN", "INSTRUCTOR"):
            with self.subTest(code=code):
                r = self.client.post("/api/auth/login", json={"code": code})
                self.assertEqual(r.status_code, 401,
                                 f"{code} was accepted by /api/auth/login")

    def test_admin_code_cannot_reach_beacon_truth(self):
        """The X-1 gate, exercised through the X-10 path specifically."""
        client = type(self.client)(self.main.app)
        client.get("/join/ADMIN", follow_redirects=False)
        r = client.get("/api/auth/me")
        self.assertNotEqual(r.json().get("role"), "instructor",
                            "ADMIN produced an instructor identity")


class DenyByDefaultTests(unittest.TestCase):
    """X-11: with no tokens configured, the console must not be wide open.

    enforce() used to return - allowing the call - when no token was set for a
    role and no session was active, and /api/auth/me reported an instructor
    identity to anonymous callers in the same state. .env.example ships all
    three tokens blank, so that was the default deployment.
    """

    def setUp(self):
        # No tokens at all: the misconfiguration the old code treated as dev mode.
        self.main, self.client, self.db = build_app()

    def tearDown(self):
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_auth_me_does_not_claim_instructor_when_anonymous(self):
        r = self.client.get("/api/auth/me")
        body = r.json()
        self.assertFalse(body.get("authenticated"),
                         "anonymous caller was reported as authenticated")
        self.assertNotEqual(body.get("role"), "instructor",
                            "anonymous caller was handed an instructor role")

    def test_anonymous_cannot_mutate_with_no_tokens_configured(self):
        r = self.client.post("/api/scenarios", json={
            "name": "unauthorised", "beacon_lat": 33.0, "beacon_lon": -116.0,
        })
        # 503 matches what /api/plugin/scenario already does when its token is
        # missing: the refusal is a misconfigured server, not a forbidden user.
        # What matters is that it is refused rather than silently allowed.
        self.assertIn(r.status_code, (401, 403, 503),
                      "scenario creation succeeded with no auth configured")
        self.assertNotEqual(r.status_code // 100, 2,
                            "scenario creation returned success")

    def test_dev_open_is_deliberate_and_refused_in_production(self):
        """The escape hatch must not be reachable by omission, or in prod."""
        main, client, db = build_app(dev_open=True)
        try:
            r = client.post("/api/scenarios", json={
                "name": "dev", "beacon_lat": 33.0, "beacon_lon": -116.0})
            self.assertEqual(r.status_code // 100, 2,
                             "an explicitly open dev console should allow the call")
            os.environ["CAPVSAR_ENV"] = "production"
            r2 = client.post("/api/scenarios", json={
                "name": "prod", "beacon_lat": 33.0, "beacon_lon": -116.0})
            self.assertNotEqual(r2.status_code // 100, 2,
                                "CAPVSAR_DEV_OPEN was honoured in production")
        finally:
            os.environ.pop("CAPVSAR_ENV", None)
            os.environ.pop("CAPVSAR_DEV_OPEN", None)
            if os.path.exists(db):
                os.unlink(db)


class HardenedCredentialTests(unittest.TestCase):
    def setUp(self):
        self.main, self.client, self.db = build_app()
        from app import access
        self.access = access

    def tearDown(self):
        os.unlink(self.db)

    def test_public_labels_are_not_credentials(self):
        for row in self.access.get_roster():
            label, token = row['code'].rsplit('-', 1)
            self.assertEqual(token, row['token'])
            self.assertRegex(token, r'^[0-9A-F]{32}$')
            self.assertIsNone(self.access.authenticate_code(label))
            self.assertIsNone(self.access.authenticate_code(label + '-' + '0' * 32))
            self.assertIsNotNone(self.access.authenticate_code(row['code'].lower()))

    def test_join_get_is_read_only_and_post_requires_bound_csrf(self):
        url = '/join/' + credential('INSTR-1')
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('capvsar_session', page.cookies)
        self.assertEqual(page.headers['cache-control'], 'no-store')
        with self.access.auth_db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
            self.assertIsNone(db.execute('SELECT last_login FROM roster LIMIT 1').fetchone()[0])
        csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
        for data in ({}, {'csrf': 'bad'}):
            self.assertEqual(self.client.post(url, data=data).status_code, 403)
        other = TestClient(self.main.app, base_url='https://testserver')
        self.assertEqual(other.post(url, data={'csrf': csrf}).status_code, 403)
        self.assertEqual(self.client.post('/join/' + credential('MRO-1'), data={'csrf': csrf}).status_code, 403)
        good = self.client.post(url, data={'csrf': csrf}, follow_redirects=False)
        self.assertEqual(good.status_code, 303)
        self.assertIn('Secure', good.headers['set-cookie'])
        self.assertEqual(self.client.post(url, data={'csrf': csrf}).status_code, 403)

    def test_session_hash_expiry_query_rejection_and_logout(self):
        login = self.client.post('/api/auth/login', json={'code': credential('MRO-1')})
        secret = login.cookies['capvsar_session']
        self.assertNotIn(secret, login.text)
        self.assertNotIn(secret, self.client.get('/api/auth/me').text)
        with self.access.auth_db() as db:
            stored = db.execute('SELECT session_id FROM sessions').fetchone()[0]
        self.assertEqual(stored, self.access._session_hash(secret))
        other = TestClient(self.main.app, base_url='https://testserver')
        self.assertFalse(other.get('/api/auth/me', params={'session': secret}).json()['authenticated'])
        self.assertTrue(other.get('/api/auth/me', headers={'Authorization': 'Bearer ' + secret}).json()['authenticated'])
        self.client.post('/api/auth/logout')
        self.assertFalse(other.get('/api/auth/me', headers={'Authorization': 'Bearer ' + secret}).json()['authenticated'])
        _, secret = self.access.authenticate_code(credential('MRO-1'))
        with self.access.auth_db() as db:
            db.execute('UPDATE sessions SET expires=0')
        self.assertFalse(other.get('/api/auth/me', headers={'Authorization': 'Bearer ' + secret}).json()['authenticated'])
        with self.access.auth_db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)

    def test_roster_regeneration_revokes_old_sessions_and_codes(self):
        old_code = credential('INSTR-1')
        self.client.post('/api/auth/login', json={'code': old_code})
        self.access.save_exercise_setup('Replacement', 0, [], [])
        self.assertFalse(self.client.get('/api/auth/me').json()['authenticated'])
        self.assertIsNone(self.access.authenticate_code(old_code))
        self.assertNotEqual(credential('INSTR-1'), old_code)

    def test_direct_roster_deletion_revokes_sessions(self):
        code = credential('MRO-1')
        self.client.post('/api/auth/login', json={'code': code})
        with self.access.auth_db() as db:
            db.execute('DELETE FROM roster WHERE code=?', (code,))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
        self.assertFalse(self.client.get('/api/auth/me').json()['authenticated'])

    def test_existing_database_migration_revokes_plaintext_sessions(self):
        with self.access.auth_db() as db:
            db.execute("UPDATE roster SET code='INSTR-1', token='old' WHERE role='instructor'")
            db.execute("INSERT INTO sessions(session_id, code, role, title, expires) VALUES ('old-secret', 'INSTR-1', 'instructor', 'Old', 9999999999)")
        self.access.init_auth_db()
        self.assertIsNone(self.access.authenticate_code('INSTR-1'))
        code = credential('INSTR-1')
        self.access.init_auth_db()
        self.assertEqual(credential('INSTR-1'), code)
        with self.access.auth_db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)

    def test_radio_ics_requires_base_or_instructor(self):
        original = self.client.get('/api/radio/ics').json()
        for label in (None, 'PLT-423', 'UDF-1'):
            client = TestClient(self.main.app, base_url='https://testserver')
            if label:
                client.post('/api/auth/login', json={'code': credential(label)})
            self.assertIn(client.post('/api/radio/ics', json={'mode': 'PILOT'}).status_code, (403, 503))
            self.assertEqual(client.get('/api/radio/ics').json(), original)
        for label in ('MRO-1', 'INSTR-1'):
            client = TestClient(self.main.app, base_url='https://testserver')
            client.post('/api/auth/login', json={'code': credential(label)})
            result = client.post('/api/radio/ics', json={'mode': 'CREW'})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['mode'], 'CREW')

    def test_login_page_accepts_full_badge_and_removes_public_shortcuts(self):
        page = self.client.get('/login').text
        self.assertIn('maxlength="128"', page)
        self.assertNotIn('data-code="INSTR-1"', page)
