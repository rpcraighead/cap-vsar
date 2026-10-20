"""
Sign in with Google / OpenID Connect, with seats assigned by email (T19).

Runs offline: a fake provider in this file generates an RSA key, serves the
discovery document, the JWKS and the token endpoint through the two HTTP seams
in app/oidc.py (`fetch_json`, `post_form`), and signs ID tokens itself. The
badge-code path is exercised alongside to show both doors mint the same session.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_setup_auth import build_app, credential  # noqa: E402

ISSUER = "https://accounts.google.com"
CLIENT_ID = "123-test.apps.googleusercontent.com"
CLIENT_SECRET = "s3cret-" + "x" * 24
BASE = "https://testserver"
OIDC_ENV = {"CAPVSAR_OIDC_ISSUER": ISSUER, "CAPVSAR_OIDC_CLIENT_ID": CLIENT_ID,
            "CAPVSAR_OIDC_CLIENT_SECRET": CLIENT_SECRET, "CAPVSAR_OIDC_REDIRECT_BASE": BASE}
INSTRUCTOR_TOKEN = "instructor-token-" + "t" * 16


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class FakeProvider:
    """Just enough of an OpenID provider: discovery, JWKS, a code store and a
    token endpoint that enforces PKCE S256, the redirect URI, the client
    secret and single-use codes."""

    def __init__(self, issuer=ISSUER):
        self.issuer = issuer
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "kid-2026"
        self.codes: dict[str, dict] = {}
        self.token_requests: list[dict] = []
        self.fetches: list[str] = []

    def pem(self, key=None):
        return (key or self.key).private_bytes(serialization.Encoding.PEM,
                                               serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption())

    def jwks(self):
        numbers = self.key.public_key().public_numbers()
        def enc(n):
            return _b64(n.to_bytes((n.bit_length() + 7) // 8, "big"))
        return {"keys": [{"kty": "RSA", "kid": self.kid, "use": "sig", "alg": "RS256",
                          "n": enc(numbers.n), "e": enc(numbers.e)}]}

    def discovery(self):
        return {"issuer": self.issuer,
                "authorization_endpoint": self.issuer + "/o/oauth2/v2/auth",
                "token_endpoint": self.issuer + "/token",
                "jwks_uri": self.issuer + "/jwks"}

    # --- the two seams -------------------------------------------------
    def fetch_json(self, url):
        self.fetches.append(url)
        if url.endswith("/.well-known/openid-configuration"):
            return self.discovery()
        if url.endswith("/jwks"):
            return self.jwks()
        raise AssertionError("unexpected fetch " + url)

    def post_form(self, url, data, auth=None):
        from app import oidc
        self.token_requests.append(dict(data))
        assert url == self.issuer + "/token", url
        entry = self.codes.pop(data.get("code"), None)
        if entry is None:
            raise oidc.OIDCError("invalid_grant")
        if (data.get("client_secret") != CLIENT_SECRET or data.get("client_id") != CLIENT_ID
                or data.get("redirect_uri") != entry["redirect_uri"]
                or data.get("grant_type") != "authorization_code"):
            raise oidc.OIDCError("invalid_client")
        verifier = data.get("code_verifier", "")
        if _b64(hashlib.sha256(verifier.encode()).digest()) != entry["challenge"]:
            raise oidc.OIDCError("invalid_grant: PKCE")
        return {"access_token": "at-" + os.urandom(4).hex(), "token_type": "Bearer",
                "id_token": self.id_token(entry["nonce"], **entry["token"])}

    # --- the browser's side of the round trip ----------------------------
    def authorize(self, location: str, email: str, **token_overrides) -> tuple[str, str]:
        """What the provider does after the user consents: records the request
        and hands back (code, state) for the redirect to the callback."""
        parts = urlsplit(location)
        assert parts.scheme + "://" + parts.netloc + parts.path == self.discovery()["authorization_endpoint"]
        q = {k: v[0] for k, v in parse_qs(parts.query).items()}
        assert q["response_type"] == "code" and q["client_id"] == CLIENT_ID
        assert q["code_challenge_method"] == "S256" and "openid" in q["scope"].split()
        code = "code-" + os.urandom(8).hex()
        self.codes[code] = {"nonce": q["nonce"], "challenge": q["code_challenge"],
                            "redirect_uri": q["redirect_uri"],
                            "token": {"email": email, **token_overrides}}
        return code, q["state"]

    def id_token(self, nonce, email, *, email_verified=True, aud=CLIENT_ID, iss=None,
                 exp_offset=600, key=None, nonce_override=None, extra=None):
        now = int(time.time())
        claims = {"iss": iss or self.issuer, "aud": aud, "sub": "sub-" + hashlib.sha1(email.encode()).hexdigest()[:12],
                  "email": email, "email_verified": email_verified, "iat": now, "exp": now + exp_offset,
                  "nonce": nonce_override if nonce_override is not None else nonce}
        claims.update(extra or {})
        return jwt.encode(claims, self.pem(key), algorithm="RS256", headers={"kid": self.kid})


class OIDCBase(unittest.TestCase):
    def setUp(self):
        for key, value in OIDC_ENV.items():
            os.environ[key] = value
        for key in ("CAPVSAR_OIDC_HD", "CAPVSAR_OIDC_DIRECTOR_EMAILS", "CAPVSAR_OIDC_LABEL",
                    "CAPVSAR_SESSION_LIFETIME_S", "CAPVSAR_TRUST_PROXY"):
            os.environ.pop(key, None)
        self.main, self.client, self.db = build_app(instructor=INSTRUCTOR_TOKEN)
        from app import access, oidc
        self.access, self.oidc = access, oidc
        self.provider = FakeProvider()
        self.real_fetch_json, self.real_post_form = oidc.fetch_json, oidc.post_form
        oidc.fetch_json = self.provider.fetch_json
        oidc.post_form = self.provider.post_form
        oidc.forget_cached_metadata()
        oidc.consumed_states.clear()
        oidc.failures.clear()
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR_TOKEN}

    def tearDown(self):
        for key in list(OIDC_ENV) + ["CAPVSAR_OIDC_HD", "CAPVSAR_OIDC_DIRECTOR_EMAILS",
                                      "CAPVSAR_SESSION_LIFETIME_S", "CAPVSAR_TRUST_PROXY"]:
            os.environ.pop(key, None)
        os.unlink(self.db)

    # helpers -----------------------------------------------------------
    def setup_with_emails(self, *, mro="mro@example.org", observer="m.observer@example.org",
                          director=None, headers=None):
        body = {"name": "SAREX 2026-10", "director_email": director,
                "aircraft": [{"id": "ac-1", "callsign": "CAP 487", "crew": ["pilot", "observer"],
                              "emails": {"observer": observer}}],
                "staff": [{"role": "base", "title": "Mission Radio Operator 1", "callsign": "MRO 1", "email": mro},
                          {"role": "ground_team", "title": "Ground Team / UDF 1 Leader", "callsign": "UDF 1"}]}
        r = self.client.post("/api/setup", json=body, headers=headers or self.instr)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def fresh_client(self):
        return TestClient(self.main.app, base_url=BASE)

    def start(self, client=None, next_path=None):
        client = client or self.client
        params = {"next": next_path} if next_path is not None else None
        r = client.get("/auth/oidc/login", params=params, follow_redirects=False)
        self.assertEqual(r.status_code, 302, r.text)
        self.assertIn(self.oidc.STATE_COOKIE, client.cookies)
        return r.headers["location"]

    def callback(self, client, code, state):
        return client.get("/auth/oidc/callback", params={"code": code, "state": state},
                          follow_redirects=False)

    def sign_in(self, email, *, client=None, next_path=None, **overrides):
        client = client or self.fresh_client()
        location = self.start(client, next_path)
        code, state = self.provider.authorize(location, email, **overrides)
        return client, self.callback(client, code, state)

    def me(self, client):
        return client.get("/api/auth/me").json()


class ProvidersAndConfiguration(OIDCBase):
    def test_providers_reports_both_paths_when_configured(self):
        r = self.client.get("/api/auth/providers")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["cache-control"], "no-store")
        body = r.json()
        self.assertEqual(body["badge"], {"enabled": True})
        self.assertEqual(body["oidc"], {"enabled": True, "label": "Sign in with Google",
                                        "login_url": "/auth/oidc/login", "issuer_host": "accounts.google.com"})
        self.assertNotIn(CLIENT_SECRET, r.text)
        self.assertNotIn(CLIENT_ID, r.text)

    def test_unconfigured_console_offers_badge_only_and_login_route_says_so(self):
        os.environ.pop("CAPVSAR_OIDC_CLIENT_SECRET")
        body = self.client.get("/api/auth/providers").json()
        self.assertFalse(body["oidc"]["enabled"])
        self.assertTrue(body["badge"]["enabled"])
        r = self.client.get("/auth/oidc/login", follow_redirects=False)
        self.assertEqual(r.status_code, 503)
        self.assertIn("badge code", r.text)
        self.assertNotIn("capvsar_session", r.cookies)
        # the badge path is unaffected
        login = self.client.post("/api/auth/login", json={"code": credential("MRO-1")})
        self.assertEqual(login.status_code, 200)

    def test_login_redirect_carries_pkce_state_nonce_and_sets_a_host_cookie(self):
        location = self.start()
        q = {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}
        self.assertEqual(q["redirect_uri"], BASE + "/auth/oidc/callback")
        self.assertEqual(q["code_challenge_method"], "S256")
        self.assertGreaterEqual(len(q["state"]), 32)
        self.assertGreaterEqual(len(q["nonce"]), 32)
        self.assertNotIn("client_secret", q)
        self.assertNotIn("hd", q)
        cookie = self.client.cookies[self.oidc.STATE_COOKIE]
        self.assertNotIn(q["nonce"], cookie.split(".")[1])     # the payload is encoded, not the raw nonce
        payload = self.oidc.open_state(cookie, self.oidc.config())
        self.assertEqual(payload["state"], q["state"])
        self.assertEqual(payload["nonce"], q["nonce"])


class HappyPath(OIDCBase):
    def test_assigned_email_lands_in_its_seat_with_the_same_session_as_a_badge(self):
        self.setup_with_emails()
        client, r = self.sign_in("MRO@Example.org")           # provider case differs from the setup's
        self.assertEqual(r.status_code, 303, r.text)
        self.assertEqual(r.headers["location"], "/base")
        self.assertIn("capvsar_session", client.cookies)
        self.assertNotIn(self.oidc.STATE_COOKIE, client.cookies)
        set_cookie = r.headers["set-cookie"]
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("Secure", set_cookie)
        self.assertIn("SameSite=lax", set_cookie)
        me = self.me(client)
        self.assertTrue(me["authenticated"])
        self.assertEqual((me["role"], me["seat"], me["via"], me["email"], me["code"], me["callsign"]),
                         ("base", "mro", "oidc", "mro@example.org", "MRO-1", "MRO 1"))
        # same gates as a badge session: base may post ICS, may not read the setup
        self.assertEqual(client.post("/api/radio/ics", json={"mode": "ALL"}).status_code, 200)
        self.assertIn(client.get("/api/setup").status_code, (403, 503))
        # the roster records how the seat was taken
        row = next(x for x in self.client.get("/api/setup", headers=self.instr).json()["roster"]
                   if x["code"].startswith("MRO-1-"))
        self.assertEqual(row["last_login_via"], "oidc")
        self.assertIsNotNone(row["last_login"])
        self.assertEqual(row["email"], "mro@example.org")
        self.assertEqual(row["seat"], "mro")
        # and the badge path still works for the same seat, as a badge
        other = self.fresh_client()
        self.assertEqual(other.post("/api/auth/login", json={"code": credential("MRO-1")}).status_code, 200)
        self.assertEqual(self.me(other)["via"], "badge")
        # the token endpoint saw PKCE, the secret and the redirect URI (the fake enforces them)
        self.assertEqual(len(self.provider.token_requests), 1)
        self.assertIn("code_verifier", self.provider.token_requests[0])

    def test_observer_lands_on_its_aircraft_seat(self):
        self.setup_with_emails()
        client, r = self.sign_in("m.observer@example.org")
        self.assertEqual(r.status_code, 303)
        me = self.me(client)
        self.assertEqual((me["role"], me["seat"], me["aircraft_id"], me["callsign"]),
                         ("aircrew", "observer", "ac-1", "CAP 487"))

    def test_safe_next_is_honoured_and_unsafe_next_is_dropped(self):
        self.setup_with_emails()
        _, r = self.sign_in("mro@example.org", next_path="/radio")
        self.assertEqual(r.headers["location"], "/radio")
        for bad in ("https://evil.example/x", "//evil.example", "/\\evil.example", "/x\nSet-Cookie:y", "radio"):
            _, r = self.sign_in("mro@example.org", next_path=bad)
            self.assertEqual(r.status_code, 303, bad)
            self.assertEqual(r.headers["location"], "/base", bad)

    def test_director_allow_list_and_setup_director_email_sign_in_as_instructor(self):
        os.environ["CAPVSAR_OIDC_DIRECTOR_EMAILS"] = " Director@Example.org , second@example.org"
        self.setup_with_emails(director="chief@example.org")
        for email in ("director@example.org", "chief@example.org"):
            client, r = self.sign_in(email)
            self.assertEqual(r.status_code, 303, email)
            self.assertEqual(r.headers["location"], "/")
            me = self.me(client)
            self.assertEqual((me["role"], me["seat"], me["via"]), ("instructor", "director", "oidc"), email)
            self.assertEqual(client.get("/api/setup").status_code, 200)

    def test_sessions_are_fresh_and_logout_ends_them(self):
        self.setup_with_emails()
        client = self.fresh_client()
        client.cookies.set("capvsar_session", "attacker-chosen-value", domain="testserver.local")
        client, r = self.sign_in("mro@example.org", client=client)
        self.assertNotEqual(client.cookies["capvsar_session"], "attacker-chosen-value")
        self.assertTrue(self.me(client)["authenticated"])
        self.assertEqual(client.post("/api/auth/logout").status_code, 200)
        self.assertFalse(self.me(client)["authenticated"])

    def test_session_lifetime_is_configurable_for_both_paths(self):
        os.environ["CAPVSAR_SESSION_LIFETIME_S"] = "3600"
        self.setup_with_emails()
        client, r = self.sign_in("mro@example.org")
        self.assertIn("Max-Age=3600", r.headers["set-cookie"])
        self.assertAlmostEqual(self.me(client)["expires"], time.time() + 3600, delta=30)
        badge = self.fresh_client()
        r = badge.post("/api/auth/login", json={"code": credential("MRO-1")})
        self.assertAlmostEqual(self.me(badge)["expires"], time.time() + 3600, delta=30)
        # T23 C3: the badge cookie's Max-Age used to stay at 86400 whatever the row said.
        self.assertIn("Max-Age=3600", r.headers["set-cookie"])
        joiner = self.fresh_client()
        joiner.get("/join/" + credential("MRO-1"))
        r = joiner.post("/join/" + credential("MRO-1"), data={"csrf": self._join_csrf(joiner, credential("MRO-1"))},
                        follow_redirects=False)
        self.assertEqual(r.status_code, 303, r.text)
        self.assertIn("Max-Age=3600", r.headers["set-cookie"])

    @staticmethod
    def _join_csrf(client, code):
        import hashlib as _h
        nonce = client.cookies.get("__Host-capvsar_join")
        return _h.sha256((nonce + ":" + code).encode()).hexdigest()


class Refusals(OIDCBase):
    def assert_refused(self, client, r, *, error="oidc_failed"):
        self.assertEqual(r.status_code, 303, r.text)
        self.assertEqual(r.headers["location"], "/login?error=" + error)
        self.assertNotIn("capvsar_session", client.cookies)
        self.assertFalse(self.me(client)["authenticated"])

    def test_no_seat_for_a_verified_email_shows_a_friendly_page_and_mints_nothing(self):
        self.setup_with_emails()
        client, r = self.sign_in("stranger@example.org")
        self.assertEqual(r.status_code, 403)
        self.assertIn("stranger@example.org", r.text)
        self.assertIn("SAREX 2026-10", r.text)
        self.assertIn("Exercise Director", r.text)
        self.assertNotIn("Traceback", r.text)
        self.assertNotIn("capvsar_session", client.cookies)
        self.assertFalse(self.me(client)["authenticated"])

    def test_exact_normalised_match_only_no_dot_or_plus_canonicalisation(self):
        self.setup_with_emails(observer="  M.Observer@Example.ORG ")
        rows = self.client.get("/api/setup", headers=self.instr).json()["roster"]
        self.assertEqual(next(x["email"] for x in rows if x["code"].startswith("OBS-")), "m.observer@example.org")
        client, r = self.sign_in("M.OBSERVER@example.org ")
        self.assertEqual(r.status_code, 303)
        for impostor in ("mobserver@example.org", "m.observer+sarex@example.org", "m.o.bserver@example.org"):
            client, r = self.sign_in(impostor)
            self.assertEqual(r.status_code, 403, impostor)
            self.assertFalse(self.me(client)["authenticated"], impostor)

    def test_unverified_email_is_refused(self):
        self.setup_with_emails()
        for value in (False, "false", None, 1):
            client, r = self.sign_in("mro@example.org", email_verified=value)
            self.assert_refused(client, r)

    def test_wrong_state_missing_cookie_and_replay_are_refused(self):
        self.setup_with_emails()
        client = self.fresh_client()
        location = self.start(client)
        code, state = self.provider.authorize(location, "mro@example.org")
        self.assert_refused(client, self.callback(client, code, state + "x"))
        # the refusal cleared the state cookie; the real callback is now unusable
        self.assertNotIn(self.oidc.STATE_COOKIE, client.cookies)
        self.assert_refused(client, self.callback(client, code, state))
        # a genuine round trip, then the same callback again (cookie re-presented)
        client = self.fresh_client()
        location = self.start(client)
        state_cookie = client.cookies[self.oidc.STATE_COOKIE]
        code, state = self.provider.authorize(location, "mro@example.org")
        r = self.callback(client, code, state)
        self.assertEqual(r.status_code, 303)
        replay = self.fresh_client()
        replay.cookies.set(self.oidc.STATE_COOKIE, state_cookie)
        self.assert_refused(replay, self.callback(replay, code, state))
        # no cookie at all
        bare = self.fresh_client()
        self.assert_refused(bare, self.callback(bare, "code-x", "state-x"))

    def test_expired_state_cookie_is_refused(self):
        self.setup_with_emails()
        client = self.fresh_client()
        location = self.start(client)
        code, state = self.provider.authorize(location, "mro@example.org")
        cfg = self.oidc.config()
        payload = self.oidc.open_state(client.cookies[self.oidc.STATE_COOKIE], cfg)
        payload["t"] -= self.oidc.STATE_TTL_S + 5
        client.cookies.set(self.oidc.STATE_COOKIE, self.oidc.sign_state(payload, cfg))
        self.assert_refused(client, self.callback(client, code, state))
        # a forged cookie (wrong key) is refused too
        client = self.fresh_client()
        location = self.start(client)
        code, state = self.provider.authorize(location, "mro@example.org")
        forged = self.oidc.sign_state(payload, {**cfg, "client_secret": "other"})
        client.cookies.set(self.oidc.STATE_COOKIE, forged)
        self.assert_refused(client, self.callback(client, code, state))

    def test_bad_id_tokens_are_refused(self):
        self.setup_with_emails()
        cases = {
            "nonce": {"nonce_override": "not-the-nonce"},
            "expired": {"exp_offset": -300},
            "audience": {"aud": "someone-else"},
            "issuer": {"iss": "https://evil.example"},
            "signature": {"key": self.provider.other_key},
        }
        for name, overrides in cases.items():
            client, r = self.sign_in("mro@example.org", **overrides)
            self.assert_refused(client, r)
        # Google's alternate issuer spelling is accepted; small skew is tolerated
        client, r = self.sign_in("mro@example.org", iss="accounts.google.com")
        self.assertEqual(r.status_code, 303)
        client, r = self.sign_in("mro@example.org", exp_offset=-30)
        self.assertEqual(r.status_code, 303)

    def test_hosted_domain_is_enforced_when_configured(self):
        os.environ["CAPVSAR_OIDC_HD"] = "cawg.cap.gov"
        self.setup_with_emails(mro="mro@cawg.cap.gov")
        location = self.start(self.fresh_client())
        self.assertIn("hd=cawg.cap.gov", location)
        client, r = self.sign_in("mro@cawg.cap.gov")                 # no hd claim at all
        self.assert_refused(client, r)
        client, r = self.sign_in("mro@cawg.cap.gov", extra={"hd": "other.example"})
        self.assert_refused(client, r)
        client, r = self.sign_in("mro@cawg.cap.gov", extra={"hd": "CAWG.cap.gov"})
        self.assertEqual(r.status_code, 303)

    def test_cancelled_consent_goes_back_to_login_without_counting_as_an_attack(self):
        client = self.fresh_client()
        self.start(client)
        r = client.get("/auth/oidc/callback", params={"error": "access_denied"}, follow_redirects=False)
        self.assert_refused(client, r, error="oidc_cancelled")

    def test_repeated_failures_from_one_address_are_rate_limited(self):
        self.setup_with_emails()
        client = self.fresh_client()
        for _ in range(self.oidc.FAILURE_LIMIT):
            r = client.get("/auth/oidc/callback", params={"code": "x", "state": "y"}, follow_redirects=False)
            self.assertEqual(r.status_code, 303)
        r = client.get("/auth/oidc/callback", params={"code": "x", "state": "y"}, follow_redirects=False)
        self.assertEqual(r.status_code, 429)
        # a legitimate sign-in from that address is held too (constant behaviour), then released
        self.oidc.failures.clear()
        client, r = self.sign_in("mro@example.org")
        self.assertEqual(r.status_code, 303)

    def test_provider_outage_is_a_clear_page_not_a_stack_trace(self):
        import http.client
        # T23 C6: half-closed and garbled answers (http.client.HTTPException,
        # a non-JSON body) used to escape as a 500; they are provider outages too.
        for error in (OSError("connection refused"), http.client.BadStatusLine("garbage"),
                      http.client.IncompleteRead(b"{"), ValueError("Expecting value: line 1")):
            def down(url, _e=error):
                raise _e
            self.oidc.fetch_json = down
            self.oidc.forget_cached_metadata()
            r = self.client.get("/auth/oidc/login", follow_redirects=False)
            self.assertEqual(r.status_code, 503, repr(error))
            self.assertIn("could not be reached", r.text)
            self.assertNotIn("Traceback", r.text)
            self.assertEqual(self.client.post("/api/auth/login", json={"code": "nope"}).status_code, 401,
                             "the badge form must keep answering")
        # and at the callback, the token endpoint going away is the uniform refusal
        self.oidc.fetch_json = self.provider.fetch_json
        self.setup_with_emails()
        client = self.fresh_client()
        location = self.start(client)
        code, state = self.provider.authorize(location, "mro@example.org")
        def token_down(url, data, auth=None):
            raise http.client.RemoteDisconnected("closed")
        self.oidc.post_form = token_down
        r = self.callback(client, code, state)
        self.assert_refused(client, r)
        # the stdlib seams themselves translate every such error into OIDCError
        import urllib.request
        real = urllib.request.urlopen
        for error in (http.client.BadStatusLine("x"), http.client.IncompleteRead(b""),
                      OSError("reset"), TimeoutError("slow")):
            def boom(*a, _e=error, **k):
                raise _e
            urllib.request.urlopen = boom
            try:
                with self.assertRaises(self.oidc.OIDCError, msg=repr(error)):
                    self.real_fetch_json("https://provider.invalid/.well-known/openid-configuration")
                with self.assertRaises(self.oidc.OIDCError, msg=repr(error)):
                    self.real_post_form("https://provider.invalid/token", {"a": "b"})
            finally:
                urllib.request.urlopen = real


class SetupEmails(OIDCBase):
    def post_setup(self, body, headers=None):
        return self.client.post("/api/setup", json=body, headers=headers or self.instr)

    def test_malformed_emails_are_422_with_the_field_named(self):
        for bad in ("not-an-email", "a@b", "two@@example.org", "with space@example.org", "a" * 250 + "@x.org"):
            r = self.post_setup({"aircraft": [], "staff": [{"role": "base", "email": bad}]})
            self.assertEqual(r.status_code, 422, bad)
            self.assertIn("valid email", r.text)
        r = self.post_setup({"aircraft": [{"callsign": "CAP 1", "crew": ["pilot"], "emails": {"scanner": "s@example.org"}}]})
        self.assertEqual(r.status_code, 422)
        self.assertIn("not a crew seat", r.text)

    def test_duplicate_email_across_seats_is_refused_with_both_seats_named(self):
        r = self.post_setup({"aircraft": [{"callsign": "CAP 487", "crew": ["pilot", "observer"],
                                           "emails": {"pilot": "Same@Example.org", "observer": "same@example.org "}}],
                             "staff": []})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn("same@example.org", r.json()["detail"])
        self.assertIn("PLT-487", r.json()["detail"])
        self.assertIn("OBS-487", r.json()["detail"])
        r = self.post_setup({"director_email": "d@example.org",
                             "staff": [{"role": "base", "callsign": "MRO 1", "email": "d@example.org"}]})
        self.assertEqual(r.status_code, 422)
        self.assertIn("one seat per email", r.json()["detail"])
        # the refused save left the previous roster in place
        self.assertTrue(any(x["code"].startswith("INSTR-1-") for x in self.client.get("/api/setup", headers=self.instr).json()["roster"]))

    def test_blank_emails_mean_badge_only_and_reset_clears_them(self):
        setup = self.setup_with_emails(mro="", observer="   ")
        self.assertTrue(all(x["email"] is None for x in setup["roster"]))
        self.setup_with_emails()
        reset = self.client.post("/api/setup/reset", headers=self.instr).json()
        self.assertTrue(all(x["email"] is None for x in reset["roster"]))

    def test_saving_the_setup_keeps_the_saving_director_signed_in(self):
        """B7 (review T11): the save used to log the instructor out of their own save."""
        os.environ["CAPVSAR_OIDC_DIRECTOR_EMAILS"] = "director@example.org"
        client, r = self.sign_in("director@example.org")
        before = client.cookies["capvsar_session"]
        r = client.post("/api/setup", json={"aircraft": [], "staff": []})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("capvsar_session", r.headers.get("set-cookie", ""))
        self.assertNotEqual(client.cookies["capvsar_session"], before)
        me = self.me(client)
        self.assertEqual((me["authenticated"], me["role"], me["via"], me["email"]),
                         (True, "instructor", "oidc", "director@example.org"))
        # a badge director gets the same treatment
        badge = self.fresh_client()
        badge.post("/api/auth/login", json={"code": credential("INSTR-1")})
        r = badge.post("/api/setup/reset")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.me(badge)["role"], "instructor")

    def test_regenerating_or_reassigning_revokes_the_holders_sessions(self):
        self.setup_with_emails()
        client, _ = self.sign_in("mro@example.org")
        self.assertTrue(self.me(client)["authenticated"])
        self.setup_with_emails(mro="someone.else@example.org")          # seat reassigned
        self.assertFalse(self.me(client)["authenticated"])
        client, r = self.sign_in("mro@example.org")
        self.assertEqual(r.status_code, 403)                            # no seat any more
        client, r = self.sign_in("someone.else@example.org")
        self.assertEqual(r.status_code, 303)

    def test_who_joined_fields_and_email_visibility(self):
        self.setup_with_emails()
        self.sign_in("m.observer@example.org")
        mro = self.fresh_client()
        mro.post("/api/auth/login", json={"code": credential("MRO-1")})
        director_view = self.client.get("/api/ready", headers=self.instr).json()["seats"]
        obs = next(s for s in director_view if s["seat"] == "observer")
        mro_seat = next(s for s in director_view if s["seat"] == "mro")
        self.assertEqual((obs["last_login_via"], obs["email"]), ("oidc", "m.observer@example.org"))
        self.assertEqual(mro_seat["last_login_via"], "badge")
        self.assertIsNotNone(obs["last_login"])
        udf = next(s for s in director_view if s["seat"] == "udf")
        self.assertEqual((udf["last_login"], udf["last_login_via"], udf["email"]), (None, None, None))
        participant_view = mro.get("/api/ready").json()["seats"]
        self.assertTrue(all("email" not in s for s in participant_view))
        self.assertEqual(next(s for s in participant_view if s["seat"] == "observer")["last_login_via"], "oidc")


class SeatRecheckOnSockets(OIDCBase):
    def test_an_oidc_session_revoked_by_a_setup_save_loses_its_socket(self):
        from starlette.websockets import WebSocketDisconnect
        self.setup_with_emails()
        saved = self.access.SOCKET_RECHECK_S
        self.access.SOCKET_RECHECK_S = 0.15
        try:
            client, _ = self.sign_in("mro@example.org")
            sid = client.cookies["capvsar_session"]
            with client.websocket_connect("/ws", headers={"Authorization": "Bearer " + sid}) as ws:
                self.assertEqual(ws.receive_json()["type"], "state")
                self.setup_with_emails(mro="replacement@example.org")
                with self.assertRaises(WebSocketDisconnect):
                    ws.receive_json()
        finally:
            self.access.SOCKET_RECHECK_S = saved


class ExactAsciiEmails(OIDCBase):
    """T23 C2: "exact normalised email" was not exact for non-ASCII input
    (`casefold` turns `straße` into `strasse`; `lower` turns the Kelvin sign
    into `k`). Seats are ASCII only; a non-ASCII provider address matches nothing."""

    LOOK_ALIKES = (("strasse@example.org", "stra\u00dfe@example.org"),
                   ("kelvin@example.org", "\u212aelvin@example.org"),
                   ("mro@example.org", "mro@\u0435xample.org"))        # Cyrillic е in the domain

    def test_non_ascii_setup_email_is_a_plain_language_422(self):
        for _ascii, look_alike in self.LOOK_ALIKES:
            r = self.client.post("/api/setup", json={"aircraft": [], "staff": [
                {"role": "base", "callsign": "MRO 1", "email": look_alike}]}, headers=self.instr)
            self.assertEqual(r.status_code, 422, look_alike)
            self.assertIn("plain ASCII", r.text)
            self.assertIn("accented or non-Latin", r.text)
            r = self.client.post("/api/setup", json={"director_email": look_alike}, headers=self.instr)
            self.assertEqual(r.status_code, 422, look_alike)
            r = self.client.post("/api/setup", json={"aircraft": [{"callsign": "CAP 1", "crew": ["pilot"],
                                                                   "emails": {"pilot": look_alike}}]},
                                 headers=self.instr)
            self.assertEqual(r.status_code, 422, look_alike)
        # the refused saves left no roster row behind with a non-ASCII address
        rows = self.client.get("/api/setup", headers=self.instr).json()["roster"]
        self.assertTrue(all((x["email"] or "").isascii() for x in rows))

    def test_non_ascii_provider_address_gets_the_no_seat_page_not_the_seat(self):
        for ascii_addr, look_alike in self.LOOK_ALIKES:
            self.setup_with_emails(mro=ascii_addr)
            client, r = self.sign_in(look_alike)
            self.assertEqual(r.status_code, 403, look_alike)
            self.assertIn("no seat", r.text.lower())
            self.assertNotIn("capvsar_session", client.cookies)
            self.assertFalse(self.me(client)["authenticated"], look_alike)
            # ASCII case differences still match, as before
            client, r = self.sign_in(ascii_addr.upper())
            self.assertEqual(r.status_code, 303, ascii_addr)
            self.assertEqual(self.me(client)["email"], ascii_addr)

    def test_normalisation_is_trim_plus_ascii_lowercase_only(self):
        n = self.oidc.normalise_email
        self.assertEqual(n("  Mixed.Case+Tag@Example.ORG "), "mixed.case+tag@example.org")
        self.assertEqual(n("stra\u00dfe@x.org"), "stra\u00dfe@x.org")      # not folded to strasse
        self.assertEqual(n("\u212aelvin@x.org"), "\u212aelvin@x.org")      # not lowered to kelvin
        self.assertTrue(self.oidc.valid_email("a.b+c@example.org"))
        self.assertFalse(self.oidc.valid_email("stra\u00dfe@x.org"))
        self.assertTrue(self.oidc.well_formed_email("stra\u00dfe@x.org"))
        with self.assertRaises(ValueError) as caught:
            self.oidc.parse_setup_email("stra\u00dfe@x.org")
        self.assertIn("plain ASCII", str(caught.exception))
        self.assertIsNone(self.oidc.parse_setup_email("   "))


class PreviousSessionRevoked(OIDCBase):
    """T23 P2: a browser that signs in again used to keep its previous session
    row valid until expiry; now the row named by the incoming cookie is deleted
    once the new login has succeeded."""

    def _session_cookie(self, client):
        return client.cookies.get("capvsar_session")

    def udf(self):
        """The ground team's full credential, whatever label the setup gave it."""
        return next(r["code"] for r in self.access.get_roster() if r["role"] == "ground_team")

    def _authenticated_with(self, sess_id):
        probe = self.fresh_client()
        probe.cookies.set("capvsar_session", sess_id, domain="testserver.local")
        return self.me(probe)["authenticated"]

    def test_badge_then_oidc_in_one_browser_revokes_the_badge_session(self):
        self.setup_with_emails()
        client = self.fresh_client()
        self.assertEqual(client.post("/api/auth/login", json={"code": self.udf()}).status_code, 200)
        old = self._session_cookie(client)
        self.assertTrue(self._authenticated_with(old))
        client, r = self.sign_in("mro@example.org", client=client)
        self.assertEqual(r.status_code, 303)
        self.assertNotEqual(self._session_cookie(client), old)
        self.assertEqual(self.me(client)["seat"], "mro")
        self.assertFalse(self._authenticated_with(old), "the previous session must be gone")

    def test_badge_then_badge_and_join_confirm_revoke_too(self):
        self.setup_with_emails()
        client = self.fresh_client()
        client.post("/api/auth/login", json={"code": self.udf()})
        first = self._session_cookie(client)
        client.post("/api/auth/login", json={"code": credential("MRO-1")})
        second = self._session_cookie(client)
        self.assertFalse(self._authenticated_with(first))
        self.assertTrue(self._authenticated_with(second))
        code = self.udf()
        client.get("/join/" + code)
        import hashlib as _h
        csrf = _h.sha256((client.cookies.get("__Host-capvsar_join") + ":" + code).encode()).hexdigest()
        r = client.post("/join/" + code, data={"csrf": csrf}, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertFalse(self._authenticated_with(second))
        self.assertEqual(self.me(client)["seat"], "udf")

    def test_a_failed_login_keeps_the_existing_session(self):
        self.setup_with_emails()
        client = self.fresh_client()
        client.post("/api/auth/login", json={"code": credential("MRO-1")})
        old = self._session_cookie(client)
        self.assertEqual(client.post("/api/auth/login", json={"code": "WRONG-1-nope"}).status_code, 401)
        self.assertTrue(self._authenticated_with(old))
        client, r = self.sign_in("stranger@example.org", client=client)     # no seat: nothing minted
        self.assertEqual(r.status_code, 403)
        self.assertTrue(self._authenticated_with(old))
        client, r = self.sign_in("mro@example.org", client=client, email_verified=False)   # refused
        self.assertEqual(r.status_code, 303)
        self.assertTrue(self._authenticated_with(old))

    def test_another_device_on_the_same_seat_is_untouched(self):
        self.setup_with_emails()
        tablet, laptop = self.fresh_client(), self.fresh_client()
        tablet.post("/api/auth/login", json={"code": credential("MRO-1")})
        tablet_session = self._session_cookie(tablet)
        laptop, r = self.sign_in("mro@example.org", client=laptop)
        self.assertEqual(r.status_code, 303)
        self.assertTrue(self._authenticated_with(tablet_session))
        self.assertTrue(self.me(tablet)["authenticated"])
        self.assertTrue(self.me(laptop)["authenticated"])


class AccessLogRedaction(OIDCBase):
    """T23 C1: uvicorn's access log printed the callback's `code=` and `state=`."""

    def _uvicorn_record(self, path, status=303):
        import logging
        record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                                   '%s - "%s %s HTTP/%s" %d',
                                   ("10.0.0.5:5555", "GET", path, "1.1", status), None)
        for f in logging.getLogger("uvicorn.access").filters:
            f.filter(record)
        return record.getMessage()

    def test_filter_is_installed_when_the_app_is_assembled(self):
        import logging
        filters = logging.getLogger("uvicorn.access").filters
        self.assertTrue(any(isinstance(f, self.oidc.AccessLogRedactor) for f in filters))
        self.assertEqual(sum(isinstance(f, self.oidc.AccessLogRedactor) for f in filters), 1,
                         "installing twice must not stack filters")

    def test_callback_code_and_state_never_reach_the_access_log(self):
        line = self._uvicorn_record("/auth/oidc/callback?state=S3cr3tState&code=4%2F0AbCdEf-ghi&scope=openid%20email")
        self.assertNotIn("S3cr3tState", line)
        self.assertNotIn("4%2F0AbCdEf", line)
        self.assertIn("/auth/oidc/callback?state=[redacted]&code=[redacted]&scope=openid%20email", line)
        self.assertIn("10.0.0.5:5555", line)
        self.assertIn(" 303", line)
        # other lines are untouched
        self.assertIn("/api/ready?since=5", self._uvicorn_record("/api/ready?since=5", 200))
        self.assertIn("/join/MRO-1-ABCDEF", self._uvicorn_record("/join/MRO-1-ABCDEF", 200))
        # a pre-formatted message (another access logger) is redacted as well
        self.assertEqual(self.oidc.redact_query("GET /x?code=abc&state=def&id_token=jwt HTTP/1.1"),
                         "GET /x?code=[redacted]&state=[redacted]&id_token=[redacted] HTTP/1.1")

    def test_real_access_log_output_is_redacted(self):
        import io, logging
        logger = logging.getLogger("uvicorn.access")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        saved = logger.level
        logger.setLevel(logging.INFO)
        try:
            logger.info('%s - "%s %s HTTP/%s" %d', "c", "GET", "/auth/oidc/callback?code=XYZ&state=ABC", "1.1", 303)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(saved)
        self.assertNotIn("XYZ", stream.getvalue())
        self.assertNotIn("ABC", stream.getvalue())
        self.assertIn("[redacted]", stream.getvalue())


