"""Offline exercise of the CAP V-SAR DF engine.

    python3 tests/test_engine.py [path/to/PI_capvsar_df.py]

Loads the engine plugin against the stubbed xp module in tests/xp.py, drives it
the way Air Manager and the exercise console would, and asserts the behaviours
the panel inputs were added for - above all the 406 MHz coverage difference
between the two DF heads, which is the scenario the whole exercise is built on.

Neither X-Plane nor Air Manager is needed, which is the point: this is the only
way to check the engine on a machine that has neither. It does not test the
faceplates - for those, scripts/luacheck.py checks syntax and the rest waits on
first bring-up in Air Manager.
"""
import importlib.util
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xp  # the stub

PLUGIN = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "xplane", "PI_capvsar_df.py")))
if not os.path.exists(PLUGIN):
    sys.exit("engine plugin not found: %s" % PLUGIN)
spec = importlib.util.spec_from_file_location("PI_capvsar_df", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Clock:
    """The engine only ever asks time for time.time(). Owning it lets a test run
    a hundred 250 ms ticks without waiting 25 seconds."""
    def __init__(self):
        self.now = 1_700_000_000.0

    def time(self):
        return self.now

    def advance(self, dt):
        self.now += dt


clock = Clock()
mod.time = clock

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("   " + detail if detail else ""))
    if not cond:
        FAILED.append(name)


def new_engine(beacon_lat=39.0, beacon_lon=-105.0, beacon_ft=9000.0,
               band=406.0, beacon_hz=None, cs=None, effects=None):
    xp.REFS.clear()
    clock.now = 1_700_000_000.0
    e = mod.PythonInterface()
    e.XPluginStart()
    e.scn.update({"active": 1, "lat": beacon_lat, "lon": beacon_lon,
                  "elev_ft": beacon_ft, "band": band,
                  "beacon_freq_hz": beacon_hz, "power": 1.0,
                  "cs": cs or {}, "effects": effects if effects is not None else {}})
    # Aircraft 5 NM north of the beacon at 12,000 ft, heading south.
    xp.SIM.update({"lat": beacon_lat + 0.0833, "lon": beacon_lon,
                   "elev_m": 12000.0 / 3.28084, "psi": 180.0,
                   "phi": 0.0, "theta": 0.0})
    return e


def settle_burst(e, ticks=8):
    """Ticks with the beacon radiating throughout."""
    for _ in range(ticks):
        clock.advance(mod.LOOP_S)
        e.started = clock.now
        e.compute()


def settle(e, ticks=40):
    """Run enough 250 ms ticks to fill the averaging window."""
    for _ in range(ticks):
        clock.advance(mod.LOOP_S)
        e.compute()


def force_burst(e, open_):
    """Park the burst clock so 406 is either radiating or silent."""
    e.started = clock.now if open_ else clock.now - mod.BURST_PERIOD_S / 2.0


print("\n== the 406 coverage difference: the reason both heads exist ==")
# Beacon on 406.037 - a COSPAS-SARSAT channel the Becker 517 does not have.
for head, name, expect in ((mod.HEAD_517, "Becker 517", False),
                           (mod.HEAD_RT600, "RHOTHETA RT-600", True)):
    e = new_engine(beacon_hz=406_037_000)
    xp.write("cap/df/power", 1)
    xp.write("cap/df/head_type", head)
    xp.write("cap/df/active_freq_hz", 406_037_000)
    settle_burst(e)
    got = bool(xp.read("cap/df/valid"))
    check("%-16s on 406.037 -> %s" % (name, "hears it" if expect else "hears nothing"),
          got == expect, "valid=%d signal=%.2f" % (got, xp.read("cap/df/signal")))

# ... and on 406.025, which both heads have.
for head, name in ((mod.HEAD_517, "Becker 517"), (mod.HEAD_RT600, "RHOTHETA RT-600")):
    e = new_engine(beacon_hz=406_025_000)
    xp.write("cap/df/power", 1)
    xp.write("cap/df/head_type", head)
    xp.write("cap/df/active_freq_hz", 406_025_000)
    settle_burst(e)
    check("%-16s on 406.025 -> hears it" % name, bool(xp.read("cap/df/valid")),
          "bearing_rel=%.1f" % xp.read("cap/df/bearing_rel"))


