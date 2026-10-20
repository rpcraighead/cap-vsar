"""
Link quality on the tactical net: from reach geometry to static and dropouts
(T33, following the fixed radio sites of T31).

The user's rule: being out of range must not cut a transmission off; it must
get noisier and choppier the worse the conditions are - distance, terrain in
the way, how close the station is to the radio horizon - and become unusable
only far beyond the horizon or deep in a terrain shadow.

Two pure layers, both deterministic:

* `margin(...)` turns the geometry `radio_sites` already computes (distance,
  the two-ended radio horizon, the terrain clearance from the engine's own
  rule) into a signal-margin score 0..1. The terrain part reuses the engine's
  diffraction-loss shape (PI_capvsar_df.terrain_loss_db: 20 dB grazing, 40 dB
  in deep shadow, graded over 500 ft of obstruction, a Fresnel-ish 1,000 ft
  graze zone); the horizon part is a smooth fall from "comfortably inside"
  (60 % of the horizon distance) to nothing at 115 % of it. A scenario field
  `radio_conditions` (0..1) scales the margin for weather or atmospherics; it
  is a hook, not a weather model.
* `impairment(margin)` maps the margin to what the listener hears: the static
  level, the speech level under it, and how often and how long the audio drops
  out. Monotonic and gradual. `DropoutGate` turns the rate into a seeded,
  reproducible on/off sequence per 20 ms frame; `impair_frame` applies both to
  one PCM frame.

`link_between` picks the path for a pair of stations: direct to the base
antenna or via a repeater (the better of the two), direct air-to-air, and a
nominal good link when a station's position is not known (ground teams report
none today). The direction finder never sees any of this: repeaters are on the
tactical net, the DF listens to the beacon (docs/RADIO_SITES.md §6).
"""
from __future__ import annotations

import math
import random
import sys
from array import array

from . import radio_sites

# From xplane/PI_capvsar_df.py (the propagation engine): the diffraction-loss
# shape. Repeated here because the console must not import the plugin.
TERRAIN_GRAZE_FT = 1000.0
TERRAIN_MASK_LOSS_DB = 20.0
TERRAIN_MASK_LOSS_MAX_DB = 40.0
TERRAIN_MASK_DEPTH_FT = 500.0

# Horizon: full margin inside 60 % of the radio-horizon distance, none at 115 %.
HORIZON_COMFORT = 0.60
HORIZON_UNUSABLE = 1.15

FREQ_MHZ = 148.0                  # the tactical net; sets the Fresnel-zone size
FRESNEL_GRAZE_MIN_FT = 100.0
FRAME_S = 0.02
NOISE_PEAK = 9000                 # int16 units; static at margin 0 is loud, not deafening
NOISE_TABLE_LEN = 48000           # one second of seeded white noise, reused cyclically
USABLE_MARGIN = 0.05


def _clamp(x, low=0.0, high=1.0):
    return low if x < low else high if x > high else x


def _smooth(x):
    x = _clamp(x)
    return x * x * (3.0 - 2.0 * x)


# --------------------------------------------------------------- margin

def horizon_score(distance_nm: float, horizon_nm: float) -> float:
    """1 comfortably inside the horizon, falling smoothly to 0 just beyond it."""
    if horizon_nm <= 0.0:
        return 0.0 if distance_nm > 0.0 else 1.0
    ratio = distance_nm / horizon_nm
    if ratio <= HORIZON_COMFORT:
        return 1.0
    if ratio >= HORIZON_UNUSABLE:
        return 0.0
    return 1.0 - _smooth((ratio - HORIZON_COMFORT) / (HORIZON_UNUSABLE - HORIZON_COMFORT))


def terrain_loss_db(clearance_ft) -> float:
    """The engine's diffraction loss from the worst clearance on the path."""
    if clearance_ft is None:
        return 0.0
    if clearance_ft < 0.0:
        depth = min(1.0, -clearance_ft / TERRAIN_MASK_DEPTH_FT)
        return TERRAIN_MASK_LOSS_DB + (TERRAIN_MASK_LOSS_MAX_DB - TERRAIN_MASK_LOSS_DB) * depth
    if clearance_ft < TERRAIN_GRAZE_FT:
        return TERRAIN_MASK_LOSS_DB * (1.0 - clearance_ft / TERRAIN_GRAZE_FT)
    return 0.0


