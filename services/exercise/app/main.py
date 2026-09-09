"""
CAP V-SAR Exercise Console.

Instructor-facing service: hold beacon truth, run a sortie, ingest aircraft
positions, and serve a live map. The position ingest endpoint is the contract
the X-Plane sim bridge will implement in Phase 4.
"""
from __future__ import annotations
import asyncio, json, math, os, sqlite3, time, uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from urllib.parse import urlsplit

from fastapi import (Depends, FastAPI, HTTPException, Request, WebSocket,
                     WebSocketDisconnect)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import access, propagation, radio

DB = os.environ.get("CAPVSAR_DB", "/data/exercise.db")
STATIC = Path(__file__).parent / "static"


# ---------------------------------------------------------------- persistence
@contextmanager
def db():
    """A connection that commits on success, rolls back on error, and closes.

    `with sqlite3.connect(...)` commits but never closes, which leaked a
    connection per request. The timeout matters because the radio bridge shares
    this process: a lock wait here is a gap in someone's transmission.
    """
    c = sqlite3.connect(DB, timeout=5.0)
    c.row_factory = sqlite3.Row
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


ALERT_COLUMNS = [
    ("alert_kind", "TEXT"), ("alert_text", "TEXT"),
    ("alert_lat", "REAL"), ("alert_lon", "REAL"), ("alert_radius_nm", "REAL"),
]


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
            started REAL, stopped REAL, revealed INTEGER DEFAULT 0);
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


DEFAULT_EFFECTS = {
    "radio_horizon": True, "burst_cadence": True,
    "cone_of_confusion": True, "multipath": False,
    "multipath_offset_deg": 40.0,
    "airframe_shadowing": False,
    "df_antenna_profile": "c182_belly",
    "wing_null_max_loss_db": 24.0,
}

SEED = {
    "name": "C-1  Palomar ILS - 121.5 ELT at ESCON",
    "notes": ("121.5 ELT on the ground at the ESCON intermediate fix on the KCRQ "
              "ILS, where the plate calls for 3,300 ft. No satellite alert. SoCal "
              "Approach protects the approach altitude and issues blocks above and "
              "below. Drawn from an actual unit sortie."),
    "beacon_lat": 33.1700, "beacon_lon": -117.0792, "beacon_elev_ft": 700.0,
    "band": "121.5", "power": 1.0,
    "effects": {**DEFAULT_EFFECTS, "burst_cadence": False, "multipath": True},
    # The alert is what mission base is given. It is NOT the beacon position -
    # 121.5 has not been satellite-monitored since 2009, so this one arrives as
    # reports with no position at all.
    "alert_kind": "121.5 pilot report - no position",
    "alert_text": ("Multiple reports of a 121.5 MHz ELT signal in the McClellan-Palomar "
                   "(KCRQ) approach area. No satellite alert and no Doppler position. "
                   "Search area is the approach corridor. Expect SoCal Approach to "
                   "protect the ILS altitude - request blocks above and below."),
    "alert_lat": 33.1283, "alert_lon": -117.2800, "alert_radius_nm": 12.0,
}


# ------------------------------------------------------------- truth filtering
# The beacon position is the answer to the exercise. Every response that could
# carry it goes through public_scenario(), so there is one place to audit
# rather than a decision at each endpoint — the bug this replaces was three
# endpoints that each returned the row straight from SQLite.
TRUTH_FIELDS = ("beacon_lat", "beacon_lon", "beacon_elev_ft")


def public_scenario(sc: dict, *, include_truth: bool) -> dict:
    """A scenario safe to send to a browser. Truth only when explicitly allowed."""
    d = dict(sc)
    if not include_truth:
        for f in TRUTH_FIELDS:
            d.pop(f, None)
    return d


def role_gate(role: str):
    def dep(request: Request) -> None:
        access.enforce(role, request)
    return dep


