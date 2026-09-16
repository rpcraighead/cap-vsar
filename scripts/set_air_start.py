#!/usr/bin/env python3
"""Place CAP 487 airborne on final approach, flying, for panel and instrument testing.

THIS TOOL WRITES TO THE SIMULATOR. Like `scripts/set_test_condition.py` it is a
separate program from the read-only recorder `scripts/capture_flight_test.py`,
for the same reason: a recorder that can also move the aeroplane is a recorder
you cannot trust.

It writes position, attitude and the velocity vector. It does NOT touch the
flight controls, the autopilot, the throttle or the maneuver gate, so it does
not conflict with `services.ai_pilot.maneuver_server` or with tracker items
AI-1/AI-2. What it gives you is an aeroplane in the air at a known point with a
known velocity; holding it there afterwards is somebody else's job (X-Plane's
own autopilot is usually enough for a bench session).

WHY VELOCITY MATTERS. X-Plane's VEHS packet relocates the aircraft "without
resetting flight dynamics", which means it does not set airspeed. Relocating a
parked aeroplane to 4,000 ft leaves it at the velocity it had on the ramp -
zero - and it departs immediately. Position without velocity is not a flight
condition, so this tool always writes both.

RUNWAY GEOMETRY COMES FROM X-Plane's OWN apt.dat, not from a table in this repo,
so it cannot drift from the scenery the aeroplane is actually flying in.

PRECONDITION: start from a running-engine state. This tool does not start the
engine or advance the throttle, and a cold airframe teleported to altitude is a
glider.

Usage:
    python3 scripts/set_air_start.py --airport KRNM --runway 09 --distance-nm 9
    python3 scripts/set_air_start.py --airport KRNM --runway 09 --distance-nm 9 --glidepath
    python3 scripts/set_air_start.py --airport KRNM --runway 27 --distance-nm 5 --kias 110
    python3 scripts/set_air_start.py --airport KRNM --runway 09 --distance-nm 9 --dry-run
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, relative: str):
    """Load a module by path.

    Deliberately NOT sys.path.insert: services/ai_pilot contains its own
    `tests` directory, and putting that on the path shadows the repo-root
    `tests` package for everything imported afterwards. tests/test_geodesy.py
    and tests/test_propagation.py load their subjects the same way.
    """
    path = REPO / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s from %s" % (name, path))
    module = importlib.util.module_from_spec(spec)
    # Register before executing: @dataclass resolves its own module out of
    # sys.modules, and a path-load that skips this step fails on any module
    # that uses one.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

M_PER_FT = 0.3048
FT_PER_NM = 6076.11548556
EARTH_R_NM = 3440.065          # the console's radius; tests/test_geodesy.py holds the line
ISA_RHO0 = 1.225               # kg/m^3
ISA_T0 = 288.15                # K
ISA_LAPSE = 0.0065             # K/m
ISA_P0 = 101325.0              # Pa
ISA_G = 9.80665
ISA_R = 287.053

# A 182T at approach and cruise speeds sits a couple of degrees nose-up on the
# flight path. Used only to pick a plausible starting attitude; the sim settles
# to its own trim within a second or two either way.
NOMINAL_AOA_DEG = 2.0


# ---------------------------------------------------------------------------
# apt.dat
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RunwayEnd:
    icao: str
    designator: str
    lat: float
    lon: float
    airport_elev_ft: float
    opposite_designator: str
    opposite_lat: float
    opposite_lon: float

    @property
    def true_heading(self) -> float:
        """Runway centreline heading, measured from the scenery, not the name."""
        return initial_bearing(self.lat, self.lon, self.opposite_lat, self.opposite_lon)

    @property
    def length_ft(self) -> float:
        return great_circle_nm(self.lat, self.lon,
                               self.opposite_lat, self.opposite_lon) * FT_PER_NM


def default_apt_dat() -> Path:
    root = os.environ.get("CAPVSAR_XPLANE_ROOT") or str(Path.home() / "X-Plane 12")
    return Path(root) / "Global Scenery" / "Global Airports" / "Earth nav data" / "apt.dat"


def _normalise(designator: str) -> str:
    """'9', '09' and '9 ' are the same runway; '09L' is not '09R'."""
    d = designator.strip().upper()
    if d[:2].isdigit():
        return str(int(d[:2])).zfill(2) + d[2:]
    if d[:1].isdigit():
        return d.zfill(3) if len(d) > 1 else d.zfill(2)
    return d


def parse_runway(lines: Iterable[str], icao: str, runway: str) -> RunwayEnd:
    """Pull one runway end out of apt.dat.

    Row 1   is the airport header:  1 <elev_ft> ... <ICAO> <name>
    Row 100 is a land runway, with nine fields per end starting at token 8:
            <designator> <lat> <lon> <displaced> <blastpad> <markings> ...
    """
    icao = icao.strip().upper()
    want = _normalise(runway)
    in_airport = False
    elev_ft: Optional[float] = None

    for raw in lines:
        tok = raw.split()
        if not tok:
            continue
        if tok[0] == "1":
            # A new airport header ends the one we were reading.
            if in_airport:
                break
            if len(tok) >= 5 and tok[4].upper() == icao:
                in_airport = True
                elev_ft = float(tok[1])
            continue
        if not in_airport or tok[0] != "100" or len(tok) < 26:
            continue
        ends = ((tok[8], tok[9], tok[10]), (tok[17], tok[18], tok[19]))
        for idx, (desig, lat, lon) in enumerate(ends):
            if _normalise(desig) != want:
                continue
            other = ends[1 - idx]
            assert elev_ft is not None
            return RunwayEnd(
                icao=icao,
                designator=_normalise(desig),
                lat=float(lat),
                lon=float(lon),
                airport_elev_ft=elev_ft,
                opposite_designator=_normalise(other[0]),
                opposite_lat=float(other[1]),
                opposite_lon=float(other[2]),
            )

    if in_airport:
        raise LookupError("%s has no runway %s in apt.dat" % (icao, runway))
    raise LookupError("airport %s not found in apt.dat" % icao)


def load_runway(apt_dat: Path, icao: str, runway: str) -> RunwayEnd:
    if not apt_dat.exists():
        raise FileNotFoundError(
            "apt.dat not found: %s\nSet CAPVSAR_XPLANE_ROOT to the X-Plane 12 folder." % apt_dat)
    with open(apt_dat, encoding="utf-8", errors="replace") as fh:
        return parse_runway(fh, icao, runway)


# ---------------------------------------------------------------------------
# Geometry. Shares tests/test_geodesy.py's earth radius deliberately.
# ---------------------------------------------------------------------------

def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def great_circle_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_NM * math.asin(math.sqrt(h))


def project(lat: float, lon: float, bearing_deg: float, dist_nm: float) -> Tuple[float, float]:
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    br = math.radians(bearing_deg)
    dr = dist_nm / EARTH_R_NM
    p2 = math.asin(math.sin(p1) * math.cos(dr) + math.cos(p1) * math.sin(dr) * math.cos(br))
    l2 = l1 + math.atan2(math.sin(br) * math.sin(dr) * math.cos(p1),
                         math.cos(dr) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540.0) % 360.0 - 180.0


def isa_density(alt_ft: float) -> float:
    """Standard-atmosphere density, troposphere only."""
    h = alt_ft * M_PER_FT
    t = ISA_T0 - ISA_LAPSE * h
    p = ISA_P0 * (t / ISA_T0) ** (ISA_G / (ISA_LAPSE * ISA_R))
    return p / (ISA_R * t)


def tas_from_ias(kias: float, alt_ft: float) -> float:
    """True airspeed in knots. Indicated is a pressure reading, not a speed:
    at 4,000 ft the aeroplane is already moving several knots faster than the
    ASI admits, and writing IAS into a velocity dataref would start the run
    slow."""
    return kias * math.sqrt(ISA_RHO0 / isa_density(alt_ft))


# ---------------------------------------------------------------------------
# The flight condition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AirStart:
    icao: str
    runway: str
    distance_nm: float
    lat: float
    lon: float
    altitude_ft: float
    elevation_m: float
    heading_true: float
    pitch_deg: float
    roll_deg: float
    kias: float
    ktas: float
    glidepath_deg: float
    vertical_fpm: float
    local_vx: float
    local_vy: float
    local_vz: float
    airport_elev_ft: float
    runway_true: float
    runway_length_ft: float

    @property
    def agl_ft(self) -> float:
        """Height above FIELD elevation. Not above the terrain under the
        aircraft, which on an approach over rising ground is less."""
        return self.altitude_ft - self.airport_elev_ft


def build_air_start(end: RunwayEnd, distance_nm: float, kias: float,
                    glidepath_deg: float = 0.0,
                    altitude_ft: Optional[float] = None) -> AirStart:
    """Compute the flight condition. Pure: no sockets, no simulator."""
    if distance_nm <= 0:
        raise ValueError("distance must be positive")
    if kias <= 0:
        raise ValueError("airspeed must be positive")
    if not -10.0 <= glidepath_deg <= 15.0:
        raise ValueError("glidepath angle out of range")

    rwy_true = end.true_heading

    if altitude_ft is None:
        on_path = end.airport_elev_ft + distance_nm * FT_PER_NM * math.tan(
            math.radians(glidepath_deg if glidepath_deg else 3.0))
        # Level starts get a round altitude; a glidepath start has to be on the
        # path or the first thing it does is correct back to it.
        altitude_ft = on_path if glidepath_deg else round(on_path / 100.0) * 100.0

    # Fly the reciprocal back from the threshold to find the start point.
    lat, lon = project(end.lat, end.lon, (rwy_true + 180.0) % 360.0, distance_nm)

    ktas = tas_from_ias(kias, altitude_ft)
    tas_ms = ktas * 1852.0 / 3600.0
    gamma = math.radians(glidepath_deg)

    horiz = tas_ms * math.cos(gamma)
    # The +0.0 turns IEEE negative zero back into zero, so a level start prints
    # and compares as 0.0 rather than -0.0.
    vert = -tas_ms * math.sin(gamma) + 0.0    # descending on the path

    psi = math.radians(rwy_true)
    # X-Plane local OpenGL frame: +X east, +Y up, +Z south.
    local_vx = horiz * math.sin(psi)
    local_vz = -horiz * math.cos(psi)
    local_vy = vert

    return AirStart(
        icao=end.icao,
        runway=end.designator,
        distance_nm=distance_nm,
        lat=lat,
        lon=lon,
        altitude_ft=altitude_ft,
        elevation_m=altitude_ft * M_PER_FT,
        heading_true=rwy_true,
        pitch_deg=NOMINAL_AOA_DEG - glidepath_deg,
        roll_deg=0.0,
        kias=kias,
        ktas=ktas,
        glidepath_deg=glidepath_deg,
        vertical_fpm=vert / M_PER_FT * 60.0,
        local_vx=local_vx,
        local_vy=local_vy,
        local_vz=local_vz,
        airport_elev_ft=end.airport_elev_ft,
        runway_true=rwy_true,
        runway_length_ft=end.length_ft,
    )


# ---------------------------------------------------------------------------
# The maneuver gate's view of the condition. Read-only: this imports the limits
# and reports, it never acquires a lease or writes a control.
# ---------------------------------------------------------------------------

def gate_report(start: AirStart) -> Tuple[bool, list]:
    """Would services.ai_pilot.maneuvers.ManeuverGate accept this condition?

    Answering up front is the point: the gate is an AIRBORNE EXERCISE envelope,
    not an approach envelope, and finding that out halfway down final looks like
    a defect when it is the floor doing its job.

    The verdict is about the START POINT ONLY. A descent that begins inside the
    envelope and leaves it later is accepted and warned about - those are two
    different statements and folding them together would refuse a legal start.
    """
    lim = _load("capvsar_maneuvers", "services/ai_pilot/maneuvers.py").Limits()
    refusals = []
    if not lim.min_kias <= start.kias <= lim.max_kias:
        refusals.append("airspeed %.0f KIAS outside %.0f-%.0f"
                        % (start.kias, lim.min_kias, lim.max_kias))
    if not lim.min_altitude_ft <= start.altitude_ft <= lim.max_altitude_ft:
        refusals.append("altitude %.0f ft outside %.0f-%.0f indicated"
                        % (start.altitude_ft, lim.min_altitude_ft, lim.max_altitude_ft))
    if start.agl_ft < lim.min_agl_ft:
        refusals.append("%.0f ft above field is below the %.0f ft floor"
                        % (start.agl_ft, lim.min_agl_ft))
    if abs(start.roll_deg) > lim.max_bank_deg:
        refusals.append("bank %.0f exceeds %.0f" % (start.roll_deg, lim.max_bank_deg))

    warnings = []
    if start.glidepath_deg > 0:
        drop = FT_PER_NM * math.tan(math.radians(start.glidepath_deg))
        to_go = (start.altitude_ft - lim.min_altitude_ft) / drop
        if 0 < to_go < start.distance_nm:
            warnings.append("on this path the gate stops permitting at %.1f nm to go "
                            "(%.0f ft indicated floor)" % (to_go, lim.min_altitude_ft))
    if start.kias > lim.min_kias and start.glidepath_deg > 0:
        warnings.append("slowing to approach speed drops below the %.0f KIAS floor"
                        % lim.min_kias)
    return (not refusals), refusals + warnings


# ---------------------------------------------------------------------------
# Simulator I/O
# ---------------------------------------------------------------------------

VELOCITY_DREFS = ("sim/flightmodel/position/local_vx",
                  "sim/flightmodel/position/local_vy",
                  "sim/flightmodel/position/local_vz")


READBACK_DREFS = ("sim/flightmodel/position/latitude",
                  "sim/flightmodel/position/longitude",
                  "sim/flightmodel/position/elevation")

PAUSED_DREF = "sim/time/paused"

# NOT 49005. X-Plane keeps streaming RREF subscriptions to a receive port after
# the client that asked for them exits, and every new client restarts its
# dataref ids at zero - so a tool on the shared default reads the previous
# tool's values under its own names. Observed live: elevation returning the
# latitude. Anything that subscribes needs a port of its own.
DEFAULT_RECEIVE_PORT = 49177

# Beyond this, refuse. VEHS re-centres the horizontal origin but X-Plane keeps
# deriving the vertical from the old scenery origin, and the failure is worse
# than an error: the placement reads back EXACTLY right while the simulator is
# paused, and the aeroplane is at 4.7 million feet inverted a second after
# physics resumes. Neither retrying nor pausing fixes it - both were tried live.
# A flight must be LOADED near the destination (--load_llah at startup, or the
# Flight Configuration screen); after that, local repositioning is exact.
MAX_JUMP_NM = 100.0

ALTITUDE_TOLERANCE_FT = 50.0
POSITION_TOLERANCE_NM = 0.25


class LongJumpRefused(RuntimeError):
    """The aircraft is too far from the target for a reposition to survive."""


@dataclass(frozen=True)
class Achieved:
    lat: float
    lon: float
    altitude_ft: float
    attempts: int
    ok: bool

    def error_ft(self, wanted: AirStart) -> float:
        return self.altitude_ft - wanted.altitude_ft

    def error_nm(self, wanted: AirStart) -> float:
        return great_circle_nm(self.lat, self.lon, wanted.lat, wanted.lon)


def _read_back(client, timeout_s: float = 4.0) -> Optional[Tuple[float, float, float]]:
    for dref in READBACK_DREFS:
        client.subscribe_dref(dref, 5)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(0.4)
        cache = client.get_all_cached()
        if all(d in cache for d in READBACK_DREFS):
            lat, lon, ele_m = (cache[d] for d in READBACK_DREFS)
            if lat or lon:
                return lat, lon, ele_m / M_PER_FT
    return None


def _write_once(client, start: AirStart, settle_s: float) -> None:
    client.set_position(
        lat_deg=start.lat,
        lon_deg=start.lon,
        ele_m=start.elevation_m,
        heading_true=start.heading_true,
        pitch_deg=start.pitch_deg,
        roll_deg=start.roll_deg,
    )
    # VEHS relocates without resetting dynamics, so the velocity has to be
    # written explicitly, and after the move: writing it first would have it
    # overwritten by whatever the aircraft carried into the reposition.
    time.sleep(settle_s)
    for dref, value in zip(VELOCITY_DREFS,
                           (start.local_vx, start.local_vy, start.local_vz)):
        client.send_dref(dref, value)


def apply(start: AirStart, host: str, port: int,
          receive_port: int = DEFAULT_RECEIVE_PORT,
          settle_s: float = 1.0, attempts: int = 3,
          read_timeout_s: float = 4.0, leave_paused: bool = False,
          allow_long_jump: bool = False, client_factory=None) -> Achieved:
    """Place the aircraft, then CHECK, and place it again if the sim disagreed.

    A single write is not enough and this is not defensiveness. VEHS re-centres
    the horizontal origin across a long jump but leaves the vertical referenced
    to the old scenery origin: repositioning from Austria to California put the
    aeroplane at 4,699,505 ft descending through 36,000 fpm, while its latitude
    and longitude were correct to five decimals. The identical command applied a
    second time - with the origin now local - was exact to the digit.

    So this writes, reads the achieved position back, and writes again while the
    simulator disagrees. Reporting what was actually achieved rather than what
    was requested is the same discipline scripts/set_test_condition.py follows,
    for the same reason.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if client_factory is None:
        XPlaneUDPClient = _load("capvsar_xplane_udp",
                               "services/ai_pilot/xplane_udp.py").XPlaneUDPClient

        def client_factory():
            return XPlaneUDPClient(host=host, port=port, receive_port=receive_port)

    with client_factory() as client:
        # Pause before moving. A placement made with physics running can verify
        # correct and then diverge: after two long jumps in a row the aeroplane
        # read back at exactly 4300 ft, and seconds later was at 4,604,172 ft
        # inverted and descending through 120,778 fpm, because X-Plane kept
        # re-deriving the vertical from the stale origin while the frames ran.
        # Frozen, the placement settles before physics can act on a bad one.
        client.subscribe_dref(PAUSED_DREF, 5)
        for dref in READBACK_DREFS:
            client.subscribe_dref(dref, 5)
        time.sleep(0.6)
        cache = client.get_all_cached()
        was_paused = bool(cache.get(PAUSED_DREF, 0.0))

        # How far is the aeroplane being asked to move? Checked BEFORE writing,
        # because a refusal after the write is a refusal after the damage.
        here_lat = cache.get(READBACK_DREFS[0])
        here_lon = cache.get(READBACK_DREFS[1])
        if here_lat and here_lon and not allow_long_jump:
            jump_nm = great_circle_nm(here_lat, here_lon, start.lat, start.lon)
            if jump_nm > MAX_JUMP_NM:
                raise LongJumpRefused(
                    "refusing to move the aircraft %.0f nm (limit %.0f).\n"
                    "X-Plane keeps the vertical referenced to the scenery origin it "
                    "loaded with, so a jump this far\nreads back correct while paused "
                    "and puts the aeroplane at millions of feet the moment physics "
                    "resumes.\nLoad a flight near %s first, then reposition locally - "
                    "that is exact. --allow-long-jump overrides."
                    % (jump_nm, MAX_JUMP_NM, start.icao))
        client.set_paused(True)
        time.sleep(0.3)

        seen = None
        for attempt in range(1, attempts + 1):
            _write_once(client, start, settle_s)
            seen = _read_back(client, read_timeout_s)
            if seen is None:
                continue
            lat, lon, alt_ft = seen
            close = (abs(alt_ft - start.altitude_ft) <= ALTITUDE_TOLERANCE_FT
                     and great_circle_nm(lat, lon, start.lat, start.lon)
                     <= POSITION_TOLERANCE_NM)
            if close:
                if not (was_paused or leave_paused):
                    client.set_paused(False)
                return Achieved(lat, lon, alt_ft, attempt, True)
        # A placement that never converged is left FROZEN regardless of how the
        # simulator was found: unpausing onto a bad vertical is how the
        # aeroplane ends up inverted in space.
        if seen is None:
            # No telemetry came back at all. The write may still have landed;
            # say so rather than claiming either success or failure.
            return Achieved(float("nan"), float("nan"), float("nan"), attempts, False)
        return Achieved(seen[0], seen[1], seen[2], attempts, False)