print("\n== tuning ==")
e = new_engine(beacon_hz=121_500_000, band=121.5)
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
check("tuned to the beacon -> valid", bool(xp.read("cap/df/valid")))
xp.write("cap/df/active_freq_hz", 243_000_000)
settle(e, 80)
check("tuned away -> nothing", not bool(xp.read("cap/df/valid")))

print("\n== power ==")
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
xp.write("cap/df/power", 0)
e.compute()
check("power off -> noise floor", xp.read("cap/df/valid") == 0 and xp.read("cap/df/signal") == 0.0)

print("\n== squelch ==")
e = new_engine(beacon_hz=121_500_000, band=121.5)
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
xp.write("cap/df/squelch", -1.0)          # Auto
settle(e)
open_signal = xp.read("cap/df/signal")
check("auto squelch -> open", bool(xp.read("cap/df/valid")), "signal=%.2f" % open_signal)
xp.write("cap/df/squelch", 100.0)         # wound right up
settle(e, 80)
check("squelch at 100 %% -> closed", not bool(xp.read("cap/df/valid")),
      "signal still %.2f" % xp.read("cap/df/signal"))

print("\n== bearing, averaging and spread ==")
e = new_engine(beacon_hz=121_500_000, band=121.5)
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
rel = xp.read("cap/df/bearing_rel")
check("beacon dead ahead -> ~0 deg relative", abs(mod.ang_diff(rel, 0.0)) < 8.0,
      "bearing_rel=%.1f" % rel)
check("spread is published and small on a strong signal",
      0.0 <= xp.read("cap/df/spread") < 10.0, "spread=%.1f" % xp.read("cap/df/spread"))

# Drag error: swing the aircraft 90 deg and the averaged bearing should lag.
# The beacon is due south, so nose on 270 puts it 270 relative.
xp.SIM["psi"] = 270.0
clock.advance(mod.LOOP_S)
e.compute()
lagged = xp.read("cap/df/bearing_rel")
check("rapid course change -> drag error", abs(mod.ang_diff(lagged, 270.0)) > 20.0,
      "shows %.1f, truth is 270.0" % lagged)
xp.write("cap/df/clear_average", 1)
clock.advance(mod.LOOP_S)
e.compute()
cleared = xp.read("cap/df/bearing_rel")
check("CLR -> averaging store gone, bearing snaps back",
      abs(mod.ang_diff(cleared, 270.0)) < 20.0, "shows %.1f" % cleared)
check("clear_average self-resets", xp.read("cap/df/clear_average") == 0)

print("\n== mounting trap ==")
e = new_engine(beacon_hz=121_500_000, band=121.5)
xp.SIM["psi"] = 90.0        # beacon off to the left, ~270 relative
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
xp.write("cap/df/mounting", mod.MOUNT_TOP)
settle(e)
right = xp.read("cap/df/bearing_rel")
xp.write("cap/df/mounting", mod.MOUNT_BOTTOM)
settle(e)
wrong = xp.read("cap/df/bearing_rel")
check("wrong mounting mirror-inverts the bearing",
      abs(mod.ang_diff(wrong, -right)) < 15.0,
      "TOP %.1f -> BOTTOM %.1f" % (right, wrong))


print("\n== wing null / airframe shadowing ==")
shadow_effects = {"radio_horizon": False, "terrain_masking": False,
                  "cone_of_confusion": False,
                  "airframe_shadowing": True,
                  "df_antenna_profile": "c182_belly"}
e = new_engine(beacon_hz=121_500_000, band=121.5, effects=shadow_effects)
xp.SIM["psi"] = 90.0       # beacon is abeam to the right
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
level_signal = xp.read("cap/df/signal")
check("wings level -> negligible belly-antenna loss",
      xp.read("cap/df/airframe_shadowed") == 0 and
      xp.read("cap/df/airframe_attenuation_db") < 1.0,
      "loss %.1f dB" % xp.read("cap/df/airframe_attenuation_db"))

