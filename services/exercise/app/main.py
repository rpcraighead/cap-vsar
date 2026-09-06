"""
CAP V-SAR Exercise Console.

Instructor-facing service: hold beacon truth, run a sortie, ingest aircraft
positions, and serve a live map. The position ingest endpoint is the contract
the X-Plane sim bridge will implement in Phase 4.
"""
from __future__ import annotations
import asyncio, json, math, os, sqlite3, time, uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import propagation

DB = os.environ.get("CAPVSAR_DB", "/data/exercise.db")
STATIC = Path(__file__).parent / "static"


# ---------------------------------------------------------------- persistence
def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
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
        CREATE TABLE IF NOT EXISTS bearings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sortie_id TEXT, callsign TEXT,
            t REAL, lat REAL, lon REAL, bearing_true REAL, note TEXT);
        """)


DEFAULT_EFFECTS = {
    "radio_horizon": True, "burst_cadence": True,
    "cone_of_confusion": True, "multipath": False,
    "multipath_offset_deg": 40.0,
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
}


# ------------------------------------------------------------------ live state
class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.aircraft: dict[str, dict] = {}
        self.sortie: dict | None = None
        self.scenario: dict | None = None

    async def broadcast(self, msg: dict):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(json.dumps(msg))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    def snapshot(self, include_truth: bool = False) -> dict:
        s = {
            "sortie": self.sortie,
            "scenario": None,
            "aircraft": list(self.aircraft.values()),
            "server_time": time.time(),
        }
        if self.scenario:
            sc = dict(self.scenario)
            revealed = bool(self.sortie and self.sortie.get("revealed"))
            if not (include_truth or revealed):
                # beacon truth is withheld from the console until reveal
                sc.pop("beacon_lat", None)
                sc.pop("beacon_lon", None)
            s["scenario"] = sc
        return s


hub = Hub()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with db() as c:
        if not c.execute("SELECT 1 FROM scenarios LIMIT 1").fetchone():
            c.execute(
                "INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4())[:8], SEED["name"], SEED["notes"],
                 SEED["beacon_lat"], SEED["beacon_lon"], SEED["beacon_elev_ft"],
                 SEED["band"], SEED["power"], json.dumps(SEED["effects"]), time.time()))
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


class PositionIn(BaseModel):
    """What the sim bridge POSTs. Phase 4 contract - keep stable."""
    callsign: str
    lat: float
    lon: float
    alt_ft: float
    hdg_true: float = 0.0


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
def list_scenarios():
    with db() as c:
        return [row_to_scenario(r) for r in
                c.execute("SELECT * FROM scenarios ORDER BY created")]


@app.post("/api/scenarios")
def create_scenario(s: ScenarioIn):
    sid = str(uuid.uuid4())[:8]
    with db() as c:
        c.execute("INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (sid, s.name, s.notes, s.beacon_lat, s.beacon_lon,
                   s.beacon_elev_ft, s.band, s.power, json.dumps(s.effects), time.time()))
    return {"id": sid}


@app.delete("/api/scenarios/{sid}")
def delete_scenario(sid: str):
    with db() as c:
        c.execute("DELETE FROM scenarios WHERE id=?", (sid,))
    return {"ok": True}


# --------------------------------------------------------------------- sorties
@app.post("/api/sorties")
async def start_sortie(body: dict):
    sid = body.get("scenario_id")
    with db() as c:
        r = c.execute("SELECT * FROM scenarios WHERE id=?", (sid,)).fetchone()
        if not r:
            raise HTTPException(404, "no such scenario")
        oid = str(uuid.uuid4())[:8]
        c.execute("INSERT INTO sorties (id, scenario_id, name, started) VALUES (?,?,?,?)",
                  (oid, sid, body.get("name") or r["name"], time.time()))
    hub.scenario = row_to_scenario(r)
    hub.sortie = {"id": oid, "scenario_id": sid, "name": body.get("name") or r["name"],
                  "started": time.time(), "stopped": None, "revealed": 0}
    hub.aircraft.clear()
    await hub.broadcast({"type": "state", **hub.snapshot()})
    return hub.sortie


@app.post("/api/sorties/stop")
async def stop_sortie():
    if not hub.sortie:
        raise HTTPException(400, "no sortie running")
    with db() as c:
        c.execute("UPDATE sorties SET stopped=? WHERE id=?", (time.time(), hub.sortie["id"]))
    hub.sortie["stopped"] = time.time()
    await hub.broadcast({"type": "state", **hub.snapshot()})
    return hub.sortie


@app.post("/api/sorties/reveal")
async def reveal():
    """Debrief: expose beacon truth to every connected console."""
    if not hub.sortie:
        raise HTTPException(400, "no sortie running")
    with db() as c:
        c.execute("UPDATE sorties SET revealed=1 WHERE id=?", (hub.sortie["id"],))
    hub.sortie["revealed"] = 1
    await hub.broadcast({"type": "state", **hub.snapshot()})
    return {"revealed": True}


@app.post("/api/sorties/effects")
async def set_effects(body: dict):
    if not hub.scenario:
        raise HTTPException(400, "no sortie running")
    hub.scenario["effects"].update(body)
    with db() as c:
        c.execute("UPDATE scenarios SET effects=? WHERE id=?",
                  (json.dumps(hub.scenario["effects"]), hub.scenario["id"]))
    await hub.broadcast({"type": "state", **hub.snapshot()})
    return hub.scenario["effects"]


@app.get("/api/sorties/{oid}/track")
def track(oid: str):
    with db() as c:
        rows = c.execute(
            "SELECT callsign, t, lat, lon, alt_ft FROM positions WHERE sortie_id=? ORDER BY t",
            (oid,)).fetchall()
        brgs = c.execute(
            "SELECT callsign, t, lat, lon, bearing_true, note FROM bearings WHERE sortie_id=? ORDER BY t",
            (oid,)).fetchall()
        s = c.execute("SELECT * FROM sorties WHERE id=?", (oid,)).fetchone()
        sc = c.execute("SELECT * FROM scenarios WHERE id=?", (s["scenario_id"],)).fetchone() if s else None
    return {
        "positions": [dict(r) for r in rows],
        "bearings": [dict(r) for r in brgs],
        "beacon": ({"lat": sc["beacon_lat"], "lon": sc["beacon_lon"]} if sc else None),
    }


# ------------------------------------------------------- position ingest (sim)
@app.post("/api/positions")
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
        with db() as c:
            c.execute("INSERT INTO positions VALUES (?,?,?,?,?,?,?)",
                      (hub.sortie["id"], p.callsign, now, p.lat, p.lon, p.alt_ft, p.hdg_true))

    hub.aircraft[p.callsign] = ac
    return {"ok": True, "df": df}


@app.post("/api/bearings")
async def log_bearing(b: BearingIn):
    """Mission base logs a bearing the crew reported. Draws a line on the map."""
    if not hub.sortie:
        raise HTTPException(400, "no sortie running")
    ac = hub.aircraft.get(b.callsign)
    if not ac:
        raise HTTPException(404, "no such aircraft reporting")
    with db() as c:
        c.execute("INSERT INTO bearings (sortie_id, callsign, t, lat, lon, bearing_true, note)"
                  " VALUES (?,?,?,?,?,?,?)",
                  (hub.sortie["id"], b.callsign, time.time(), ac["lat"], ac["lon"],
                   b.bearing_true, b.note))
    await hub.broadcast({"type": "bearing", "callsign": b.callsign,
                         "lat": ac["lat"], "lon": ac["lon"],
                         "bearing_true": b.bearing_true, "note": b.note})
    return {"ok": True}


@app.get("/api/state")
def state():
    return hub.snapshot()


@app.get("/api/health")
def health():
    return {"ok": True, "sortie": bool(hub.sortie), "aircraft": len(hub.aircraft)}


@app.websocket("/ws")
async def ws(sock: WebSocket):
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


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
