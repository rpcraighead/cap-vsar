"""
Geodesy for the exercise console. One implementation, not several (C15-2).

Bearing and distance were written out five times across this project with the
same R_NM constant and slightly different arithmetic each time, which is how
`debrief.js` came to compute a track heading without scaling longitude by
cos(latitude) - about 10 degrees of error at 33 N, on the one number a debrief
is read for. That particular drift was fixed under F-3; this module exists so
the next one does not happen inside this service.

**Why this is not imported by everything.** Four of the five copies live on the
other side of a deployment boundary and cannot import Python from here:

  * `xplane/PI_capvsar_df.py` runs inside X-Plane's own interpreter, installed
    from a different directory on a different machine.
  * `services/flightplanner/app.py` is a separate container with its own image.
  * `static/debrief.js` and `static/base.js` run in a browser.

Copying is therefore the only option for those, and the guard against drift is
`tests/test_geodesy.py`, which pins every copy to the same answers on the same
fixtures and fails when one of them wanders. Within this service, though, there
is no excuse: import from here.

Formulae are the standard ones (Sinnott's haversine, the usual initial-bearing
and direct-solution forms). Distances are nautical miles and angles degrees,
because that is what every consumer here speaks.
"""
from __future__ import annotations

import math

# Mean earth radius in nautical miles. Every copy in the project uses this same
# figure; tests/test_geodesy.py is what keeps that true.
R_NM = 3440.065
M_PER_NM = 1852.0
FT_PER_M = 3.28084
FT_PER_NM = M_PER_NM * FT_PER_M


def bearing_true(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from 1 to 2, degrees true, 0..360."""
    dlon = math.radians(lon2 - lon1)
    la1, la2 = math.radians(lat1), math.radians(lat2)
    y = math.sin(dlon) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    la1, la2 = math.radians(lat1), math.radians(lat2)
    dla, dlo = la2 - la1, math.radians(lon2 - lon1)
    a = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * R_NM * math.asin(min(1.0, math.sqrt(a)))


def move(lat: float, lon: float, bearing_deg: float, distance: float):
    """Direct solution: the point `distance` NM from here on `bearing_deg`."""
    b, d = math.radians(bearing_deg), distance / R_NM
    la = math.radians(lat)
    la2 = math.asin(math.sin(la) * math.cos(d) + math.cos(la) * math.sin(d) * math.cos(b))
    lo2 = math.radians(lon) + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(la),
        math.cos(d) - math.sin(la) * math.sin(la2))
    # Normalise into -180..180 so a track across the antimeridian does not come
    # back as 190 degrees east.
    return math.degrees(la2), (math.degrees(lo2) + 540.0) % 360.0 - 180.0


def track_heading(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Heading implied by two consecutive fixes, for a track with no heading.

    Kept separate from bearing_true because this is the flat-earth form the
    debrief uses over a few hundred metres between fixes - but it still has to
    scale longitude by cos(latitude), which is exactly what the F-3 bug did
    not do.
    """
    dx = (lon2 - lon1) * math.cos(math.radians(lat2))
    return (math.degrees(math.atan2(dx, lat2 - lat1)) + 360.0) % 360.0
