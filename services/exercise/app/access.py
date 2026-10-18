"""
Role tokens and session-based access control for the exercise console.

Roles:
    instructor   scenario authoring, sortie control, setup, truth reveal
    base         mission base: log bearings, Form 110, send messages, base radio
    aircrew      flight planning, observer radio aids, debriefing
    ground_team  mobile phone radio, UDF ground bearing check-in
    plugin       X-Plane plugin: ingest aircraft telemetry, beacon truth

Authentication modes:
1. Session Cookie (`capvsar_session`) or Bearer Token: established via participant
   short codes or QR code mobile scan (/join/<code>).
2. Shared-secret environment tokens (`CAPVSAR_TOKEN_*`) via the `X-CAPVSAR-Token`
   header only. X2-10: a `?token=` query parameter used to work as well, and so
   put role tokens (including the plugin key on the one route that serves beacon
   truth) into uvicorn and Caddy access logs. It is no longer read.
"""
from __future__ import annotations

import hashlib
import secrets
import hmac
import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager

from fastapi import HTTPException, Request

log = logging.getLogger("capvsar.console.access")

TOKEN_HEADER = "X-CAPVSAR-Token"
SESSION_COOKIE = "capvsar_session"
ROLES = ("instructor", "evaluator", "base", "aircrew", "ground_team", "plugin")

# D5: seats are the unit of membership; the role is the permission class a
# seat maps to. This is the only list of seats in the code. `kind` says what a
# seat belongs to, which is what the Ready room groups tiles by.
SEATS: dict[str, dict] = {
    "director":  {"role": "instructor",  "label": "Exercise Director",     "kind": "exercise", "lands": "/instructor"},
    "ic":        {"role": "base",        "label": "Incident Commander",    "kind": "base",     "lands": "/base?mode=ic"},
    "aobd":      {"role": "base",        "label": "Air Ops Branch Director", "kind": "base",   "lands": "/base?mode=aobd"},
    "mro":       {"role": "base",        "label": "Mission Radio Operator", "kind": "base",    "lands": "/radio"},
    "base":      {"role": "base",        "label": "Base staff",            "kind": "base",     "lands": "/base"},
    "evaluator": {"role": "evaluator",   "label": "Evaluator (SET)",       "kind": "exercise", "lands": "/debrief"},
    "pilot":     {"role": "aircrew",     "label": "Mission Pilot",         "kind": "aircraft", "lands": "/base"},
    "observer":  {"role": "aircrew",     "label": "Mission Observer",      "kind": "aircraft", "lands": "/base"},
    "scanner":   {"role": "aircrew",     "label": "Mission Scanner",       "kind": "aircraft", "lands": "/base"},
    "udf":       {"role": "ground_team", "label": "Ground team / UDF",     "kind": "ground",   "lands": "/radio"},
    "station":   {"role": "plugin",      "label": "Simulator station",     "kind": "aircraft", "lands": ""},
}


def seat_of(row: dict) -> str:
    """The seat a roster row holds (D5). Rows written before the `seat`
    column get it from their title and assigned name, the same words the
    radio's crew classification already keys on; rows with a `seat` field
    use it."""
    seat = (row.get("seat") or "").strip().lower()
    if seat in SEATS:
        return seat
    role = row.get("role", "")
    text = " ".join(str(row.get(k) or "") for k in ("title", "assigned_name")).upper()
    if role == "instructor":
        return "director"
    if role == "evaluator":
        return "evaluator"
    if role == "base":
        if "RADIO" in text or "MRO" in text:
            return "mro"
        if "AIR OP" in text or "AOBD" in text:
            return "aobd"
        if "INCIDENT" in text or " IC" in text or text.startswith("IC"):
            return "ic"
        return "base"
    if role == "aircrew":
        if "PILOT" in text:
            return "pilot"
        if "SCANNER" in text:
            return "scanner"
        return "observer"
    if role == "ground_team":
        return "udf"
    if role == "plugin":
        return "station"
    return "base"


