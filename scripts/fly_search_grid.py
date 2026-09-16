#!/usr/bin/env python3
"""Fly a parallel-track search grid over a point, using X-Plane's own autopilot.

THIS TOOL WRITES TO THE SIMULATOR. It steers by moving the autopilot's heading
bug and nothing else: it does not touch the control surfaces, the throttle, the
maneuver gate or `services.ai_pilot.maneuver_server`, so it cannot conflict with
AI-1/AI-2. The aeroplane is flown by the aeroplane's autopilot; this only tells
it where to point, the way a crew would turn the bug.

The pattern is the parallel track (creeping line) a CAP crew flies over a
datum: legs of a fixed length on a fixed axis, each offset from the last by the
track spacing, alternating direction so the aeroplane flies a boustrophedon and
never deadheads. Leg count is forced ODD so the pattern is symmetric about the
datum - an even count puts the datum between two legs instead of on the middle
one.

Track spacing is a search parameter, not a nicety: it is what decides whether
the pattern covers the area or samples it. This tool will not guess it for you
beyond a default, and prints the resulting coverage so the number is visible.

Usage:
    python3 scripts/fly_search_grid.py --lat 33.17 --lon -117.0792 --dry-run
    python3 scripts/fly_search_grid.py --lat 33.17 --lon -117.0792 --legs 5 --fly
    python3 scripts/fly_search_grid.py --beacon --fly     # read the live beacon
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, relative: str):
    """Load by path; services/ai_pilot holds a `tests` dir that would shadow the
    repo-root package if it went on sys.path. See scripts/set_air_start.py."""
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_sas = _load("capvsar_set_air_start", "scripts/set_air_start.py")
great_circle_nm = _sas.great_circle_nm
initial_bearing = _sas.initial_bearing
project = _sas.project

# Not 49005, and not set_air_start's port either - two tools subscribing on one
# port read each other's values under their own names.
DEFAULT_RECEIVE_PORT = 49178

HEADING_BUG_DREF = "sim/cockpit2/autopilot/heading_dial_deg_mag_pilot"
AP_MODE_DREF = "sim/cockpit/autopilot/autopilot_mode"
POS_DREFS = ("sim/flightmodel/position/latitude",
             "sim/flightmodel/position/longitude")
BEACON_DREFS = ("cap/scenario/beacon_lat", "cap/scenario/beacon_lon")
DF_DREFS = ("cap/df/valid", "cap/df/signal", "cap/df/bearing_true",
            "cap/df/distance_nm", "cap/scenario/active")

# Magnetic variation at Ramona/Palomar, 2026. The heading bug is MAGNETIC and
# every bearing computed here is TRUE; converting is not optional.
DEFAULT_VARIATION_E = 11.5

CAPTURE_NM = 0.35


@dataclass(frozen=True)
class Waypoint:
    lat: float
    lon: float
    leg: int
    label: str


def parallel_track(lat: float, lon: float, track_deg: float,
                   spacing_nm: float, leg_nm: float, legs: int) -> List[Waypoint]:
    """Corner points of a parallel-track pattern centred on (lat, lon).

    `track_deg` is the TRUE heading of the legs. Legs alternate direction; the
    offset axis is 90 degrees right of the track.
    """
    if legs < 1:
        raise ValueError("need at least one leg")
    if legs % 2 == 0:
        raise ValueError("leg count must be odd so the datum sits on a leg, not between two")
    if spacing_nm <= 0 or leg_nm <= 0:
        raise ValueError("spacing and leg length must be positive")

    offset_axis = (track_deg + 90.0) % 360.0
    first = -(legs // 2) * spacing_nm
    points: List[Waypoint] = []

    for i in range(legs):
        # Centre of this leg: step sideways from the datum.
        across = first + i * spacing_nm
        if across >= 0:
            mid_lat, mid_lon = project(lat, lon, offset_axis, across)
        else:
            mid_lat, mid_lon = project(lat, lon, (offset_axis + 180.0) % 360.0, -across)

        outbound = (i % 2 == 0)
        head = track_deg if outbound else (track_deg + 180.0) % 360.0
        start = project(mid_lat, mid_lon, (head + 180.0) % 360.0, leg_nm / 2.0)
        end = project(mid_lat, mid_lon, head, leg_nm / 2.0)
        points.append(Waypoint(start[0], start[1], i + 1, "leg %d start" % (i + 1)))
        points.append(Waypoint(end[0], end[1], i + 1, "leg %d end" % (i + 1)))
    return points


def coverage(spacing_nm: float, leg_nm: float, legs: int) -> Tuple[float, float]:
    """(width_nm, area_sq_nm) the pattern sweeps."""
    width = (legs - 1) * spacing_nm
    return width, width * leg_nm


def describe(points: List[Waypoint], lat: float, lon: float, track_deg: float,
             spacing_nm: float, leg_nm: float, legs: int, variation_e: float) -> str:
    width, area = coverage(spacing_nm, leg_nm, legs)
    total = sum(great_circle_nm(points[i].lat, points[i].lon,
                                points[i + 1].lat, points[i + 1].lon)
                for i in range(len(points) - 1))
    out = [
        "parallel-track grid on %.4f, %.4f" % (lat, lon),
        "  track      %.0f true (%.0f magnetic, var %.1fE)"
        % (track_deg, (track_deg - variation_e) % 360.0, variation_e),
        "  %d legs x %.1f nm, %.2f nm spacing" % (legs, leg_nm, spacing_nm),
        "  sweeps     %.1f nm wide, %.1f square nm" % (width, area),
        "  track miles %.1f nm over %d waypoints" % (total, len(points)),
        "",
    ]
    for w in points:
        d = great_circle_nm(w.lat, w.lon, lat, lon)
        out.append("  %-14s %9.5f, %10.5f   %5.2f nm from datum"
                   % (w.label, w.lat, w.lon, d))
    return "\n".join(out)


def _client(host, port, receive_port):
    XPlaneUDPClient = _load("capvsar_xplane_udp",
                           "services/ai_pilot/xplane_udp.py").XPlaneUDPClient
    return XPlaneUDPClient(host=host, port=port, receive_port=receive_port)


def fly(points: List[Waypoint], host: str, port: int, receive_port: int,
        variation_e: float, timeout_s: float, capture_nm: float = CAPTURE_NM,
        tick_s: float = 2.0, on_sample=None) -> bool:
    """Steer the heading bug from waypoint to waypoint. True if all were made."""
    with _client(host, port, receive_port) as c:
        for d in POS_DREFS + DF_DREFS:
            c.subscribe_dref(d, 5)
        time.sleep(2.0)

        deadline = time.time() + timeout_s
        for idx, wp in enumerate(points):
            while True:
                if time.time() > deadline:
                    return False
                g = c.get_all_cached()
                lat = g.get(POS_DREFS[0])
                lon = g.get(POS_DREFS[1])
                if not lat or not lon:
                    time.sleep(tick_s)
                    continue
                dist = great_circle_nm(lat, lon, wp.lat, wp.lon)
                if dist <= capture_nm:
                    break
                brg_true = initial_bearing(lat, lon, wp.lat, wp.lon)
                # The bug is magnetic; every bearing here is true.
                c.send_dref(HEADING_BUG_DREF, (brg_true - variation_e) % 360.0)
                if on_sample:
                    on_sample(idx, wp, lat, lon, dist, brg_true, g)
                time.sleep(tick_s)
        return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fly a parallel-track search grid.")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--beacon", action="store_true",
                    help="read the datum from cap/scenario/beacon_lat|lon")
    ap.add_argument("--track", type=float, default=90.0, help="leg heading true (default 090)")
    ap.add_argument("--spacing-nm", type=float, default=1.0)
    ap.add_argument("--leg-nm", type=float, default=6.0)
    ap.add_argument("--legs", type=int, default=5, help="odd; datum sits on the middle leg")
    ap.add_argument("--variation-e", type=float, default=DEFAULT_VARIATION_E)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=49000)
    ap.add_argument("--receive-port", type=int, default=DEFAULT_RECEIVE_PORT)
    ap.add_argument("--timeout-min", type=float, default=45.0)
    ap.add_argument("--fly", action="store_true", help="actually fly it")
    ap.add_argument("--dry-run", action="store_true", help="print the pattern only")
    args = ap.parse_args(argv)

    lat, lon = args.lat, args.lon
    if args.beacon:
        with _client(args.host, args.port, args.receive_port) as c:
            for d in BEACON_DREFS:
                c.subscribe_dref(d, 5)
            time.sleep(2.5)
            g = c.get_all_cached()
            lat, lon = g.get(BEACON_DREFS[0]), g.get(BEACON_DREFS[1])
        if not lat or not lon:
            print("error: the simulator reports no beacon position", file=sys.stderr)
            return 2
    if lat is None or lon is None:
        print("error: give --lat/--lon or --beacon", file=sys.stderr)
        return 2

    try:
        points = parallel_track(lat, lon, args.track, args.spacing_nm,
                                args.leg_nm, args.legs)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    print(describe(points, lat, lon, args.track, args.spacing_nm,
                   args.leg_nm, args.legs, args.variation_e))
    if not args.fly or args.dry_run:
        print("\ndry run: nothing was written to the simulator")
        return 0

    print("\nflying. The autopilot must be engaged and holding altitude.\n")
    print("%-14s %8s %8s   %s" % ("waypoint", "dist nm", "brg", "DF"))

    def sample(idx, wp, lat_, lon_, dist, brg, g):
        df = "-"
        if g.get("cap/scenario/active"):
            df = ("valid=%.0f sig=%.3f brg=%.0f d=%.1f"
                  % (g.get("cap/df/valid", 0), g.get("cap/df/signal", 0.0),
                     g.get("cap/df/bearing_true", 0.0), g.get("cap/df/distance_nm", 0.0)))
        print("%-14s %8.2f %8.0f   %s" % (wp.label, dist, brg, df))

    ok = fly(points, args.host, args.port, args.receive_port, args.variation_e,
             args.timeout_min * 60.0, on_sample=sample)
    print("\npattern complete" if ok else "\nTIMED OUT before the last waypoint",
          file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
