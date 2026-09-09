"""
CAP V-SAR - DF propagation engine.

Phase 1 of the implementation plan. This runs inside X-Plane because two things
it must do are only possible here: probing real terrain for line-of-sight, and
reading aircraft state at frame rate.

It publishes what the direction finder would show as custom datarefs, which any
external program can read - Air Manager subscribes to these exactly as it would
to a stock dataref:

    cap/df/valid          int    1 when a usable bearing exists
    cap/df/bearing_rel    float  degrees relative to the nose - drives the needle
    cap/df/bearing_true   float  degrees true
    cap/df/signal         float  0..1 signal strength - drives the bar
    cap/df/distance_nm    float  slant range, for the instructor
    cap/df/in_cone        int    1 inside the cone of confusion
    cap/df/blocked        int    1 when terrain is masking the signal
    cap/df/airframe_shadowed int 1 when the aircraft is attenuating the signal
    cap/df/airframe_attenuation_db float current installation loss in dB
    cap/df/rx_open        int    1 when a transmission is audible right now
    cap/df/band           float  121.5 / 243 / 406
    cap/df/spread         float  bearing quality - deg of scatter before averaging
    cap/df/error_code     int    -1 none, else Becker E0..E12

    cap/df/cs_sync           int      0 none, 1 SYNC OK, 2 SELFTEST
    cap/df/cs_protocol       int      1 USER, 2 STANDARD, 3 NATIONAL; +4 = TEST
    cap/df/cs_hex15          byte[15] 15-hex beacon ident, one ASCII char per byte
    cap/df/cs_country        int
    cap/df/cs_has_position   int
    cap/df/cs_lat            float
    cap/df/cs_lon            float
    cap/df/cs_msg_age_sec    float

The faceplates talk back. These are writable and are what the DF head tells the
engine about itself; see docs/DATAREF_CONTRACT.md in the instrument repo:

    cap/df/power          int    0/1 - outputs sit at the noise floor when off
    cap/df/active_freq_hz int    what the head is tuned to; supersedes the
                                 console-selected band
    cap/df/head_type      int    0 = Becker SAR-DF 517, 1 = RHOTHETA RT-600
    cap/df/squelch        float  % 0-100, or -1 for the RT-600's Auto Squelch
    cap/df/mode           int    0 = Emergency, 1 = Training (517 only)
    cap/df/scan_enable    int    0/1 - 406 <-> 121.5/243.0 per 517 3.3.3
    cap/df/clear_average  int    panel pulses 1; we clear and self-reset
    cap/df/timehold_sec   float  how long a lost bearing is held on screen
    cap/df/offset_deg     float  antenna offset correction dialled in by the crew
    cap/df/mounting       int    0 = TOP, 1 = BOTTOM
    cap/df/rx_span_hz     int    half-width the receiver covers either side of
                                 active_freq_hz; 0 for a single-channel set, half
                                 the group width for an RT-600 CPSAR selection
    cap/df/scan_alt1_hz   int    the two continuous frequencies scan sweeps
    cap/df/scan_alt2_hz   int    between 406 bursts (517 3.3.3)

The head-type input is the one that matters most for the exercise: the Becker
517 Emergency mode hears one of the nineteen COSPAS-SARSAT channels and the
RT-600 covers all nineteen in groups, which is the whole argument for the fleet replacement. Until the
panel could say which head was fitted and what it was tuned to, that could not
be demonstrated. It can now.

Nothing here reads the panel until the panel writes something. If no faceplate
is running, the engine behaves exactly as it did before: the exercise console
picks the band and the receiver is assumed to be tuned to the beacon.

Beacon truth and effect switches arrive from the exercise console over HTTP on
a background thread, so no network call ever runs in the flight loop. The same
thread reports position back, which makes this the sim bridge as well - one
component rather than the two the plan sketched.

    cap/scenario/active       int
    cap/scenario/beacon_lat   double   (writable, for offline testing)
    cap/scenario/beacon_lon   double
    cap/scenario/beacon_elev  float    feet MSL
"""
import collections
import configparser
import hashlib
import json
import math
import os
import random
import threading
import time
import urllib.error
import urllib.request

import xp

# O-2: three aircraft used to mean three hand-edited copies of this file,
# because CONSOLE/CALLSIGN/PLUGIN_KEY were literals. They now come from
# capvsar_station.ini next to wherever this plugin is actually deployed
# (built by scripts/build_station_kit.py), so the tracked source in
# xplane/ stays identical for every station and deploy_xplane_plugin.py's
# hash check keeps meaning something. A station with no ini - or a
# pre-O-2 install that only ever had this file - gets exactly the old
# hardcoded single-station defaults, so this is not a breaking change.
_DEFAULT_CONSOLE = "http://192.0.2.151:8700"
_DEFAULT_CALLSIGN = "CAP-1"
STATION_INI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capvsar_station.ini")


def _load_station_config(path=STATION_INI):
    """Read [station] console/callsign/plugin_key from an ini beside the
    plugin. Missing file, missing section, or a missing individual key all
    fall back independently - a station can override just the callsign.

    CAPVSAR_TOKEN_PLUGIN, if set, always wins over the ini's plugin_key: the
    env var is the documented mechanism used by the exercise console's own
    tokened routes (docs/DATAREF_CONTRACT.md) and by ms01 deploys, and a
    station.ini checked out alongside a plugin should not silently defeat it.
    """
    console, callsign = _DEFAULT_CONSOLE, _DEFAULT_CALLSIGN
    plugin_key = os.environ.get("CAPVSAR_TOKEN_PLUGIN", "")
    if os.path.exists(path):
        cfg = configparser.ConfigParser()
        cfg.read(path)
        if cfg.has_section("station"):
            console = cfg.get("station", "console", fallback=console)
            callsign = cfg.get("station", "callsign", fallback=callsign)
            if not plugin_key:
                plugin_key = cfg.get("station", "plugin_key", fallback="")
    return console, callsign, plugin_key


# Shared secret for the console's plugin routes. The console withholds the
# beacon position from every browser until the instructor reveals, so this key
# is how the engine that actually needs it - this one - gets it. Without a key
# the console answers 503 and the DF stays silent rather than searching for a
# beacon at 0,0.
CONSOLE, CALLSIGN, PLUGIN_KEY = _load_station_config()
POLL_S = 3.0            # scenario refresh
REPORT_S = 2.0          # position report
LOOP_S = 0.25           # DF recompute
R_NM = 3440.065
M_PER_NM = 1852.0
FT_PER_M = 3.28084
LOS_SAMPLES = 24        # terrain probes along the path

