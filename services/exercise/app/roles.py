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

def public_scenario(sc: dict, *, include_truth: bool) -> dict:
    """A scenario safe to send to a browser. Truth only when explicitly allowed."""
    d = dict(sc)
    if not include_truth:
        for f in TRUTH_FIELDS:
            d.pop(f, None)
    return d


def role_gate(role: str):
    def dep(request: Request) -> None:
        access.enforce(role, request)
    return dep


instructor_only = Depends(role_gate("instructor"))
base_or_instructor = Depends(role_gate("base"))
plugin_only = Depends(role_gate("plugin"))