def terrain_score(clearance_ft) -> float:
    """1 with a Fresnel-clear path, 0.5 grazing, 0 in deep shadow; 1 when unchecked."""
    return 1.0 - terrain_loss_db(clearance_ft) / TERRAIN_MASK_LOSS_MAX_DB


def fresnel_radius_ft(d1_nm: float, d2_nm: float) -> float:
    """First Fresnel zone radius at a point d1 from one end and d2 from the other."""
    total = d1_nm + d2_nm
    if total <= 0.0 or d1_nm <= 0.0 or d2_nm <= 0.0:
        return 0.0
    km = 1.852
    r_m = 17.32 * math.sqrt((d1_nm * km) * (d2_nm * km) / ((FREQ_MHZ / 1000.0) * (total * km)))
    return r_m * radio_sites.FT_PER_M


def terrain_loss_along(lat1, lon1, alt1_ft, lat2, lon2, alt2_ft, terrain_ft) -> float:
    """Worst diffraction loss (dB) along a path, the engine's sampling and
    obstruction rule with one adaptation: the engine's fixed 1,000 ft graze
    zone describes a beacon lying on the ground, where the ray really does
    graze; for a link between two antennas the zone that matters is the first
    Fresnel zone, which is only tens of feet wide near an elevated antenna.
    The graze zone here is the Fresnel radius at each sample, clamped to
    100-1,000 ft; the obstruction (negative clearance) rule is unchanged."""
    d_nm = radio_sites.distance_nm(lat1, lon1, lat2, lon2)
    samples = radio_sites.los_sample_count(d_nm)
    worst = 0.0
    for k in range(1, samples):
        fr = k / float(samples)
        ground = terrain_ft(lat1 + (lat2 - lat1) * fr, lon1 + (lon2 - lon1) * fr)
        if ground is None:
            continue
        ray = alt1_ft + (alt2_ft - alt1_ft) * fr - radio_sites.earth_bulge_ft(d_nm, fr)
        clearance = ray + radio_sites.PROBE_MARGIN_FT - ground
        if clearance < 0.0:
            loss = terrain_loss_db(clearance)
        else:
            graze = _clamp(fresnel_radius_ft(d_nm * fr, d_nm * (1.0 - fr)),
                           FRESNEL_GRAZE_MIN_FT, TERRAIN_GRAZE_FT)
            loss = TERRAIN_MASK_LOSS_DB * (1.0 - clearance / graze) if clearance < graze else 0.0
        worst = max(worst, loss)
    return worst


def path_margin(lat1, lon1, alt1_ft, lat2, lon2, alt2_ft, *, conditions=1.0, terrain_ft=None,
                radio_horizon=True) -> float:
    """Signal margin between two points: horizon score, Fresnel-aware terrain
    loss when a terrain sampler is given, and the conditions factor."""
    d_nm = radio_sites.distance_nm(lat1, lon1, lat2, lon2)
    horizon_nm = radio_sites.radio_horizon_nm(alt1_ft, alt2_ft)
    score = horizon_score(d_nm, horizon_nm) if radio_horizon else 1.0
    if terrain_ft is not None:
        score *= 1.0 - terrain_loss_along(lat1, lon1, alt1_ft, lat2, lon2, alt2_ft,
                                          terrain_ft) / TERRAIN_MASK_LOSS_MAX_DB
    return _clamp(score * _clamp(conditions))


def margin(distance_nm: float, horizon_nm: float, clearance_ft=None, *,
           conditions: float = 1.0, radio_horizon: bool = True) -> float:
    """Signal margin 0..1 for one path."""
    score = horizon_score(distance_nm, horizon_nm) if radio_horizon else 1.0
    return _clamp(score * terrain_score(clearance_ft) * _clamp(conditions))


def link_margin(link: dict, *, conditions: float = 1.0, radio_horizon: bool = True) -> float:
    """`margin` for a dict shaped like radio_sites.path / site_link output.
    Uses the engine's fixed graze zone (conservative near an elevated
    antenna); callers with positions and a terrain sampler get the
    Fresnel-aware figure from `path_margin`."""
    return margin(link["distance_nm"], link["horizon_nm"],
                  link.get("clearance_ft") if link.get("terrain_checked") else None,
                  conditions=conditions, radio_horizon=radio_horizon)