HEAD_517, HEAD_RT600 = 0, 1
MODE_EMERGENCY, MODE_TRAINING = 0, 1
MOUNT_TOP, MOUNT_BOTTOM = 0, 1

# COSPAS-SARSAT channel grid, 3 kHz spacing, 406.022 to 406.076 inclusive. That
# is NINETEEN channels, A through S - RT-600 manual 2.2.3 lists them as seven
# selectable groups (A-C, D-F, G-H, I-K, L-N, O-Q, R-S). An earlier build
# counted eighteen by stopping at 406.073.
CS_LO_HZ, CS_HI_HZ = 406_022_000, 406_076_000
CS_SPACING_HZ = 3_000
CS_CHANNEL_COUNT = (CS_HI_HZ - CS_LO_HZ) // CS_SPACING_HZ + 1      # 19

# The Becker's technical data lists its receiving frequencies outright, and in
# Emergency mode the COSPAS/SARSAT entry is a SINGLE channel:
#
#   Emergency mode   121.500 / 156.800 / 243.000 / 406.025 MHz
#   Training mode    118.000-122.975 / 156.000-157.975 /
#                    240.000-245.975 / 400.000-409.975 MHz
#
# So in Emergency mode the head sits on one 406 channel while the RT-600 covers
# a whole group, and in Training mode the head is a freely tunable receiver
# across the entire 400-410 range. Both halves of that matter: an earlier build
# gave the Becker two emergency channels it does not have, and refused it its
# own default 406.037 training frequency.
BECKER_406_CHANNELS_HZ = (406_025_000,)
BECKER_TRAINING_UHF_HI_HZ = 409_975_000
BECKER_TRAINING_UHF_LO_HZ = 400_000_000

# How far off channel the head can be and still hear the beacon. The C/S grid is
# 3 kHz apart so half a channel is the natural figure; the continuous emergency
# frequencies are wider.
TUNE_TOL_CS_HZ = 1_500.0
TUNE_TOL_WIDE_HZ = 5_000.0

# 406 bursts. The 517 manual says ~400 ms and the RT-600 manual 440 or 520 ms;
# SOURCES.md prefers the RT-600 figure as the newer document.
BURST_PERIOD_S = 50.0
BURST_LEN_S = 0.44

# Squelch maps a percentage onto a threshold on the 0..1 signal. 0 % (and Auto)
# sits at the old hard-coded noise floor, so behaviour with no panel attached is
# unchanged. The ceiling is just above a saturated signal, so a squelch wound
# fully up really is deaf - the signal model saturates inside about 5 NM, and a
# lower ceiling would make the top of the control do nothing exactly where the
# crew is closing on the beacon. The RT-600's scale stops at 60 %, which is why
# its squelch cannot be wound as tight as the 517's; that difference is real and
# is preserved here.
SQUELCH_FLOOR = 0.08
SQUELCH_CEIL = 1.01

# Averaging. Both manuals describe roughly two seconds of drag error after a
# rapid course change, longer on a weak signal. The un-averaged stream is what
# cap/df/spread is measured from, which is why the averaging has to live here
# and not in the faceplate.
AVERAGE_S = 2.0
AVERAGE_S_MAX = 6.0
NOISE_DEG = 14.0        # scatter at zero signal; falls off as the signal rises

# Scan mode, 517 3.3.3: 406.025 while a burst is expected, otherwise the two
# continuous emergency frequencies in turn, holding on one if it answers.
SCAN_DWELL_S = 4.0

# Decoding the BCH-protected COSPAS-SARSAT frame needs more signal than getting
# a bearing does, and a good frame stays on screen between bursts.
DECODE_MIN_SIGNAL = 0.25
DECODE_HOLD_S = 120.0

DEFAULT_TIMEHOLD_S = 10.0
ERR_NONE = -1

# Nominal training geometry, in aircraft body coordinates. This is deliberately
# configurable: antenna position and airframe geometry vary between tail
# numbers, and the available CAP material does not establish a universal loss
# curve. z=0 is the wing plane; a belly antenna is below it and a top antenna is
# above it. The rectangular wing/fuselage projection is softened at its edges
# so a bank produces an audible fade rather than a binary switch.
AIRFRAME_PROFILES = {
    "c182_belly": {
        "location": "belly",
        "antenna_plane_distance_ft": 1.8,
        "wing_half_span_ft": 18.0,
        "wing_half_chord_ft": 2.75,
        "fuselage_half_width_ft": 2.0,
        "fuselage_half_length_ft": 10.5,
        "edge_softness_ft": 1.25,
        "max_loss_db": 24.0,
    },
    "c182_top": {
        "location": "top",
        "antenna_plane_distance_ft": 1.8,
        "wing_half_span_ft": 18.0,
        "wing_half_chord_ft": 2.75,
        "fuselage_half_width_ft": 2.0,
        "fuselage_half_length_ft": 10.5,
        "edge_softness_ft": 1.25,
        "max_loss_db": 24.0,
    },
}


