"""
Simplified DF propagation model.

SCOPE: this exists so the exercise console is demonstrable and testable before
the X-Plane plugin exists. It models range, radio horizon, 406 burst cadence,
cone of confusion and an optional multipath offset.

It deliberately does NOT model terrain masking, because that needs a terrain
probe which only the simulator has. Per the implementation plan the
authoritative engine lives in the XPPython3 plugin; this is the stand-in that
lets the console, the map and the bearing log be built and validated first.
When the real plugin lands it reports bearing/signal directly and this module
is used only by the mock bridge.
"""
from __future__ import annotations
import math, random
from dataclasses import dataclass

R_NM = 3440.065


def true_bearing(lat1, lon1, lat2, lon2) -> float:
    dlon = math.radians(lon2 - lon1)
    la1, la2 = math.radians(lat1), math.radians(lat2)
    y = math.sin(dlon) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def distance_nm(lat1, lon1, lat2, lon2) -> float:
    la1, la2 = math.radians(lat1), math.radians(lat2)
    dla, dlo = la2 - la1, math.radians(lon2 - lon1)
    a = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * R_NM * math.asin(min(1.0, math.sqrt(a)))


def radio_horizon_nm(alt_ft_msl: float, beacon_elev_ft: float) -> float:
    """1.23 * sqrt(height above the beacon), the standard VHF line-of-sight rule."""
    h = max(alt_ft_msl - beacon_elev_ft, 0.0)
    return 1.23 * math.sqrt(h)


@dataclass
class DFResult:
    valid: bool
    bearing_rel: float | None      # degrees relative to the nose
    bearing_true: float | None
    signal: float                  # 0..1
    distance_nm: float
    in_cone: bool
    note: str = ""


def compute(aircraft, beacon, effects, elapsed_s: float, squelch: float = 0.08) -> DFResult:
    d = distance_nm(aircraft["lat"], aircraft["lon"], beacon["lat"], beacon["lon"])
    brg_true = true_bearing(aircraft["lat"], aircraft["lon"], beacon["lat"], beacon["lon"])

    horizon = radio_horizon_nm(aircraft["alt_ft"], beacon.get("elev_ft", 0.0))
    if effects.get("radio_horizon", True) and d > horizon:
        return DFResult(False, None, None, 0.0, d, False, "below radio horizon")

    # free-space-ish falloff, normalised so a strong close signal saturates
    power = float(beacon.get("power", 1.0))
    signal = min(1.0, power * 25.0 / max(d * d, 0.25))

    # 406 transmits a short burst about every 50 s; between bursts the needle holds
    note = ""
    if beacon.get("band") == "406" and effects.get("burst_cadence", True):
        phase = elapsed_s % 50.0
        if phase > 1.5:
            note = f"holding - next burst in {50.0 - phase:.0f}s"

    if signal < squelch:
        return DFResult(False, None, None, signal, d, False, "below squelch")

    # cone of confusion: bearing indeterminate within a cone above the source
    agl = max(aircraft["alt_ft"] - beacon.get("elev_ft", 0.0), 1.0)
    cone_radius_nm = (agl / 6076.0) * math.tan(math.radians(30.0))
    in_cone = effects.get("cone_of_confusion", True) and d < cone_radius_nm
    if in_cone:
        return DFResult(False, None, None, signal, d, True, "cone of confusion")

    if effects.get("multipath", False):
        # a plausible false bearing: offset that appears intermittently
        if int(elapsed_s / 12.0) % 3 == 0:
            brg_true = (brg_true + effects.get("multipath_offset_deg", 40.0)) % 360.0
            note = "multipath"

    rel = (brg_true - aircraft.get("hdg_true", 0.0)) % 360.0
    return DFResult(True, rel, brg_true, signal, d, False, note)
