"""
Debrief scoring for one sortie (docs/UX_REVIEW_2026-10-11.md 3.4 and 4.5).

The debrief used to score in the browser, from whatever page of /track it had
loaded: one paragraph per aircraft, closest approach and track efficiency, and
nothing about the bearings. This works out the measures the SAREX rehearsal is
judged on (docs/USE_CASE_SAREX_REHEARSAL.md, "What the system records") on the
server, from every recorded row, with app/geo.py's geometry:

  * what the direction finder needle showed against the true bearing, from the
    `df` recorded with each position (V2-5);
  * the bearings mission base logged against the true bearing;
  * closest point of approach, and the first logged bearing within
    GOOD_CUT_DEG of the truth;
  * track efficiency, defined exactly as debrief.js defined it: the direct
    line from the first fix to the beacon over the distance flown.

Every one of those is beacon truth in another form - an error plus the
reported bearing is the true bearing, and two of them are a fix. So the truth
decision is not made here: it is the /track endpoint's decision, taken by
calling it, so the two cannot drift apart. Unrevealed, or withheld because the
same beacon is being flown right now (X2-2), the counts and the distance flown
come back and every truth-derived field is null.
"""
from __future__ import annotations

import json
import math

from fastapi import APIRouter, HTTPException, Request

from .. import access
from ..geo import bearing_true, distance_nm
from ..roles import any_role
from ..store import db, load_effects
from . import sorties

router = APIRouter()

# A logged bearing within this many degrees of the truth is a "good cut".
GOOD_CUT_DEG = 10.0

# The needle series is downsampled past this many points per aircraft. A plugin
# reports about once a second, so a two-hour sortie is 7,000 samples an
# aircraft; the chart is a few hundred pixels wide. Each bucket keeps its
# lowest and highest error, so a multipath swing survives the reduction.
SERIES_MAX_POINTS = 1200

# Sentence-case names for the effects an instructor can inject (app.js).
EFFECT_LABELS = {
    "radio_horizon": "Radio horizon",
    "terrain_masking": "Terrain masking",
    "burst_cadence": "406 burst cadence",
    "cone_of_confusion": "Cone of confusion",
    "multipath": "Multipath",
    "airframe_shadowing": "Wing blanking",
}


# ------------------------------------------------------------------ the maths
def signed_error(reported: float, lat: float, lon: float, beacon: dict) -> float:
    """Reported bearing minus the true bearing from (lat, lon) to the beacon.

    Degrees in [-180, 180): positive is clockwise of the truth. A position due
    north of the beacon has a true bearing of 180, so a report of 170 is -10.
    """
    truth = bearing_true(lat, lon, beacon["lat"], beacon["lon"])
    return (float(reported) - truth + 540.0) % 360.0 - 180.0


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def df_error_series(positions: list[dict], beacon: dict) -> tuple[list[dict], int]:
    """Needle error for every position whose recorded `df` carries a bearing.

    A sample the receiver itself marked `valid: false` is skipped and counted:
    the plugin leaves the last (or a zero) bearing in place when it has no
    signal, and charting that as an error would score a needle nobody could
    read. Returns (series, skipped).
    """
    out, skipped = [], 0
    for p in positions:
        df = p.get("df")
        if not isinstance(df, dict) or not _number(df.get("bearing_true")):
            continue
        if df.get("valid") is False:
            skipped += 1
            continue
        point = {"t": p["t"], "error": round(signed_error(
            df["bearing_true"], p["lat"], p["lon"], beacon), 2)}
        if df.get("in_cone") is True:
            point["in_cone"] = True
        out.append(point)
    return out, skipped


def bearing_error_series(bearings: list[dict], beacon: dict) -> list[dict]:
    """Each bearing mission base logged, against the truth from where it was taken."""
    return [{"t": b["t"], "bearing_true": b["bearing_true"],
             "error": round(signed_error(b["bearing_true"], b["lat"], b["lon"], beacon), 2),
             "note": b.get("note") or ""}
            for b in bearings if _number(b.get("bearing_true"))]


