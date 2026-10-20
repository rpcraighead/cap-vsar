"""
OpenID Connect relying party for the exercise console (identity plan §4-6).

A generic authorization-code + PKCE client: configured by environment with an
issuer, so it works against Google directly (https://accounts.google.com) or
against authentik (https://auth.example.org/application/o/<slug>/) without
code changes. The console owns seats; the provider only proves control of an
email. The verified email is matched to the roster (access.py) and the result
is the same session a badge login mints.

What this module deliberately does NOT do:

* keep server-side login state. The state, nonce, PKCE verifier and the
  requested destination travel in one signed, HttpOnly, 10-minute cookie
  (`STATE_COOKIE`), bound to the provider round trip. A replayed callback is
  refused by a bounded in-process set of consumed states as well.
* canonicalise emails beyond trim + ASCII lower-case. Gmail's dot and
  plus-tag aliasing is Google's business; applying it to every provider would
  let `john.doe@` claim `johndoe@`'s seat (plan §5.6). Addresses are ASCII
  only (T23 C2): Unicode folding is not exact either (`straße` -> `strasse`,
  the Kelvin sign -> `k`), so a non-ASCII address can be assigned to no seat
  and matches none.
* log tokens, secrets or full addresses. One audit line per attempt:
  outcome, seat, masked email.

HTTP to the provider goes through two module-level functions (`fetch_json`,
`post_form`, stdlib urllib with timeouts) so tests replace them with a fake
provider and never touch the network.
"""
from __future__ import annotations

import base64
import collections
import hashlib
import hmac
import http.client
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt
from jwt import PyJWK

log = logging.getLogger("capvsar.console.oidc")

STATE_COOKIE = "__Host-capvsar_oidc"
STATE_TTL_S = 600.0
CALLBACK_PATH = "/auth/oidc/callback"
LOGIN_PATH = "/auth/oidc/login"
SCOPES = "openid email"
ALGORITHMS = ("RS256", "ES256")
CLOCK_SKEW_S = 60
HTTP_TIMEOUT_S = 8.0
DISCOVERY_TTL_S = 3600.0
JWKS_TTL_S = 3600.0
# One client address may fail the callback this many times per window before
# it is told to wait: a code-guessing or state-guessing run is otherwise free.
FAILURE_LIMIT = 10
FAILURE_WINDOW_S = 60.0

GOOGLE_ISSUER = "https://accounts.google.com"
# Google's ID tokens carry iss as either form (Google's own documentation).
GOOGLE_ISSUERS = (GOOGLE_ISSUER, "accounts.google.com")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ----------------------------------------------------------------- config

def config() -> dict:
    """Read the OIDC settings from the environment every time (never cached:
    tests and operators change them without a restart; nothing here is logged)."""
    issuer = os.environ.get("CAPVSAR_OIDC_ISSUER", "").strip().rstrip("/")
    client_id = os.environ.get("CAPVSAR_OIDC_CLIENT_ID", "").strip()
    client_secret = os.environ.get("CAPVSAR_OIDC_CLIENT_SECRET", "").strip()
    redirect_base = os.environ.get("CAPVSAR_OIDC_REDIRECT_BASE", "").strip().rstrip("/")
    enabled = bool(issuer and client_id and client_secret and redirect_base)
    label = os.environ.get("CAPVSAR_OIDC_LABEL", "").strip() or (
        "Sign in with Google" if issuer in GOOGLE_ISSUERS else "Sign in")
    directors = tuple(sorted({normalise_email(e) for e in
                              os.environ.get("CAPVSAR_OIDC_DIRECTOR_EMAILS", "").split(",")
                              if e.strip()}))
    return {
        "enabled": enabled, "issuer": issuer, "client_id": client_id,
        "client_secret": client_secret, "redirect_base": redirect_base,
        "redirect_uri": redirect_base + CALLBACK_PATH if redirect_base else "",
        "label": label, "hd": os.environ.get("CAPVSAR_OIDC_HD", "").strip().casefold(),
        "director_emails": directors,
        "issuer_host": urllib.parse.urlsplit(issuer).netloc if issuer else "",
        "trust_proxy": os.environ.get("CAPVSAR_TRUST_PROXY", "").strip() in ("1", "true", "yes", "on"),
    }