class FrontEndFixes(unittest.TestCase):
    """T23 C4, C5, C7: the static files, checked as source and (for the invite
    message) run under node."""

    STATIC = Path(__file__).resolve().parent.parent / "services" / "exercise" / "app" / "static"

    def src(self, name):
        return (self.STATIC / name).read_text()

    def test_login_page_offline_tag_id_matches_the_script(self):
        html, js = self.src("login.html"), self.src("login.js")
        self.assertIn('id="badgeFallbackTag"', html)
        self.assertIn('getElementById("badgeFallbackTag")', js)
        self.assertNotIn("badgeSectionTag", js)

    def test_login_page_has_no_dead_no_seat_branch(self):
        js = self.src("login.js")
        self.assertNotIn('errorParam === "no_seat"', js)
        for live in ("oidc_cancelled", "oidc_failed", "invalid_code", "instructor_required"):
            self.assertIn(f'errorParam === "{live}"', js)

    def _invite(self, item):
        from test_console_frontend import block, run_block
        code = block("setup.js", "T24 PURE INVITE MESSAGE")
        return run_block(code, f"buildInviteMessage({json.dumps(item)}, 'SAREX 2026-10', 'https://vsar.example.org')")

    def test_invite_email_never_carries_the_director_credential(self):
        director = {"role": "instructor", "title": "Exercise Director / Evaluator", "callsign": "INSTRUCTOR",
                    "code": "INSTR-1-0123456789ABCDEF0123456789ABCDEF", "target_url": "/", "email": None}
        for email in (None, "director@example.org"):
            msg = self._invite(dict(director, email=email))
            self.assertNotIn("INSTR-1-0123", msg["body"])
            self.assertNotIn("INSTR-1-0123", msg["subject"])
            self.assertNotIn("/join/", msg["body"])
            self.assertIn("https://vsar.example.org/login", msg["body"])
            self.assertEqual(msg["to"], email or "")

    def test_invite_for_an_email_seat_has_the_sign_in_page_and_the_seat_only(self):
        msg = self._invite({"role": "base", "title": "Mission Radio Operator 1", "callsign": "MRO 1",
                            "code": "MRO-1-FEDCBA9876543210FEDCBA9876543210", "target_url": "/base",
                            "email": "mro@example.org"})
        self.assertEqual(msg["to"], "mro@example.org")
        self.assertNotIn("MRO-1-FEDCBA", msg["body"])
        self.assertNotIn("/join/", msg["body"])
        self.assertNotIn("Badge Code:", msg["body"])
        self.assertIn("Mission Radio Operator 1", msg["body"])
        self.assertIn("MRO 1", msg["body"])
        self.assertIn("Sign in with Google", msg["body"])
        self.assertIn("https://vsar.example.org/login", msg["body"])

    def test_invite_for_a_badge_only_seat_still_carries_its_badge(self):
        msg = self._invite({"role": "ground_team", "title": "Ground Team / UDF 1 Leader", "callsign": "UDF 1",
                            "code": "UDF-1-0011223344556677889900AABBCCDDEE", "target_url": "/udf", "email": None})
        self.assertEqual(msg["to"], "")
        self.assertIn("UDF-1-0011223344556677889900AABBCCDDEE", msg["body"])
        self.assertIn("https://vsar.example.org/join/UDF-1-0011223344556677889900AABBCCDDEE", msg["body"])

    def test_the_page_builds_its_mailto_from_that_message(self):
        js = self.src("setup.js")
        self.assertIn("const msg = buildInviteMessage(item, exTitle, origin);", js)
        self.assertNotIn("Offline / Backup Badge Code: ${item.code", js.split("// END T24 PURE INVITE MESSAGE")[1])


if __name__ == "__main__":
    unittest.main()
