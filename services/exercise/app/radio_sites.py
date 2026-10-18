"""
Fixed radio sites: where the Mission Base antenna and the repeater physically
are, and whether a station at some position can reach them (T31).

Radio reach in a real exercise depends on where the fixed equipment stands:
a base antenna at an airfield in a valley hears a different sky than a
repeater on a mountain. The exercise models that with a small static list of
sites (settings.RADIO_SITES, or a JSON file named by CAPVSAR_RADIO_SITES) and
two reach rules that already exist in this repository:

* the two-ended VHF radio horizon, `propagation.radio_horizon_nm`, the same
  form the propagation engine uses for the beacon; and
* the engine's terrain line-of-sight rule, `PI_capvsar_df.terrain_clearance`:
  sample the straight path every LOS_SPACING_NM, drop the ray by the earth's
  bulge (4/3 effective radius), and call the path blocked when the ground
  comes within PROBE_MARGIN_FT of it. The numbers below are the engine's;
  they are repeated here because the console must not import the X-Plane
  plugin. The console has no terrain of its own, so a caller passes a
  `terrain_ft(lat, lon)` sampler (the simulator's probe, a DEM, or a test's
  synthetic ridge); with none, only the radio horizon applies and the result
  says so (`terrain_checked: False`).

Routing (`route`): a station is heard at base directly when it reaches the
base antenna; otherwise via a repeater when it reaches the repeater and the
repeater's fixed link reaches the base; otherwise it is out of range. Nothing
in the live radio path uses this yet - the voice net does not gate delivery on
position - so this module is data, arithmetic and an endpoint, not behaviour.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

from .geo import distance_nm
from .propagation import radio_horizon_nm
from . import settings

ROLES = ("base_antenna", "repeater")

# National CAP repeater pair convention (docs/CA_WING_REPEATERS.md): the
# repeater transmits on the output and listens on the input.
REPEATER_PAIRS = {
    "primary": {"input_mhz": 143.550, "output_mhz": 148.125},
    "secondary": {"input_mhz": 143.700, "output_mhz": 148.150},
}

# Same values as xplane/PI_capvsar_df.py (the propagation engine).
LOS_SAMPLES = 24
LOS_SAMPLES_MAX = 96
LOS_SPACING_NM = 0.25
M_PER_NM = 1852.0
FT_PER_M = 3.28084
EARTH_R_M = 6_371_000.0
EARTH_RADIUS_K = 4.0 / 3.0
PROBE_MARGIN_FT = 50.0

MAX_ANTENNA_AGL_FT = 500.0


@dataclass(frozen=True)
class RadioSite:
    id: str
    role: str
    lat: float
    lon: float
    ground_elev_ft: float
    antenna_agl_ft: float
    name: str = ""

    def __post_init__(self):
        if not isinstance(self.id, str) or not 1 <= len(self.id) <= 32:
            raise ValueError("radio site id must be 1-32 characters")
        if self.role not in ROLES:
            raise ValueError("radio site %s: role must be one of %s" % (self.id, ", ".join(ROLES)))
        for key in ("lat", "lon", "ground_elev_ft", "antenna_agl_ft"):
            value = getattr(self, key)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("radio site %s: %s must be a finite number" % (self.id, key))
        if not -90.0 <= self.lat <= 90.0 or not -180.0 <= self.lon <= 180.0:
            raise ValueError("radio site %s: position outside the globe" % self.id)
        if not -1500.0 <= self.ground_elev_ft <= 30000.0:
            raise ValueError("radio site %s: ground elevation implausible" % self.id)
        if not 0.0 <= self.antenna_agl_ft <= MAX_ANTENNA_AGL_FT:
            raise ValueError("radio site %s: antenna height must be 0-%d ft AGL"
                             % (self.id, MAX_ANTENNA_AGL_FT))

    @property
    def antenna_msl_ft(self) -> float:
        return float(self.ground_elev_ft + self.antenna_agl_ft)

    def as_dict(self) -> dict:
        return {"id": self.id, "role": self.role, "name": self.name, "lat": self.lat, "lon": self.lon,
                "ground_elev_ft": self.ground_elev_ft, "antenna_agl_ft": self.antenna_agl_ft,
                "antenna_msl_ft": self.antenna_msl_ft}


def load_sites(rows) -> list[RadioSite]:
    """Validate a site list: unique ids, exactly one base antenna, any number of repeaters."""
    if not isinstance(rows, (list, tuple)):
        raise ValueError("radio sites must be a list")
    sites = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each radio site must be an object")
        unknown = set(row) - {"id", "role", "lat", "lon", "ground_elev_ft", "antenna_agl_ft", "name"}
        if unknown:
            raise ValueError("radio site has unknown keys: %s" % ", ".join(sorted(unknown)))
        sites.append(RadioSite(**{**row, "name": str(row.get("name", ""))}))
    ids = [s.id for s in sites]
    if len(set(ids)) != len(ids):
        raise ValueError("radio site ids must be unique")
    if sum(1 for s in sites if s.role == "base_antenna") != 1:
        raise ValueError("exactly one base_antenna site is required")
    return sites


def repeater_pair(name) -> dict:
    if name not in REPEATER_PAIRS:
        raise ValueError("repeater pair must be one of %s" % ", ".join(REPEATER_PAIRS))
    return {"name": name, **REPEATER_PAIRS[name]}


def configured() -> dict:
    """The exercise's sites and repeater pair: settings, or the JSON file
    CAPVSAR_RADIO_SITES names ({"sites": [...], "repeater_pair": "primary"})."""
    path = os.environ.get("CAPVSAR_RADIO_SITES", "").strip()
    if path:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or "sites" not in data:
            raise ValueError("CAPVSAR_RADIO_SITES must hold an object with a 'sites' list")
        rows, pair = data["sites"], data.get("repeater_pair", settings.REPEATER_PAIR)
    else:
        rows, pair = settings.RADIO_SITES, settings.REPEATER_PAIR
    return {"sites": load_sites(rows), "repeater_pair": repeater_pair(pair)}


# ------------------------------------------------------------------ reach

def earth_bulge_ft(d_nm: float, fr: float) -> float:
    """Height of the curved surface above the straight chord, in feet (engine form)."""
    d_m = d_nm * M_PER_NM
    return fr * (1.0 - fr) * d_m * d_m / (2.0 * EARTH_R_M * EARTH_RADIUS_K) * FT_PER_M


def los_sample_count(d_nm: float) -> int:
    wanted = math.ceil(max(0.0, d_nm) / LOS_SPACING_NM)
    return int(max(LOS_SAMPLES, min(LOS_SAMPLES_MAX, wanted)))


def terrain_clearance(lat1, lon1, alt1_ft, lat2, lon2, alt2_ft, terrain_ft, d_nm=None):
    """(blocked, worst_clearance_ft): the engine's rule with an injected sampler.

    `terrain_ft(lat, lon)` returns ground elevation in feet, or None where it
    has no data (treated as clear, as the engine treats unloaded scenery).
    """
    if d_nm is None:
        d_nm = distance_nm(lat1, lon1, lat2, lon2)
    samples = los_sample_count(d_nm)
    worst = None
    for k in range(1, samples):
        fr = k / float(samples)
        lat = lat1 + (lat2 - lat1) * fr
        lon = lon1 + (lon2 - lon1) * fr
        ground = terrain_ft(lat, lon)
        if ground is None:
            continue
        ray = alt1_ft + (alt2_ft - alt1_ft) * fr - earth_bulge_ft(d_nm, fr)
        clearance = ray + PROBE_MARGIN_FT - ground
        if worst is None or clearance < worst:
            worst = clearance
    if worst is None:
        return False, None
    return worst < 0.0, worst


def _link(lat1, lon1, alt1_ft, lat2, lon2, alt2_ft, *, terrain_ft=None, radio_horizon=True) -> dict:
    d = distance_nm(lat1, lon1, lat2, lon2)
    horizon = radio_horizon_nm(alt1_ft, alt2_ft)
    within = (not radio_horizon) or d <= horizon
    if terrain_ft is not None:
        blocked, clearance = terrain_clearance(lat1, lon1, alt1_ft, lat2, lon2, alt2_ft, terrain_ft, d)
    else:
        blocked, clearance = False, None
    return {"distance_nm": round(d, 2), "horizon_nm": round(horizon, 1), "within_horizon": within,
            "terrain_checked": terrain_ft is not None, "terrain_blocked": blocked,
            "clearance_ft": None if clearance is None else round(clearance),
            "reachable": bool(within and not blocked)}


def path(lat, lon, alt_ft, site: RadioSite, *, terrain_ft=None, radio_horizon=True) -> dict:
    """Can a station at (lat, lon, alt_ft MSL) reach `site`'s antenna?"""
    return {"site": site.id, "role": site.role,
            **_link(lat, lon, alt_ft, site.lat, site.lon, site.antenna_msl_ft,
                    terrain_ft=terrain_ft, radio_horizon=radio_horizon)}


