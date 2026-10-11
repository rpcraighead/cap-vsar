"""
SQLite for the exercise console: connections, schema, and retention (C15-1).

Every route used to reach into the database directly from main.py, so the
schema, the WAL settings, the migrations and the retention policy were spread
through the same file as the HTTP handlers. This is the whole data layer.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from . import access
from . import settings
from .settings import ALERT_COLUMNS, DB, SEED, log


@contextmanager
def db():
    """A connection that commits on success, rolls back on error, and closes.

    `with sqlite3.connect(...)` commits but never closes, which leaked a
    connection per request. The timeout matters because the radio bridge shares
    this process: a lock wait here is a gap in someone's transmission.
    """
    c = sqlite3.connect(DB, timeout=5.0)
    c.row_factory = sqlite3.Row
    # FE-9: `synchronous` is a per-CONNECTION pragma - only `journal_mode`
    # persists in the file. init_db() set it once and every later connection
    # silently reverted to FULL, so each commit fsynced: exactly the stall X-3
    # set out to remove, moved into a worker thread rather than fixed. WAL plus
    # NORMAL is the correct pairing and is durable against process crash (only
    # a power loss can lose the last commits, which for exercise telemetry is
    # the right trade).
    c.execute("PRAGMA synchronous=NORMAL")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def _exec(sql: str, params: tuple = ()):
    with db() as c:
        c.execute(sql, params)


def _fetchone(sql: str, params: tuple = ()):
    with db() as c:
        return c.execute(sql, params).fetchone()


async def db_call(fn, *args):
    """Run a blocking database function off the event loop.

    Every handler here shares one loop with the Mumble bridge's 20 ms audio
    frames (radio.py). A synchronous commit fsyncing on a bind mount stalls
    that loop, trips the bridge's buffer check and unkeys the operator
    mid-transmission, so database work belongs in a worker thread.
    """
    return await run_in_threadpool(fn, *args)


# X-8: the console had no logging at all - two print() calls, one of them a
# security warning. After an exercise the only record of what the instructor
# did was whatever anyone wrote down. Sortie lifecycle events (start, stop,
# reveal, effect change) go through here because that is the spine an
# after-action review reads.

def init_db():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        # WAL lets the 1 Hz ticker and the debrief read while a sortie writes,
        # instead of serialising behind it. The setting lives in the database
        # file, so this runs once and every later connection inherits it.
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS scenarios (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, notes TEXT,
            beacon_lat REAL, beacon_lon REAL, beacon_elev_ft REAL,
            band TEXT, power REAL, effects TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS sorties (
            id TEXT PRIMARY KEY, scenario_id TEXT, name TEXT,
            started REAL, stopped REAL, revealed INTEGER DEFAULT 0,
            effects TEXT);
        CREATE TABLE IF NOT EXISTS positions (
            sortie_id TEXT, callsign TEXT, t REAL,
            lat REAL, lon REAL, alt_ft REAL, hdg_true REAL);
        CREATE INDEX IF NOT EXISTS positions_sortie ON positions(sortie_id, t);
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sortie_id TEXT, t REAL,
            sender TEXT, recipient TEXT, body TEXT);
        CREATE TABLE IF NOT EXISTS bearings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sortie_id TEXT, callsign TEXT,
            t REAL, lat REAL, lon REAL, bearing_true REAL, note TEXT);
        """)
        # additive migration for databases created before the alert model
        existing = {r["name"] for r in c.execute("PRAGMA table_info(scenarios)")}
        for col, typ in ALERT_COLUMNS:
            if col not in existing:
                c.execute(f"ALTER TABLE scenarios ADD COLUMN {col} {typ}")
        # X-6: effects are a property of the sortie being flown, not of the
        # scenario definition. Older databases have the column missing and
        # their scenario rows carry whatever the last exercise left behind;
        # nothing is migrated back out of those rows, because there is no way
        # to tell an instructor's deliberate default from an effect they
        # toggled once mid-exercise three weeks ago.
        sortie_cols = {r["name"] for r in c.execute("PRAGMA table_info(sorties)")}
        if "effects" not in sortie_cols:
            c.execute("ALTER TABLE sorties ADD COLUMN effects TEXT")
        # X2-2: the beacon a sortie flew is a property of the sortie. /track
        # used to read it back from the scenario row, so a scenario that was
        # edited or reused after the sortie answered with the wrong beacon,
        # and a revealed old sortie disclosed the one now being flown.
        # Sorties that predate the column fall back to the scenario row.
        if "truth" not in sortie_cols:
            c.execute("ALTER TABLE sorties ADD COLUMN truth TEXT")
        # V2-5: the recorded track held only where the aircraft was, never what
        # the direction finder was showing at the time. The debrief could
        # therefore score the bearings the crew *reported* but never compare
        # them against what the needle actually did - which is the teaching
        # moment the whole exercise exists for. The plugin already sends this
        # on every position report; it was being thrown away.
        pos_cols = {r["name"] for r in c.execute("PRAGMA table_info(positions)")}
        if "df_json" not in pos_cols:
            c.execute("ALTER TABLE positions ADD COLUMN df_json TEXT")
        # A scenario may name the exact 406 channel the beacon transmits on.
        # Without it a 406 beacon is assumed to be on 406.025, which the Becker
        # always hears - so the Becker-vs-RT-600 coverage lesson, the reason
        # both heads were built, cannot be set up from the console (B-5).
        scen_cols = {r["name"] for r in c.execute("PRAGMA table_info(scenarios)")}
        if "beacon_freq_hz" not in scen_cols:
            c.execute("ALTER TABLE scenarios ADD COLUMN beacon_freq_hz INTEGER")
    access.init_auth_db()



def prune_positions():
    """Drop position history for sorties older than the retention window (X-8).

    `positions` had no retention at all, so it grew for the life of the
    console and /track got slower every exercise. Bearings and messages are
    kept: they are the written record, they are small, and an after-action
    review reads them. Positions are the bulk, and a replay of a sortie from
    six months ago is not what the retention window is for.
    """
    keep_sorties = settings.POSITION_RETENTION_SORTIES
    if keep_sorties <= 0:
        return
    try:
        with db() as c:
            keep = [r["id"] for r in c.execute(
                "SELECT id FROM sorties ORDER BY started DESC LIMIT ?",
                (keep_sorties,))]
            if not keep:
                return
            marks = ",".join("?" * len(keep))
            n = c.execute(
                f"DELETE FROM positions WHERE sortie_id NOT IN ({marks})",
                keep).rowcount
        if n:
            log.info("pruned %d position rows outside the last %d sorties",
                     n, keep_sorties)
    except sqlite3.Error as e:
        log.warning("position prune failed: %s", e)



def load_effects(raw) -> dict:
    """Parse a stored effects blob, dropping anything JSON cannot carry (X2-3).

    Rows written before the create route validated its body can hold a bare
    NaN or Infinity (Python's json writes and reads them). One such row made
    /api/scenarios and /api/state fail for everyone, so a non-finite value is
    discarded here and the engine's own default applies.
    """
    effects = json.loads(raw or "{}", parse_constant=lambda _c: None)
    return {k: v for k, v in effects.items() if v is not None}


def row_to_scenario(r) -> dict:
    d = dict(r)
    d["effects"] = load_effects(d["effects"])
    return d


