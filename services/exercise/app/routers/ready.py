"""
The Ready room: who is here, and who is ready (UX phase 2 reference screen,
docs/UX_REVIEW_2026-10-11.md §4.3; seats and checks per docs/DECISIONS_2026-10-11.md D5).

Everything here is derived: the roster says who should be here, the hub's
presence records say who has opened a page, the radio's session table says
who is on the net, and the plugin's reports say which stations are alive and
whether the DF head is powered. Nothing is stored except the checks a
participant attests to (mic tested, briefing read), which live in the hub and
reset with the console, as a readiness check should.
"""
from __future__ import annotations

import re
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import access, radio
from ..hub import hub
from ..roles import any_role, public_scenario

router = APIRouter()

STATION_FRESH_S = 10.0     # a plugin report younger than this is "alive"
STATION_STALE_S = 60.0     # older than this, the station is lost
HUMAN_SEATS = tuple(s for s, d in access.SEATS.items() if d["role"] != "plugin")
SELF_CHECKS = ("mic", "briefing")


def norm_callsign(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _on_net() -> set[str]:
    return {norm_callsign(getattr(r, "callsign", "")) for r in radio.SESSIONS}


def _aircraft_by_callsign() -> dict[str, dict]:
    return {norm_callsign(a.get("callsign")): a for a in hub.aircraft.values()}


def _presence_for(row: dict) -> dict | None:
    key = (row.get("code") or "").rsplit("-", 1)[0]
    return hub.presence.get(key)


def _checks_for(seat: str, row: dict, pres: dict | None, ac: dict | None,
                on_net: set[str], now: float) -> dict[str, str]:
    """One state per applicable check: ok / pending / bad. Checks that do not
    apply to the seat are absent, so the tile only shows what it needs."""
    kind = access.SEATS[seat]["kind"]
    role = access.SEATS[seat]["role"]
    checks: dict[str, str] = {}
    joined = bool(pres) or bool(row.get("last_login"))
    if seat != "station":
        checks["joined"] = "ok" if joined else "pending"
    if role in ("base", "aircrew", "ground_team"):
        checks["on_net"] = "ok" if norm_callsign(row.get("callsign")) in on_net else "pending"
        checks["mic"] = "ok" if (pres or {}).get("checks", {}).get("mic") else "pending"
    if kind == "aircraft":
        age = (now - ac["t"]) if ac else None
        if age is None:
            checks["station"] = "pending"
        elif age <= STATION_FRESH_S:
            checks["station"] = "ok"
        else:
            checks["station"] = "bad"
        if seat == "observer":
            df = (ac or {}).get("df") or {}
            if not ac or not df:
                checks["df_head"] = "pending"
            elif df.get("power") and df.get("head_type"):
                checks["df_head"] = "ok"
            else:
                checks["df_head"] = "bad"
    if seat in HUMAN_SEATS:
        checks["briefing"] = "ok" if (pres or {}).get("checks", {}).get("briefing") else "pending"
    return checks


def _status(seat: str, checks: dict, pres: dict | None, ac: dict | None,
            running: bool, now: float) -> str:
    kind = access.SEATS[seat]["kind"]
    if pres and not pres.get("socket") and now - pres.get("last_seen", now) > STATION_STALE_S:
        return "lost"
    if kind == "aircraft" and ac and now - ac["t"] > STATION_STALE_S:
        return "lost"
    if kind == "aircraft" and ac and now - ac["t"] > STATION_FRESH_S:
        return "stale"
    if running and kind == "aircraft" and checks.get("station") == "ok":
        return "flying"
    if checks and all(v == "ok" for v in checks.values()):
        return "ready"
    if checks.get("on_net") == "ok":
        return "on_net"
    if checks.get("joined") == "ok" or (pres and pres.get("socket")):
        return "joined"
    return "invited"


def build_ready_state(*, include_email: bool = False) -> dict:
    """`include_email`: only an instructor viewer is shown the addresses seats
    were assigned to; everyone sees when and how a seat last signed in."""
    now = time.time()
    setup = access.get_exercise_setup()
    roster = access.get_roster()
    on_net = _on_net()
    by_callsign = _aircraft_by_callsign()
    running = bool(hub.sortie and not hub.sortie.get("stopped"))

    # Aircraft slots in the order the setup page lists the aircraft: the slot
    # is the colour (D6.4), so it must not depend on roster row order.
    slots: dict[str, int] = {}
    def ac_key(callsign, aircraft_id):
        return norm_callsign(callsign) or (aircraft_id or "")

    for ac in (setup.get("config") or {}).get("aircraft") or []:
        key = ac_key(ac.get("callsign"), ac.get("id"))
        if key and key not in slots:
            slots[key] = len(slots) + 1
    for row in roster:
        key = ac_key(row.get("callsign"), row.get("aircraft_id"))
        if access.SEATS[access.seat_of(row)]["kind"] == "aircraft" and key and key not in slots:
            slots[key] = len(slots) + 1

    seats = []
    for row in roster:
        seat = access.seat_of(row)
        pres = _presence_for(row)
        ac = by_callsign.get(norm_callsign(row.get("callsign"))) if access.SEATS[seat]["kind"] == "aircraft" else None
        checks = _checks_for(seat, row, pres, ac, on_net, now)
        key = ac_key(row.get("callsign"), row.get("aircraft_id"))
        seats.append({
            "id": row["id"],
            "seat": seat,
            "label": access.SEATS[seat]["label"],
            "kind": access.SEATS[seat]["kind"],
            "role": row.get("role"),
            "title": row.get("title") or "",
            "name": row.get("assigned_name") or "",
            "callsign": row.get("callsign") or "",
            "aircraft_id": row.get("aircraft_id") or "",
            "ac_slot": slots.get(key) if access.SEATS[seat]["kind"] == "aircraft" else None,
            "status": _status(seat, checks, pres, ac, running, now),
            "checks": checks,
            "page": (pres or {}).get("page", ""),
            "seen_ago": round(now - pres["last_seen"], 1) if pres else None,
            "last_login": row.get("last_login"),
            "last_login_via": row.get("last_login_via"),
            **({"email": row.get("email")} if include_email else {}),
        })

    scenario = None
    if hub.scenario:
        pub = public_scenario(hub.scenario, include_truth=False)
        scenario = {k: pub.get(k) for k in ("id", "name", "band", "alert_kind",
                                             "alert_text", "alert_lat", "alert_lon",
                                             "alert_radius_nm")}
    human = [s for s in seats if s["seat"] != "station"]
    ready = [s for s in human if s["status"] in ("ready", "flying")]
    blocking = [f"{s['callsign'] or s['label']}: " + ", ".join(
        k for k, v in s["checks"].items() if v != "ok") for s in human if s["status"] not in ("ready", "flying")]
    return {
        "exercise": {"name": setup.get("name") or "Exercise", "updated": setup.get("updated")},
        "sortie": hub.sortie,
        "scenario": scenario,
        "channels": radio.CHANNELS,
        "seats": seats,
        "summary": {"ready": len(ready), "total": len(human), "blocking": blocking},
        "server_time": now,
    }


@router.get("/api/ready", dependencies=[any_role])
def ready_state(request: Request):
    sess = access.get_session_from_request(request)
    key = (sess or {}).get("code") or "DEV"
    hub.touch_presence(key, role=(sess or {}).get("role", ""))
    state = build_ready_state(include_email=access.is_instructor(request))
    state["me"] = {"key": key, "role": (sess or {}).get("role") or ("instructor" if access.dev_open() else ""),
                   "callsign": (sess or {}).get("callsign", ""),
                   "checks": hub.presence.get(key, {}).get("checks", {})}
    return state


class CheckIn(BaseModel):
    check: str = Field(pattern="^(mic|briefing)$")
    ok: bool = True


@router.post("/api/ready/check", dependencies=[any_role])
def ready_check(body: CheckIn, request: Request):
    """A participant attests to a check (headset tested, briefing read)."""
    sess = access.get_session_from_request(request)
    key = (sess or {}).get("code") or "DEV"
    rec = hub.touch_presence(key, role=(sess or {}).get("role", ""))
    rec["checks"][body.check] = bool(body.ok)
    return {"ok": True, "checks": rec["checks"]}