# Positive phi is a right bank. With the beacon on the right, the lowered wing
# lies between a belly antenna and the beacon.
xp.SIM["phi"] = 35.0
clock.advance(mod.LOOP_S)
e.compute()
null_signal = xp.read("cap/df/signal")
check("lowered wing toward beacon -> deep null",
      xp.read("cap/df/airframe_shadowed") == 1 and
      xp.read("cap/df/airframe_attenuation_db") > 20.0 and
      null_signal < level_signal * 0.02,
      "loss %.1f dB, signal %.3f" %
      (xp.read("cap/df/airframe_attenuation_db"), null_signal))
check("null closes instantaneous audio but keeps TIMEHOLD bearing",
      xp.read("cap/df/rx_open") == 0 and xp.read("cap/df/valid") == 1)
check("airframe shadow does not masquerade as terrain masking",
      xp.read("cap/df/blocked") == 0)

# Both causes can exist together and must still be diagnosable independently.
xp.TERRAIN_FT = 20000.0
e.scn["effects"]["terrain_masking"] = True
e.compute()
check("terrain mask and airframe shadow remain separate",
      xp.read("cap/df/blocked") == 1 and
      xp.read("cap/df/airframe_shadowed") == 1)
xp.TERRAIN_FT = 0.0
e.scn["effects"]["terrain_masking"] = False

xp.SIM["phi"] = -35.0
settle(e)
check("opposite bank restores reception",
      xp.read("cap/df/airframe_shadowed") == 0 and
      xp.read("cap/df/rx_open") == 1 and xp.read("cap/df/signal") > 0.9)

# Mirror the setup: beacon abeam left and left wing down.
xp.SIM["psi"] = 270.0
xp.SIM["phi"] = -35.0
settle(e)
check("left and right wing-null cases are symmetric",
      xp.read("cap/df/airframe_attenuation_db") > 20.0)

