"""
State, beacon truth for the plugin, health, and the console websocket.

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

import os
from urllib.parse import urlsplit

from fastapi import WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

router = APIRouter()

@router.get("/api/state", dependencies=[any_role])
def state(request: Request):
    return hub.snapshot(include_df=access.is_instructor(request))


@router.get("/api/plugin/scenario")
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

# Aeronautical chart tile services -- the same ones the flight planner
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


@router.get("/api/tile-sources")
def tile_sources():
    """Basemap URLs for the map views. Override any of them with CAPVSAR_TILES_*."""
    return TILE_SOURCES

@router.get("/api/health")
def health(response: Response):
    """Health, including whether the database is actually usable (X-8).

    This used to answer {"ok": true} from memory alone, so a container with a
    deleted, unreadable or corrupt database reported healthy and Docker kept
    routing an exercise at it. The query is deliberately one that touches a
    real table rather than SELECT 1, which a half-initialised file will happily
    answer.
    """
    db_ok, detail = True, "ok"
    try:
        with db() as c:
            c.execute("SELECT COUNT(*) FROM scenarios").fetchone()
    except Exception as e:                      # sqlite3.Error, OSError, ...
        db_ok, detail = False, f"{type(e).__name__}: {e}"
        log.error("healthcheck: database unusable: %s", detail)
    if not db_ok:
        response.status_code = 503
    return {"ok": db_ok, "db": detail, "sortie": bool(hub.sortie),
            "aircraft": len(hub.aircraft)}


@router.websocket("/ws")
async def ws(sock: WebSocket):
    # Same-origin only, matching the radio stream's check: a browser on another
    # site should not be able to open a live feed of the exercise.
    origin = sock.headers.get("origin")
    if origin and urlsplit(origin).netloc != sock.headers.get("host"):
        await sock.close(code=1008)
        return
    # D1.3: a live feed of the exercise needs a login, and the login decides
    # which rendering of the state this socket receives. The handshake carries
    # the session cookie because the page and the socket share an origin.
    # Both lookups hit SQLite, so they run in a worker thread (X2-5).
    def admit():
        access.enforce_read(sock)
        return access.is_instructor(sock)
    try:
        sees_truth = await run_in_threadpool(admit)
    except HTTPException:
        await sock.close(code=1008)
        return
    await sock.accept()
    hub.clients.add(sock)
    if sees_truth:
        hub.truth_clients.add(sock)
    try:
        await sock.send_text(json.dumps(
            {"type": "state", **hub.snapshot(include_df=sees_truth)},
            allow_nan=False))
        while True:
            await sock.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(sock)
        hub.truth_clients.discard(sock)

