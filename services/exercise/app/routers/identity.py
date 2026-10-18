"""
OpenID Connect sign-in routes and the public provider description.

    GET /api/auth/providers    what sign-in paths this console offers (public)
    GET /auth/oidc/login       start the authorization-code + PKCE flow
    GET /auth/oidc/callback    finish it: verified email -> seat -> session

The badge-code login in routers/auth.py is untouched and remains the offline
path; both mint the same session (access.create_session), so every page and
role gate behaves the same whichever door a person came in by. The protocol
lives in app/oidc.py; this file is HTTP: cookies, redirects, pages, the audit
line and the callback rate limit.
"""
from __future__ import annotations

import html
import http.client
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import access, oidc

router = APIRouter()
log = logging.getLogger("capvsar.console.identity")

NO_STORE = {"Cache-Control": "no-store"}
CSP = ("default-src 'none'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
       "img-src 'self' data:; frame-ancestors 'none'")


def _page(title: str, heading: str, paragraphs: list[str], status: int) -> HTMLResponse:
    """A small server-rendered page in the console's own styles. Every dynamic
    value is escaped by the caller; this only assembles the shell."""
    body = "".join("<p class=\"hint\">%s</p>" % p for p in paragraphs)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{html.escape(title)}</title>'
        '<link rel="stylesheet" href="/static/vendor/fonts/fonts.css">'
        '<link rel="stylesheet" href="/static/style.css">'
        '<link rel="stylesheet" href="/static/onboarding.css">'
        '</head><body class="login-body onb"><main class="login-wrapper"><div class="login-card">'
        '<div class="login-brand"><div class="login-logo-text">CIVIL AIR PATROL V-SAR</div></div>'
        f'<div class="login-title-block"><h1>{html.escape(heading)}</h1></div>{body}'
        '<div style="margin-top:14px"><a href="/login" class="primary btn-block btn-lg" '
        'style="display:block;text-align:center;text-decoration:none">Back to sign in</a></div>'
        '</div></main></body></html>')
    return HTMLResponse(page, status_code=status, headers={**NO_STORE, "Content-Security-Policy": CSP})


def _clear_state(response):
    response.delete_cookie(oidc.STATE_COOKIE, secure=True, httponly=True, samesite="lax", path="/")
    return response


def _login_redirect(error: str):
    response = RedirectResponse("/login?error=" + error, status_code=303)
    response.headers["Cache-Control"] = "no-store"
    return _clear_state(response)


@router.get("/api/auth/providers")
def auth_providers():
    """Public: which sign-in paths this console offers. The login page shows the
    OIDC button only when `oidc.enabled`; the badge form is always there."""
    return JSONResponse(oidc.providers(), headers=NO_STORE)


@router.get("/auth/oidc/login")
def oidc_login(request: Request, next: str | None = None):
    cfg = oidc.config()
    if not cfg["enabled"]:
        return _page("Sign-in not available", "Sign in with Google is not set up on this console",
                     ["This console is running without an identity provider (offline field use). "
                      "Sign in with the badge code from your briefing card instead."], 503)
    try:
        url, state_cookie = oidc.begin(next, cfg)
    except (oidc.OIDCError, OSError, http.client.HTTPException, ValueError) as error:
        log.warning("oidc sign-in: outcome=unavailable reason=%s", type(error).__name__)
        return _page("Sign-in unavailable", "The sign-in provider could not be reached",
                     ["The console could not contact the identity provider. Try again in a moment, "
                      "or sign in with your badge code."], 503)
    response = RedirectResponse(url, status_code=302, headers=NO_STORE)
    # Lax, not Strict: the provider sends the browser back here with a top-level
    # GET, and a Strict cookie would not accompany that cross-site navigation.
    response.set_cookie(oidc.STATE_COOKIE, state_cookie, secure=True, httponly=True,
                        samesite="lax", max_age=int(oidc.STATE_TTL_S), path="/")
    return response


@router.get("/auth/oidc/callback")
def oidc_callback(request: Request):
    cfg = oidc.config()
    address = oidc.client_address(request, cfg)
    if oidc.failures.blocked(address):
        return _page("Too many attempts", "Too many sign-in attempts",
                     ["Please wait a minute and try again."], 429)
    query = dict(request.query_params)
    if query.get("error"):
        # The person cancelled or the provider refused consent: not a failure of ours.
        log.info("oidc sign-in: outcome=cancelled")
        return _login_redirect("oidc_cancelled")
    try:
        identity = oidc.complete(query, request.cookies.get(oidc.STATE_COOKIE), cfg)
    except (oidc.OIDCError, OSError, http.client.HTTPException, ValueError, KeyError, TypeError) as error:
        oidc.failures.record(address)
        # One uniform outcome for every refusal; the reason stays in the log.
        log.info("oidc sign-in: outcome=refused reason=%s", str(error)[:80] or type(error).__name__)
        return _login_redirect("oidc_failed")
    email = identity["email"]
    result = access.login_with_email(email, directors=cfg["director_emails"])
    if result is None:
        log.info("oidc sign-in: outcome=no_seat email=%s", oidc.mask_email(email))
        exercise = access.get_exercise_setup().get("name") or "this exercise"
        return _clear_state(_page(
            "No seat assigned", "There is no seat for you in this exercise",
            ["You signed in as <b>%s</b>, but the Exercise Director has not assigned that address "
             "to a seat in <b>%s</b>." % (html.escape(email), html.escape(str(exercise))),
             "Ask the Exercise Director to add your email in Setup, or sign in with the badge code "
             "from your briefing card."], 403))
    user, sess_id = result
    access.revoke_previous_session(request)
    log.info("oidc sign-in: outcome=ok seat=%s role=%s email=%s",
             access.seat_of(user), user.get("role"), oidc.mask_email(email))
    destination = oidc.safe_next(identity.get("next"), cfg["redirect_base"]) or user.get("target_url") or "/"
    response = RedirectResponse(destination, status_code=303, headers=NO_STORE)
    # A fresh session id on every login (no fixation): the cookie is set, never reused.
    response.set_cookie(access.SESSION_COOKIE, sess_id, secure=True, httponly=True,
                        max_age=int(access.session_lifetime_s()), samesite="lax")
    return _clear_state(response)
