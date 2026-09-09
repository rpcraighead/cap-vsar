"""
Role tokens for the exercise console.

Three roles, one shared-secret token each, supplied by the environment:

    CAPVSAR_TOKEN_INSTRUCTOR   scenario authoring, sortie control, reveal
    CAPVSAR_TOKEN_BASE         mission base: log bearings, send messages
    CAPVSAR_TOKEN_PLUGIN       the X-Plane plugin: ingest, and beacon truth

A caller presents one in the `X-CAPVSAR-Token` header, or as a `token` query
parameter where a header is awkward (the WebSocket handshake). An instructor
token also satisfies the base role; a plugin key satisfies nothing else.

Two deliberately different defaults, because the two failure modes are not
symmetrical:

* **Beacon truth is deny-by-default.** A response carries the beacon position
  only if the sortie has been revealed, or if a *configured* instructor token
  was presented. With no instructor token configured nothing unlocks it, so a
  half-configured deployment withholds truth rather than leaking it. This is
  the whole teaching mechanism of the exercise and must fail closed.

* **Mutating endpoints are open-by-default.** Enforcing them unconditionally
  would lock every operator out of the already-running stack the moment this
  code deployed, before its `.env` carries any tokens. Setting a role's token
  switches enforcement on for that role. `unconfigured()` reports which roles
  are still open so the app can say so loudly at startup.

So: secrecy fails closed, availability fails open, and the open case is
announced rather than silent.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request

TOKEN_HEADER = "X-CAPVSAR-Token"
ROLES = ("instructor", "base", "plugin")

# Which configured tokens satisfy a role. An instructor may act as base staff;
# nothing else is transitive.
SATISFIED_BY: dict[str, tuple[str, ...]] = {
    "instructor": ("instructor",),
    "base": ("base", "instructor"),
    "plugin": ("plugin",),
}


def token_for(role: str) -> str:
    return os.environ.get(f"CAPVSAR_TOKEN_{role.upper()}", "").strip()


def unconfigured() -> list[str]:
    """Roles with no token set — their endpoints are unauthenticated."""
    return [r for r in ROLES if not token_for(r)]


def presented(request: Request) -> str:
    return (request.headers.get(TOKEN_HEADER)
            or request.query_params.get("token")
            or "").strip()


def _matches(supplied: str, accepted: list[str]) -> bool:
    # compare_digest against every candidate, without short-circuiting on the
    # first match, so a caller cannot time which role its token belongs to.
    ok = False
    for token in accepted:
        if hmac.compare_digest(supplied.encode(), token.encode()):
            ok = True
    return ok


def enforce(role: str, request: Request) -> None:
    """Authorise a mutating call. Open when the role has no token configured."""
    accepted = [t for t in (token_for(r) for r in SATISFIED_BY[role]) if t]
    if not accepted:
        return
    supplied = presented(request)
    if not supplied or not _matches(supplied, accepted):
        raise HTTPException(
            403, f"This action needs the {role} token. Send it in the "
                 f"{TOKEN_HEADER} header.")


def is_instructor(request: Request) -> bool:
    """True only for a presented token matching a configured instructor token.

    Used to unlock beacon truth, so an unset token means False, never True.
    """
    token = token_for("instructor")
    if not token:
        return False
    supplied = presented(request)
    return bool(supplied) and hmac.compare_digest(supplied.encode(), token.encode())


def require_plugin(request: Request) -> None:
    """Gate the endpoint that hands out beacon truth before reveal.

    Fails closed: with no plugin key configured there is no way to reach it.
    """
    token = token_for("plugin")
    if not token:
        raise HTTPException(
            503, "Beacon truth is not being served: CAPVSAR_TOKEN_PLUGIN is "
                 "not set on this console.")
    supplied = presented(request)
    if not supplied or not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(403, "Incorrect plugin key.")
