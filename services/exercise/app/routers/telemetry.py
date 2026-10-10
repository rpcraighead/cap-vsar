"""
Position ingest from the sim bridge, and the bearings mission base logs.

Split out of main.py under C15-1.
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from .. import access
from ..hub import hub
from ..roles import (base_or_instructor, instructor_only, plugin_only,
                     public_scenario)
from ..settings import log
from ..roles import any_role
from ..store import _exec, _fetchone, db, db_call, row_to_scenario

from .. import propagation
from ..models import BearingIn, PositionIn

router = APIRouter()

# ------------------------------------------------------- position ingest (sim)
@router.post("/api/positions", dependencies=[plugin_only])
async def ingest(p: PositionIn):
    """
    Sim bridge -> here. Phase 4 contract.

    Returns what the direction finder would show, so the mock bridge can drive
    a DF display from this response. That synthesis is opt-in (`mock: true`)
    and is marked `synthetic` in the reply - see P-11 and app/propagation.py.
    The plugin is authoritative for every real station.
    """
    now = time.time()
    ac = {"callsign": p.callsign, "lat": p.lat, "lon": p.lon,
          "alt_ft": p.alt_ft, "hdg_true": p.hdg_true, "t": now}

    df = None
    if hub.sortie and not hub.sortie.get("stopped") and hub.scenario:
        if p.df is not None:
            # The X-Plane plugin is authoritative when it reports receiver
            # state. It alone has real aircraft attitude and terrain probes.
            df = dict(p.df)
        elif p.mock:
            # Mock bridge, explicitly. Never a real station: a stub that
            # disagrees with the cockpit is worse than a blank panel, because
            # the instructor cannot tell which one they are looking at (P-11).
            sc = hub.scenario
            elapsed = now - hub.sortie["started"]
            r = propagation.compute(
                ac,
                {"lat": sc["beacon_lat"], "lon": sc["beacon_lon"],
                 "elev_ft": sc["beacon_elev_ft"], "band": sc["band"], "power": sc["power"]},
                sc["effects"], elapsed)
            df = {"valid": r.valid, "bearing_rel": r.bearing_rel,
                  "bearing_true": r.bearing_true, "signal": round(r.signal, 4),
                  "distance_nm": round(r.distance_nm, 2), "in_cone": r.in_cone,
                  "note": r.note, "synthetic": True}
        # else: a real station reporting no receiver state. The position is
        # still tracked; the DF panel simply has nothing to show, which is the
        # honest answer and is what tells the instructor the plugin is not
        # reporting.
        if df is not None:
            ac["df"] = df
        # V2-5: record what the direction finder was showing, not just where
        # the aircraft was. Without it the debrief can score the bearings the
        # crew reported but never compare them with what the needle did.
        df_json = json.dumps(df) if df is not None else None
        await db_call(lambda: _exec(
            "INSERT INTO positions (sortie_id, callsign, t, lat, lon, alt_ft,"
            " hdg_true, df_json) VALUES (?,?,?,?,?,?,?,?)",
            (hub.sortie["id"], p.callsign, now, p.lat, p.lon, p.alt_ft,
             p.hdg_true, df_json)))

    hub.aircraft[p.callsign] = ac
    return {"ok": True, "df": df}


@router.post("/api/bearings", dependencies=[base_or_instructor])
async def log_bearing(b: BearingIn):
    """Mission base logs a bearing the crew reported. Draws a line on the map."""
    if not hub.sortie or hub.sortie.get("stopped"):
        raise HTTPException(400, "no sortie running")
    now = time.time()

    def go():
        ac = hub.aircraft.get(b.callsign)
        if ac:
            lat, lon = ac["lat"], ac["lon"]
        else:
            # The aircraft expires from the live map after 30 s of silence, but
            # a bearing passed over voice is often typed in well after that.
            # Fall back to its last recorded position for this sortie rather
            # than refusing a report the crew actually made.
            row = _fetchone(
                "SELECT lat, lon FROM positions WHERE sortie_id=? AND callsign=?"
                " ORDER BY t DESC LIMIT 1", (hub.sortie["id"], b.callsign))
            if not row:
                return None
            lat, lon = row["lat"], row["lon"]
        with db() as c:
            cursor = c.execute(
                "INSERT INTO bearings (sortie_id, callsign, t, lat, lon, bearing_true, note)"
                " VALUES (?,?,?,?,?,?,?)",
                (hub.sortie["id"], b.callsign, now, lat, lon,
                 b.bearing_true, b.note))
            bearing_id = cursor.lastrowid
        return lat, lon, bearing_id

    where = await db_call(go)
    if where is None:
        raise HTTPException(404, "no position on record for that aircraft")
    lat, lon, bearing_id = where
    await hub.broadcast({"type": "bearing", "id": bearing_id,
                         "callsign": b.callsign, "t": now, "lat": lat, "lon": lon,
                         "bearing_true": b.bearing_true, "note": b.note})
    return {"ok": True}


@router.get("/api/bearings", dependencies=[any_role])
def list_bearings(since: float = 0.0):
    """Persisted bearings missed by a reconnecting mission-base console."""
    if not hub.sortie:
        return []
    sortie_id = hub.sortie["id"]
    with db() as c:
        return [{"type": "bearing", **dict(r)} for r in c.execute(
            "SELECT id, callsign, t, lat, lon, bearing_true, note FROM bearings"
            " WHERE sortie_id=? AND t>? ORDER BY t, id", (sortie_id, since))]