# ----------------------------------------------------------- impairment

def impairment(margin_value: float) -> dict:
    """What a listener hears at this margin. Every field is monotonic in it."""
    m = _clamp(margin_value)
    return {
        "margin": m,
        "noise": (1.0 - m) ** 1.5,                              # static level 0..1
        "speech_gain": 0.35 + 0.65 * m,                         # speech under the static
        "dropout_rate": 0.9 * _clamp((0.7 - m) / 0.7) ** 1.5,   # fraction of time dropped
        "dropout_s": 0.06 + 0.54 * (1.0 - m),                   # mean dropout length
        "usable": m > USABLE_MARGIN,
    }


def quality_word(margin_value: float) -> str:
    m = _clamp(margin_value)
    if m >= 0.8:
        return "clear"
    if m >= 0.4:
        return "weak"
    if m > USABLE_MARGIN:
        return "broken"
    return "unusable"


class DropoutGate:
    """A seeded on/off sequence per frame whose long-run dropped fraction is
    `rate` and whose dropouts last `mean_s` on average (half to one and a half
    times that). Deterministic for a seed, so a test can replay it."""

    def __init__(self, rate: float, mean_s: float, seed, frame_s: float = FRAME_S):
        self.rate = _clamp(rate, 0.0, 0.95)
        self.mean_frames = max(1.0, mean_s / frame_s)
        self.rng = random.Random(seed)
        self.remaining = 0
        self.p_start = (0.0 if self.rate <= 0.0
                        else min(1.0, self.rate / ((1.0 - self.rate) * self.mean_frames)))

    def next(self) -> bool:
        """True when the next 20 ms frame is dropped."""
        if self.remaining > 0:
            self.remaining -= 1
            return True
        if self.p_start > 0.0 and self.rng.random() < self.p_start:
            length = max(1, round(self.mean_frames * self.rng.uniform(0.5, 1.5)))
            self.remaining = length - 1
            return True
        return False


def _noise_table() -> array:
    rng = random.Random(0x5A1E)
    table = array("h", (rng.randint(-NOISE_PEAK, NOISE_PEAK) for _ in range(NOISE_TABLE_LEN)))
    return table


NOISE = _noise_table()


def impair_frame(pcm: bytes, imp: dict, phase: int, dropped: bool) -> tuple[bytes, int]:
    """One 16-bit little-endian mono PCM frame through the impairment.

    A dropped frame is silence (the squelch closes). Otherwise the speech is
    scaled by `speech_gain` and seeded static added at `noise`; the noise
    phase carries across frames so the static is continuous. A clear link
    returns the frame untouched, at no cost.
    """
    if dropped:
        return bytes(len(pcm)), phase
    if imp["noise"] <= 0.001 and imp["speech_gain"] >= 0.999:
        return pcm, phase
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    gain, noise, n = imp["speech_gain"], imp["noise"], NOISE_TABLE_LEN
    out = array("h", bytes(len(pcm)))
    for i, s in enumerate(samples):
        v = int(s * gain + NOISE[(phase + i) % n] * noise)
        out[i] = 32767 if v > 32767 else -32768 if v < -32768 else v
    if sys.byteorder != "little":
        out.byteswap()
    return out.tobytes(), (phase + len(samples)) % n


# --------------------------------------------------------------- routing

NOMINAL = {"path": "nominal", "via": None, "via_name": None, "to_base": None, "margin": 1.0,
           "heard": "position not reported; link assumed good"}


def _has_position(endpoint: dict) -> bool:
    return all(isinstance(endpoint.get(k), (int, float)) and math.isfinite(endpoint[k])
               for k in ("lat", "lon", "alt_ft"))


