"""
Login, the join-by-code flow, and exercise setup.

Split out of main.py under C15-1.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import secrets
import re
from urllib.parse import parse_qs, quote

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

from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from ..models import LoginPayload, SetupPayload
from ..settings import STATIC

router = APIRouter()




@router.get("/login")
def login_page():
    # Adapt the legacy static template while keeping credential handling here.
    page = (STATIC / "login.html").read_text()
    page = page.replace('maxlength="12"', 'maxlength="128"').replace(
        'placeholder="e.g. OBS-423"', 'placeholder="Full code from your badge"')
    page = re.sub(r'    <div class="login-shortcuts-section">.*?(?=    <div class="login-footer-notice">)',
                  '', page, flags=re.S)
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


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
        secure=True,
        max_age=86400,
        samesite="lax"
    )
    return {
        "ok": True,
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
    return {"authenticated": True, **{k: v for k, v in sess.items() if k != "session_id"}}


@router.post("/api/auth/logout")
def api_logout(request: Request, response: Response):
    sess_id = request.cookies.get(access.SESSION_COOKIE)
    if sess_id:
        access.delete_session(sess_id)
    response.delete_cookie(key=access.SESSION_COOKIE, secure=True, httponly=True, samesite="lax")
    return {"ok": True}


JOIN_CSRF_COOKIE = "__Host-capvsar_join"


@router.get("/join/{code}")
def join_by_code(code: str):
    # Validate without minting a session or updating last_login.
    if not any(hmac.compare_digest(code.strip().upper().encode(), row["code"].encode())
               for row in access.get_roster()):
        return RedirectResponse("/login?error=invalid_code", status_code=302)
    nonce = secrets.token_urlsafe(32)
    csrf = hashlib.sha256((nonce + ":" + code).encode()).hexdigest()
    action = html.escape("/join/" + quote(code, safe=""), quote=True)
    resp = HTMLResponse(
        '<!doctype html><html><head><title>Confirm sign in</title></head><body>'
        '<h1>Sign in with this participant badge?</h1>'
        f'<form method="post" action="{action}">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        '<button type="submit">Confirm sign in</button></form></body></html>',
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                 "Content-Security-Policy": "default-src 'none'; form-action 'self'; frame-ancestors 'none'"})
    resp.set_cookie(JOIN_CSRF_COOKIE, nonce, secure=True, httponly=True,
                    samesite="strict", max_age=600, path="/")
    return resp


@router.post("/join/{code}")
async def confirm_join(code: str, request: Request):
    nonce = request.cookies.get(JOIN_CSRF_COOKIE, "")
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(403, "Invalid sign-in confirmation")
    fields = parse_qs((await request.body()).decode("utf-8", errors="replace"))
    csrf = fields.get("csrf", [""])[0]
    expected = hashlib.sha256((nonce + ":" + code).encode()).hexdigest()
    if not nonce or not hmac.compare_digest(csrf.encode(), expected.encode()):
        raise HTTPException(403, "Invalid sign-in confirmation")
    res = access.authenticate_code(code)
    if not res:
        return RedirectResponse("/login?error=invalid_code", status_code=303)
    user, sess_id = res
    resp = RedirectResponse(user.get("target_url") or "/", status_code=303)
    resp.set_cookie(access.SESSION_COOKIE, sess_id, secure=True, httponly=True,
                    max_age=86400, samesite="lax")
    resp.delete_cookie(JOIN_CSRF_COOKIE, secure=True, httponly=True, samesite="strict")
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