instructor_only = Depends(role_gate("instructor"))
base_or_instructor = Depends(role_gate("base"))
plugin_only = Depends(role_gate("plugin"))


# ------------------------------------------------------------------ live state
class Hub:
    SEND_TIMEOUT_S = 1.0        # a console that cannot take a frame in a second
                                # is not going to catch up on the next one

    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.aircraft: dict[str, dict] = {}
        self.sortie: dict | None = None
        self.scenario: dict | None = None
        self.messages: list[dict] = []

    async def broadcast(self, msg: dict):
        """Send to every console at once, and drop anyone who cannot keep up.

        Sequential awaits meant one wedged tablet blocked the 1 Hz ticker and
        every handler that broadcasts. A half-open socket never raises, so it
        needs a timeout rather than an exception to be noticed.
        """
        if not self.clients:
            return
        text = json.dumps(msg)

        async def send(ws):
            try:
                await asyncio.wait_for(ws.send_text(text), self.SEND_TIMEOUT_S)
            except Exception:
                return ws          # dead, wedged, or too slow - same outcome
            return None

        for ws in await asyncio.gather(*(send(w) for w in list(self.clients))):
            if ws is not None:
                self.clients.discard(ws)

    def snapshot(self, include_truth: bool = False) -> dict:
        s = {
            "sortie": self.sortie,
            "scenario": None,
            "aircraft": list(self.aircraft.values()),
            "server_time": time.time(),
        }
        if self.scenario:
            revealed = bool(self.sortie and self.sortie.get("revealed"))
            s["scenario"] = public_scenario(
                self.scenario, include_truth=include_truth or revealed)
        return s


hub = Hub()


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
        hub.messages = [
            {"type": "message", **dict(m)} for m in reversed(c.execute(
                "SELECT t, sender, recipient, body FROM messages"
                " WHERE sortie_id=? ORDER BY t DESC LIMIT 100",
                (row["id"],)).fetchall())]
    # Aircraft are deliberately not restored: their positions are seconds old
    # and the plugins will re-report within a few seconds anyway. A stale
    # aircraft on the map is worse than a briefly empty one.
    print(f"[capvsar] resumed sortie {hub.sortie['id']} "
          f"({len(hub.messages)} messages)", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with db() as c:
        if not c.execute("SELECT 1 FROM scenarios LIMIT 1").fetchone():
            c.execute(
                "INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4())[:8], SEED["name"], SEED["notes"],
                 SEED["beacon_lat"], SEED["beacon_lon"], SEED["beacon_elev_ft"],
                 SEED["band"], SEED["power"], json.dumps(SEED["effects"]), time.time(),
                 SEED["alert_kind"], SEED["alert_text"],
                 SEED["alert_lat"], SEED["alert_lon"], SEED["alert_radius_nm"]))
    wide_open = access.unconfigured()
    if wide_open:
        print("[capvsar] WARNING: no token configured for "
              f"{', '.join(wide_open)} - those endpoints accept anyone who can "
              "reach this console. Set CAPVSAR_TOKEN_INSTRUCTOR / _BASE / "
              "_PLUGIN in .env before an exercise.", flush=True)
    rehydrate()
    asyncio.create_task(ticker())
    yield


async def ticker():
    """Push state to consoles, and expire aircraft that stop reporting."""
    while True:
        await asyncio.sleep(1.0)
        now = time.time()
        stale = [k for k, a in hub.aircraft.items() if now - a["t"] > 30]
        for k in stale:
            hub.aircraft.pop(k, None)
        if hub.clients:
            await hub.broadcast({"type": "state", **hub.snapshot()})


app = FastAPI(title="CAP V-SAR Exercise Console", lifespan=lifespan)


# ---------------------------------------------------------------------- models
class ScenarioIn(BaseModel):
    name: str
    notes: str = ""
    beacon_lat: float
    beacon_lon: float
    beacon_elev_ft: float = 0.0
    band: str = Field("121.5", pattern="^(121\\.5|243|406)$")
    power: float = 1.0
    effects: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_EFFECTS))
    alert_kind: str = ""
    alert_text: str = ""
    alert_lat: float | None = None
    alert_lon: float | None = None
    alert_radius_nm: float | None = None