# A top antenna reverses which bank places the airframe in the ray.
top_effects = dict(shadow_effects, df_antenna_profile="c182_top")
e = new_engine(beacon_hz=121_500_000, band=121.5, effects=top_effects)
xp.SIM.update({"psi": 90.0, "phi": 35.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
top_right_loss = xp.read("cap/df/airframe_attenuation_db")
xp.SIM["phi"] = -35.0
settle(e)
top_left_loss = xp.read("cap/df/airframe_attenuation_db")
check("top antenna reverses the null direction",
      top_right_loss < 1.0 and top_left_loss > 10.0,
      "right bank %.1f dB, left bank %.1f dB" %
      (top_right_loss, top_left_loss))

# Loss is applied to the unsaturated field strength. At very close range a
# powerful signal can therefore penetrate a partial/deep shadow.
e = new_engine(beacon_lat=39.0, beacon_lon=-105.0, beacon_ft=9000.0,
               beacon_hz=121_500_000, band=121.5, effects=shadow_effects)
xp.SIM.update({"lat": 39.0 + 0.00833, "elev_m": 9000.0 / 3.28084,
               "psi": 90.0, "phi": 35.0, "theta": 0.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
check("strong close signal remains receivable through shielding",
      xp.read("cap/df/airframe_shadowed") == 1 and
      xp.read("cap/df/rx_open") == 1,
      "signal %.2f" % xp.read("cap/df/signal"))

# The feature flag must preserve legacy propagation exactly.
e = new_engine(beacon_hz=121_500_000, band=121.5,
               effects={"terrain_masking": False, "airframe_shadowing": False})
xp.SIM.update({"psi": 90.0, "phi": 35.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
check("disabled shadowing preserves legacy signal",
      xp.read("cap/df/airframe_shadowed") == 0 and
      xp.read("cap/df/airframe_attenuation_db") == 0.0 and
      xp.read("cap/df/signal") > 0.9)

print("\n== timehold across the 406 burst gap ==")
e = new_engine(beacon_hz=406_025_000)
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 406_025_000)
xp.write("cap/df/timehold_sec", 10.0)
settle_burst(e, 8)
check("burst -> valid", bool(xp.read("cap/df/valid")))
check("burst -> instantaneous receiver open", bool(xp.read("cap/df/rx_open")))
force_burst(e, False)
e.compute()
check("between bursts, inside timehold -> held", bool(xp.read("cap/df/valid")))
check("between bursts -> receiver closed despite held bearing",
      not bool(xp.read("cap/df/rx_open")))
e.held = (e.held[0] - 11.0, e.held[1], e.held[2])   # age it past timehold
e.compute()
check("between bursts, past timehold -> dropped", not bool(xp.read("cap/df/valid")))

print("\n== COSPAS/SARSAT decode ==")
e = new_engine(beacon_hz=406_025_000,
               cs={"hex15": "ADCC0123456789A", "country": 366, "protocol": 2,
                   "has_position": True, "lat": 39.0, "lon": -105.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 406_025_000)
settle_burst(e, 8)
check("burst decodes -> SYNC OK", xp.read("cap/df/cs_sync") == 1)
check("ident comes through the byte array",
      xp.read("cap/df/cs_hex15") == "ADCC0123456789A", xp.read("cap/df/cs_hex15"))
check("country", xp.read("cap/df/cs_country") == 366)
check("position present", xp.read("cap/df/cs_has_position") == 1)

# Training mode flags the frame as the TEST variant, which the panels render.
xp.write("cap/df/mode", mod.MODE_TRAINING)
settle(e, 4)
check("training mode -> TEST protocol variant", xp.read("cap/df/cs_protocol") == 6,
      "protocol=%d" % xp.read("cap/df/cs_protocol"))

# No cs block from the console: ident is synthesised, position stays absent.
e = new_engine(beacon_hz=406_025_000)
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 406_025_000)
settle_burst(e, 8)
ident = xp.read("cap/df/cs_hex15")
check("no console cs block -> 15-hex ident synthesised",
      len(ident) == 15 and all(c in "0123456789ABCDEF" for c in ident), ident)
check("no console cs block -> no position claimed",
      xp.read("cap/df/cs_has_position") == 0)

print("\n== no panel attached: the old behaviour is unchanged ==")
e = new_engine(band=121.5, beacon_hz=None)
settle(e)
check("console picks the band, receiver assumed tuned", bool(xp.read("cap/df/valid")))
check("cap/df/band still reports the console band", abs(xp.read("cap/df/band") - 121.5) < 0.01)

print("\n== error code ==")
e = new_engine(effects={"error_code": 6})
check("instructor-injected E6 reaches the panel", xp.read("cap/df/error_code") == 6)
e = new_engine()
check("no fault -> -1, so E0 stays reachable", xp.read("cap/df/error_code") == -1)

print("\n== spread reports bearing quality ==")
# Close in: strong signal, tight scatter.
e = new_engine(beacon_hz=121_500_000, band=121.5)
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
tight = xp.read("cap/df/spread")

# Further out: the signal is weaker, still above squelch, and the un-averaged
# bearings scatter. This is the figure an operator reads to decide whether to
# trust the needle at all. ~8.5 NM puts the signal near 0.35.
e = new_engine(beacon_hz=121_500_000, band=121.5,
               effects={"terrain_masking": False})
xp.SIM.update({"lat": 39.0 + 0.141, "lon": -105.0, "elev_m": 25000.0 / 3.28084, "psi": 180.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
loose = xp.read("cap/df/spread")
check("weak signal scatters more than a strong one", loose > tight,
      "signal %.2f spread %.1f deg vs signal 1.00 spread %.1f deg"
      % (xp.read("cap/df/signal"), loose, tight))

print("\n== scan mode (517 3.3.3) ==")
# Beacon on 121.500 while the head sits on a 406 channel, scanning. The sweep
# should find the continuous signal and stay on it.
e = new_engine(beacon_hz=121_500_000, band=121.5)
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_517)
xp.write("cap/df/active_freq_hz", 406_025_000)
xp.write("cap/df/scan_enable", 0)
settle(e, 20)
check("not scanning, parked on 406 -> misses a 121.5 beacon",
      not bool(xp.read("cap/df/valid")))
xp.write("cap/df/scan_enable", 1)
settle(e, 80)
check("scanning -> finds it and holds", bool(xp.read("cap/df/valid")),
      "holding %.3f MHz" % xp.read("cap/df/band"))
check("cap/df/band reports the frequency actually being listened to",
      abs(xp.read("cap/df/band") - 121.5) < 0.01)

print("\n== Becker Emergency vs Training coverage ==")
# The Becker's technical data gives Emergency mode a single COSPAS/SARSAT
# channel and Training mode a freely adjustable 400.000-409.975 MHz receiver.
for mode, name, expect in ((mod.MODE_EMERGENCY, "Emergency", False),
                           (mod.MODE_TRAINING, "Training", True)):
    e = new_engine(beacon_hz=406_037_000)
    xp.write("cap/df/power", 1)
    xp.write("cap/df/head_type", mod.HEAD_517)
    xp.write("cap/df/mode", mode)
    xp.write("cap/df/active_freq_hz", 406_037_000)
    settle_burst(e)
    got = bool(xp.read("cap/df/valid"))
    check("Becker %-9s tuned to 406.037 -> %s"
          % (name, "hears it" if expect else "cannot tune there"),
          got == expect, "valid=%d" % got)

e = new_engine(beacon_hz=406_037_000)
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_517)
xp.write("cap/df/mode", mod.MODE_EMERGENCY)
xp.write("cap/df/active_freq_hz", 406_025_000)     # its only emergency channel
settle_burst(e)
check("Becker on its one emergency channel still misses a 406.037 beacon",
      not bool(xp.read("cap/df/valid")))
check("Becker emergency C/S set is the single channel the manual lists",
      mod.BECKER_406_CHANNELS_HZ == (406_025_000,),
      str(mod.BECKER_406_CHANNELS_HZ))

print("\n== RT-600 CPSAR groups ==")
check("the C/S grid is 19 channels, A through S",
      mod.CS_CHANNEL_COUNT == 19, str(mod.CS_CHANNEL_COUNT))

# CPSAR2 "031-037" covers channels D, E and F at once: centre 406.034, half-span
# 3 kHz. One selection has to hear a beacon on any of the three.
GROUP_CENTRE, GROUP_SPAN = 406_034_000, 3_000
for beacon in (406_031_000, 406_034_000, 406_037_000):
    e = new_engine(beacon_hz=beacon)
    xp.write("cap/df/power", 1)
    xp.write("cap/df/head_type", mod.HEAD_RT600)
    xp.write("cap/df/active_freq_hz", GROUP_CENTRE)
    xp.write("cap/df/rx_span_hz", GROUP_SPAN)
    settle_burst(e)
    check("CPSAR2 hears a beacon on %.3f" % (beacon / 1e6),
          bool(xp.read("cap/df/valid")))

# ... and must not hear one in the next group up.
e = new_engine(beacon_hz=406_043_000)
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", GROUP_CENTRE)
xp.write("cap/df/rx_span_hz", GROUP_SPAN)
settle_burst(e)
check("CPSAR2 does not reach into the next group", not bool(xp.read("cap/df/valid")))

print("\n== scan sweeps the pair the panel names ==")
# In Training mode the continuous frequencies are the crew's training channels,
# so the engine has to be told rather than assuming 121.500 / 243.000.
e = new_engine(beacon_hz=121_600_000, band=121.5)
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_517)
xp.write("cap/df/mode", mod.MODE_TRAINING)
xp.write("cap/df/active_freq_hz", 406_037_000)
xp.write("cap/df/scan_enable", 1)
xp.write("cap/df/scan_alt1_hz", 121_600_000)      # the training VHF channel
xp.write("cap/df/scan_alt2_hz", 243_100_000)
settle(e, 80)
check("training scan finds a beacon on the training VHF channel",
      bool(xp.read("cap/df/valid")), "holding %.3f MHz" % xp.read("cap/df/band"))

print("\n" + ("ALL PASS" if not FAILED else "FAILURES: " + ", ".join(FAILED)))
sys.exit(1 if FAILED else 0)
