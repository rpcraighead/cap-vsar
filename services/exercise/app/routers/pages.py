"""
The HTML the browsers actually load.

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
from ..store import _exec, _fetchone, db, db_call, row_to_scenario

from pathlib import Path

from fastapi.responses import FileResponse, RedirectResponse

from ..settings import STATIC

router = APIRouter()

@router.get("/")
def index(request: Request):
    sess = access.get_session_from_request(request)
    if sess and sess.get("role") == "instructor":
        return FileResponse(STATIC / "index.html")
    if sess and sess.get("role") != "instructor":
        return RedirectResponse("/login?error=instructor_required", status_code=302)
    if access.token_for("instructor"):
        return RedirectResponse("/login?next=/", status_code=302)
    return FileResponse(STATIC / "index.html")


@router.get("/debrief")
def debrief(request: Request):
    """Replay a recorded sortie against beacon truth. The product, per the plan."""
    return FileResponse(STATIC / "debrief.html")


@router.get("/base")
def mission_base(request: Request):
    """Mission base view: no instructor controls, never shows beacon truth
    until the instructor reveals it."""
    sess = access.get_session_from_request(request)
    if sess and sess.get("role") in ("base", "instructor", "aircrew"):
        return FileResponse(STATIC / "base.html")
    if access.token_for("base"):
        return RedirectResponse("/login?next=/base", status_code=302)
    return FileResponse(STATIC / "base.html")


@router.get("/radio")
def base_radio():
    """Mission base headset radio: APX 4500 / EFJohnson 5300, live Mumble voice."""
    return FileResponse(STATIC / "mission-radio.html")


@router.get("/radio-legacy")
def legacy_radio():
    """Previous APX6500 / Icom text-message training console."""
    return FileResponse(STATIC / "radio.html")


@router.get("/radio-ca.crt")
def radio_certificate():
    """Public local HTTPS trust certificate; no private keys are served."""
    path = Path("/radio-public/mission-base-ca.crt")
    if not path.is_file():
        raise HTTPException(404, "The local HTTPS certificate has not been installed yet.")
    return FileResponse(path, media_type="application/x-x509-ca-cert",
                        filename="cap-vsar-mission-base-ca.crt")


