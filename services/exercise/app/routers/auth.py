"""
Login, the join-by-code flow, and exercise setup.

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

from fastapi.responses import FileResponse, RedirectResponse

from ..models import LoginPayload, SetupPayload
from ..settings import STATIC

router = APIRouter()




@router.get("/login")
def login_page():
    return FileResponse(STATIC / "login.html")


@router.post("/api/auth/login")
def api_login(payload: LoginPayload, response: Response):
    res = access.authenticate_code(payload.code)
    if not res:
        raise HTTPException(401, "Invalid participant access code. Please verify your code or scan your QR badge.")
    user, sess_id = res
    response.set_cookie(
        key=access.SESSION_COOKIE,
        value=sess_id,
        httponly=True,
        max_age=86400,
        samesite="lax"
    )
    return {
        "ok": True,
        "session_id": sess_id,
        "user": user,
        "target_url": user.get("target_url") or "/"
    }


@router.get("/api/auth/me")
def api_auth_me(request: Request):
    sess = access.get_session_from_request(request)
    if not sess:
        # X-11: this used to report an authenticated instructor identity to any
        # anonymous caller whenever no instructor/base token was configured, so
        # the UI rendered full Exercise Director controls for a stranger and
        # the console asserted an identity nobody had proved. The dev console
        # is still reachable, but it now says plainly that it is unauthenticated
        # and it only does so when the operator asked for an open console.
        if access.dev_open():
            return {
                "authenticated": False,
                "dev_open": True,
                "role": "instructor",
                "title": "Exercise Director (unauthenticated dev console)",
                "code": "DEV",
                "callsign": "DEV",
            }
        return {"authenticated": False}
    return {"authenticated": True, **sess}


@router.post("/api/auth/logout")
def api_logout(request: Request, response: Response):
    sess_id = request.cookies.get(access.SESSION_COOKIE)
    if sess_id:
        access.delete_session(sess_id)
    response.delete_cookie(key=access.SESSION_COOKIE)
    return {"ok": True}


@router.get("/join/{code}")
def join_by_code(code: str):
    res = access.authenticate_code(code)
    if not res:
        return RedirectResponse(f"/login?error=invalid_code&code={code}", status_code=302)
    user, sess_id = res
    target = user.get("target_url") or "/"
    resp = RedirectResponse(target, status_code=302)
    resp.set_cookie(
        key=access.SESSION_COOKIE,
        value=sess_id,
        httponly=True,
        max_age=86400,
        samesite="lax"
    )
    return resp


@router.get("/setup")
def setup_page(request: Request):
    sess = access.get_session_from_request(request)
    if sess and sess.get("role") == "instructor":
        return FileResponse(STATIC / "setup.html")
    if sess and sess.get("role") != "instructor":
        return RedirectResponse("/login?error=instructor_required", status_code=302)
    if access.token_for("instructor"):
        return RedirectResponse("/login?next=/setup", status_code=302)
    return FileResponse(STATIC / "setup.html")


@router.get("/api/setup")
def api_get_setup(request: Request):
    access.enforce("instructor", request)
    return access.get_exercise_setup()



@router.post("/api/setup")
def api_save_setup(payload: SetupPayload, request: Request):
    access.enforce("instructor", request)
    return access.save_exercise_setup(
        name=payload.name,
        num_aircraft=payload.num_aircraft,
        aircraft_list=payload.aircraft,
        staff_list=payload.staff
    )


@router.post("/api/setup/reset")
def api_reset_setup(request: Request):
    access.enforce("instructor", request)
    default_setup = access.get_exercise_setup()
    return access.save_exercise_setup(
        name=default_setup.get("name", "Civil Air Patrol SAREX Exercise"),
        num_aircraft=1,
        aircraft_list=[{
            "id": "ac-1",
            "callsign": "CAP 423",
            "tail": "CAP 487",
            "df_model": "Becker SAR-DF 517",
            "crew": ["pilot", "observer", "scanner"]
        }],
        staff_list=[
            {"role": "base", "title": "Mission Radio Operator 1", "callsign": "MRO 1"},
            {"role": "ground_team", "title": "Ground Team / UDF 1 Leader", "callsign": "UDF 1"}
        ]
    )