class PositionIn(BaseModel):
    """What the sim bridge POSTs. Phase 4 contract - keep stable."""
    callsign: str
    lat: float
    lon: float
    alt_ft: float
    hdg_true: float = 0.0
    df: dict[str, Any] | None = None


class BearingIn(BaseModel):
    callsign: str
    bearing_true: float
    note: str = ""


# ------------------------------------------------------------------- scenarios
def row_to_scenario(r) -> dict:
    d = dict(r)
    d["effects"] = json.loads(d["effects"] or "{}")
    return d


@app.get("/api/scenarios")
def list_scenarios(request: Request):
    """Scenario definitions. Beacon positions only for a presented instructor
    token — the picker needs names and notes, not the answer."""
    truth = access.is_instructor(request)
    with db() as c:
        rows = [row_to_scenario(r) for r in
                c.execute("SELECT * FROM scenarios ORDER BY created")]
    return [public_scenario(r, include_truth=truth) for r in rows]


@app.post("/api/scenarios", dependencies=[instructor_only])
def create_scenario(s: ScenarioIn):
    sid = str(uuid.uuid4())[:8]
    with db() as c:
        c.execute("INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (sid, s.name, s.notes, s.beacon_lat, s.beacon_lon,
                   s.beacon_elev_ft, s.band, s.power, json.dumps(s.effects), time.time(),
                   s.alert_kind, s.alert_text, s.alert_lat, s.alert_lon, s.alert_radius_nm))
    return {"id": sid}


@app.delete("/api/scenarios/{sid}", dependencies=[instructor_only])
def delete_scenario(sid: str):
    with db() as c:
        c.execute("DELETE FROM scenarios WHERE id=?", (sid,))
    return {"ok": True}


# --------------------------------------------------------------------- sorties
@app.post("/api/sorties", dependencies=[instructor_only])
async def start_sortie(body: dict):
    sid = body.get("scenario_id")
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
            c.execute("INSERT INTO sorties (id, scenario_id, name, started)"
                      " VALUES (?,?,?,?)",
                      (oid, sid, body.get("name") or r["name"], started))
            return oid, row_to_scenario(r)

    oid, scenario = await db_call(go)
    if oid is None:
        raise HTTPException(404, "no such scenario")
    hub.scenario = scenario
    hub.sortie = {"id": oid, "scenario_id": sid,
                  "name": body.get("name") or scenario["name"],
                  "started": started, "stopped": None, "revealed": 0}
    hub.aircraft.clear()
    hub.messages.clear()
    await hub.broadcast({"type": "state", **hub.snapshot()})
    return hub.sortie


@app.post("/api/sorties/stop", dependencies=[instructor_only])
async def stop_sortie():
    if not hub.sortie:
        raise HTTPException(400, "no sortie running")
    stopped = time.time()
    await db_call(lambda: _exec("UPDATE sorties SET stopped=? WHERE id=?",
                                (stopped, hub.sortie["id"])))
    hub.sortie["stopped"] = stopped
    await hub.broadcast({"type": "state", **hub.snapshot()})
    return hub.sortie


@app.post("/api/sorties/reveal", dependencies=[instructor_only])
async def reveal():
    """Debrief: expose beacon truth to every connected console."""
    if not hub.sortie:
        raise HTTPException(400, "no sortie running")
    await db_call(lambda: _exec("UPDATE sorties SET revealed=1 WHERE id=?",
                                (hub.sortie["id"],)))
    hub.sortie["revealed"] = 1
    await hub.broadcast({"type": "state", **hub.snapshot()})
    return {"revealed": True}


