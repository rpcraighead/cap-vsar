"""
Scenario definitions: what the exercise designer set up, not what is being flown.

Split out of main.py under C15-1.
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, HTTPException, Request

from .. import access
from ..hub import hub
from ..roles import instructor_only, public_scenario
from ..roles import any_role
from ..store import db, db_call, row_to_scenario

from ..models import ScenarioIn

router = APIRouter()

# ------------------------------------------------------------------- scenarios
@router.get("/api/scenarios", dependencies=[any_role])
def list_scenarios(request: Request):
    """Scenario definitions. Beacon positions only for a presented instructor
    token — the picker needs names and notes, not the answer."""
    truth = access.is_instructor(request)
    with db() as c:
        rows = [row_to_scenario(r) for r in
                c.execute("SELECT * FROM scenarios ORDER BY created")]
    return [public_scenario(r, include_truth=truth) for r in rows]


@router.post("/api/scenarios", dependencies=[instructor_only])
def create_scenario(s: ScenarioIn):
    sid = str(uuid.uuid4())[:8]
    with db() as c:
        # Named columns: the positional form bound fifteen values to whatever
        # order the table happened to have, so the next ALTER TABLE would have
        # written alert_kind into alert_text and nothing would have raised.
        c.execute(
            "INSERT INTO scenarios (id, name, notes, beacon_lat, beacon_lon,"
            " beacon_elev_ft, band, beacon_freq_hz, power, effects, created,"
            " alert_kind, alert_text, alert_lat, alert_lon, alert_radius_nm)"
            " VALUES (:id, :name, :notes, :beacon_lat, :beacon_lon,"
            " :beacon_elev_ft, :band, :beacon_freq_hz, :power, :effects,"
            " :created, :alert_kind, :alert_text, :alert_lat, :alert_lon,"
            " :alert_radius_nm)",
            {"id": sid, "name": s.name, "notes": s.notes,
             "beacon_lat": s.beacon_lat, "beacon_lon": s.beacon_lon,
             "beacon_elev_ft": s.beacon_elev_ft, "band": s.band,
             "beacon_freq_hz": s.beacon_freq_hz,
             "power": s.power, "effects": json.dumps(s.effects.changes(), allow_nan=False),
             "created": time.time(), "alert_kind": s.alert_kind,
             "alert_text": s.alert_text, "alert_lat": s.alert_lat,
             "alert_lon": s.alert_lon, "alert_radius_nm": s.alert_radius_nm})
    return {"id": sid}


@router.delete("/api/scenarios/{sid}", dependencies=[instructor_only])
async def delete_scenario(sid: str):
    """Delete a scenario definition. Refused while a sortie is flying it.

    X2-11: deleting the scenario of a running sortie stranded it: rehydrate()
    returns early when the scenario row is gone, so after a restart the sortie
    was never resumed and never closed.
    """
    def go():
        with db() as c:
            open_sortie = c.execute(
                "SELECT id FROM sorties WHERE scenario_id=? AND stopped IS NULL"
                " LIMIT 1", (sid,)).fetchone()
            if open_sortie:
                return open_sortie["id"]
            c.execute("DELETE FROM scenarios WHERE id=?", (sid,))
        return None

    async with hub.sortie_lock():
        blocking = await db_call(go)
    if blocking:
        raise HTTPException(
            409, f"Sortie {blocking} is still running on this scenario. "
                 f"Stop it before deleting the scenario.")
    return {"ok": True}


