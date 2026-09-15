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


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _unit(v):
    length = math.sqrt(sum(x * x for x in v))
    return tuple(x / length for x in v) if length > 1e-15 else None


def bearing_intersection(first: dict, second: dict,
                         max_range_nm: float = 40.0):
    """Intersection of two forward great-circle bearing rays.

    Each mapping supplies ``lat``, ``lon`` and ``bearing_true``.  ``None`` is
    returned for parallel/coincident paths, an intersection behind either
    observer, or a cut farther than ``max_range_nm`` from either observer.
    The range cap matches the Mission Base rays and prevents their antipodal
    great-circle crossing from becoming a plausible-looking search cut.
    """
    def path_plane(row):
        lat = math.radians(float(row["lat"]))
        lon = math.radians(float(row["lon"]))
        brg = math.radians(float(row["bearing_true"]) % 360.0)
        point = (math.cos(lat) * math.cos(lon),
                 math.cos(lat) * math.sin(lon), math.sin(lat))
        north = (-math.sin(lat) * math.cos(lon),
                 -math.sin(lat) * math.sin(lon), math.cos(lat))
        east = (-math.sin(lon), math.cos(lon), 0.0)
        tangent = tuple(north[i] * math.cos(brg) + east[i] * math.sin(brg)
                        for i in range(3))
        return point, tangent, _cross(point, tangent)

    p1, d1, n1 = path_plane(first)
    p2, d2, n2 = path_plane(second)
    crossing = _unit(_cross(n1, n2))
    if crossing is None:
        return None

    candidates = []
    for q in (crossing, tuple(-x for x in crossing)):
        # A ray is the forward half of its great circle.  At its origin the
        # candidate's tangent projection must point along, not against, the
        # reported bearing.
        forward1 = sum(d1[i] * q[i] for i in range(3))
        forward2 = sum(d2[i] * q[i] for i in range(3))
        if forward1 <= 1e-12 or forward2 <= 1e-12:
            continue
        lat = math.degrees(math.asin(max(-1.0, min(1.0, q[2]))))
        lon = math.degrees(math.atan2(q[1], q[0]))
        d_first = distance_nm(first["lat"], first["lon"], lat, lon)
        d_second = distance_nm(second["lat"], second["lon"], lat, lon)
        if d_first <= max_range_nm and d_second <= max_range_nm:
            candidates.append((d_first + d_second, (lat, lon)))
    return min(candidates, default=(None, None), key=lambda x: x[0])[1]


def bearing_cut_polygon(bearings: list[dict], max_range_nm: float = 40.0):
    """Return the sorted, de-duplicated pairwise cuts for a confidence area."""
    points = []
    for i, first in enumerate(bearings):
        for second in bearings[i + 1:]:
            point = bearing_intersection(first, second, max_range_nm)
            if point is None:
                continue
            if not any(distance_nm(point[0], point[1], old[0], old[1]) < 0.01
                       for old in points):
                points.append(point)
    if len(points) < 3:
        return points

    centre_lat = sum(p[0] for p in points) / len(points)
    lon_x = sum(math.cos(math.radians(p[1])) for p in points)
    lon_y = sum(math.sin(math.radians(p[1])) for p in points)
    centre_lon = math.degrees(math.atan2(lon_y, lon_x))

    def around(point):
        dlon = (point[1] - centre_lon + 540.0) % 360.0 - 180.0
        return math.atan2(dlon * math.cos(math.radians(centre_lat)),
                          point[0] - centre_lat)

    return sorted(points, key=around)


def track_heading(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Heading implied by two consecutive fixes, for a track with no heading.

    Kept separate from bearing_true because this is the flat-earth form the
    debrief uses over a few hundred metres between fixes - but it still has to
    scale longitude by cos(latitude), which is exactly what the F-3 bug did
    not do.
    """
    dx = (lon2 - lon1) * math.cos(math.radians(lat2))
    return (math.degrees(math.atan2(dx, lat2 - lat1)) + 360.0) % 360.0