def site_link(a: RadioSite, b: RadioSite, *, terrain_ft=None, radio_horizon=True) -> dict:
    """The fixed antenna-to-antenna link between two sites (repeater to base)."""
    return {"from": a.id, "to": b.id,
            **_link(a.lat, a.lon, a.antenna_msl_ft, b.lat, b.lon, b.antenna_msl_ft,
                    terrain_ft=terrain_ft, radio_horizon=radio_horizon)}


def route(lat, lon, alt_ft, sites, *, terrain_ft=None, radio_horizon=True) -> dict:
    """How a transmission from (lat, lon, alt_ft) gets to Mission Base.

    direct    - the station reaches the base antenna;
    repeater  - it reaches a repeater whose fixed link reaches the base;
    none      - neither. `heard` is the phrase for the radio log.
    """
    base = next(s for s in sites if s.role == "base_antenna")
    paths = {s.id: path(lat, lon, alt_ft, s, terrain_ft=terrain_ft, radio_horizon=radio_horizon)
             for s in sites}
    if paths[base.id]["reachable"]:
        return {"path": "direct", "via": None, "heard": "heard direct at %s" % (base.name or base.id),
                "paths": paths}
    for site in sites:
        if site.role != "repeater" or not paths[site.id]["reachable"]:
            continue
        link = site_link(site, base, terrain_ft=terrain_ft, radio_horizon=radio_horizon)
        if link["reachable"]:
            return {"path": "repeater", "via": site.id,
                    "heard": "heard via %s repeater" % (site.name or site.id), "paths": paths}
    return {"path": "none", "via": None, "heard": "out of range of base and repeater", "paths": paths}