@app.post("/api/sorties/effects", dependencies=[instructor_only])
async def set_effects(body: dict):
    if not hub.scenario:
        raise HTTPException(400, "no sortie running")
    hub.scenario["effects"].update(body)
    await db_call(lambda: _exec("UPDATE scenarios SET effects=? WHERE id=?",
                                (json.dumps(hub.scenario["effects"]),
                                 hub.scenario["id"])))
    await hub.broadcast({"type": "state", **hub.snapshot()})
    return hub.scenario["effects"]


@app.get("/api/sorties")
def list_sorties():
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT s.id, s.name, s.started, s.stopped, s.revealed,"
            "  (SELECT COUNT(*) FROM positions p WHERE p.sortie_id=s.id) AS points"
            " FROM sorties s ORDER BY s.started DESC LIMIT 50")]


@app.get("/api/sorties/{oid}/track")
def track(oid: str):
    with db() as c:
        rows = c.execute(
            "SELECT callsign, t, lat, lon, alt_ft, hdg_true FROM positions"
            " WHERE sortie_id=? ORDER BY t",
            (oid,)).fetchall()
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
    return {
        "positions": [dict(r) for r in rows],
        "bearings": [dict(r) for r in brgs],
        "messages": [dict(r) for r in msgs],
        "revealed": revealed,
        "beacon": ({"lat": sc["beacon_lat"], "lon": sc["beacon_lon"]}
                   if (sc and revealed) else None),
    }