def providers() -> dict:
    """The public description the login page reads (GET /api/auth/providers)."""
    cfg = config()
    return {"oidc": {"enabled": cfg["enabled"], "label": cfg["label"],
                     "login_url": LOGIN_PATH, "issuer_host": cfg["issuer_host"]},
            "badge": {"enabled": True}}


# ------------------------------------------------------------------ emails

NON_ASCII_MESSAGE = ("email must use plain ASCII letters, digits and punctuation "
                     "(accented or non-Latin characters are not accepted)")
MALFORMED_MESSAGE = "value is not a valid email address"


def normalise_email(value: str) -> str:
    """Trim, and lower-case ASCII. Nothing else, on purpose (module docstring).

    A non-ASCII address is only trimmed: `str.lower()` and `str.casefold()`
    both map look-alike code points onto ASCII (the Kelvin sign onto `k`), which
    would let one spelling claim another's seat. Such an address is never
    stored (parse_setup_email refuses it), so leaving it unfolded means it
    matches nothing."""
    value = (value or "").strip()
    return value.lower() if value.isascii() else value


def well_formed_email(value: str) -> bool:
    """Structure only: one `@`, a dotted domain, no whitespace, <= 254 chars."""
    return bool(value) and len(value) <= 254 and EMAIL_RE.fullmatch(value) is not None


def valid_email(value: str) -> bool:
    """What a seat may be assigned: well formed and ASCII (T23 C2)."""
    return well_formed_email(value) and value.isascii()