def describe(start: AirStart) -> str:
    ok, notes = gate_report(start)
    path = ("level" if not start.glidepath_deg
            else "%.1f deg glidepath, %.0f fpm" % (start.glidepath_deg, start.vertical_fpm))
    out = [
        "%s runway %s - %.1f nm final" % (start.icao, start.runway, start.distance_nm),
        "  runway          %.1f deg true, %.0f ft, field %.0f ft"
        % (start.runway_true, start.runway_length_ft, start.airport_elev_ft),
        "  position        %.6f, %.6f" % (start.lat, start.lon),
        "  altitude        %.0f ft MSL (%.0f above field), %s"
        % (start.altitude_ft, start.agl_ft, path),
        "  heading         %.1f deg true" % start.heading_true,
        "  speed           %.0f KIAS = %.0f KTAS at this altitude" % (start.kias, start.ktas),
        "  velocity (m/s)  vx %+.1f east, vy %+.1f up, vz %+.1f south"
        % (start.local_vx, start.local_vy, start.local_vz),
        "  attitude        pitch %+.1f, roll %+.1f" % (start.pitch_deg, start.roll_deg),
        "  maneuver gate   %s" % ("would accept this condition" if ok else "WOULD REFUSE"),
    ]
    out += ["                  - %s" % n for n in notes]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Place the aeroplane airborne on final, flying, for panel testing.")
    ap.add_argument("--airport", required=True, help="ICAO, e.g. KRNM")
    ap.add_argument("--runway", required=True, help="runway designator, e.g. 09 or 27")
    ap.add_argument("--distance-nm", type=float, default=9.0, help="final length (default 9)")
    ap.add_argument("--kias", type=float, default=100.0, help="indicated airspeed (default 100)")
    ap.add_argument("--glidepath", nargs="?", type=float, const=3.0, default=0.0,
                    metavar="DEG",
                    help="descend on a glidepath instead of level (default 3.0 deg)")
    ap.add_argument("--altitude-ft", type=float, default=None,
                    help="override the computed altitude")
    ap.add_argument("--apt-dat", type=Path, default=None, help="override apt.dat location")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=49000)
    ap.add_argument("--receive-port", type=int, default=DEFAULT_RECEIVE_PORT,
                    help="UDP port to receive telemetry on; must not be shared "
                         "with another running tool (default %d)" % DEFAULT_RECEIVE_PORT)
    ap.add_argument("--attempts", type=int, default=3,
                    help="write-and-verify passes before giving up (default 3)")
    ap.add_argument("--allow-long-jump", action="store_true",
                    help="permit a reposition beyond %.0f nm (known to leave the "
                         "aircraft at millions of feet)" % MAX_JUMP_NM)
    ap.add_argument("--leave-paused", action="store_true",
                    help="stay paused after placing, instead of restoring the "
                         "simulator's previous run state")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print, write nothing to the simulator")
    args = ap.parse_args(argv)

    try:
        end = load_runway(args.apt_dat or default_apt_dat(), args.airport, args.runway)
        start = build_air_start(end, args.distance_nm, args.kias,
                                args.glidepath, args.altitude_ft)
    except (LookupError, FileNotFoundError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    print(describe(start))
    if args.dry_run:
        print("\ndry run: nothing was written to the simulator")
        return 0

    try:
        got = apply(start, args.host, args.port, receive_port=args.receive_port,
                    attempts=args.attempts, leave_paused=args.leave_paused,
                    allow_long_jump=args.allow_long_jump)
    except LongJumpRefused as exc:
        print("\nerror: %s" % exc, file=sys.stderr)
        return 4

    if got.ok:
        print("\nachieved on attempt %d of %d: %.5f, %.5f at %.0f ft MSL"
              % (got.attempts, args.attempts, got.lat, got.lon, got.altitude_ft))
        print("  %+.0f ft and %.2f nm from the requested point"
              % (got.error_ft(start), got.error_nm(start)))
        print("\nThe engine must already be running - this tool does not advance the"
              "\nthrottle, and a cold airframe at altitude is a glider.")
        return 0

    if got.altitude_ft != got.altitude_ft:      # NaN: nothing came back
        print("\nwrote to %s:%d but the simulator sent no telemetry back, so the"
              "\nresult is UNVERIFIED. Is a flight loaded? X-Plane answers no UDP"
              "\nwhile it sits on the Quick Flight menu." % (args.host, args.port),
              file=sys.stderr)
        return 3

    print("\nFAILED after %d attempts. The simulator reports %.5f, %.5f at %.0f ft"
          "\nMSL - %+.0f ft and %.2f nm from what was asked for."
          % (got.attempts, got.lat, got.lon, got.altitude_ft,
             got.error_ft(start), got.error_nm(start)), file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
