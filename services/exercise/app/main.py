"""
CAP V-SAR Exercise Console.

Instructor-facing service: hold beacon truth, run a sortie, ingest aircraft
positions, and serve a live map. The position ingest endpoint is the contract
the X-Plane sim bridge implements.

C15-1: this file used to be all of it - schema, migrations, truth filtering,
role checks, the WebSocket hub, the retention policy and every route on one
page, which is why X-3 happened here and why the CalTopo relay had nowhere
obvious to land. The pieces now live next door:

    settings.py   what the console reads from its environment
    store.py      SQLite: connections, schema, retention
    roles.py      who may call what, and how much truth they see
    hub.py        live sortie state, the browser fan-out, the 1 Hz ticker
    models.py     every request body
    routers/      the routes themselves, grouped by what they are about

What is left here is assembly: build the app, run the lifespan, mount the
routers. Names that other modules and the test suite import from `app.main`
are re-exported at the bottom, so this split is not an API change.
"""
from __future__ import annotations
import asyncio, json, logging, math, os, sqlite3, time, uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from urllib.parse import urlsplit

from fastapi import (Depends, FastAPI, HTTPException, Request, Response,
                     WebSocket, WebSocketDisconnect)
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import access, propagation, radio
from .settings import (ALERT_COLUMNS, DB, DEFAULT_EFFECTS, LOG_LEVEL,
                       POSITION_RETENTION_SORTIES, SEED, STATIC,
                       TRACK_PAGE_DEFAULT, TRACK_PAGE_MAX, log)
from .store import (_exec, _fetchone, db, db_call, init_db, prune_positions,
                    row_to_scenario)
from .roles import (base_or_instructor, instructor_only, plugin_only,
                    public_scenario, role_gate)
from .hub import Hub, hub, ticker
from .models import (BearingIn, EffectsIn, LoginPayload, MessageIn, PositionIn,
                     ScenarioIn, SetupPayload, SortieIn)

def rehydrate():
    """Reload the running sortie into memory at startup.

    Live state was in-process only, so a container restart mid-exercise
    orphaned the sortie: positions were discarded because hub.sortie was None,
    /api/messages answered empty because it reads memory rather than the table,
    and the row kept stopped=NULL forever. An exercise cannot depend on the
    console never restarting.
    """
    with db() as c:
        row = c.execute("SELECT * FROM sorties WHERE stopped IS NULL"
                        " ORDER BY started DESC LIMIT 1").fetchone()
        if not row:
            return
        sc = c.execute("SELECT * FROM scenarios WHERE id=?",
                       (row["scenario_id"],)).fetchone()
        if not sc:
            return
        hub.sortie = dict(row)
        hub.scenario = row_to_scenario(sc)
        # The sortie's own effects win over the scenario's defaults: they are
        # what was being flown when the console went down (X-6). Sorties that
        # predate the column have none, and fall back to the scenario.
        sortie_effects = dict(row).get("effects")
        if sortie_effects:
            try:
                hub.scenario["effects"] = json.loads(sortie_effects)
            except (TypeError, ValueError):
                pass
        hub.sortie.pop("effects", None)
        hub.messages = [
            {"type": "message", **dict(m)} for m in reversed(c.execute(
                "SELECT t, sender, recipient, body FROM messages"
                " WHERE sortie_id=? ORDER BY t DESC LIMIT 100",
                (row["id"],)).fetchall())]
    # Aircraft are deliberately not restored: their positions are seconds old
    # and the plugins will re-report within a few seconds anyway. A stale
    # aircraft on the map is worse than a briefly empty one.
    log.info("resumed sortie %s (%d messages)", hub.sortie["id"],
             len(hub.messages))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with db() as c:
        if not c.execute("SELECT 1 FROM scenarios LIMIT 1").fetchone():
            c.execute(
                "INSERT INTO scenarios (id, name, notes, beacon_lat,"
                " beacon_lon, beacon_elev_ft, band, power, effects, created,"
                " alert_kind, alert_text, alert_lat, alert_lon,"
                " alert_radius_nm) VALUES (:id, :name, :notes, :beacon_lat,"
                " :beacon_lon, :beacon_elev_ft, :band, :power, :effects,"
                " :created, :alert_kind, :alert_text, :alert_lat, :alert_lon,"
                " :alert_radius_nm)",
                dict(SEED, id=str(uuid.uuid4())[:8],
                     effects=json.dumps(SEED["effects"]), created=time.time()))
    wide_open = access.unconfigured()
    if wide_open:
        log.warning(
            "no token configured for %s - those endpoints accept anyone who "
            "can reach this console. Set CAPVSAR_TOKEN_INSTRUCTOR / _BASE / "
            "_PLUGIN in .env before an exercise.", ", ".join(wide_open))
    rehydrate()
    prune_positions()
    task = asyncio.create_task(ticker())
    log.info("console ready (log level %s, keeping %d sorties of positions)",
             LOG_LEVEL, POSITION_RETENTION_SORTIES)
    try:
        yield
    finally:
        # X-8: the ticker was never cancelled, so a shutdown left it running
        # against a closing event loop and the container's stop looked like a
        # hang until Docker's timeout killed it.
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        log.info("console shut down")



app = FastAPI(title="CAP V-SAR Exercise Console", lifespan=lifespan)



# ---------------------------------------------------------------- assembly
#
# C15-1: the routes live in routers/, grouped by what they are about. Order
# matters in one place only - the static mount and the page routes come after
# the API routers, exactly as they did when this was one file.
from .routers import (auth, comms, pages, scenarios, sorties, system,
                      telemetry)                                # noqa: E402

for _router in (scenarios.router, sorties.router, telemetry.router,
                comms.router, system.router):
    app.include_router(_router)

app.include_router(radio.router)
app.include_router(auth.router)

app.mount("/static", StaticFiles(directory=STATIC), name="static")

app.include_router(pages.router)


# Re-exported so `app.main.<name>` keeps working for the test suite and for
# anything that imported them before the split.
__all__ = [
    "app", "hub", "db", "db_call", "_exec", "_fetchone", "init_db",
    "prune_positions", "rehydrate", "row_to_scenario", "public_scenario",
    "ticker", "lifespan",
]

# The handlers the tests call directly rather than over HTTP.
list_messages = comms.list_messages
list_bearings = telemetry.list_bearings
track = sorties.track