def _best_to_base(station: dict, base: radio_sites.RadioSite, sites, *, conditions, terrain_ft,
                  radio_horizon) -> dict:
    lat, lon, alt = station["lat"], station["lon"], station["alt_ft"]
    opts = {"conditions": conditions, "terrain_ft": terrain_ft, "radio_horizon": radio_horizon}
    direct = path_margin(lat, lon, alt, base.lat, base.lon, base.antenna_msl_ft, **opts)
    best = {"path": "direct", "via": None, "via_name": None, "margin": direct, "to_base": True}
    for site in sites:
        if site.role != "repeater":
            continue
        up = path_margin(lat, lon, alt, site.lat, site.lon, site.antenna_msl_ft, **opts)
        down = path_margin(site.lat, site.lon, site.antenna_msl_ft, base.lat, base.lon,
                           base.antenna_msl_ft, **opts)
        via = min(up, down)
        if via > best["margin"]:
            best = {"path": "repeater", "via": site.id, "via_name": site.name or site.id, "margin": via,
                    "to_base": True, "site": site}
    if best["margin"] <= 0.0:
        return {"path": "none", "via": None, "via_name": None, "margin": 0.0, "to_base": True,
                "heard": "out of range of base and repeater"}
    if best["path"] == "direct":
        best["heard"] = "heard direct at %s, %s" % (base.name or base.id, quality_word(best["margin"]))
    else:
        site = best.pop("site")
        best["heard"] = "heard via %s repeater, %s" % (site.name or site.id, quality_word(best["margin"]))
    return best


def link_between(a: dict, b: dict, sites, *, conditions: float = 1.0, terrain_ft=None,
                 radio_horizon: bool = True) -> dict:
    """The link two stations share. Endpoints: {"kind": aircraft|ground|base|unknown,
    "lat", "lon", "alt_ft"}; a base endpoint sits at the base antenna.

    Air or ground to base: the better of direct and via a repeater. Station to
    station (air-air, air-ground): direct line of sight. Any endpoint without a
    position, and base to base, is a nominal good link.
    """
    kinds = (a.get("kind"), b.get("kind"))
    if "base" in kinds and kinds == ("base", "base"):
        return dict(NOMINAL, heard="same station")
    base = next(s for s in sites if s.role == "base_antenna")
    if "base" in kinds:
        station = b if a.get("kind") == "base" else a
        if not _has_position(station):
            return dict(NOMINAL)
        return _best_to_base(station, base, sites, conditions=conditions, terrain_ft=terrain_ft,
                             radio_horizon=radio_horizon)
    if not (_has_position(a) and _has_position(b)):
        return dict(NOMINAL)
    m = path_margin(a["lat"], a["lon"], a["alt_ft"], b["lat"], b["lon"], b["alt_ft"],
                    conditions=conditions, terrain_ft=terrain_ft, radio_horizon=radio_horizon)
    if m <= 0.0:
        return {"path": "none", "via": None, "via_name": None, "margin": 0.0, "to_base": False,
                "heard": "out of range, direct"}
    return {"path": "direct", "via": None, "via_name": None, "margin": m, "to_base": False,
            "heard": "heard direct, %s" % quality_word(m)}


class LinkState:
    """One listener's view of one speaker: the link, its impairment and the
    running dropout gate and noise phase. `process` takes a PCM frame."""

    def __init__(self, link: dict, seed):
        self.link = link
        self.imp = impairment(link["margin"])
        self.gate = DropoutGate(self.imp["dropout_rate"], self.imp["dropout_s"], seed)
        self.phase = 0

    def update(self, link: dict, seed) -> bool:
        """Adopt a recomputed link; True when the audible state changed."""
        changed = (link["path"], link["via"], round(link["margin"], 2)) != \
                  (self.link["path"], self.link["via"], round(self.link["margin"], 2))
        if changed:
            self.link = link
            self.imp = impairment(link["margin"])
            self.gate = DropoutGate(self.imp["dropout_rate"], self.imp["dropout_s"], seed)
        return changed

    def process(self, pcm: bytes) -> bytes:
        dropped = self.gate.next()
        out, self.phase = impair_frame(pcm, self.imp, self.phase, dropped)
        return out

    def describe(self) -> dict:
        return {"path": self.link["path"], "via": self.link["via"], "via_name": self.link.get("via_name"),
                "to_base": self.link.get("to_base"),
                "margin": round(self.link["margin"], 3), "quality": quality_word(self.link["margin"]),
                "heard": self.link["heard"]}
