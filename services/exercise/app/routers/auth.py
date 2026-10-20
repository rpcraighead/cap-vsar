"""
Login, the join-by-code flow, and exercise setup.

Split out of main.py under C15-1.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import secrets
from urllib.parse import parse_qs, quote


from fastapi import APIRouter, HTTPException, Request, Response

from .. import access

from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from ..models import LoginPayload, SetupPayload
from ..settings import STATIC
import io
from urllib.parse import urlsplit

import segno

router = APIRouter()




@router.get("/login")
def login_page():
    # Adapt the legacy static template while keeping credential handling here.
    page = (STATIC / "login.html").read_text()
    page = page.replace('maxlength="12"', 'maxlength="128"').replace(
        'placeholder="e.g. OBS-423"', 'placeholder="Full code from your badge"')
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


@router.post("/api/auth/login")
def api_login(payload: LoginPayload, request: Request, response: Response):
    res = access.authenticate_code(payload.code)
    if not res:
        raise HTTPException(401, "Invalid participant access code. Please verify your code or scan your QR badge.")
    user, sess_id = res
    access.revoke_previous_session(request)
    response.set_cookie(
        key=access.SESSION_COOKIE,
        value=sess_id,
        httponly=True,
        secure=True,
        max_age=int(access.session_lifetime_s()),   # the same lifetime the row carries
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
    norm_code = code.strip().upper().encode()
    matched = next(
        (row for row in access.get_roster()
         if hmac.compare_digest(norm_code, row["code"].encode())),
        None,
    )
    if matched is None:
        return RedirectResponse("/login?error=invalid_code", status_code=302)

    setup_info = access.get_exercise_setup()
    exercise_name = html.escape(
        str(setup_info.get("name") or "Civil Air Patrol SAREX Exercise"), quote=True
    )
    seat_id = access.seat_of(matched) or "SEAT"
    seat_meta = access.SEATS.get(seat_id, {})
    seat_label = html.escape(str(seat_meta.get("label") or matched.get("title") or "Participant"), quote=True)
    seat_code = html.escape(str(seat_id), quote=True)
    role_raw = str(matched.get("role") or "aircrew")
    role_display = html.escape(role_raw.replace("_", " ").upper(), quote=True)
    callsign = html.escape(str(matched.get("callsign") or "ASSIGNED"), quote=True)
    assigned_unit = html.escape(str(matched.get("assigned_name") or "Exercise Net"), quote=True)
    target_url = html.escape(str(matched.get("target_url") or "/"), quote=True)
    badge_prefix = html.escape(str(matched["code"].rsplit("-", 1)[0]), quote=True)

    role_pill_cls = "role-aircrew"
    if role_raw == "instructor":
        role_pill_cls = "role-instructor"
    elif role_raw == "base":
        role_pill_cls = "role-base"
    elif role_raw == "ground_team":
        role_pill_cls = "role-ground"

    if role_raw == "instructor":
        prep_items = (
            "Review active fleet &amp; ground roster in <code>/setup</code> or <code>/ready</code>.",
            "Verify ELT scenario parameters and weather/propagation effects before sortie start.",
            "Monitor live aircraft tracks, DF bearings, and net traffic on the Exercise Console.",
        )
    elif role_raw == "base":
        prep_items = (
            "Connect headset &amp; microphone and verify audio levels in <code>/ready</code>.",
            "Monitor primary tactical VHF-FM net and log traffic on CAP Form 110.",
            "Plot incoming aircrew &amp; UDF L-Per bearings on the Mission Base map.",
        )
    elif role_raw == "ground_team":
        prep_items = (
            "Enable mobile audio for tactical VHF-FM push-to-talk (PTT) communications.",
            "Stand by for Mission Base dispatch to sector coordinates.",
            "Submit handheld L-Per magnetic bearings and signal strength reports from <code>/udf</code>.",
        )
    else:
        prep_items = (
            "Verify assigned aircraft callsign, tail number, and DF receiver head model.",
            "Complete headset &amp; microphone check in <code>/ready</code> before engine start.",
            "Coordinate DF homing cuts and position reports with Mission Base on VHF.",
        )

    checklist_html = "".join(
        f'<li><span class="mono" style="color:var(--onb-good);font-weight:700">&#10003;</span><span>{item}</span></li>'
        for item in prep_items
    )

    nonce = secrets.token_urlsafe(32)
    csrf = hashlib.sha256((nonce + ":" + code).encode()).hexdigest()
    action = html.escape("/join/" + quote(code, safe=""), quote=True)
    page_html = (
        '<!doctype html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Confirm sign in — CAP V-SAR Boarding Pass</title>'
        '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 24 24\' fill=\'%232563eb\'%3E%3Cpath d=\'M12 2L3 7v6c0 5.25 3.75 10.15 9 11 5.25-.85 9-5.75 9-11V7l-9-5z\'/%3E%3C/svg%3E">'
        '<link rel="stylesheet" href="/static/vendor/fonts/fonts.css">'
        '<link rel="stylesheet" href="/static/style.css">'
        '<link rel="stylesheet" href="/static/onboarding.css">'
        '</head><body class="login-body onb">'
        '<header class="onb-auth-topbar">'
        '<div class="onb-brand">'
        '<span class="onb-brand-mark" aria-hidden="true">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 2L3 7v6c0 5.25 3.75 10.15 9 11 5.25-.85 9-5.75 9-11V7l-9-5z"/>'
        '<path d="M12 7l2.2 4.5 5 .7-3.6 3.5.85 5-4.45-2.35L7.55 20.7l.85-5L4.8 12.2l5-.7L12 7z"/>'
        '</svg></span>'
        '<div class="onb-brand-text"><b>CAP V-SAR</b><span>Participant Boarding Pass</span></div>'
        '</div>'
        '<div class="onb-safety-pill">'
        '<span>EXERCISE TRAFFIC &middot; NOT A REAL DISTRESS</span>'
        '</div>'
        '</header>'
        '<main class="login-wrapper join-wrapper">'
        '<div class="login-card">'
        '<div class="login-brand">'
        '<div class="login-logo-text">CIVIL AIR PATROL V-SAR</div>'
        f'<div class="login-sub-text">{exercise_name}</div>'
        '</div>'
        '<div class="login-title-block">'
        '<h1>Sign in with this participant badge?</h1>'
        '<p class="hint">Confirm your seat assignment below to activate your station session.</p>'
        '</div>'
        '<div class="onb-boarding-pass" role="region" aria-label="Assigned seat details">'
        '<div class="onb-pass-header">'
        f'<span class="onb-role-pill {role_pill_cls}">{role_display}</span>'
        f'<span class="mono" style="font-size:12px;font-weight:700">SEAT {seat_code} &middot; {badge_prefix}</span>'
        '</div>'
        '<div class="onb-pass-grid">'
        f'<div class="onb-pass-field"><span>Assigned Position</span><b>{seat_label}</b></div>'
        f'<div class="onb-pass-field"><span>Tactical Callsign</span><b class="mono">{callsign}</b></div>'
        f'<div class="onb-pass-field"><span>Unit / Airframe</span><b>{assigned_unit}</b></div>'
        f'<div class="onb-pass-field"><span>Destination Console</span><b class="mono">{target_url}</b></div>'
        '</div>'
        '</div>'
        '<ul class="onb-pass-checklist" aria-label="Station preparation checklist">'
        f'{checklist_html}'
        '</ul>'
        f'<form method="post" action="{action}">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        '<button type="submit" class="primary btn-block btn-lg">Confirm sign in &amp; Open Station</button>'
        '</form>'
        '<div style="margin-top:10px;text-align:center">'
        '<a href="/login" class="navlink" style="font-size:12px;color:var(--onb-muted)">Not your seat? Enter a different badge code at /login</a>'
        '</div>'
        '<div class="login-footer-notice">'
        '<span>CRYPTOGRAPHIC BADGE VERIFIED &bull; SESSION VALID 24H</span>'
        '</div>'
        '</div></main></body></html>'
    )
    resp = HTMLResponse(
        page_html,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'self' 'unsafe-inline'; "
                "font-src 'self'; img-src 'self' data:; "
                "form-action 'self'; frame-ancestors 'none'"
            ),
        },
    )
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
    access.revoke_previous_session(request)
    resp = RedirectResponse(user.get("target_url") or "/", status_code=303)
    resp.set_cookie(access.SESSION_COOKIE, sess_id, secure=True, httponly=True,
                    max_age=int(access.session_lifetime_s()), samesite="lax")
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



@router.get("/api/setup/badge/{roster_id}.svg")
def api_setup_badge(roster_id: str, origin: str, request: Request):
    """The QR for one roster seat, rendered on the server (U-2).

    The client used to draw these with a vendored "lightweight" QR library
    whose Reed-Solomon table was truncated: every badge was blank, and the
    levels that did render would have produced wrong error-correction
    blocks. `segno` is a complete encoder.

    `origin` is the scheme and host the page was loaded from (the single
    front door, as the badge's link must survive being scanned from another
    device); it must match the Host the request arrived on, so the instructor
    cannot be made to mint a QR for someone else's domain.
    """
    access.enforce("instructor", request)
    parts = urlsplit(origin)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise HTTPException(400, "origin must be like https://host")
    if parts.netloc != request.headers.get("host", ""):
        raise HTTPException(400, "origin does not match this console")
    row = next((r for r in access.get_roster() if r["id"] == roster_id), None)
    if row is None:
        raise HTTPException(404, "no such roster seat")
    url = f"{parts.scheme}://{parts.netloc}/join/{quote(row['code'], safe='')}"
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=4, border=2,
                                     dark="#0B2545", light="#FFFFFF")
    return Response(buf.getvalue(), media_type="image/svg+xml",
                    headers={"Cache-Control": "private, no-store"})


def _keep_caller_signed_in(request: Request, response: Response, previous: dict | None) -> None:
    """B7 (review T11): saving the setup regenerates the roster and revokes every
    session, the director's own included, so the page that just saved was logged
    out and the new INSTR-1 code shown once. Re-issue the caller's session on the
    new director row and set the cookie on this response."""
    if not previous or not request.cookies.get(access.SESSION_COOKIE):
        return
    new_id = access.reissue_instructor_session(previous)
    if new_id:
        response.set_cookie(key=access.SESSION_COOKIE, value=new_id, httponly=True, secure=True,
                            max_age=int(access.session_lifetime_s()), samesite="lax")


@router.post("/api/setup")
def api_save_setup(payload: SetupPayload, request: Request, response: Response):
    access.enforce("instructor", request)
    previous = access.get_session_from_request(request)
    try:
        result = access.save_exercise_setup(
            name=payload.name,
            num_aircraft=payload.num_aircraft,
            aircraft_list=[a.model_dump(exclude_none=True) for a in payload.aircraft],
            staff_list=[st.model_dump(exclude_none=True) for st in payload.staff],
            director_email=payload.director_email,
        )
    except ValueError as error:          # duplicate or malformed seat email
        raise HTTPException(422, str(error))
    _keep_caller_signed_in(request, response, previous)
    return result


@router.post("/api/setup/reset")
def api_reset_setup(request: Request, response: Response):
    access.enforce("instructor", request)
    previous = access.get_session_from_request(request)
    default_setup = access.get_exercise_setup()
    result = access.save_exercise_setup(
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
    _keep_caller_signed_in(request, response, previous)
    return result