def parse_setup_email(value):
    """A seat's email as typed in Setup: None when blank, the normalised
    address otherwise. Raises ValueError with a plain-language message the
    route answers 422 with. One function for the pydantic models and the
    store, so both say the same thing."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(MALFORMED_MESSAGE)
    email = normalise_email(value)
    if email == "":
        return None
    if not email.isascii():
        raise ValueError(NON_ASCII_MESSAGE)
    if not well_formed_email(email):
        raise ValueError(MALFORMED_MESSAGE)
    return email


def mask_email(value: str) -> str:
    """`m***@example.org`: enough to recognise an attempt in the log, not an address."""
    if not value or "@" not in value:
        return "***"
    local, domain = value.split("@", 1)
    return (local[:1] or "*") + "***@" + domain


# ------------------------------------------------------------ HTTP (seam)

# Everything the stdlib client can raise for a dead, slow, or garbled provider
# (T23 C6): socket and URL errors, HTTP status errors, half-closed responses
# (`http.client.HTTPException`: BadStatusLine, IncompleteRead, ...) and a body
# that is not JSON. The routes catch OIDCError and show the friendly page.
PROVIDER_ERRORS = (OSError, http.client.HTTPException, ValueError)


def fetch_json(url: str) -> dict:
    """GET a JSON document from the provider. Replaced by the tests' fake provider."""
    request = urllib.request.Request(url, headers={"Accept": "application/json",
                                                   "User-Agent": "capvsar-console"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise OIDCError("provider answered HTTP %d" % error.code) from error
    except PROVIDER_ERRORS as error:
        raise OIDCError("provider unreachable: %s" % type(error).__name__) from error


def post_form(url: str, data: dict, *, auth: tuple[str, str] | None = None) -> dict:
    """POST a form (the token request) and return the JSON reply. Replaced in tests."""
    body = urllib.parse.urlencode(data).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
               "User-Agent": "capvsar-console"}
    if auth:
        headers["Authorization"] = "Basic " + base64.b64encode(
            ("%s:%s" % auth).encode()).decode()
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise OIDCError("token endpoint answered HTTP %d" % error.code) from error
    except PROVIDER_ERRORS as error:
        raise OIDCError("token endpoint unreachable: %s" % type(error).__name__) from error


class OIDCError(Exception):
    """Any reason a sign-in cannot complete. The message is for the log only."""


# ------------------------------------------------------- provider metadata

_cache_lock = threading.Lock()
_discovery: dict = {}          # issuer -> (expires_at, document)
_jwks: dict = {}               # jwks_uri -> (expires_at, keys)


def discovery(issuer: str) -> dict:
    with _cache_lock:
        hit = _discovery.get(issuer)
        if hit and hit[0] > time.monotonic():
            return hit[1]
    doc = fetch_json(issuer + "/.well-known/openid-configuration")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri", "issuer"):
        if not isinstance(doc.get(key), str) or not doc[key]:
            raise OIDCError("discovery document lacks " + key)
    with _cache_lock:
        _discovery[issuer] = (time.monotonic() + DISCOVERY_TTL_S, doc)
    return doc


def signing_key(jwks_uri: str, kid: str | None, *, refresh: bool = False):
    """The provider key for `kid`, refetching the JWKS once on a miss (rotation)."""
    with _cache_lock:
        hit = _jwks.get(jwks_uri)
        keys = hit[1] if hit and hit[0] > time.monotonic() and not refresh else None
    if keys is None:
        doc = fetch_json(jwks_uri)
        keys = [k for k in doc.get("keys", []) if isinstance(k, dict)]
        with _cache_lock:
            _jwks[jwks_uri] = (time.monotonic() + JWKS_TTL_S, keys)
    for key in keys:
        if kid is None or key.get("kid") == kid:
            return PyJWK(key).key
    if not refresh:
        return signing_key(jwks_uri, kid, refresh=True)
    raise OIDCError("no signing key for kid")


def forget_cached_metadata() -> None:
    with _cache_lock:
        _discovery.clear()
        _jwks.clear()


# ------------------------------------------------------- state cookie

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _state_key(cfg: dict) -> bytes:
    # Derived, never the secret itself; a leaked cookie signature says nothing
    # about the client secret.
    return hashlib.sha256(("capvsar-oidc-state:" + cfg["client_secret"]).encode()).digest()


def sign_state(payload: dict, cfg: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return body + "." + _b64(hmac.new(_state_key(cfg), body.encode(), hashlib.sha256).digest())


def open_state(cookie: str, cfg: dict, now: float | None = None) -> dict:
    if not cookie or "." not in cookie:
        raise OIDCError("state cookie missing")
    body, sig = cookie.rsplit(".", 1)
    expected = _b64(hmac.new(_state_key(cfg), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig.encode(), expected.encode()):
        raise OIDCError("state cookie signature mismatch")
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, UnicodeDecodeError) as error:
        raise OIDCError("state cookie unreadable") from error
    issued = payload.get("t")
    if type(issued) not in (int, float) or (now or time.time()) - issued > STATE_TTL_S or issued > (now or time.time()) + 60:
        raise OIDCError("state cookie expired")
    for key in ("state", "nonce", "verifier"):
        if not isinstance(payload.get(key), str) or len(payload[key]) < 16:
            raise OIDCError("state cookie incomplete")
    return payload


# ------------------------------------------------------- safe next

def safe_next(raw, origin: str | None = None) -> str | None:
    """The login page's F2-6 rule, server-side: one leading `/`, no `//` or `/\\`,
    no control characters, and the same origin when resolved."""
    if not isinstance(raw, str) or raw == "" or raw[0] != "/":
        return None
    if len(raw) > 1 and raw[1] in ("/", "\\"):
        return None
    if re.search(r"[\\\x00-\x1f\x7f]", raw):
        return None
    if len(raw) > 2048:
        return None
    base = (origin or "https://console").rstrip("/")
    try:
        resolved = urllib.parse.urljoin(base + "/", raw)
    except ValueError:
        return None
    if urllib.parse.urlsplit(resolved).netloc != urllib.parse.urlsplit(base).netloc:
        return None
    return raw


# ------------------------------------------------------- begin / complete

def begin(next_path: str | None, cfg: dict | None = None) -> tuple[str, str]:
    """(authorization URL to redirect to, state cookie value)."""
    cfg = cfg or config()
    if not cfg["enabled"]:
        raise OIDCError("OIDC is not configured")
    doc = discovery(cfg["issuer"])
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    query = {
        "response_type": "code", "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"], "scope": SCOPES,
        "state": state, "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256",
    }
    if cfg["hd"]:
        query["hd"] = cfg["hd"]
    url = doc["authorization_endpoint"] + ("&" if "?" in doc["authorization_endpoint"] else "?") \
        + urllib.parse.urlencode(query)
    cookie = sign_state({"state": state, "nonce": nonce, "verifier": verifier,
                         "next": safe_next(next_path, cfg["redirect_base"]) or "",
                         "t": time.time()}, cfg)
    return url, cookie


class _ConsumedStates:
    """Bounded memory of states already exchanged: a replayed callback inside
    the cookie's lifetime is refused here even if the provider would not."""

    def __init__(self, limit: int = 4096):
        self._lock = threading.Lock()
        self._seen = collections.OrderedDict()
        self._limit = limit

    def consume(self, state: str) -> bool:
        """True the first time; False if `state` was seen before."""
        with self._lock:
            now = time.time()
            for key in [k for k, t in self._seen.items() if now - t > STATE_TTL_S]:
                del self._seen[key]
            if state in self._seen:
                return False
            self._seen[state] = now
            while len(self._seen) > self._limit:
                self._seen.popitem(last=False)
            return True

    def clear(self):
        with self._lock:
            self._seen.clear()


consumed_states = _ConsumedStates()


class _FailureCounter:
    """Per-client-address failures of the callback within a sliding window."""

    def __init__(self):
        self._lock = threading.Lock()
        self._hits: dict[str, collections.deque] = {}

    def blocked(self, address: str) -> bool:
        with self._lock:
            hits = self._hits.get(address)
            if not hits:
                return False
            now = time.monotonic()
            while hits and now - hits[0] > FAILURE_WINDOW_S:
                hits.popleft()
            return len(hits) >= FAILURE_LIMIT

    def record(self, address: str) -> None:
        with self._lock:
            self._hits.setdefault(address, collections.deque()).append(time.monotonic())
            if len(self._hits) > 10000:        # a flood of addresses: forget the oldest
                self._hits.pop(next(iter(self._hits)))

    def clear(self):
        with self._lock:
            self._hits.clear()


failures = _FailureCounter()


def verify_id_token(id_token: str, nonce: str, cfg: dict, doc: dict) -> dict:
    """Signature (provider JWKS), iss, aud, exp/iat with skew, nonce, email_verified, hd."""
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as error:
        raise OIDCError("id_token header unreadable") from error
    if header.get("alg") not in ALGORITHMS:
        raise OIDCError("id_token algorithm not allowed")
    key = signing_key(doc["jwks_uri"], header.get("kid"))
    try:
        claims = jwt.decode(
            id_token, key=key, algorithms=list(ALGORITHMS), audience=cfg["client_id"],
            leeway=CLOCK_SKEW_S,
            options={"require": ["exp", "iat", "sub", "aud", "iss"], "verify_iss": False})
    except jwt.PyJWTError as error:
        raise OIDCError("id_token rejected: %s" % type(error).__name__) from error
    accepted_issuers = {cfg["issuer"], doc["issuer"].rstrip("/")}
    if cfg["issuer"] in GOOGLE_ISSUERS:
        accepted_issuers.update(GOOGLE_ISSUERS)
    if claims.get("iss", "").rstrip("/") not in accepted_issuers:
        raise OIDCError("id_token issuer mismatch")
    token_nonce = claims.get("nonce")
    if not isinstance(token_nonce, str) or not hmac.compare_digest(token_nonce.encode(), nonce.encode()):
        raise OIDCError("nonce mismatch")
    verified = claims.get("email_verified")
    if not (verified is True or (isinstance(verified, str) and verified.lower() == "true")):
        raise OIDCError("email not verified by the provider")
    # Structure only: a non-ASCII address is let through unfolded so that it
    # reaches the seat lookup, matches nothing (no seat can hold one) and the
    # person sees the "no seat" page rather than an opaque failure (T23 C2).
    email = normalise_email(claims.get("email") if isinstance(claims.get("email"), str) else "")
    if not well_formed_email(email):
        raise OIDCError("id_token carries no usable email")
    if cfg["hd"]:
        hd = claims.get("hd")
        if not isinstance(hd, str) or hd.casefold() != cfg["hd"]:
            raise OIDCError("hosted domain mismatch")
    return {"email": email, "sub": claims.get("sub")}


def complete(query: dict, cookie: str | None, cfg: dict | None = None) -> dict:
    """Exchange the callback for a verified email.

    Returns {"email", "sub", "next"}; raises OIDCError for every refusal. The
    caller turns the email into a seat (or a "no seat" page) and a session.
    """
    cfg = cfg or config()
    if not cfg["enabled"]:
        raise OIDCError("OIDC is not configured")
    payload = open_state(cookie or "", cfg)
    state = query.get("state")
    if not isinstance(state, str) or not hmac.compare_digest(state.encode(), payload["state"].encode()):
        raise OIDCError("state mismatch")
    if not consumed_states.consume(state):
        raise OIDCError("state already used")
    code = query.get("code")
    if not isinstance(code, str) or not 1 <= len(code) <= 2048:
        raise OIDCError("authorization code missing")
    doc = discovery(cfg["issuer"])
    token = post_form(doc["token_endpoint"], {
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": cfg["redirect_uri"], "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"], "code_verifier": payload["verifier"],
    })
    id_token = token.get("id_token") if isinstance(token, dict) else None
    if not isinstance(id_token, str) or not id_token:
        raise OIDCError("token response lacks id_token")
    identity = verify_id_token(id_token, payload["nonce"], cfg, doc)
    identity["next"] = payload.get("next") or ""
    return identity


# ------------------------------------------------------- access log (C1)

_SENSITIVE_QUERY = re.compile(r"(?i)([?&](?:code|state|id_token|access_token|error_description)=)[^&#\s\"]*")


def redact_query(text: str) -> str:
    """`?code=4/0A...&state=xyz` -> `?code=[redacted]&state=[redacted]`."""
    return _SENSITIVE_QUERY.sub(r"\1[redacted]", text)


class AccessLogRedactor(logging.Filter):
    """uvicorn's access log writes the request line, so without this every
    sign-in left `GET /auth/oidc/callback?code=...&state=...` in `docker logs`
    (T23 C1). The authorization code is single-use and PKCE-bound, but it is a
    credential and the state is the round trip's CSRF secret. uvicorn passes
    (client, method, full_path, http_version, status) as the record's args;
    the path is rewritten before the formatter sees it. Pre-formatted messages
    are rewritten too, for any other access logger."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple):
            record.args = tuple(redact_query(a) if isinstance(a, str) and ("code=" in a or "state=" in a)
                                else a for a in args)
        if isinstance(record.msg, str) and ("code=" in record.msg or "state=" in record.msg):
            record.msg = redact_query(record.msg)
        return True


def install_access_log_redaction(logger_name: str = "uvicorn.access") -> logging.Filter:
    """Idempotent: the console's app module is imported once per process in
    production and many times in the test suite."""
    logger = logging.getLogger(logger_name)
    for existing in logger.filters:
        if isinstance(existing, AccessLogRedactor):
            return existing
    redactor = AccessLogRedactor()
    logger.addFilter(redactor)
    return redactor


def client_address(request, cfg: dict | None = None) -> str:
    """The address the callback rate limit keys on: the proxy's first
    X-Forwarded-For hop only when the operator says the proxy is trusted."""
    cfg = cfg or config()
    if cfg["trust_proxy"]:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    client = getattr(request, "client", None)
    return (getattr(client, "host", None) or "unknown")[:64]
