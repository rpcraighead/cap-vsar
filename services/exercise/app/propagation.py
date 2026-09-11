"""
Mock-bridge DF stub. NOT the propagation model.

`xplane/PI_capvsar_df.py` is the propagation model and the only authority on
what a direction finder shows. It has the aircraft's real attitude, a terrain
probe, the head and tuning the crew actually selected, a calibrated per-band
link budget, squelch, averaging and TIMEHOLD. This file has none of that and
never will: it exists so `mock_bridge.py` can drive the console, the map and
the bearing log with no simulator attached.

**It must never stand in for the plugin during a sortie** (P-11). It used to:
`/api/positions` called it whenever a station omitted `df`, so a plugin that
was loading, disabled or mid-reconnect silently handed the instructor a
different DF picture than the crew was looking at - with no marker saying so.
A DF display the exercise fabricated is worse than a blank one, because the
instructor cannot tell it is fabricated. The console now requires a caller to
ask for this explicitly (`mock: true`), and a real station that reports no
receiver state gets silence.

Where this stub does model something the plugin models, it uses the plugin's
figure so the demo is not actively misleading - see BURST_LEN_S below, which
`tests/test_propagation.py` pins to the plugin's own constant. The signal
curve is deliberately NOT a copy of the plugin's link budget: this is a stub,
not a second implementation to keep in step.
"""
from __future__ import annotations
import math, random
from dataclasses import dataclass

# C15-2: bearing and distance were spelled out here as well as in four other
# places. They live in app/geo.py now. true_bearing keeps its old name because
# that is what this module's callers say.
from .geo import R_NM, bearing_true, distance_nm      # noqa: F401

true_bearing = bearing_true

# Matched to PI_capvsar_df.py's BURST_PERIOD_S / BURST_LEN_S. This file used
# 1.5 s, and used it only to compose a note - the signal and the bearing stayed
# live right through the 49.5 s a 406 beacon is silent.
BURST_PERIOD_S = 50.0
BURST_LEN_S = 0.44


def is_406(band) -> bool:
    """Band tolerant of the shapes the console stores it in.

    It was compared as the string "406" only, so a scenario carrying 406.0, the
    float, or "406.025" got no burst cadence at all.
    """
    try:
        return float(band) > 400.0
    except (TypeError, ValueError):
        return str(band).strip().startswith("406")


def radio_horizon_nm(alt_ft_msl: float, beacon_elev_ft: float) -> float:
    """The standard VHF rule, 1.23*(sqrt(h_ac) + sqrt(h_bcn)), heights in feet.

    Both ends raise the horizon. This previously used the aircraft's height
    *above the beacon*, which went to zero as soon as the beacon sat higher
    than the aircraft — an aircraft below a ridge-top beacon a mile away was
    ruled out of range entirely. Kept identical to the plugin's form
    (PI_capvsar_df.py); the plugin remains authoritative whenever it reports.
    """
    return 1.23 * (math.sqrt(max(alt_ft_msl, 0.0))
                   + math.sqrt(max(beacon_elev_ft, 0.0)))


@dataclass
class DFResult:
    valid: bool
    bearing_rel: float | None      # degrees relative to the nose
    bearing_true: float | None
    signal: float                  # 0..1
    distance_nm: float
    in_cone: bool
    note: str = ""
    # Always true from this module. It travels with the result so nothing
    # downstream can present a stub reading as though the sim produced it.
    synthetic: bool = True


def compute(aircraft, beacon, effects, elapsed_s: float, squelch: float = 0.08) -> DFResult:
    d = distance_nm(aircraft["lat"], aircraft["lon"], beacon["lat"], beacon["lon"])
    brg_true = true_bearing(aircraft["lat"], aircraft["lon"], beacon["lat"], beacon["lon"])

    horizon = radio_horizon_nm(aircraft["alt_ft"], beacon.get("elev_ft", 0.0))
    if effects.get("radio_horizon", True) and d > horizon:
        return DFResult(False, None, None, 0.0, d, False, "below radio horizon")

    # free-space-ish falloff, normalised so a strong close signal saturates
    power = float(beacon.get("power", 1.0))
    signal = min(1.0, power * 25.0 / max(d * d, 0.25))

    # 406 radiates for 440 ms every 50 s. Between bursts nothing is arriving,
    # so there is no signal and no bearing to take - the plugin gates the
    # published value and carries the last bearing on TIMEHOLD. This stub has
    # no TIMEHOLD, so it reports the gap honestly instead of inventing one.
    note = ""
    if is_406(beacon.get("band")) and effects.get("burst_cadence", True):
        phase = elapsed_s % BURST_PERIOD_S
        if phase > BURST_LEN_S:
            return DFResult(False, None, None, 0.0, d, False,
                            "between 406 bursts - next in %.0fs"
                            % (BURST_PERIOD_S - phase))

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