def error_stats(series: list[dict]) -> dict | None:
    if not series:
        return None
    errs = [abs(p["error"]) for p in series]
    return {"n": len(errs), "mean_abs": round(sum(errs) / len(errs), 2),
            "max_abs": round(max(errs), 2),
            "good": sum(1 for e in errs if e <= GOOD_CUT_DEG)}


def closest_approach(positions: list[dict], beacon: dict) -> dict | None:
    """Closest point of approach: the first fix at the least distance."""
    best = None
    for p in positions:
        d = distance_nm(p["lat"], p["lon"], beacon["lat"], beacon["lon"])
        if best is None or d < best["nm"]:
            best = {"nm": d, "t": p["t"]}
    if best:
        best["nm"] = round(best["nm"], 3)
    return best


def first_good_cut(errors: list[dict], within: float = GOOD_CUT_DEG) -> dict | None:
    """The earliest logged bearing within `within` degrees of the truth."""
    for b in sorted(errors, key=lambda b: b["t"]):
        if abs(b["error"]) <= within:
            return {"t": b["t"], "error": b["error"]}
    return None


def flown_nm(positions: list[dict]) -> float:
    return sum(distance_nm(a["lat"], a["lon"], b["lat"], b["lon"])
               for a, b in zip(positions, positions[1:]))


def track_efficiency(positions: list[dict], beacon: dict) -> dict | None:
    """debrief.js's definition, unchanged: direct line from the first fix to the
    beacon, over the distance flown (floored at 0.01 nm), as a percentage."""
    if not positions:
        return None
    flown = flown_nm(positions)
    first = positions[0]
    direct = distance_nm(first["lat"], first["lon"], beacon["lat"], beacon["lon"])
    return {"flown_nm": round(flown, 2), "direct_nm": round(direct, 2),
            "efficiency_pct": round(direct / max(flown, 0.01) * 100.0, 1)}


