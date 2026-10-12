"""
The HTML the browsers actually load.

Split out of main.py under C15-1.
"""
from __future__ import annotations

import html

from fastapi import APIRouter, HTTPException, Request

from .. import access

from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from ..settings import STATIC

router = APIRouter()

@router.get("/")
@router.get("/portal")
def portal(request: Request):
    """Role-aware landing page for the one O-8 participant origin."""
    sess = access.get_session_from_request(request)
    if not sess and not access.dev_open():
        return RedirectResponse("/login?next=/", status_code=302)
    role = sess.get("role", "") if sess else "instructor"
    title = sess.get("title", role) if sess else "Local development operator"
    common = [("Flight Planner", "/planner/",
               "Routes, performance, weight and balance, and SAR patterns")]
    by_role = {
        "instructor": [
            ("Exercise Console", "/instructor", "Scenario and exercise control"),
            ("Exercise Setup", "/setup", "Roster, stations and invite badges"),
            ("Mission Base", "/base", "Aircraft status, bearings and tasking"),
            ("Base Radio", "/radio", "Mission voice and communications log"),
            ("Debrief", "/debrief", "Sortie replay and scoring"),
        ],
        "base": [
            ("Mission Base", "/base", "Aircraft status, bearings and tasking"),
            ("Base Radio", "/radio", "Mission voice and communications log"),
        ],
        "aircrew": [
            ("Mission Base", "/base", "Aircraft status and tasking"),
        ],
        "ground_team": [
            ("Base Radio", "/radio", "Mission voice and communications log"),
        ],
    }
    cards = "".join(
        f'<a class="card" href="{href}"><b>{html.escape(name)}</b>'
        f'<span>{html.escape(description)}</span></a>'
        for name, href, description in by_role.get(role, []) + common
    )
    body = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CAP V-SAR</title><style>
body{{margin:0;background:#0e1621;color:#eef4fb;font:16px system-ui,sans-serif}}
main{{max-width:900px;margin:0 auto;padding:3rem 1.2rem}}h1{{margin-bottom:.25rem}}
.who{{color:#a9b8c8;margin-bottom:2rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem}}
.card{{display:flex;flex-direction:column;gap:.45rem;padding:1.2rem;border:1px solid #36516b;border-radius:10px;background:#172536;color:#fff;text-decoration:none}}
.card:hover,.card:focus{{border-color:#71b7ff;background:#1d3045}}.card span{{color:#b9c8d7;font-size:.9rem}}
.note{{margin-top:2rem;color:#90a5b8;font-size:.85rem}}
</style></head><body><main><h1>CAP V-SAR</h1>
<div class="who">{html.escape(str(title))} · {html.escape(role or 'unknown role')}</div>
<div class="grid">{cards}</div>
<p class="note">One trusted HTTPS origin. Your signed-in role determines which stations are listed.</p>
</main></body></html>"""
    return HTMLResponse(body, headers={
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
    })


@router.get("/instructor")
def index(request: Request):
    sess = access.get_session_from_request(request)
    if sess and sess.get("role") == "instructor":
        return FileResponse(STATIC / "index.html")
    if sess and sess.get("role") != "instructor":
        return RedirectResponse("/login?error=instructor_required", status_code=302)
    if not access.dev_open() or access.token_for("instructor"):
        return RedirectResponse("/login?next=/instructor", status_code=302)
    return FileResponse(STATIC / "index.html")


@router.get("/ready")
def ready_room(request: Request):
    """The Ready room (UX phase 2 reference screen): who is here, who is ready."""
    if not access.get_session_from_request(request) and not access.dev_open():
        return RedirectResponse("/login?next=/ready", status_code=302)
    return FileResponse(STATIC / "ready.html")


@router.get("/debrief")
def debrief(request: Request):
    """Replay a recorded sortie against beacon truth. The product, per the plan."""
    if not access.get_session_from_request(request) and not access.dev_open():
        return RedirectResponse("/login?next=/debrief", status_code=302)
    return FileResponse(STATIC / "debrief.html")


@router.get("/base")
def mission_base(request: Request):
    """Mission base view: no instructor controls, never shows beacon truth
    until the instructor reveals it."""
    sess = access.get_session_from_request(request)
    if sess and sess.get("role") in ("base", "instructor", "aircrew"):
        return FileResponse(STATIC / "base.html")
    if not access.dev_open() or access.token_for("base"):
        return RedirectResponse("/login?next=/base", status_code=302)
    return FileResponse(STATIC / "base.html")


@router.get("/radio")
def base_radio(request: Request):
    """Mission base headset radio: APX 4500 / EFJohnson 5300, live Mumble voice."""
    if not access.get_session_from_request(request) and not access.dev_open():
        return RedirectResponse("/login?next=/radio", status_code=302)
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