# ------------------------------------------------------- position ingest (sim)
@app.post("/api/positions", dependencies=[plugin_only])
async def ingest(p: PositionIn):
    """
    Sim bridge -> here. Phase 4 contract.

    Returns what the direction finder would show, so a bridge without its own
    propagation engine (the mock, or an early plugin) can drive a DF display
    from this response.
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
        else:
            # Backward-compatible path for the mock bridge and older plugins.
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
                  "note": r.note}
        ac["df"] = df
        await db_call(lambda: _exec(
            "INSERT INTO positions VALUES (?,?,?,?,?,?,?)",
            (hub.sortie["id"], p.callsign, now, p.lat, p.lon, p.alt_ft, p.hdg_true)))

    hub.aircraft[p.callsign] = ac
    return {"ok": True, "df": df}


@app.post("/api/bearings", dependencies=[base_or_instructor])
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
        _exec("INSERT INTO bearings (sortie_id, callsign, t, lat, lon, bearing_true, note)"
              " VALUES (?,?,?,?,?,?,?)",
              (hub.sortie["id"], b.callsign, now, lat, lon, b.bearing_true, b.note))
        return lat, lon

    where = await db_call(go)
    if where is None:
        raise HTTPException(404, "no position on record for that aircraft")
    lat, lon = where
    await hub.broadcast({"type": "bearing", "callsign": b.callsign,
                         "lat": lat, "lon": lon,
                         "bearing_true": b.bearing_true, "note": b.note})
    return {"ok": True}


class MessageIn(BaseModel):
    sender: str = "MISSION BASE"
    recipient: str = "ALL"
    body: str


@app.post("/api/messages", dependencies=[base_or_instructor])
async def send_message(m: MessageIn):
    """Retasking and coordination text. Supplements voice and leaves a record."""
    now = time.time()
    if hub.sortie and not hub.sortie.get("stopped"):
        # After a sortie is stopped its record is closed: late traffic is
        # broadcast to whoever is still watching but not written into it.
        await db_call(lambda: _exec(
            "INSERT INTO messages (sortie_id, t, sender, recipient, body)"
            " VALUES (?,?,?,?,?)",
            (hub.sortie["id"], now, m.sender, m.recipient, m.body)))
    msg = {"type": "message", "t": now, "sender": m.sender,
           "recipient": m.recipient, "body": m.body}
    hub.messages.append(msg)
    await hub.broadcast(msg)
    return {"ok": True}


@app.get("/api/messages")
def list_messages():
    return hub.messages[-100:]


@app.get("/api/state")
def state():
    return hub.snapshot()


@app.get("/api/plugin/scenario")
def plugin_scenario(request: Request):
    """Beacon truth for the in-sim propagation engine.

    The X-Plane plugin is the authoritative DF engine and cannot work without
    the real beacon position — it has to compute bearing, terrain masking and
    signal strength from it. So this is the one endpoint that serves truth
    before the instructor reveals, and it is gated on CAPVSAR_TOKEN_PLUGIN
    rather than on a role default: with no key configured it returns 503, so
    it can never be open by accident.

    The shape matches /api/state deliberately, so the plugin's net thread only
    changes which URL it polls and gains one header.
    """
    access.require_plugin(request)
    return hub.snapshot(include_truth=True)

# Aeronautical chart tile services -- the same ones the N499CP flight planner
# uses. Served rather than hardcoded in the page so a wing running its own tile
# cache can repoint the console without editing JS. FAA's ArcGIS caches are
# {z}/{y}/{x}; OSM is {z}/{x}/{y}.
TILE_SOURCES = {
    "vfr": os.environ.get(
        "CAPVSAR_TILES_VFR",
        "https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services"
        "/VFR_Sectional/MapServer/tile/{z}/{y}/{x}"),
    "ifr_low": os.environ.get(
        "CAPVSAR_TILES_IFR_LOW",
        "https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services"
        "/IFR_AreaLow/MapServer/tile/{z}/{y}/{x}"),
    "ifr_high": os.environ.get(
        "CAPVSAR_TILES_IFR_HIGH",
        "https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services"
        "/IFR_High/MapServer/tile/{z}/{y}/{x}"),
    "sat": os.environ.get(
        "CAPVSAR_TILES_SAT",
        "https://server.arcgisonline.com/ArcGIS/rest/services"
        "/World_Imagery/MapServer/tile/{z}/{y}/{x}"),
    "osm": os.environ.get(
        "CAPVSAR_TILES_OSM",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
}


@app.get("/api/tile-sources")
def tile_sources():
    """Basemap URLs for the map views. Override any of them with CAPVSAR_TILES_*."""
    return TILE_SOURCES

@app.get("/api/health")
def health():
    return {"ok": True, "sortie": bool(hub.sortie), "aircraft": len(hub.aircraft)}


@app.websocket("/ws")
async def ws(sock: WebSocket):
    # Same-origin only, matching the radio stream's check: a browser on another
    # site should not be able to open a live feed of the exercise.
    origin = sock.headers.get("origin")
    if origin and urlsplit(origin).netloc != sock.headers.get("host"):
        await sock.close(code=1008)
        return
    await sock.accept()
    hub.clients.add(sock)
    try:
        await sock.send_text(json.dumps({"type": "state", **hub.snapshot()}))
        while True:
            await sock.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(sock)


app.include_router(radio.router)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/debrief")
def debrief():
    """Replay a recorded sortie against beacon truth. The product, per the plan."""
    return FileResponse(STATIC / "debrief.html")


@app.get("/base")
def mission_base():
    """Mission base view: no instructor controls, never shows beacon truth
    until the instructor reveals it."""
    return FileResponse(STATIC / "base.html")


@app.get("/radio")
def base_radio():
    """Mission base headset radio: APX 4500 / EFJohnson 5300, live Mumble voice."""
    return FileResponse(STATIC / "mission-radio.html")


@app.get("/radio-legacy")
def legacy_radio():
    """Previous APX6500 / Icom text-message training console."""
    return FileResponse(STATIC / "radio.html")


@app.get("/radio-ca.crt")
def radio_certificate():
    """Public local HTTPS trust certificate; no private keys are served."""
    path = Path("/radio-public/mission-base-ca.crt")
    if not path.is_file():
        raise HTTPException(404, "The local HTTPS certificate has not been installed yet.")
    return FileResponse(path, media_type="application/x-x509-ca-cert",
                        filename="cap-vsar-mission-base-ca.crt")