def downsample(series: list[dict], max_points: int = SERIES_MAX_POINTS) -> list[dict]:
    """At most about `max_points` points, keeping each bucket's extremes in time order."""
    if len(series) <= max_points:
        return series
    size = math.ceil(len(series) / max(1, max_points // 2))
    out = []
    for i in range(0, len(series), size):
        bucket = series[i:i + size]
        lo = min(bucket, key=lambda p: p["error"])
        hi = max(bucket, key=lambda p: p["error"])
        out.extend([lo] if lo is hi else sorted((lo, hi), key=lambda p: p["t"]))
    return out


# --------------------------------------------------------------- who is who
def _key(callsign) -> str:
    return " ".join(str(callsign or "").split()).casefold()


def roster_callsigns() -> list[str]:
    """Aircraft callsigns in the order the exercise setup lists them."""
    try:
        aircraft = access.get_exercise_setup().get("config", {}).get("aircraft", [])
    except Exception:            # an auth database that is missing or locked
        return []
    return [a.get("callsign") for a in aircraft if isinstance(a, dict) and a.get("callsign")]


def assign_slots(callsigns, roster: list[str]) -> list[tuple[str, int | None]]:
    """(callsign, slot) in display order. D6: aircraft 1-4 take --ac-1..4 in
    roster order, and colour follows the aircraft, not its rank, so a roster
    aircraft keeps its slot when another did not fly. Callsigns the roster does
    not list take the free slots alphabetically; past four there is no slot."""
    order = {_key(c): i for i, c in enumerate(roster)}
    slots, taken = {}, set()
    for cs in callsigns:
        i = order.get(_key(cs))
        if i is not None and i < 4:
            slots[cs] = i + 1
            taken.add(i + 1)
    free = [s for s in (1, 2, 3, 4) if s not in taken]
    for cs in sorted(c for c in callsigns if c not in slots):
        slots[cs] = free.pop(0) if free else None
    return sorted(slots.items(), key=lambda kv: (kv[1] is None, kv[1] or 0, kv[0]))


# -------------------------------------------------------------------- route
@router.get("/api/sorties/{oid}/analysis", dependencies=[any_role])
def analysis(oid: str, request: Request):
    """Per-aircraft scoring for the debrief dashboard."""
    with db() as c:
        s = c.execute("SELECT * FROM sorties WHERE id=?", (oid,)).fetchone()
        if not s:
            raise HTTPException(404, "no such sortie")
        rows = c.execute(
            "SELECT callsign, t, lat, lon, df_json FROM positions"
            " WHERE sortie_id=? ORDER BY t", (oid,)).fetchall()
    # One truth decision for the debrief, not two: whatever /track would hand
    # this viewer (revealed, withheld for a live sortie on the same beacon, or
    # neither) is what this endpoint scores against.
    view = sorties.track(oid, since=0.0, limit=1, request=request)
    beacon = view["beacon"] if view["revealed"] else None
    bearings, messages = view["bearings"], view["messages"]

    by_cs: dict[str, list[dict]] = {}
    for r in rows:
        p = {"t": r["t"], "lat": r["lat"], "lon": r["lon"]}
        if beacon is not None and r["df_json"]:
            try:
                p["df"] = json.loads(r["df_json"])
            except (TypeError, ValueError):
                pass
        by_cs.setdefault(r["callsign"] or "UNKNOWN", []).append(p)
    brg_by_cs: dict[str, list[dict]] = {}
    for b in bearings:
        brg_by_cs.setdefault(b["callsign"], []).append(b)

    try:
        effects = load_effects(s["effects"]) if s["effects"] else {}
    except (TypeError, ValueError):
        effects = {}
    active = []
    for k, label in EFFECT_LABELS.items():
        if effects.get(k) is True:
            if k == "multipath" and _number(effects.get("multipath_offset_deg")):
                label = f"{label} ({effects['multipath_offset_deg']:g}° offset)"
            active.append({"key": k, "label": label})

    aircraft = []
    for cs, slot in assign_slots(set(by_cs) | set(brg_by_cs), roster_callsigns()):
        P, B = by_cs.get(cs, []), brg_by_cs.get(cs, [])
        k = _key(cs)
        entry = {
            "callsign": cs, "slot": slot,
            "counts": {"positions": len(P), "bearings": len(B),
                       "messages": sum(1 for m in messages
                                       if k in (_key(m["sender"]), _key(m["recipient"])))},
            "flown_nm": round(flown_nm(P), 2),
            "df_error": None, "df_error_stats": None, "df_invalid": None,
            "bearing_error": None, "bearing_error_stats": None,
            "cpa": None, "first_good_cut": None, "track": None,
        }
        if beacon is not None:
            df, skipped = df_error_series(P, beacon)
            berr = bearing_error_series(B, beacon)
            entry.update({
                "df_error": downsample(df), "df_error_stats": error_stats(df),
                "df_invalid": skipped,
                "bearing_error": berr, "bearing_error_stats": error_stats(berr),
                "cpa": closest_approach(P, beacon),
                "first_good_cut": first_good_cut(berr),
                "track": track_efficiency(P, beacon),
            })
        aircraft.append(entry)

    return {
        "id": s["id"], "name": s["name"], "started": s["started"],
        "stopped": s["stopped"],
        "revealed": bool(view["revealed"]), "withheld": bool(view["withheld"]),
        "t0": rows[0]["t"] if rows else None, "t1": rows[-1]["t"] if rows else None,
        "good_cut_deg": GOOD_CUT_DEG,
        "effects": effects, "effects_active": active,
        "counts": {"positions": len(rows), "bearings": len(bearings),
                   "messages": len(messages)},
        "aircraft": aircraft,
    }
