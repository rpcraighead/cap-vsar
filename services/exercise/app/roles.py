"""
Who may call what, and what they are allowed to see (C15-1).

The role dependencies and the truth filter belong together: one decides
whether a request is admitted, the other decides how much of the beacon the
answer contains. Both were inline in main.py.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from . import access

# The three fields that are the answer to the exercise. Everything the console
# sends to a browser goes through public_scenario(), and these come out of it
# unless the caller has explicitly been allowed them.
TRUTH_FIELDS = ("beacon_lat", "beacon_lon", "beacon_elev_ft")

# X2-8: the instructor's notes are written to describe the exercise to the
# instructor and the seed scenario's name the beacon's location in words.
# Mission base is given alert_text and the alert_* fields, which are written
# to be shown. Notes travel with the truth fields.
TRUTH_ONLY_TEXT = ("notes",)

# X2-1: what the direction finder was showing is beacon truth in another form
# (bearing plus distance from a known position is a fix). The receiver's
# *state* is not: base may know a head is fitted, powered and tuned, which is
# what it needs to ask "why can't they hear it". Everything geometric stays
# behind the same gate as the beacon itself.
DF_PUBLIC_KEYS = ("valid", "head_type", "power", "tuned_to")


def public_scenario(sc: dict, *, include_truth: bool) -> dict:
    """A scenario safe to send to a browser. Truth only when explicitly allowed."""
    d = dict(sc)
    if not include_truth:
        for f in TRUTH_FIELDS + TRUTH_ONLY_TEXT:
            d.pop(f, None)
    return d


def public_aircraft(ac: dict, *, include_truth: bool) -> dict:
    """An aircraft record safe to send to a browser (X2-1)."""
    if include_truth or "df" not in ac:
        return ac
    out = dict(ac)
    df = ac.get("df") or {}
    out["df"] = {k: df[k] for k in DF_PUBLIC_KEYS if k in df}
    return out


def viewer_sees_truth(request) -> bool:
    """True only for an instructor session or the configured instructor token.

    Works for a WebSocket as well as a Request: both carry the headers and
    cookies the session lookup reads.
    """
    return access.is_instructor(request)


def role_gate(role: str):
    def dep(request: Request) -> None:
        access.enforce(role, request)
    return dep


def _read_gate(request: Request) -> None:
    access.enforce_read(request)


any_role = Depends(_read_gate)
instructor_only = Depends(role_gate("instructor"))
base_or_instructor = Depends(role_gate("base"))
plugin_only = Depends(role_gate("plugin"))


