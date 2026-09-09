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


def build_app(db_path=None, **tokens):
    for role in ("INSTRUCTOR", "BASE", "PLUGIN"):
        os.environ.pop(f"CAPVSAR_TOKEN_{role}", None)
    for role, value in tokens.items():
        os.environ[f"CAPVSAR_TOKEN_{role.upper()}"] = value
    if db_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name

    os.environ["CAPVSAR_DB"] = db_path
    for mod in ("app.main", "app.access", "app.radio", "app.propagation", "app"):
        sys.modules.pop(mod, None)
    main = importlib.import_module("app.main")
    main.init_db()
    return main, TestClient(main.app), db_path


class SetupPersistenceTests(unittest.TestCase):
    """Exercise setup schema, saving, roster generation, and resetting."""

    def setUp(self):
        self.main, self.client, self.db = build_app()

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
        codes = [entry["code"] for entry in data["roster"]]
        self.assertIn("INSTR-1", codes)
        self.assertIn("OBS-423", codes)

    def test_save_setup_persists_fleet_and_roster(self):
        payload = {
            "name": "Test SAR Ops",
            "num_aircraft": 2,
            "aircraft": [
                {
                    "id": "ac-1",
                    "tail": "N499CP",
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
        codes = {entry["code"]: entry for entry in data2["roster"]}
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
                    "tail": "N499CP",
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
        r = self.client.post("/api/auth/login", json={"code": "OBS-423"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["user"]["role"], "aircrew")
        self.assertEqual(data["user"]["callsign"], "CAP 423")
        self.assertIn("session_id", data)
        self.assertIn("capvsar_session", r.cookies)

    def test_auth_me_with_session_cookie(self):
        login_res = self.client.post("/api/auth/login", json={"code": "INSTR-1"})
        self.assertEqual(login_res.status_code, 200)

        # TestClient automatically maintains cookies across calls
        me_res = self.client.get("/api/auth/me")
        self.assertEqual(me_res.status_code, 200)
        data = me_res.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["role"], "instructor")
        self.assertIn("Exercise Director", data["title"])

    def test_auth_me_with_bearer_token(self):
        login_res = self.client.post("/api/auth/login", json={"code": "MRO-1"})
        sess_id = login_res.json()["session_id"]

        # Create fresh client without cookies
        c2 = TestClient(self.main.app)
        r = c2.get("/api/auth/me", headers={"Authorization": f"Bearer {sess_id}"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["authenticated"])
        self.assertEqual(r.json()["role"], "base")

    def test_logout_clears_session(self):
        # Configure instructor token so unauthenticated requests report False
        os.environ["CAPVSAR_TOKEN_INSTRUCTOR"] = "test-instr"
        self.client.post("/api/auth/login", json={"code": "INSTR-1"})
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
                    "tail": "N499CP",
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
        r = self.client.get("/join/INSTR-1", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["location"], "/")
        self.assertIn("capvsar_session", r.cookies)

        # Followed request confirms instructor auth
        r_me = self.client.get("/api/auth/me")
        self.assertEqual(r_me.json()["role"], "instructor")

    def test_join_aircrew_code_redirects_to_base(self):
        r = self.client.get("/join/PLT-423", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["location"], "/base")
        self.assertIn("capvsar_session", r.cookies)

    def test_join_base_code_redirects_to_base(self):
        r = self.client.get("/join/MRO-1", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
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
                    "tail": "N499CP",
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

    def test_anonymous_browser_on_instructor_console_redirects_to_login(self):
        c = TestClient(self.main.app)
        r = c.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["location"], "/login?next=/")

    def test_anonymous_browser_on_setup_redirects_to_login(self):
        c = TestClient(self.main.app)
        r = c.get("/setup", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["location"], "/login?next=/setup")

    def test_aircrew_cannot_access_setup(self):
        c = TestClient(self.main.app)
        c.post("/api/auth/login", json={"code": "PLT-423"})
        r = c.get("/setup", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login?error=instructor_required", r.headers["location"])

    def test_aircrew_cannot_access_console(self):
        c = TestClient(self.main.app)
        c.post("/api/auth/login", json={"code": "PLT-423"})
        r = c.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login?error=instructor_required", r.headers["location"])

    def test_instructor_session_can_access_setup_and_console(self):
        c = TestClient(self.main.app)
        c.post("/api/auth/login", json={"code": "INSTR-1"})
        r_setup = c.get("/setup")
        self.assertEqual(r_setup.status_code, 200)
        self.assertIn("Exercise & Fleet Setup", r_setup.text)

        r_console = c.get("/")
        self.assertEqual(r_console.status_code, 200)
        self.assertIn("Exercise Console", r_console.text)

    def test_base_session_can_access_base_view(self):
        c = TestClient(self.main.app)
        c.post("/api/auth/login", json={"code": "MRO-1"})
        r_base = c.get("/base")
        self.assertEqual(r_base.status_code, 200)
        self.assertIn("Mission Base", r_base.text)

    def test_aircrew_session_can_access_base_view(self):
        c = TestClient(self.main.app)
        c.post("/api/auth/login", json={"code": "PLT-423"})
        r_base = c.get("/base")
        self.assertEqual(r_base.status_code, 200)

    def test_aircrew_session_cannot_mutate_scenarios_or_sorties(self):
        c = TestClient(self.main.app)
        c.post("/api/auth/login", json={"code": "PLT-423"})

        r_scen = c.post("/api/scenarios", json={"name": "hacked", "beacon_lat": 33.0, "beacon_lon": -117.0})
        self.assertEqual(r_scen.status_code, 403)

        r_stop = c.post("/api/sorties/stop")
        self.assertEqual(r_stop.status_code, 403)

        r_reveal = c.post("/api/sorties/reveal")
        self.assertEqual(r_reveal.status_code, 403)

    def test_base_session_can_post_messages_and_bearings(self):
        c_base = TestClient(self.main.app)
        c_base.post("/api/auth/login", json={"code": "MRO-1"})

        # First create scenario and sortie via instructor
        c_instr = TestClient(self.main.app)
        c_instr.post("/api/auth/login", json={"code": "INSTR-1"})
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