def bearing_true(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    la1, la2 = math.radians(lat1), math.radians(lat2)
    y = math.sin(dlon) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def distance_nm(lat1, lon1, lat2, lon2):
    la1, la2 = math.radians(lat1), math.radians(lat2)
    dla, dlo = la2 - la1, math.radians(lon2 - lon1)
    a = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * R_NM * math.asin(min(1.0, math.sqrt(a)))


def interp(lat1, lon1, lat2, lon2, f):
    """Good enough over search-area distances, and far cheaper than a slerp."""
    return lat1 + (lat2 - lat1) * f, lon1 + (lon2 - lon1) * f


def ang_diff(a, b):
    """Signed a - b wrapped to -180..180."""
    return (a - b + 180.0) % 360.0 - 180.0


def smoothstep(edge0, edge1, value):
    """Cubic 0..1 transition used to soften the airframe silhouette."""
    if edge1 <= edge0:
        return 1.0 if value >= edge1 else 0.0
    t = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def _inside(value, limit, softness):
    """1 inside a symmetric boundary, fading to 0 just outside it."""
    return 1.0 - smoothstep(limit, limit + softness, abs(value))


def _outside(value, limit, softness):
    """1 outside a symmetric boundary, with a soft transition."""
    return smoothstep(max(0.0, limit - softness), limit + softness, abs(value))


def airframe_shadow_loss_db(brg_true, hdg_true, horizontal_ft, height_delta_ft,
                            roll_deg, pitch_deg, effects):
    """Return attenuation from a simplified wing/fuselage ray intersection.

    The beacon ray is transformed from a heading-level frame into aircraft body
    coordinates. For a belly antenna it is shadowed when the ray travels upward
    through the wing/fuselage plane; for a top antenna the sense reverses. This
    makes opposite banks and top/belly installations behave naturally without
    tying the model to a particular turn direction.
    """
    profile_name = str(effects.get("df_antenna_profile", "c182_belly"))
    base = AIRFRAME_PROFILES.get(profile_name, AIRFRAME_PROFILES["c182_belly"])
    profile = dict(base)
    overrides = {
        "df_antenna_location": "location",
        "wing_null_antenna_plane_distance_ft": "antenna_plane_distance_ft",
        "wing_null_half_span_ft": "wing_half_span_ft",
        "wing_null_half_chord_ft": "wing_half_chord_ft",
        "wing_null_fuselage_half_width_ft": "fuselage_half_width_ft",
        "wing_null_fuselage_half_length_ft": "fuselage_half_length_ft",
        "wing_null_edge_softness_ft": "edge_softness_ft",
        "wing_null_max_loss_db": "max_loss_db",
    }
    for source, target in overrides.items():
        if source in effects:
            profile[target] = effects[source]

    rel = math.radians(ang_diff(brg_true, hdg_true))
    elev = math.atan2(height_delta_ft, max(horizontal_ft, 1.0))

    # Heading-level coordinates: forward, right, up.
    forward_h = math.cos(elev) * math.cos(rel)
    right_h = math.cos(elev) * math.sin(rel)
    up_h = math.sin(elev)

    # Remove pitch, then roll, to express the ray in aircraft body coordinates.
    pitch = math.radians(pitch_deg)
    roll = math.radians(roll_deg)
    forward_b = forward_h * math.cos(pitch) + up_h * math.sin(pitch)
    up_after_pitch = -forward_h * math.sin(pitch) + up_h * math.cos(pitch)
    right_b = right_h * math.cos(roll) - up_after_pitch * math.sin(roll)
    up_b = right_h * math.sin(roll) + up_after_pitch * math.cos(roll)

    # Belly antenna rays must travel upward to cross the airframe plane; top
    # antenna rays must travel downward. A nearly parallel ray intersects too
    # far away to be blocked.
    direction = 1.0 if str(profile["location"]).lower() != "top" else -1.0
    toward_plane = direction * up_b
    if toward_plane <= 0.005:
        return 0.0

    antenna_distance = max(0.1, float(profile["antenna_plane_distance_ft"]))
    distance_to_plane = antenna_distance / toward_plane
    x = distance_to_plane * forward_b
    y = distance_to_plane * right_b

    soft = max(0.05, float(profile["edge_softness_ft"]))
    fuselage_width = max(0.1, float(profile["fuselage_half_width_ft"]))
    wing = (_inside(x, float(profile["wing_half_chord_ft"]), soft)
            * _outside(y, fuselage_width, soft)
            * _inside(y, float(profile["wing_half_span_ft"]), soft))
    fuselage = (_inside(x, float(profile["fuselage_half_length_ft"]), soft)
                * _inside(y, fuselage_width, soft))

    # The fuselage is also a useful shield but is less sharply directional than
    # a wing null, so cap its contribution below the wing's peak loss.
    coverage = max(wing, 0.70 * fuselage)
    return max(0.0, float(profile["max_loss_db"])) * coverage


def circular_mean(degrees):
    """Mean of angles. Averaging 359 and 1 has to give 0, not 180."""
    if not degrees:
        return 0.0
    sy = sum(math.sin(math.radians(d)) for d in degrees)
    sx = sum(math.cos(math.radians(d)) for d in degrees)
    if sx == 0.0 and sy == 0.0:
        return degrees[-1]
    return math.degrees(math.atan2(sy, sx)) % 360.0


def on_cs_grid(hz):
    return CS_LO_HZ - TUNE_TOL_CS_HZ <= hz <= CS_HI_HZ + TUNE_TOL_CS_HZ


def head_can_receive(head, hz, mode=MODE_EMERGENCY):
    """
    Whether the fitted head can be tuned here at all.

    The Becker's Emergency mode offers one fixed COSPAS/SARSAT channel; its
    Training mode is a freely adjustable 400.000-409.975 MHz receiver and can sit
    anywhere on the grid. The RT-600 covers the band either way. Outside the grid
    both heads are ordinary tunable receivers.
    """
    if not on_cs_grid(hz):
        return True
    if head == HEAD_517:
        if mode == MODE_TRAINING:
            return BECKER_TRAINING_UHF_LO_HZ <= hz <= BECKER_TRAINING_UHF_HI_HZ
        return any(abs(hz - c) <= TUNE_TOL_CS_HZ for c in BECKER_406_CHANNELS_HZ)
    return True


def tuned_to(hz, beacon_hz, span_hz=0.0):
    """
    Whether a receiver centred on hz hears a beacon on beacon_hz.

    span_hz is the half-width the receiver covers either side of centre. It is
    zero for a single-channel set such as the Becker, and half the group width
    for an RT-600 CPSAR selection, which takes in two or three 3 kHz channels at
    once. That breadth is the receiver difference the exercise is built on.
    """
    tol = TUNE_TOL_CS_HZ if on_cs_grid(beacon_hz) else TUNE_TOL_WIDE_HZ
    return abs(hz - beacon_hz) <= tol + max(0.0, span_hz)


def synth_hex15(lat, lon):
    """
    A stable 15-hex ident for a beacon the console has not given one for.

    Derived from the beacon's own position so it is the same every time that
    beacon is used, and obviously synthetic rather than a real registration. The
    console can override it, and should for any exercise where the ident matters.
    """
    h = hashlib.sha1(("cap-vsar:%.5f:%.5f" % (lat, lon)).encode()).hexdigest()
    return h.upper()[:15]


class PythonInterface:
    def __init__(self):
        self.probe = None
        self.loop = None
        self.accessors = []
        self.stop = threading.Event()

        # published DF state
        self.valid = 0
        self.bearing_rel = 0.0
        self.bearing_true = 0.0
        self.signal = 0.0
        self.distance = 0.0
        self.in_cone = 0
        self.blocked = 0
        self.airframe_shadowed = 0
        self.airframe_attenuation_db = 0.0
        self.rx_open = 0
        self.spread = 0.0

        # published COSPAS-SARSAT decode
        self.cs_sync = 0
        self.cs_protocol = 0
        self.cs_hex15 = b""
        self.cs_country = 0
        self.cs_has_position = 0
        self.cs_lat = 0.0
        self.cs_lon = 0.0
        self.cs_decoded_at = None

        # panel inputs. panel_seen stays false until a faceplate writes one of
        # them, and while it is false the engine behaves exactly as it did before
        # the panel could talk to it.
        self.panel_seen = False
        self.power = 1
        self.active_freq_hz = 0
        self.head_type = HEAD_517
        self.squelch = -1.0
        self.mode = MODE_EMERGENCY
        self.scan_enable = 0
        self.timehold = DEFAULT_TIMEHOLD_S
        self.offset_deg = 0.0
        self.mounting = MOUNT_TOP
        self.rx_span_hz = 0
        self.scan_alt1_hz = 0
        self.scan_alt2_hz = 0
        self.clear_pending = False

        # averaging store, and the last bearing being held between bursts
        self.samples = collections.deque()      # (t, rel, true)
        self.held = None                        # (t, rel, true)
        self.scan_hold_hz = None

        # scenario, replaced wholesale by the network thread
        self.scn = {"active": 0, "lat": 0.0, "lon": 0.0, "elev_ft": 0.0,
                    "band": 121.5, "power": 1.0, "effects": {}}
        self.started = time.time()
        self.pos = (0.0, 0.0, 0.0, 0.0)   # lat, lon, alt_ft, hdg_true
        self.attitude = (0.0, 0.0)          # roll, pitch

    # ------------------------------------------------------------- lifecycle
    def XPluginStart(self):
        self.dr_lat = xp.findDataRef("sim/flightmodel/position/latitude")
        self.dr_lon = xp.findDataRef("sim/flightmodel/position/longitude")
        self.dr_elev = xp.findDataRef("sim/flightmodel/position/elevation")
        self.dr_psi = xp.findDataRef("sim/flightmodel/position/psi")
        self.dr_phi = xp.findDataRef("sim/flightmodel/position/phi")
        self.dr_theta = xp.findDataRef("sim/flightmodel/position/theta")

        def f(name, get):
            self.accessors.append(
                xp.registerDataAccessor(name, xp.Type_Float, 0, readFloat=lambda r, g=get: g()))

        def i(name, get):
            self.accessors.append(
                xp.registerDataAccessor(name, xp.Type_Int, 0, readInt=lambda r, g=get: g()))

        def b(name, get):
            """Byte-array accessor. X-Plane asks for the length by passing no
            buffer, and count == -1 means 'all of it'."""
            def read(refCon, values, offset, count, g=get):
                raw = g()
                if values is None:
                    return len(raw)
                if count < 0:
                    count = len(raw)
                chunk = raw[offset:offset + count]
                values.extend(chunk)
                return len(chunk)
            self.accessors.append(
                xp.registerDataAccessor(name, xp.Type_Data, 0, readData=read))

        i("cap/df/valid", lambda: self.valid)
        f("cap/df/bearing_rel", lambda: self.bearing_rel)
        f("cap/df/bearing_true", lambda: self.bearing_true)
        f("cap/df/signal", lambda: self.signal)
        f("cap/df/distance_nm", lambda: self.distance)
        i("cap/df/in_cone", lambda: self.in_cone)
        i("cap/df/blocked", lambda: self.blocked)
        i("cap/df/airframe_shadowed", lambda: self.airframe_shadowed)
        f("cap/df/airframe_attenuation_db", lambda: self.airframe_attenuation_db)
        i("cap/df/rx_open", lambda: self.rx_open)
        f("cap/df/band", lambda: self.published_band())
        f("cap/df/spread", lambda: self.spread)
        i("cap/df/error_code", lambda: int(self.scn.get("effects", {}).get("error_code", ERR_NONE)))
        i("cap/scenario/active", lambda: int(self.scn.get("active", 0)))

        i("cap/df/cs_sync", lambda: self.cs_sync)
        i("cap/df/cs_protocol", lambda: self.cs_protocol)
        b("cap/df/cs_hex15", lambda: self.cs_hex15)
        i("cap/df/cs_country", lambda: self.cs_country)
        i("cap/df/cs_has_position", lambda: self.cs_has_position)
        f("cap/df/cs_lat", lambda: self.cs_lat)
        f("cap/df/cs_lon", lambda: self.cs_lon)
        f("cap/df/cs_msg_age_sec", lambda: self.cs_msg_age())

        # ---- panel inputs, writable ----------------------------------------
        # Readable as well as writable so the instructor console and DataRefTool
        # can see what the crew has actually set.

        def in_int(name, attr, clamp=None):
            def write(refCon, v, a=attr, c=clamp):
                v = int(v)
                if c:
                    v = max(c[0], min(c[1], v))
                setattr(self, a, v)
                self.panel_seen = True
            self.accessors.append(xp.registerDataAccessor(
                name, xp.Type_Int, 1,
                readInt=lambda r, a=attr: int(getattr(self, a)),
                writeInt=write))

        def in_float(name, attr, clamp=None):
            def write(refCon, v, a=attr, c=clamp):
                v = float(v)
                if c:
                    v = max(c[0], min(c[1], v))
                setattr(self, a, v)
                self.panel_seen = True
            self.accessors.append(xp.registerDataAccessor(
                name, xp.Type_Float, 1,
                readFloat=lambda r, a=attr: float(getattr(self, a)),
                writeFloat=write))

        in_int("cap/df/power", "power", (0, 1))
        in_int("cap/df/active_freq_hz", "active_freq_hz", (0, 2_000_000_000))
        in_int("cap/df/head_type", "head_type", (HEAD_517, HEAD_RT600))
        in_int("cap/df/mode", "mode", (MODE_EMERGENCY, MODE_TRAINING))
        in_int("cap/df/scan_enable", "scan_enable", (0, 1))
        in_int("cap/df/mounting", "mounting", (MOUNT_TOP, MOUNT_BOTTOM))
        in_int("cap/df/rx_span_hz", "rx_span_hz", (0, 10_000_000))
        in_int("cap/df/scan_alt1_hz", "scan_alt1_hz", (0, 2_000_000_000))
        in_int("cap/df/scan_alt2_hz", "scan_alt2_hz", (0, 2_000_000_000))
        in_float("cap/df/squelch", "squelch", (-1.0, 100.0))
        in_float("cap/df/timehold_sec", "timehold", (0.0, 300.0))
        in_float("cap/df/offset_deg", "offset_deg", (-180.0, 360.0))

        # The panel pulses 1 and we self-reset, so it never has to write a 0.
        def write_clear(refCon, v):
            self.panel_seen = True
            if int(v):
                self.clear_pending = True
        self.accessors.append(xp.registerDataAccessor(
            "cap/df/clear_average", xp.Type_Int, 1,
            readInt=lambda r: 1 if self.clear_pending else 0,
            writeInt=write_clear))

        # writable, so a scenario can be set by hand with no console reachable
        self.accessors.append(xp.registerDataAccessor(
            "cap/scenario/beacon_lat", xp.Type_Double, 1,
            readDouble=lambda r: float(self.scn["lat"]),
            writeDouble=lambda r, v: self.scn.__setitem__("lat", v)))
        self.accessors.append(xp.registerDataAccessor(
            "cap/scenario/beacon_lon", xp.Type_Double, 1,
            readDouble=lambda r: float(self.scn["lon"]),
            writeDouble=lambda r, v: self.scn.__setitem__("lon", v)))
        self.accessors.append(xp.registerDataAccessor(
            "cap/scenario/beacon_elev", xp.Type_Float, 1,
            readFloat=lambda r: float(self.scn["elev_ft"]),
            writeFloat=lambda r, v: self.scn.__setitem__("elev_ft", v)))

        self.probe = xp.createProbe(xp.ProbeY)
        xp.log("CAP V-SAR: DF engine started, %d datarefs published" % len(self.accessors))
        return "CAP V-SAR DF", "org.cap.vsar.df", "Direction finder propagation engine"

    def XPluginEnable(self):
        # A fresh event: XPluginDisable sets the old one and X-Plane reuses the
        # instance, so re-enabling with the set event started a thread that
        # exited on its first check. The datarefs kept publishing stale state
        # with no console link and nothing said so.
        self.stop = threading.Event()
        self.loop = xp.createFlightLoop(self.flight_loop, xp.FlightLoop_Phase_AfterFlightModel)
        xp.scheduleFlightLoop(self.loop, LOOP_S)
        self.net = threading.Thread(target=self.net_worker, daemon=True)
        self.net.start()
        return 1

    def XPluginDisable(self):
        self.stop.set()
        # Give the worker a moment to notice, but never block X-Plane on it: it
        # may be inside a 4 s urlopen. It is a daemon and the event is set, so
        # it will exit on its own either way.
        if self.net and self.net.is_alive():
            self.net.join(timeout=1.0)
        self.net = None
        if self.loop:
            xp.destroyFlightLoop(self.loop)
            self.loop = None

    def XPluginStop(self):
        for a in self.accessors:
            xp.unregisterDataAccessor(a)
        self.accessors = []
        if self.probe:
            xp.destroyProbe(self.probe)
            self.probe = None

    def XPluginReceiveMessage(self, inFrom, inMsg, inParam):
        pass

    # -------------------------------------------------------------- terrain
    def terrain_ft(self, lat, lon):
        """Terrain elevation in feet MSL, or None if outside loaded scenery."""
        x, y, z = xp.worldToLocal(lat, lon, 0.0)
        info = xp.probeTerrainXYZ(self.probe, x, y, z)
        if info.result != xp.ProbeHitTerrain:
            return None
        _, _, alt_m = xp.localToWorld(info.locationX, info.locationY, info.locationZ)
        return alt_m * FT_PER_M

    def line_of_sight_blocked(self, ac_lat, ac_lon, ac_ft, b_lat, b_lon, b_ft):
        """
        Sample terrain along the path and compare it to the straight ray.

        This is the reason the engine lives in the simulator: no server-side
        model can see the ridge between the aircraft and the beacon.
        """
        for k in range(1, LOS_SAMPLES):
            fr = k / float(LOS_SAMPLES)
            lat, lon = interp(ac_lat, ac_lon, b_lat, b_lon, fr)
            ground = self.terrain_ft(lat, lon)
            if ground is None:
                continue                      # unloaded scenery: assume clear
            ray = ac_ft + (b_ft - ac_ft) * fr  # linear, adequate at these ranges
            if ground > ray + 50.0:           # 50 ft margin for probe noise
                return True
        return False

    # ---------------------------------------------------------- receiver
    def beacon_hz(self):
        """What the beacon is actually transmitting on."""
        s = self.scn
        hz = s.get("beacon_freq_hz")
        if hz:
            return float(hz)
        band = float(s.get("band", 121.5))
        if band > 400:
            return 406_025_000.0
        if band > 200:
            return 243_000_000.0
        return 121_500_000.0

    def burst_open(self):
        """True during the ~440 ms a 406 beacon is actually radiating."""
        return (time.time() - self.started) % BURST_PERIOD_S < BURST_LEN_S

    def tuned_hz(self):
        """The channel the crew has selected, ignoring any scan stepping."""
        if not self.panel_seen:
            return self.beacon_hz()
        return float(self.active_freq_hz) if self.active_freq_hz else self.beacon_hz()

    def effective_freq_hz(self):
        """
        What the receiver is listening to this instant.

        Without a panel this is simply the beacon's frequency - the old
        behaviour, where the console picks the band and the head is assumed to be
        on it. With a panel it is what the crew tuned, except in scan mode where
        the receiver is stepping between channels on its own.
        """
        if not self.panel_seen:
            return self.beacon_hz()
        tuned = self.tuned_hz()
        if not self.scan_enable:
            return tuned
        # 517 3.3.3: surveil the COSPAS/SARSAT burst, and in the 5-45 s gap
        # between bursts listen to the two continuous frequencies; if one of them
        # answers, stay there rather than resuming the sweep.
        #
        # Which frequencies those are comes from the panel, not from here. In
        # Emergency mode they are 121.500 and 243.000; in Training mode they are
        # whatever the crew adjusted the training channels to, and the engine has
        # no way to guess that. The fallbacks keep the old behaviour if a panel
        # never writes them.
        if self.scan_hold_hz:
            return self.scan_hold_hz
        if self.burst_open():
            return tuned
        alt1 = float(self.scan_alt1_hz) or 121_500_000.0
        alt2 = float(self.scan_alt2_hz) or 243_000_000.0
        phase = int((time.time() - self.started) / SCAN_DWELL_S) % 2
        return alt1 if phase == 0 else alt2

    def published_band(self):
        """cap/df/band in MHz - what the head is on, not what the console picked."""
        if not self.panel_seen:
            return float(self.scn.get("band", 121.5))
        return self.effective_freq_hz() / 1e6

    def squelch_threshold(self):
        """Signal a station must beat to open the squelch, on the 0..1 scale."""
        if not self.panel_seen or self.squelch < 0:
            return SQUELCH_FLOOR            # Auto, and the no-panel default
        pct = max(0.0, min(100.0, self.squelch)) / 100.0
        return SQUELCH_FLOOR + pct * (SQUELCH_CEIL - SQUELCH_FLOOR)

    def average_window_s(self):
        """Longer on a weak signal, as both manuals describe."""
        weak = 1.0 - max(0.0, min(1.0, self.signal))
        return AVERAGE_S + (AVERAGE_S_MAX - AVERAGE_S) * weak

    def cs_msg_age(self):
        if self.cs_decoded_at is None:
            return 0.0
        return time.time() - self.cs_decoded_at

    # ------------------------------------------------------------ main loop
    def flight_loop(self, sinceLast, elapsed, counter, refCon):
        try:
            self.compute()
        except Exception as e:
            xp.log("CAP V-SAR: compute failed: %s" % e)
        return LOOP_S

    def silent(self, keep_distance=False, keep_hold=False):
        """Noise floor. Nothing is being received.

        keep_hold leaves the TIMEHOLD bearing standing for a caller that is
        about to run hold_or_drop: the receiver is quiet for a reason the crew
        expects, not because the signal was lost.
        """
        self.valid, self.signal, self.blocked, self.in_cone = 0, 0.0, 0, 0
        self.airframe_shadowed = 0
        self.airframe_attenuation_db = 0.0
        self.rx_open = 0
        if not keep_hold:
            self.spread = 0.0
            self.samples.clear()
            self.held = None
        if not keep_distance:
            self.distance = 0.0

    def compute(self):
        now = time.time()
        lat = xp.getDatad(self.dr_lat)
        lon = xp.getDatad(self.dr_lon)
        alt_ft = xp.getDatad(self.dr_elev) * FT_PER_M
        hdg = xp.getDataf(self.dr_psi)
        roll = xp.getDataf(self.dr_phi)
        pitch = xp.getDataf(self.dr_theta)
        self.pos = (lat, lon, alt_ft, hdg)
        self.attitude = (roll, pitch)

        if self.clear_pending:
            # CLR on the 517, or a long CLR press on the RT-600: throw the
            # averaging store away so the drag error after a course change goes
            # with it. Self-resetting, so the panel only ever writes a 1.
            self.samples.clear()
            self.clear_pending = False

        s = self.scn
        if not s.get("active"):
            self.silent()
            self.clear_decode()
            return

        # Powered off: the head is not receiving anything and is not holding
        # anything either.
        if self.panel_seen and not self.power:
            self.silent()
            self.clear_decode()
            self.scan_hold_hz = None
            return

        b_lat, b_lon, b_ft = s["lat"], s["lon"], s["elev_ft"]
        eff = s.get("effects", {})

        d = distance_nm(lat, lon, b_lat, b_lon)
        self.distance = d
        brg = bearing_true(lat, lon, b_lat, b_lon)

        # Radio horizon. Both ends contribute: 1.23*(sqrt(h_ac) + sqrt(h_bcn)),
        # heights in feet MSL. The old form used the aircraft's height *above
        # the beacon*, which collapsed to zero the moment the beacon sat higher
        # than the aircraft - so an aircraft in a valley below a ridge-top
        # beacon a mile away heard nothing at all. Terrain between the two is a
        # separate question, answered by the line-of-sight probe below.
        if eff.get("radio_horizon", True):
            horizon = 1.23 * (math.sqrt(max(alt_ft, 0.0)) + math.sqrt(max(b_ft, 0.0)))
            if d > horizon:
                self.silent(keep_distance=True)
                self.decode_tick(False)
                return

        # Tuning. The head only hears the beacon if it is on the right channel
        # and physically able to receive it - which for a 406 channel depends on
        # which head is fitted.
        listening_hz = self.effective_freq_hz()
        if self.panel_seen:
            if not head_can_receive(self.head_type, listening_hz, self.mode):
                # A 517 parked on a C/S channel it does not have. The set looks
                # perfectly healthy and hears nothing, which is the point.
                self.silent(keep_distance=True)
                self.decode_tick(False)
                return
            if not tuned_to(listening_hz, self.beacon_hz(), self.rx_span_hz):
                if self.scan_enable and listening_hz != self.tuned_hz():
                    # Scan has stepped off the tuned channel between bursts
                    # (517 3.3.3). That is the receiver doing its job, not the
                    # signal going away, and TIMEHOLD is precisely what carries
                    # the bearing across the gap. Clearing it here made the
                    # bearing vanish the instant each 440 ms burst ended - in
                    # the 517's normal 406 posture, scan on.
                    self.silent(keep_distance=True, keep_hold=True)
                    self.hold_or_drop(now)
                else:
                    # Genuinely parked on the wrong channel: nothing to hold.
                    self.silent(keep_distance=True)
                self.decode_tick(False)
                self.scan_hold_hz = None
                return

        # terrain masking - the effect only the simulator can produce
        blocked = False
        if eff.get("terrain_masking", True) and d > 0.3:
            blocked = self.line_of_sight_blocked(lat, lon, alt_ft, b_lat, b_lon, b_ft)
        self.blocked = 1 if blocked else 0

        # Accumulate propagation losses before saturation. This lets a very
        # strong nearby beacon remain audible through partial shielding while a
        # weak distant beacon can disappear into the null.
        raw_signal = float(s.get("power", 1.0)) * 25.0 / max(d * d, 0.25)
        if blocked:
            raw_signal *= 0.06                # heavy attenuation, not silence

        loss_db = 0.0
        if eff.get("airframe_shadowing", False):
            loss_db = airframe_shadow_loss_db(
                brg, hdg, d * 6076.0, b_ft - alt_ft, roll, pitch, eff)
            raw_signal *= 10.0 ** (-loss_db / 10.0)
        self.airframe_attenuation_db = loss_db
        self.airframe_shadowed = 1 if loss_db >= 1.0 else 0

        signal = min(1.0, raw_signal)
        self.signal = signal
        self.rx_open = 0
        self.in_cone = 0

        if signal < self.squelch_threshold():
            # Squelched, either by the noise floor or because the crew wound it
            # too far up. Either way the set is quiet and the needle is dead.
            self.hold_or_drop(now)
            self.decode_tick(False)
            if self.scan_enable:
                self.scan_hold_hz = None
            return

        # In scan mode a continuous emergency frequency that answers is worth
        # staying on (517 3.3.3).
        if self.panel_seen and self.scan_enable and not on_cs_grid(listening_hz):
            self.scan_hold_hz = listening_hz

        # 406 transmits a burst about every 50 s. Outside the burst there is
        # nothing to take a bearing from, so the last one is held for as long as
        # the crew's TIMEHOLD setting allows and then dropped.
        on_406 = listening_hz > 400e6
        if on_406 and eff.get("burst_cadence", True) and not self.burst_open():
            self.hold_or_drop(now)
            self.decode_tick(False)
            return

        # This is instantaneous reception, separate from a bearing which may be
        # held across a null or between 406 bursts. The audio path should follow
        # rx_open rather than cap/df/valid.
        self.rx_open = 1

        # cone of confusion: the transmission is audible, but no directional
        # bearing can be resolved.
        agl = max(alt_ft - b_ft, 1.0)
        cone_nm = (agl / 6076.0) * math.tan(math.radians(30.0))
        if eff.get("cone_of_confusion", True) and d < cone_nm:
            self.in_cone, self.valid = 1, 0
            self.samples.clear()
            self.held = None
            self.spread = 0.0
            self.decode_tick(signal >= DECODE_MIN_SIGNAL)
            return
        self.in_cone = 0

        if eff.get("multipath", False):
            if int((now - self.started) / 12.0) % 3 == 0:
                brg = (brg + float(eff.get("multipath_offset_deg", 40.0))) % 360.0

        rel = (brg - hdg) % 360.0

        # Antenna offset: the installation has a real misalignment and the crew
        # dials in a correction. They cancel when the correction is right.
        installed_offset = float(eff.get("antenna_offset_deg", 0.0))
        rel = (rel + installed_offset - (self.offset_deg if self.panel_seen else 0.0)) % 360.0

        # Mounting: a top-mounted antenna set to BOTTOM (or the reverse) puts
        # the bearing out on the wrong side. Cheap trap, entirely realistic.
        if self.panel_seen and self.mounting != int(eff.get("mounting", MOUNT_TOP)):
            rel = (-rel) % 360.0

        # One un-averaged sample. Scatter grows as the signal falls, and it is
        # this scatter - not the averaged output - that cap/df/spread reports.
        sigma = NOISE_DEG * (1.0 - min(1.0, signal)) ** 2
        noisy_rel = (rel + (random.gauss(0.0, sigma) if sigma > 0.01 else 0.0)) % 360.0
        self.samples.append((now, noisy_rel, (noisy_rel + hdg) % 360.0))

        window = self.average_window_s()
        while self.samples and now - self.samples[0][0] > window:
            self.samples.popleft()

        rels = [smp[1] for smp in self.samples]
        mean_rel = circular_mean(rels)
        self.bearing_rel = mean_rel
        self.bearing_true = (mean_rel + hdg) % 360.0
        self.spread = max((abs(ang_diff(r, mean_rel)) for r in rels), default=0.0)
        self.valid = 1
        self.held = (now, self.bearing_rel, self.bearing_true)

        self.decode_tick(signal >= DECODE_MIN_SIGNAL and on_406 and self.burst_open())

    def hold_or_drop(self, now):
        """
        Keep showing the last bearing for TIMEHOLD seconds, then give up.

        This is what carries the display across the 45-odd seconds between 406
        bursts, and it is why TIMEHOLD is on the 517's edit menu.
        """
        hold = self.timehold if self.panel_seen else DEFAULT_TIMEHOLD_S
        if self.held and now - self.held[0] <= max(0.0, hold):
            self.valid = 1
            self.bearing_rel = self.held[1]
            self.bearing_true = self.held[2]
        else:
            self.valid = 0
            self.held = None
            self.samples.clear()
            self.spread = 0.0

    # -------------------------------------------------- COSPAS-SARSAT decode
    def clear_decode(self):
        self.cs_sync = 0
        self.cs_protocol = 0
        self.cs_hex15 = b""
        self.cs_country = 0
        self.cs_has_position = 0
        self.cs_lat = self.cs_lon = 0.0
        self.cs_decoded_at = None

    def decode_tick(self, frame_received):
        """
        Hold, refresh or drop the decoded frame.

        A frame is only decoded when a burst is actually heard with enough
        signal to get through the BCH check; once decoded it stays on screen for
        DECODE_HOLD_S so the page does not blink out between bursts.
        """
        if frame_received:
            self.load_decode()
            self.cs_decoded_at = time.time()
            return
        if self.cs_decoded_at is not None and self.cs_msg_age() > DECODE_HOLD_S:
            self.clear_decode()

    def load_decode(self):
        """
        Populate the decode from the scenario.

        The console owns beacon truth. If it sends a "cs" block every field comes
        from there; if it does not, ident and country are synthesised from the
        beacon position so the page is usable in training, and the position field
        stays absent unless the scenario says the beacon is GPS-encoded - a plain
        406 ELT without GPS is both the commoner case and the more interesting
        search.
        """
        s = self.scn
        cs = s.get("cs") or {}

        self.cs_sync = 2 if cs.get("selftest") else 1

        proto = int(cs.get("protocol", 2))      # 2 = STANDARD
        if self.panel_seen and self.mode == MODE_TRAINING and proto <= 3:
            proto += 4                          # the TEST variant, as the panels render it
        self.cs_protocol = proto

        ident = cs.get("hex15") or synth_hex15(s["lat"], s["lon"])
        self.cs_hex15 = str(ident).upper()[:15].encode("ascii", "replace")
        self.cs_country = int(cs.get("country", 366))   # 366 = United States

        has_pos = cs.get("has_position")
        if has_pos is None:
            has_pos = bool(s.get("effects", {}).get("beacon_has_gps", False))
        self.cs_has_position = 1 if has_pos else 0
        if self.cs_has_position:
            self.cs_lat = float(cs.get("lat", s["lat"]))
            self.cs_lon = float(cs.get("lon", s["lon"]))
        else:
            self.cs_lat = self.cs_lon = 0.0

    # ------------------------------------------------------- network thread
    def truth_note(self, state, message):
        """Log a change in whether the console will give us the beacon.

        Once per transition, not once per poll: a silent DF is the symptom the
        crew reports, and this is where the reason gets recorded.
        """
        if getattr(self, "_truth_state", None) != state:
            self._truth_state = state
            xp.log("CAP V-SAR: " + message)

    def fetch_scenario(self):
        """The running sortie, with beacon truth, from the console.

        Returns the decoded body, or None when the console is reachable but
        will not serve truth - the caller then goes silent rather than
        pointing the DF at a stale or null position.
        """
        req = urllib.request.Request(CONSOLE + "/api/plugin/scenario",
                                     headers={"X-CAPVSAR-Token": PLUGIN_KEY}
                                     if PLUGIN_KEY else {})
        try:
            with urllib.request.urlopen(req, timeout=4) as r:
                st = json.load(r)
            self.truth_note("ok", "beacon truth channel open")
            return st
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Console predates the plugin truth channel. Fall back to the
                # public state so the sortie flag still tracks, but that feed
                # withholds the beacon, so the DF stays silent.
                self.truth_note("legacy", "console has no /api/plugin/scenario "
                                          "- update it; DF has no beacon truth")
            elif e.code == 503:
                self.truth_note("unconfigured", "console has no CAPVSAR_TOKEN_PLUGIN "
                                                "set - DF has no beacon truth")
            elif e.code == 403:
                self.truth_note("rejected", "console rejected this station's plugin "
                                            "key - DF has no beacon truth")
            else:
                self.truth_note("http%d" % e.code,
                                "console returned HTTP %d for beacon truth" % e.code)
            return None

    def net_worker(self):
        last_report = 0.0
        while not self.stop.is_set():
            try:
                st = self.fetch_scenario()
                if st is None:
                    # Console is up but will not give us the beacon. Silence is
                    # the honest state: a DF homing on a stale or null position
                    # teaches the crew something false.
                    self.scn["active"] = 0
                else:
                    sc = st.get("scenario") or {}
                    so = st.get("sortie") or {}
                    running = bool(so and not so.get("stopped"))
                    if running and sc.get("beacon_lat") is not None:
                        self.scn.update({"active": 1, "lat": sc["beacon_lat"],
                                         "lon": sc["beacon_lon"],
                                         "elev_ft": sc.get("beacon_elev_ft", 0.0),
                                         "band": float(sc.get("band", 121.5)),
                                         "beacon_freq_hz": sc.get("beacon_freq_hz"),
                                         "power": sc.get("power", 1.0),
                                         "cs": sc.get("cs", {}),
                                         "effects": sc.get("effects", {})})
                    elif running:
                        # Sortie running but no beacon in the payload: the
                        # scenario is incomplete. Effects still apply, but
                        # there is nothing to home on.
                        self.truth_note("no-beacon",
                                        "sortie running with no beacon position")
                        self.scn["active"] = 0
                        self.scn["effects"] = sc.get("effects", self.scn["effects"])
                    else:
                        self.scn["active"] = 0
            except Exception:
                pass                          # console offline is not an error

            now = time.time()
            if now - last_report >= REPORT_S:
                last_report = now
                try:
                    lat, lon, alt_ft, hdg = self.pos
                    report = {"callsign": CALLSIGN, "lat": lat, "lon": lon,
                              "alt_ft": alt_ft, "hdg_true": hdg}
                    if self.panel_seen:
                        # What the crew has the DF set to. The instructor cannot
                        # see over their shoulder, and "why can't they hear it"
                        # is usually answered here.
                        report["df"] = {
                            "valid": bool(self.valid),
                            "bearing_rel": round(self.bearing_rel, 1),
                            "bearing_true": round(self.bearing_true, 1),
                            "signal": round(self.signal, 4),
                            "distance_nm": round(self.distance, 2),
                            "in_cone": bool(self.in_cone),
                            "blocked": bool(self.blocked),
                            "power": self.power,
                            "head_type": self.head_type,
                            "freq_hz": int(self.effective_freq_hz()),
                            "rx_span_hz": int(self.rx_span_hz),
                            "squelch": self.squelch,
                            "mode": self.mode,
                            "scan": self.scan_enable,
                            "mounting": self.mounting,
                            "offset_deg": self.offset_deg,
                            "rx_open": self.rx_open,
                            "airframe_shadowed": self.airframe_shadowed,
                            "airframe_attenuation_db": round(self.airframe_attenuation_db, 1),
                            "roll_deg": round(self.attitude[0], 1),
                            "pitch_deg": round(self.attitude[1], 1),
                            "note": ("wing null" if self.airframe_shadowed and not self.rx_open
                                     else "airframe attenuation" if self.airframe_shadowed
                                     else "terrain masked" if self.blocked
                                     else "cone of confusion" if self.in_cone
                                     else "holding" if self.valid and not self.rx_open
                                     else ""),
                        }
                    body = json.dumps(report).encode()
                    headers = {"Content-Type": "application/json"}
                    if PLUGIN_KEY:
                        # Position ingest carries the same key: the console
                        # gates it on the plugin role once tokens are set.
                        headers["X-CAPVSAR-Token"] = PLUGIN_KEY
                    req = urllib.request.Request(
                        CONSOLE + "/api/positions", data=body, headers=headers)
                    urllib.request.urlopen(req, timeout=4).read()
                except Exception:
                    pass
            self.stop.wait(POLL_S)
