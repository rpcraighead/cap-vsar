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
2. Shared-secret environment tokens (`CAPVSAR_TOKEN_*`) via `X-CAPVSAR-Token` header
   or `?token=` query param (preserved for backward compatibility with scripts/plugin).
"""
from __future__ import annotations

import hmac
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager

from fastapi import HTTPException, Request

TOKEN_HEADER = "X-CAPVSAR-Token"
SESSION_COOKIE = "capvsar_session"
ROLES = ("instructor", "base", "aircrew", "ground_team", "plugin")

# Which roles/tokens satisfy an access requirement.
# An instructor may act in any role; base staff can direct ground teams.
SATISFIED_BY: dict[str, tuple[str, ...]] = {
    "instructor": ("instructor",),
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
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_auth_db() -> None:
    """Ensure roster, session, and exercise configuration tables exist."""
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
        # If roster is completely empty, seed standard starter codes
        count = c.execute("SELECT COUNT(*) FROM roster").fetchone()[0]
        if count == 0:
            now = time.time()
            starter = [
                ("r-instr", "INSTR-1", "instructor", "Exercise Director / Evaluator", "INSTRUCTOR", "", "Instructor", uuid.uuid4().hex[:12], "/", now),
                ("r-mro1", "MRO-1", "base", "Mission Radio Operator 1", "BASE MRO 1", "", "MRO 1", uuid.uuid4().hex[:12], "/base", now),
                ("r-plt423", "PLT-423", "aircrew", "CAP 423 SAR Mission Pilot", "CAP 423", "ac-1", "Pilot", uuid.uuid4().hex[:12], "/base", now),
                ("r-obs423", "OBS-423", "aircrew", "CAP 423 Mission Observer (TDFM/DF)", "CAP 423", "ac-1", "Observer", uuid.uuid4().hex[:12], "/base", now),
                ("r-udf1", "UDF-1", "ground_team", "Ground Team / UDF 1 Leader", "UDF 1", "", "Ground Team 1", uuid.uuid4().hex[:12], "/radio", now),
            ]
            c.executemany(
                "INSERT OR IGNORE INTO roster (id, code, role, title, callsign, aircraft_id, assigned_name, token, target_url, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", starter
            )


def token_for(role: str) -> str:
    return os.environ.get(f"CAPVSAR_TOKEN_{role.upper()}", "").strip()


def unconfigured() -> list[str]:
    """Roles with no token set — their endpoints are unauthenticated."""
    return [r for r in ("instructor", "base", "plugin") if not token_for(r)]


def presented(request: Request) -> str:
    return (request.headers.get(TOKEN_HEADER)
            or request.query_params.get("token")
            or "").strip()


def _matches(supplied: str, accepted: list[str]) -> bool:
    ok = False
    for token in accepted:
        if hmac.compare_digest(supplied.encode(), token.encode()):
            ok = True
    return ok


def get_session_from_request(request: Request) -> dict | None:
    """Resolve an active session from cookies, Bearer header, or query param."""
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
                }

    # 2. Check session ID from cookie or Bearer authorization
    sess_id = request.cookies.get(SESSION_COOKIE)
    if not sess_id:
        auth_hdr = request.headers.get("Authorization", "").strip()
        if auth_hdr.startswith("Bearer "):
            sess_id = auth_hdr[7:].strip()
    if not sess_id:
        sess_id = request.query_params.get("session", "").strip()

    if not sess_id:
        return None

    init_auth_db()
    now = time.time()
    with auth_db() as c:
        row = c.execute(
            "SELECT session_id, code, role, title, callsign, aircraft_id, target_url, expires "
            "FROM sessions WHERE session_id=? AND expires>?",
            (sess_id, now)
        ).fetchone()
        if row:
            return dict(row)
    return None


def create_session(code: str, role: str, title: str, callsign: str = "",
                   aircraft_id: str = "", target_url: str = "") -> str:
    """Create a persistent session token lasting 24 hours."""
    init_auth_db()
    sess_id = uuid.uuid4().hex
    now = time.time()
    expires = now + 86400.0  # 24 hours
    with auth_db() as c:
        c.execute(
            "INSERT INTO sessions (session_id, code, role, title, callsign, aircraft_id, target_url, created, expires) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sess_id, code, role, title, callsign, aircraft_id, target_url, now, expires)
        )
    return sess_id


def delete_session(sess_id: str) -> None:
    init_auth_db()
    with auth_db() as c:
        c.execute("DELETE FROM sessions WHERE session_id=?", (sess_id,))


def authenticate_code(code: str) -> tuple[dict, str] | None:
    """Validate a participant access code (case-insensitive) and return (roster_row, session_id)."""
    init_auth_db()
    clean_code = code.strip().upper()
    now = time.time()

    # Instructor shortcut via configured environment token
    instr_token = token_for("instructor")
    if clean_code in ("ADMIN", "INSTRUCTOR") and instr_token:
        sess_id = create_session(clean_code, "instructor", "Exercise Director", "INSTRUCTOR", "", "/")
        return ({"code": clean_code, "role": "instructor", "title": "Exercise Director", "callsign": "INSTRUCTOR", "target_url": "/"}, sess_id)

    with auth_db() as c:
        row = c.execute(
            "SELECT id, code, role, title, callsign, aircraft_id, assigned_name, target_url "
            "FROM roster WHERE UPPER(code)=?",
            (clean_code,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        c.execute("UPDATE roster SET last_login=? WHERE id=?", (now, d["id"]))

    sess_id = create_session(
        code=d["code"],
        role=d["role"],
        title=d["title"],
        callsign=d.get("callsign") or "",
        aircraft_id=d.get("aircraft_id") or "",
        target_url=d.get("target_url") or "/"
    )
    return (d, sess_id)


def get_roster() -> list[dict]:
    init_auth_db()
    with auth_db() as c:
        rows = c.execute(
            "SELECT id, code, role, title, callsign, aircraft_id, assigned_name, token, target_url, created, last_login "
            "FROM roster ORDER BY created, id"
        ).fetchall()
        return [dict(r) for r in rows]


def get_exercise_setup() -> dict:
    init_auth_db()
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


def save_exercise_setup(name: str, num_aircraft: int, aircraft_list: list[dict], staff_list: list[dict]) -> dict:
    """Save exercise configuration and generate participant roster with codes and invite URLs."""
    init_auth_db()
    now = time.time()
    config_obj = {"aircraft": aircraft_list, "staff": staff_list}
    config_json = json.dumps(config_obj)

    with auth_db() as c:
        # Mark previous configs inactive
        c.execute("UPDATE exercise_config SET active=0")
        setup_id = f"setup-{uuid.uuid4().hex[:8]}"
        c.execute(
            "INSERT INTO exercise_config (id, name, num_aircraft, config_json, active, updated) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (setup_id, name, num_aircraft, config_json, now)
        )
        # Clear previous dynamic roster
        c.execute("DELETE FROM roster")

        new_roster = []
        # 1. Instructor
        new_roster.append((
            f"r-instr-{uuid.uuid4().hex[:6]}", "INSTR-1", "instructor",
            "Exercise Director / Evaluator", "INSTRUCTOR", "", "Instructor",
            uuid.uuid4().hex[:12], "/", now
        ))

        # 2. Aircraft crews
        for ac_idx, ac in enumerate(aircraft_list, 1):
            ac_id = ac.get("id") or f"ac-{ac_idx}"
            callsign = ac.get("callsign") or f"CAP {420 + ac_idx}"
            tail = ac.get("tail") or "CAP 487"
            df_model = ac.get("df_model") or "Becker SAR-DF 517"
            num_suffix = callsign.split()[-1] if " " in callsign else str(ac_idx)

            crew_roles = ac.get("crew") or ["pilot", "observer"]
            if "pilot" in crew_roles:
                new_roster.append((
                    f"r-plt-{uuid.uuid4().hex[:6]}", f"PLT-{num_suffix}", "aircrew",
                    f"{callsign} ({tail}) SAR Mission Pilot", callsign, ac_id, "Mission Pilot",
                    uuid.uuid4().hex[:12], "/base", now
                ))
            if "observer" in crew_roles:
                new_roster.append((
                    f"r-obs-{uuid.uuid4().hex[:6]}", f"OBS-{num_suffix}", "aircrew",
                    f"{callsign} ({tail}) Mission Observer [{df_model}]", callsign, ac_id, "Mission Observer",
                    uuid.uuid4().hex[:12], "/base", now
                ))
            if "scanner" in crew_roles:
                new_roster.append((
                    f"r-scn-{uuid.uuid4().hex[:6]}", f"SCN-{num_suffix}", "aircrew",
                    f"{callsign} ({tail}) Mission Scanner", callsign, ac_id, "Mission Scanner",
                    uuid.uuid4().hex[:12], "/base", now
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
                uuid.uuid4().hex[:12], target, now
            ))

        c.executemany(
            "INSERT INTO roster (id, code, role, title, callsign, aircraft_id, assigned_name, token, target_url, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", new_roster
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
        # If no tokens are configured and no session is active, open for local dev
        return
    supplied = presented(request)
    if not supplied or not _matches(supplied, accepted):
        raise HTTPException(
            403, f"This action needs the {role} token or an authenticated session. "
                 f"Send it in the {TOKEN_HEADER} header or log in at /login.")


def is_instructor(request: Request) -> bool:
    """True for an authenticated instructor session or matching instructor token."""
    sess = get_session_from_request(request)
    if sess and sess.get("role") == "instructor":
        return True
    token = token_for("instructor")
    if not token:
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

