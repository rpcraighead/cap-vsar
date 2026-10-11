"""
Starting, stopping, revealing and re-tasking the exercise in progress.

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

from ..models import EffectsIn, SortieIn
from ..settings import TRACK_PAGE_DEFAULT, TRACK_PAGE_MAX

router = APIRouter()

# What a sortie keeps of its scenario's truth (X2-2).
TRUTH_SNAPSHOT_KEYS = ("beacon_lat", "beacon_lon", "beacon_elev_ft",
                       "beacon_freq_hz", "band")

# --------------------------------------------------------------------- sorties
@router.post("/api/sorties", dependencies=[instructor_only])
async def start_sortie(body: SortieIn):
    sid = body.scenario_id
    started = time.time()

    def go():
        with db() as c:
            r = c.execute("SELECT * FROM scenarios WHERE id=?", (sid,)).fetchone()
            if not r:
                return None, None
            # Close out anything still open. Starting a second sortie used to
            # leave the first with stopped=NULL forever, so the debrief list
            # showed two running exercises and rehydrate() would resume the
            # wrong one.
            c.execute("UPDATE sorties SET stopped=? WHERE stopped IS NULL",
                      (started,))
            oid = str(uuid.uuid4())[:8]
            # The sortie takes a COPY of the scenario's effects to fly with
            # (X-6). Toggling an effect now changes this sortie and nothing
            # else; the scenario keeps whatever the instructor set it up with.
            scenario = row_to_scenario(r)
            # X2-2: the sortie keeps its own copy of the beacon it flies.
            truth = {k: scenario.get(k) for k in TRUTH_SNAPSHOT_KEYS}
            earlier = c.execute(
                "SELECT id, started FROM sorties WHERE scenario_id=? AND"
                " revealed=1 ORDER BY started DESC LIMIT 1", (sid,)).fetchone()
            c.execute("INSERT INTO sorties (id, scenario_id, name, started,"
                      " effects, truth) VALUES (:id, :scenario_id, :name,"
                      " :started, :effects, :truth)",
                      {"id": oid, "scenario_id": sid,
                       "name": body.name or r["name"], "started": started,
                       "effects": json.dumps(scenario["effects"], allow_nan=False),
                       "truth": json.dumps(truth)})
            scenario["_earlier_reveal"] = dict(earlier) if earlier else None
            return oid, scenario

    # X2-9: two starts could interleave their database work and then assign
    # hub.sortie in the opposite order, leaving the hub on a sortie the
    # database had just closed. The whole change of sortie is one critical
    # section.
    async with hub.sortie_lock():
        oid, scenario = await db_call(go)
        if oid is None:
            raise HTTPException(404, "no such scenario")
        earlier = scenario.pop("_earlier_reveal", None)
        hub.scenario = scenario
        hub.sortie = {"id": oid, "scenario_id": sid,
                      "name": body.name or scenario["name"],
                      "started": started, "stopped": None, "revealed": 0}
        hub.aircraft.clear()
    log.info("sortie %s started: scenario %s (%s), band %s",
             oid, sid, scenario.get("name"), scenario.get("band"))
    await hub.broadcast_state()
    if earlier:
        # D1.6: the console cannot know whether the same crews are in the
        # room, but the instructor can.
        return {**hub.sortie, "warning": (
            f"This scenario was revealed in sortie {earlier['id']}; anyone who "
            f"saw that debrief knows where the beacon is.")}
    return hub.sortie


@router.post("/api/sorties/stop", dependencies=[instructor_only])
async def stop_sortie():
    async with hub.sortie_lock():
        sortie = hub.sortie
        if not sortie:
            raise HTTPException(400, "no sortie running")
        if sortie.get("stopped"):
            # Idempotent (X2-9): a double click, or a retry after a timeout,
            # used to re-stamp `stopped` and move the end of the sortie.
            return sortie
        stopped = time.time()
        await db_call(lambda: _exec(
            "UPDATE sorties SET stopped=? WHERE id=? AND stopped IS NULL",
            (stopped, sortie["id"])))
        sortie["stopped"] = stopped
        log.info("sortie %s stopped after %.0f s, %d aircraft reporting",
                 sortie["id"], stopped - sortie["started"], len(hub.aircraft))
    await hub.broadcast_state()
    return sortie


@router.post("/api/sorties/reveal", dependencies=[instructor_only])
async def reveal():
    """Debrief: expose beacon truth to every connected console."""
    async with hub.sortie_lock():
        sortie = hub.sortie
        if not sortie:
            raise HTTPException(400, "no sortie running")
        await db_call(lambda: _exec("UPDATE sorties SET revealed=1 WHERE id=?",
                                    (sortie["id"],)))
        sortie["revealed"] = 1
        log.info("sortie %s: beacon truth revealed to every console",
                 sortie["id"])
    await hub.broadcast_state()
    return {"revealed": True}


@router.post("/api/sorties/effects", dependencies=[instructor_only])
async def set_effects(body: EffectsIn):
    """Change an effect for the sortie in progress.

    X-6: this used to write straight into the SCENARIO row, so an instructor
    turning terrain masking off for one demonstration rewrote the scenario
    definition permanently and every future sortie from it started with
    masking off. The scenario is the exercise designer's intent; the sortie is
    what is being flown right now. Only the sortie changes here.
    """
    async with hub.sortie_lock():
        sortie = hub.sortie
        if not sortie or sortie.get("stopped") or not hub.scenario:
            raise HTTPException(400, "no sortie running")
        changes = body.changes()
        if not changes:
            return hub.scenario["effects"]
        hub.scenario["effects"].update(changes)
        effects = hub.scenario["effects"]
        effects_json = json.dumps(effects, allow_nan=False)
        await db_call(lambda: _exec("UPDATE sorties SET effects=? WHERE id=?",
                                    (effects_json, sortie["id"])))
        log.info("effects changed on sortie %s: %s", sortie["id"],
                 ", ".join(f"{k}={v!r}" for k, v in sorted(changes.items())))
    await hub.broadcast_state()
    return effects


@router.get("/api/sorties", dependencies=[any_role])
def list_sorties():
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT s.id, s.name, s.started, s.stopped, s.revealed,"
            "  (SELECT COUNT(*) FROM positions p WHERE p.sortie_id=s.id) AS points"
            " FROM sorties s ORDER BY s.started DESC LIMIT 50")]


def _beacon_of(sortie_row, scenario_row) -> dict | None:
    """The beacon this sortie flew: its own snapshot, else the scenario row."""
    raw = sortie_row["truth"] if sortie_row and "truth" in sortie_row.keys() else None
    if raw:
        try:
            t = json.loads(raw)
            if t.get("beacon_lat") is not None:
                return {"lat": t["beacon_lat"], "lon": t["beacon_lon"]}
        except (TypeError, ValueError):
            pass
    if scenario_row is not None:
        return {"lat": scenario_row["beacon_lat"], "lon": scenario_row["beacon_lon"]}
    return None


def _same_place(a: dict, b: dict) -> bool:
    return abs(a["lat"] - b["lat"]) < 1e-5 and abs(a["lon"] - b["lon"]) < 1e-5


@router.get("/api/sorties/{oid}/track", dependencies=[any_role])
def track(oid: str, since: float = 0.0, limit: int = TRACK_PAGE_DEFAULT,
          request: Request = None):
    """Replay data for a sortie.

    X-8: positions were returned unpaginated, so a long exercise made this
    endpoint slower all day and eventually large enough to stall the debrief
    view loading it. `since` and `limit` page through; the response carries
    `next_since` when there is more, and callers that ignore both still get
    the first page rather than an error.
    """
    limit = max(1, min(int(limit), TRACK_PAGE_MAX))
    with db() as c:
        rows = c.execute(
            "SELECT callsign, t, lat, lon, alt_ft, hdg_true, df_json FROM positions"
            " WHERE sortie_id=? AND t > ? ORDER BY t LIMIT ?",
            (oid, since, limit)).fetchall()
        brgs = c.execute(
            "SELECT callsign, t, lat, lon, bearing_true, note FROM bearings WHERE sortie_id=? ORDER BY t",
            (oid,)).fetchall()
        msgs = c.execute(
            "SELECT t, sender, recipient, body FROM messages WHERE sortie_id=? ORDER BY t",
            (oid,)).fetchall()
        s = c.execute("SELECT * FROM sorties WHERE id=?", (oid,)).fetchone()
        sc = c.execute("SELECT * FROM scenarios WHERE id=?", (s["scenario_id"],)).fetchone() if s else None
    # Truth belongs to the debrief. Until this sortie is revealed the replay
    # gets no beacon, which is what the debrief view's "never revealed"
    # message was always written for.
    revealed = bool(s and s["revealed"])
    beacon = _beacon_of(s, sc) if revealed else None
    # X2-2: a revealed sortie on a scenario that is being flown right now
    # would give the live crews the answer by way of the debrief list. Only
    # the instructor sees it until the running sortie is itself revealed.
    withheld = False
    live = hub.sortie
    if (revealed and beacon and live and not live.get("stopped")
            and live["id"] != oid and not live.get("revealed")
            and not (request is not None and access.is_instructor(request))):
        live_beacon = hub.scenario and {"lat": hub.scenario.get("beacon_lat"),
                                        "lon": hub.scenario.get("beacon_lon")}
        if live_beacon and live_beacon["lat"] is not None and _same_place(beacon, live_beacon):
            withheld, revealed, beacon = True, False, None
    positions = []
    for r in rows:
        row = dict(r)
        raw = row.pop("df_json", None)
        # The DF telemetry is beacon truth in another form: bearing_true plus
        # distance_nm from a known position is a fix. It travels only once the
        # sortie is revealed, exactly like the beacon itself (V2-5).
        if revealed and raw:
            try:
                row["df"] = json.loads(raw)
            except (TypeError, ValueError):
                pass
        positions.append(row)
    return {
        "positions": positions,
        # None when this is the last page. The debrief follows it until it is.
        "next_since": positions[-1]["t"] if len(positions) == limit else None,
        "position_limit": limit,
        "bearings": [dict(r) for r in brgs],
        "messages": [dict(r) for r in msgs],
        "revealed": revealed,
        "withheld": withheld,
        "beacon": beacon,
    }