# Which roles/tokens satisfy an access requirement.
# An instructor may act in any role; base staff can direct ground teams.
SATISFIED_BY: dict[str, tuple[str, ...]] = {
    "instructor": ("instructor",),
    # D5: a read-only seat; satisfies reads (any_role) and nothing else.
    "evaluator": ("evaluator", "instructor"),
    "base": ("base", "instructor"),
    "aircrew": ("aircrew", "instructor"),
    "ground_team": ("ground_team", "base", "instructor"),
    "plugin": ("plugin",),
}

DB_PATH_ENV = os.environ.get("CAPVSAR_DB", "/data/exercise.db")


@contextmanager
def auth_db():
    db_file = os.environ.get("CAPVSAR_DB", DB_PATH_ENV)
    c = sqlite3.connect(db_file, timeout=5.0)
    c.row_factory = sqlite3.Row
    # X2-6: same pairing as store.db() (FE-9). `synchronous` is per connection,
    # and this one opens on every authenticated request, so left at FULL each
    # session write fsynced. busy_timeout is stated rather than left to the
    # connect() argument so a lock wait here is bounded the same way.
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("PRAGMA synchronous=NORMAL")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_auth_db() -> None:
    """Ensure roster, session, and exercise configuration tables exist.

    X2-6: run once, from store.init_db() at startup. It used to run, migrations
    and a write transaction included, on every authenticated request. Nothing
    on the request path calls it now; a caller that builds its own database
    (a test, a script) calls it explicitly.
    """
    with auth_db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS roster (
            id TEXT PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            title TEXT NOT NULL,
            callsign TEXT,
            aircraft_id TEXT,
            assigned_name TEXT,
            token TEXT,
            target_url TEXT,
            created REAL,
            last_login REAL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            role TEXT NOT NULL,
            title TEXT NOT NULL,
            callsign TEXT,
            aircraft_id TEXT,
            target_url TEXT,
            created REAL,
            expires REAL
        );
        CREATE TABLE IF NOT EXISTS exercise_config (
            id TEXT PRIMARY KEY,
            name TEXT,
            num_aircraft INTEGER,
            config_json TEXT,
            active INTEGER DEFAULT 1,
            updated REAL
        );
        CREATE INDEX IF NOT EXISTS idx_roster_code ON roster(code);
        CREATE INDEX IF NOT EXISTS idx_sessions_id ON sessions(session_id);
        """)
        # Seats assigned by email (OIDC sign-in, identity plan §5): the roster row
        # carries the normalised address and how its holder last signed in; a
        # session carries which path minted it and the verified email, so the
        # director's "who joined" view and the audit line never guess.
        # Additive, like every migration in store.init_db().
        roster_cols = {r["name"] for r in c.execute("PRAGMA table_info(roster)")}
        if "email" not in roster_cols:
            c.execute("ALTER TABLE roster ADD COLUMN email TEXT")
        if "last_login_via" not in roster_cols:
            c.execute("ALTER TABLE roster ADD COLUMN last_login_via TEXT")
        session_cols = {r["name"] for r in c.execute("PRAGMA table_info(sessions)")}
        if "via" not in session_cols:
            c.execute("ALTER TABLE sessions ADD COLUMN via TEXT")
        if "email" not in session_cols:
            c.execute("ALTER TABLE sessions ADD COLUMN email TEXT")
        # One email holds one seat per exercise (v1): the database says so too,
        # not only the setup validation.
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_roster_email ON roster(email) "
                  "WHERE email IS NOT NULL AND email != ''")
        # Existing databases have no FK: triggers also cover direct roster deletion.
        c.executescript("""
        CREATE TRIGGER IF NOT EXISTS revoke_roster_sessions AFTER DELETE ON roster
        BEGIN DELETE FROM sessions WHERE code=OLD.code; END;
        CREATE TRIGGER IF NOT EXISTS revoke_changed_roster_sessions AFTER UPDATE OF code ON roster
        BEGIN DELETE FROM sessions WHERE code=OLD.code; END;
        """)
        # Revoke pre-hardening plaintext sessions, and reclaim expired rows.
        c.execute("DELETE FROM sessions WHERE session_id NOT LIKE 'sha256:%' OR expires IS NULL OR expires<=?", (time.time(),))
        # Upgrade previously distributed guessable badges once. Reissue these badges.
        for row in c.execute("SELECT id, code, token FROM roster").fetchall():
            token = row["token"] or ""
            if len(token) != 32 or not row["code"].endswith("-" + token):
                token = secrets.token_hex(16).upper()
                c.execute("UPDATE roster SET code=?, token=? WHERE id=?",
                          (row["code"] + "-" + token, token, row["id"]))
        # If roster is completely empty, seed standard starter codes
        count = c.execute("SELECT COUNT(*) FROM roster").fetchone()[0]
        if count == 0:
            now = time.time()
            starter = [
                ("r-instr", "INSTR-1", "instructor", "Exercise Director / Evaluator", "INSTRUCTOR", "", "Instructor", secrets.token_hex(16).upper(), "/", now),
                ("r-mro1", "MRO-1", "base", "Mission Radio Operator 1", "BASE MRO 1", "", "MRO 1", secrets.token_hex(16).upper(), "/base", now),
                ("r-plt423", "PLT-423", "aircrew", "CAP 423 SAR Mission Pilot", "CAP 423", "ac-1", "Pilot", secrets.token_hex(16).upper(), "/base", now),
                ("r-obs423", "OBS-423", "aircrew", "CAP 423 Mission Observer (TDFM/DF)", "CAP 423", "ac-1", "Observer", secrets.token_hex(16).upper(), "/base", now),
                ("r-udf1", "UDF-1", "ground_team", "Ground Team / UDF 1 Leader", "UDF 1", "", "Ground Team 1", secrets.token_hex(16).upper(), "/radio", now),
            ]
            starter = [_credential_row(row) for row in starter]
            c.executemany(
                "INSERT OR IGNORE INTO roster (id, code, role, title, callsign, aircraft_id, assigned_name, token, target_url, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", starter
            )


def sweep_expired_sessions() -> int:
    """Delete expired session rows. Called from the ticker, not per request."""
    with auth_db() as c:
        return c.execute("DELETE FROM sessions WHERE expires<=?",
                         (time.time(),)).rowcount


def _credential_row(row: tuple) -> tuple:
    """The public badge label alone is never a credential; require its random token."""
    return (row[0], row[1] + "-" + row[7], *row[2:])


def _session_hash(session_id: str) -> str:
    return "sha256:" + hashlib.sha256(session_id.encode()).hexdigest()


def token_for(role: str) -> str:
    return os.environ.get(f"CAPVSAR_TOKEN_{role.upper()}", "").strip()


def unconfigured() -> list[str]:
    """Roles with no token set — their endpoints are unauthenticated."""
    return [r for r in ("instructor", "base", "plugin") if not token_for(r)]


def dev_open() -> bool:
    """True when the operator has explicitly asked for an unauthenticated console.

    X-11: a missing token used to mean "open", so forgetting to configure one
    silently disabled access control. Opening the console is now a deliberate
    act with its own variable, and it is refused outright once the deployment
    marks itself as production, so the flag cannot travel from a laptop into
    an exercise by way of a copied .env.
    """
    if os.environ.get("CAPVSAR_ENV", "").strip().lower() in ("prod", "production"):
        return False
    return os.environ.get("CAPVSAR_DEV_OPEN", "").strip() in ("1", "true", "yes", "on")


def presented(request: Request) -> str:
    # Header only (X2-10): a token in the URL ends up in access logs.
    return (request.headers.get(TOKEN_HEADER) or "").strip()


def _matches(supplied: str, accepted: list[str]) -> bool:
    ok = False
    for token in accepted:
        if hmac.compare_digest(supplied.encode(), token.encode()):
            ok = True
    return ok


def get_session_from_request(request: Request) -> dict | None:
    """Resolve an active session from cookies or the Bearer header."""
    # 1. Check legacy token matching configured instructor/base/plugin
    legacy_token = presented(request)
    if legacy_token:
        for r in ("instructor", "base", "plugin"):
            cfg = token_for(r)
            if cfg and hmac.compare_digest(legacy_token.encode(), cfg.encode()):
                return {
                    "session_id": f"token_{r}",
                    "code": r.upper(),
                    "role": r,
                    "title": f"Configured {r.title()} Token",
                    "callsign": r.upper(),
                    "aircraft_id": "",
                    "target_url": "/" if r == "instructor" else "/base",
                    "via": "token", "email": None,
                    "seat": {"instructor": "director", "base": "base", "plugin": "station"}[r],
                }

    # 2. Check session ID from cookie or Bearer authorization
    sess_id = request.cookies.get(SESSION_COOKIE)
    if not sess_id:
        auth_hdr = request.headers.get("Authorization", "").strip()
        if auth_hdr.startswith("Bearer "):
            sess_id = auth_hdr[7:].strip()

    if not sess_id:
        return None

    now = time.time()
    with auth_db() as c:
        # One indexed read (X2-6). assigned_name comes from the roster row the
        # session was minted for, so the radio can tell a pilot from an
        # observer by what the roster says rather than by the callsign.
        row = c.execute(
            "SELECT code, role, title, callsign, aircraft_id, target_url, expires, via, email, "
            "(SELECT assigned_name FROM roster WHERE roster.code=sessions.code) "
            "AS assigned_name "
            "FROM sessions WHERE session_id=? AND expires>?",
            (_session_hash(sess_id), now)
        ).fetchone()
        if row:
            identity = dict(row)
            identity["code"] = identity["code"].rsplit("-", 1)[0]
            identity["via"] = identity.get("via") or "badge"
            identity["seat"] = seat_of(identity)
            return identity
    return None


SESSION_LIFETIME_DEFAULT_S = 86400.0


def session_lifetime_s() -> float:
    """CAPVSAR_SESSION_LIFETIME_S, 5 minutes to 30 days; the 24 h default otherwise.
    Read on every mint so an operator change needs no restart."""
    raw = os.environ.get("CAPVSAR_SESSION_LIFETIME_S", "").strip()
    try:
        value = float(raw) if raw else SESSION_LIFETIME_DEFAULT_S
    except ValueError:
        return SESSION_LIFETIME_DEFAULT_S
    return value if 300.0 <= value <= 30 * 86400.0 else SESSION_LIFETIME_DEFAULT_S


def create_session(code: str, role: str, title: str, callsign: str = "",
                   aircraft_id: str = "", target_url: str = "", *,
                   via: str = "badge", email: str | None = None) -> str:
    """Mint a session. `via` says which path proved the identity (badge, oidc);
    `email` is the provider-verified address for an OIDC login, else None."""
    sess_id = secrets.token_urlsafe(32)
    now = time.time()
    expires = now + session_lifetime_s()
    with auth_db() as c:
        c.execute(
            "INSERT INTO sessions (session_id, code, role, title, callsign, aircraft_id, target_url, "
            "created, expires, via, email) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_session_hash(sess_id), code, role, title, callsign, aircraft_id, target_url, now, expires,
             via, email)
        )
    return sess_id


def delete_session(sess_id: str) -> None:
    with auth_db() as c:
        c.execute("DELETE FROM sessions WHERE session_id=?", (_session_hash(sess_id),))


def revoke_previous_session(request: Request) -> None:
    """T23 P2: a browser that signs in again gets a fresh session id and the
    cookie is overwritten, but the row it used to carry stayed valid until it
    expired. Delete it once the new login has succeeded. Every tab of that
    browser shares the cookie jar, so no open tab is still presenting the old
    id; another device on the same seat has its own session and is untouched."""
    previous = request.cookies.get(SESSION_COOKIE)
    if previous:
        delete_session(previous)


def authenticate_code(code: str) -> tuple[dict, str] | None:
    """Validate a participant access code (case-insensitive) and return (roster_row, session_id)."""
    clean_code = code.strip().upper()
    now = time.time()

    # X-10: there was an instructor shortcut here. It accepted the literal
    # codes ADMIN and INSTRUCTOR whenever CAPVSAR_TOKEN_INSTRUCTOR was set,
    # testing only that the token existed and never comparing it to what the
    # caller supplied, so GET /join/ADMIN minted an Exercise Director session
    # for anyone who could reach the console. Since instructor satisfies every
    # other role, that also defeated X-1: truth is gated on a presented
    # instructor token, but the session was obtainable without presenting one.
    # An instructor now authenticates the same way as everyone else - a roster
    # credential, or the configured token via the X-CAPVSAR-Token header.

    with auth_db() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT id, code, role, title, callsign, aircraft_id, assigned_name, target_url "
            "FROM roster WHERE UPPER(code)=?",
            (clean_code,)
        ).fetchone()
        if not row:
            # Review T11: a refused code used to leave no trace at all, so a
            # guessing run was invisible. The value itself is never logged.
            log.warning("login refused: unknown participant code (%d chars)", len(clean_code))
            return None
        d = dict(row)
        sess_id = secrets.token_urlsafe(32)
        c.execute("UPDATE roster SET last_login=?, last_login_via='badge' WHERE id=?", (now, d["id"]))
        c.execute(
            "INSERT INTO sessions (session_id, code, role, title, callsign, aircraft_id, target_url, "
            "created, expires, via, email) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'badge', NULL)",
            (_session_hash(sess_id), d["code"], d["role"], d["title"],
             d["callsign"], d["aircraft_id"], d["target_url"], now, now + session_lifetime_s()))

    d["code"] = d["code"].rsplit("-", 1)[0]
    return (d, sess_id)


def _roster_row_public(row) -> dict:
    d = dict(row)
    d["code"] = d["code"].rsplit("-", 1)[0]
    return d


def login_with_email(email: str, *, directors: tuple = ()) -> tuple[dict, str] | None:
    """The OIDC counterpart of authenticate_code(): a provider-verified,
    normalised email becomes the seat the director assigned to it.

    A configured director email becomes an instructor session bound to the
    roster's director row (so presence and the Ready room work), whatever that
    row's own email says. Anyone else must match a roster row exactly (after
    the same trim + case-fold the setup applied; no alias canonicalisation).
    None means "no seat": the caller shows the friendly page and mints nothing.
    """
    now = time.time()
    with auth_db() as c:
        c.execute("BEGIN IMMEDIATE")
        if email in directors:
            row = c.execute(
                "SELECT id, code, role, title, callsign, aircraft_id, assigned_name, target_url "
                "FROM roster WHERE role='instructor' ORDER BY created, id LIMIT 1").fetchone()
            if row is None:
                # A console with no director row at all (never set up): the
                # allow-list still gets the director in, on a roster-less code.
                d = {"id": None, "code": "INSTR-1-DIRECTOR", "role": "instructor",
                     "title": "Exercise Director", "callsign": "INSTRUCTOR",
                     "aircraft_id": "", "assigned_name": "Instructor", "target_url": "/"}
            else:
                d = dict(row)
        else:
            row = c.execute(
                "SELECT id, code, role, title, callsign, aircraft_id, assigned_name, target_url "
                "FROM roster WHERE email=?", (email,)).fetchone()
            if row is None:
                return None
            d = dict(row)
        sess_id = secrets.token_urlsafe(32)
        if d.get("id"):
            c.execute("UPDATE roster SET last_login=?, last_login_via='oidc' WHERE id=?", (now, d["id"]))
        c.execute(
            "INSERT INTO sessions (session_id, code, role, title, callsign, aircraft_id, target_url, "
            "created, expires, via, email) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'oidc', ?)",
            (_session_hash(sess_id), d["code"], d["role"], d["title"], d["callsign"],
             d["aircraft_id"], d["target_url"], now, now + session_lifetime_s(), email))
    return (_roster_row_public(d), sess_id)


def reissue_instructor_session(previous: dict) -> str | None:
    """B7: a setup save regenerates the roster and revokes every session,
    the saving instructor's included. Mint them a fresh one on the new
    director row so the page they are on stays signed in. Token-header
    identities need nothing."""
    if not previous or previous.get("role") != "instructor" or previous.get("via") == "token":
        return None
    with auth_db() as c:
        row = c.execute("SELECT code, title, callsign, target_url FROM roster WHERE role='instructor' "
                        "ORDER BY created, id LIMIT 1").fetchone()
    if row is None:
        return None
    return create_session(row["code"], "instructor", row["title"], row["callsign"] or "INSTRUCTOR", "",
                          row["target_url"] or "/", via=previous.get("via") or "badge",
                          email=previous.get("email"))


def get_roster() -> list[dict]:
    with auth_db() as c:
        rows = c.execute(
            "SELECT id, code, role, title, callsign, aircraft_id, assigned_name, token, target_url, created, "
            "last_login, email, last_login_via FROM roster ORDER BY created, id"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["seat"] = seat_of(d)
            result.append(d)
        return result


def get_exercise_setup() -> dict:
    with auth_db() as c:
        row = c.execute(
            "SELECT id, name, num_aircraft, config_json, updated FROM exercise_config WHERE active=1 ORDER BY updated DESC LIMIT 1"
        ).fetchone()
        if row:
            d = dict(row)
            d["config"] = json.loads(d.get("config_json") or "{}")
            d["roster"] = get_roster()
            return d
        return {
            "id": "default",
            "name": "Civil Air Patrol SAREX Exercise",
            "num_aircraft": 1,
            "config": {
                "scenario_id": "",
                "aircraft": [
                    {
                        "id": "ac-1",
                        "callsign": "CAP 423",
                        "tail": "CAP 487",
                        "df_model": "Becker SAR-DF 517",
                        "crew": ["pilot", "observer", "scanner"]
                    }
                ],
                "staff": [
                    {"role": "base", "title": "Mission Radio Operator 1", "callsign": "MRO 1"},
                    {"role": "ground_team", "title": "Ground Team / UDF 1 Leader", "callsign": "UDF 1"}
                ]
            },
            "roster": get_roster()
        }


def _normalised_email(value) -> str | None:
    """Trim + ASCII lower-case, nothing more; None for empty. Raises ValueError
    (plain-language message) for a malformed or non-ASCII address so the route
    can answer 422. One rule for the models and the store: oidc.parse_setup_email."""
    from .oidc import parse_setup_email
    return parse_setup_email(value)


def save_exercise_setup(name: str, num_aircraft: int, aircraft_list: list[dict], staff_list: list[dict],
                        *, director_email: str | None = None) -> dict:
    """Save exercise configuration and generate participant roster with codes and invite URLs.

    Seats may carry an email (`director_email`, `aircraft[].emails[seat]`,
    `staff[].email`): the address Google (or authentik) must verify for the
    holder to be signed into that seat. One email, one seat: a duplicate
    raises ValueError naming the seats, and the route answers 422.
    """
    now = time.time()
    director_email = _normalised_email(director_email)
    config_obj = {"aircraft": aircraft_list, "staff": staff_list, "director_email": director_email}
    config_json = json.dumps(config_obj)
    assigned: dict[str, list[str]] = {}

    def claim(email, seat_label):
        if email:
            assigned.setdefault(email, []).append(seat_label)
        return email

    with auth_db() as c:
        # Mark previous configs inactive
        c.execute("UPDATE exercise_config SET active=0")
        setup_id = f"setup-{uuid.uuid4().hex[:8]}"
        c.execute(
            "INSERT INTO exercise_config (id, name, num_aircraft, config_json, active, updated) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (setup_id, name, num_aircraft, config_json, now)
        )
        # Regeneration also revokes sessions minted by internal callers.
        c.execute("DELETE FROM sessions")
        c.execute("DELETE FROM roster")

        new_roster = []
        # 1. Instructor
        new_roster.append((
            f"r-instr-{uuid.uuid4().hex[:6]}", "INSTR-1", "instructor",
            "Exercise Director / Evaluator", "INSTRUCTOR", "", "Instructor",
            secrets.token_hex(16).upper(), "/", now, claim(director_email, "INSTR-1")
        ))

        # 2. Aircraft crews
        for ac_idx, ac in enumerate(aircraft_list, 1):
            ac_id = ac.get("id") or f"ac-{ac_idx}"
            callsign = ac.get("callsign") or f"CAP {420 + ac_idx}"
            tail = (ac.get("tail") or "").strip()
            # A tail number is shown only when there is one; this used to fall
            # back to a fixed callsign and print "CAP 487 (CAP 487)" on badges.
            tail_part = f" ({tail})" if tail and tail != callsign else ""
            df_model = ac.get("df_model") or "Becker SAR-DF 517"
            num_suffix = callsign.split()[-1] if " " in callsign else str(ac_idx)

            crew_roles = ac.get("crew") or ["pilot", "observer"]
            crew_emails = ac.get("emails") or {}
            if not isinstance(crew_emails, dict):
                raise ValueError("emails must map crew seats to addresses")
            for seat_key in crew_emails:
                if seat_key not in crew_roles:
                    raise ValueError("emails key '%s' is not a crew seat of this aircraft" % seat_key)
            if "pilot" in crew_roles:
                new_roster.append((
                    f"r-plt-{uuid.uuid4().hex[:6]}", f"PLT-{num_suffix}", "aircrew",
                    f"{callsign}{tail_part} SAR Mission Pilot", callsign, ac_id, "Mission Pilot",
                    secrets.token_hex(16).upper(), "/base", now,
                    claim(_normalised_email(crew_emails.get("pilot")), f"PLT-{num_suffix}")
                ))
            if "observer" in crew_roles:
                new_roster.append((
                    f"r-obs-{uuid.uuid4().hex[:6]}", f"OBS-{num_suffix}", "aircrew",
                    f"{callsign}{tail_part} Mission Observer [{df_model}]", callsign, ac_id, "Mission Observer",
                    secrets.token_hex(16).upper(), "/base", now,
                    claim(_normalised_email(crew_emails.get("observer")), f"OBS-{num_suffix}")
                ))
            if "scanner" in crew_roles:
                new_roster.append((
                    f"r-scn-{uuid.uuid4().hex[:6]}", f"SCN-{num_suffix}", "aircrew",
                    f"{callsign}{tail_part} Mission Scanner", callsign, ac_id, "Mission Scanner",
                    secrets.token_hex(16).upper(), "/base", now,
                    claim(_normalised_email(crew_emails.get("scanner")), f"SCN-{num_suffix}")
                ))

        # 3. Ground Staff & MROs
        for s_idx, st in enumerate(staff_list, 1):
            s_role = st.get("role", "base")
            s_title = st.get("title") or f"Staff Member {s_idx}"
            s_callsign = st.get("callsign") or f"BASE {s_idx}"
            prefix = "MRO" if "radio" in s_title.lower() or "mro" in s_title.lower() else ("UDF" if s_role == "ground_team" else "STAFF")
            code = f"{prefix}-{s_idx}"
            target = "/radio" if s_role == "ground_team" else "/base"
            new_roster.append((
                f"r-staff-{uuid.uuid4().hex[:6]}", code, s_role,
                s_title, s_callsign, "", s_title,
                secrets.token_hex(16).upper(), target, now,
                claim(_normalised_email(st.get("email")), s_callsign or code)
            ))

        duplicates = {e: seats for e, seats in assigned.items() if len(seats) > 1}
        if duplicates:
            email, seats = sorted(duplicates.items())[0]
            raise ValueError("email %s is assigned to more than one seat (%s); one seat per email"
                             % (email, ", ".join(seats)))

        new_roster = [_credential_row(row) for row in new_roster]
        c.executemany(
            "INSERT INTO roster (id, code, role, title, callsign, aircraft_id, assigned_name, token, "
            "target_url, created, email) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", new_roster
        )

    return get_exercise_setup()


def enforce(role: str, request: Request) -> None:
    """Authorise a mutating call. Satisfied by session cookie or configured token."""
    # Check session
    sess = get_session_from_request(request)
    if sess:
        sess_role = sess.get("role", "")
        if sess_role in SATISFIED_BY.get(role, ()):
            return

    # Check legacy token
    accepted = [t for t in (token_for(r) for r in SATISFIED_BY[role]) if t]
    if not accepted:
        # X-11: this used to return, allowing the call. With .env.example
        # shipping every token blank that made the default deployment
        # unauthenticated, and the failure was silent - a missing token opened
        # an endpoint rather than closing it. Deny unless the operator has
        # explicitly asked for an open console on this machine.
        if dev_open():
            return
        raise HTTPException(
            503, f"This console has no {role} credential configured, so the "
                 f"action cannot be authorised. Set CAPVSAR_TOKEN_"
                 f"{role.upper()} (or log in with a roster code). For a local "
                 f"development console with no authentication, set "
                 f"CAPVSAR_DEV_OPEN=1 deliberately.")
    supplied = presented(request)
    if not supplied or not _matches(supplied, accepted):
        raise HTTPException(
            403, f"This action needs the {role} token or an authenticated session. "
                 f"Send it in the {TOKEN_HEADER} header or log in at /login.")


def enforce_read(request: Request) -> None:
    """Admit any authenticated viewer to a read endpoint (X2-1, D1.3).

    Reads used to need nothing at all, which was tolerable while they carried
    no truth. They now carry state a participant should only see in redacted
    form, and "redacted for whom" needs to know who is asking. Any roster
    session or configured token will do; an open dev console (explicit
    CAPVSAR_DEV_OPEN) lets everyone in, as it does for writes, and an
    anonymous dev viewer is shown the redacted form.
    """
    if get_session_from_request(request):
        return
    if dev_open():
        return
    raise HTTPException(
        403, "Log in at /login (or send a role token in the "
             f"{TOKEN_HEADER} header) to read exercise state.")


# A13 (review T11): how often an open socket (/ws, the radio stream) re-reads
# its session. Sessions are revoked by logout, expiry and roster regeneration,
# none of which used to reach a socket that had authenticated once.
SOCKET_RECHECK_S = 60.0


def session_satisfies(role: str, sess: dict | None) -> bool:
    """enforce()'s decision for a credential already resolved from a socket.

    A websocket carries no X-CAPVSAR-Token after the handshake, so the token
    branch reduces to: the role has no token configured and the console is an
    explicitly open dev console. Anything else needs the session's role to be
    in SATISFIED_BY, exactly as the REST routes require.
    """
    if sess and sess.get("role", "") in SATISFIED_BY.get(role, ()):
        return True
    accepted = [t for t in (token_for(r) for r in SATISFIED_BY[role]) if t]
    return not accepted and dev_open()


def socket_still_admitted(sess: dict | None, *, required: bool) -> bool:
    """Re-check of an open socket's credential (A13).

    `required` is whether a session existed when the socket was admitted. A
    socket admitted on a session must still have one; a socket admitted
    anonymously on an open dev console (the only way in without one) stays as
    long as the console is still open.
    """
    if sess:
        return True
    return not required and dev_open()


def is_instructor(request: Request) -> bool:
    """True for an authenticated instructor session or matching instructor token."""
    sess = get_session_from_request(request)
    if sess and sess.get("role") == "instructor":
        return True
    token = token_for("instructor")
    if not token:
        # Deliberately not widened for an open dev console (U-3 considered
        # it): X-1's invariant is that an anonymous viewer never receives
        # truth, dev console or not. The instructor page renders a redacted
        # DF dictionary gracefully instead.
        return False
    supplied = presented(request)
    return bool(supplied) and hmac.compare_digest(supplied.encode(), token.encode())


def require_plugin(request: Request) -> None:
    """Gate the endpoint that hands out beacon truth before reveal."""
    token = token_for("plugin")
    if not token:
        raise HTTPException(
            503, "Beacon truth is not being served: CAPVSAR_TOKEN_PLUGIN is "
                 "not set on this console.")
    supplied = presented(request)
    if not supplied or not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(403, "Incorrect plugin key.")

