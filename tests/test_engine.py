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
import math
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xp  # the stub

# The argv override is for running this file directly against another plugin
# copy. Under pytest, argv holds pytest's own flags, so only honour it as a
# script.
_OVERRIDE = sys.argv[1] if (__name__ == "__main__" and len(sys.argv) > 1) else None
PLUGIN = _OVERRIDE or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "xplane", "PI_capvsar_df.py"))
if not os.path.exists(PLUGIN):
    if __name__ == "__main__":
        sys.exit("engine plugin not found: %s" % PLUGIN)
    # SystemExit during import aborts collection for the entire run; a normal
    # exception fails just this module.
    raise FileNotFoundError("engine plugin not found: %s" % PLUGIN)
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

# The engine adds Gaussian scatter to every un-averaged bearing, so an
# unseeded run makes any tight bearing assertion a coin toss that usually
# lands. Seed it: the noise is still exercised, the same way every run.
mod.random.seed(20260910)

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
mid_spread = xp.read("cap/df/spread")
check("spread is published", 0.0 <= mid_spread < 30.0, "spread=%.1f" % mid_spread)

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

# Genuinely strong signal: 1 NM out, outside the cone of confusion. 5 NM on a
# 0.1 W ELT is mid-scale since P-13 recalibrated the bar, so it is no longer
# the geometry to test "strong" against. spread is peak to peak (P-10), so it
# is the full width of the hollow-marker band the faceplates draw at
# bearing +/- spread/2, not a one-sided deviation. Deliberately last in this
# section: new_engine() re-registers the datarefs, so anything reading through
# xp.read() after this point sees this engine, not the one above.
strong = new_engine(beacon_hz=121_500_000, band=121.5,
                    effects={"terrain_masking": False})
xp.SIM.update({"lat": 39.0 + 0.0167, "lon": -105.0,
               "elev_m": 12000.0 / 3.28084, "psi": 180.0,
               "phi": 0.0, "theta": 0.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(strong)
check("spread is tight on a strong signal", xp.read("cap/df/spread") < 3.0,
      "spread=%.2f deg at signal %.2f"
      % (xp.read("cap/df/spread"), xp.read("cap/df/signal")))
check("...and wider at mid scale", mid_spread > xp.read("cap/df/spread"),
      "%.1f deg vs %.2f deg" % (mid_spread, xp.read("cap/df/spread")))

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
      xp.read("cap/df/rx_open") == 1 and
      abs(xp.read("cap/df/signal") - level_signal) < 0.01,
      "signal %.2f back to the wings-level %.2f"
      % (xp.read("cap/df/signal"), level_signal))

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
# P-13 recalibrated the bar onto a link budget, so 5 NM on a 0.1 W 121.5 ELT
# is about half scale rather than pegged. What this test is for is that the
# effect switch costs nothing when it is off: no flag, no dB, and the same
# signal the unshadowed link budget gives.
check("disabled shadowing costs nothing",
      xp.read("cap/df/airframe_shadowed") == 0 and
      xp.read("cap/df/airframe_attenuation_db") == 0.0 and
      abs(xp.read("cap/df/signal") - level_signal) < 0.01,
      "signal %.2f" % xp.read("cap/df/signal"))

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
check("weak signal scatters more than a strong one", loose > tight + 1.0,
      "signal %.2f spread %.1f deg vs the close-in %.1f deg"
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

print("\n== terrain masking: line-of-sight ray geometry (P-1) ==")
# Test geometry: aircraft at 6000 ft MSL, beacon on the ground at 1000 ft MSL.
# Horizontal distance ~6.0 NM (lat 39.1 to 39.0).
# Ridge band elevation is 5000 ft MSL (base elevation is 1000 ft MSL).
# LOS_SAMPLES is 24, so probes sample at fr = k/24 for k = 1..23.
ac_lat, ac_lon, ac_alt_ft = 39.1, -105.0, 6000.0
b_lat, b_lon, b_alt_ft = 39.0, -105.0, 1000.0


def make_ridge_fn(fr_min, fr_max, ridge_ft=5000.0, base_ft=1000.0):
    def terrain(lat, lon):
        fr = (ac_lat - lat) / (ac_lat - b_lat)
        if fr_min <= fr <= fr_max:
            return ridge_ft
        return base_ft
    return terrain


# (a) Ridge near the beacon (fr 0.80..0.95):
# Probes land at fr = 20/24 (~0.833), 21/24 (0.875), 22/24 (~0.917).
# Correct ray is 1417..1833 ft, so the 5000 ft ridge MUST block the signal.
# Mirrored buggy ray is 5167..5583 ft and falsely passes above the ridge.
e = new_engine(beacon_lat=b_lat, beacon_lon=b_lon, beacon_ft=b_alt_ft,
               band=121.5, beacon_hz=121_500_000,
               effects={"terrain_masking": True})
xp.SIM.update({"lat": ac_lat, "lon": ac_lon,
               "elev_m": ac_alt_ft / 3.28084, "psi": 180.0,
               "phi": 0.0, "theta": 0.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_517)
xp.write("cap/df/active_freq_hz", 121_500_000)

xp.TERRAIN_FN = make_ridge_fn(0.80, 0.95)
e.compute()
check("ridge near beacon (80-95 % of path) blocks low beacon",
      xp.read("cap/df/blocked") == 1,
      "blocked=%d" % xp.read("cap/df/blocked"))

# (b) Ridge near the aircraft (fr 0.05..0.20):
# Probes land at fr = 2/24 (~0.083), 3/24 (0.125), 4/24 (~0.167).
# Correct ray is 5167..5583 ft, so aircraft at 6000 ft clears the 5000 ft ridge.
# Mirrored buggy ray is 1417..1833 ft and falsely reports blocked.
xp.TERRAIN_FN = make_ridge_fn(0.05, 0.20)
e.compute()
check("ridge near aircraft (5-20 % of path) clears high aircraft",
      xp.read("cap/df/blocked") == 0,
      "blocked=%d" % xp.read("cap/df/blocked"))

xp.TERRAIN_FN = None

print("\n== 406 with scan on: TIMEHOLD across the scan step (P-3) ==")
# The 517's normal 406 posture is scan on: surveil the burst, listen to the
# continuous channels in the 50 s gap. Stepping away is the receiver doing its
# job, and TIMEHOLD is what carries the bearing across the gap - so a bearing
# must survive the step, not vanish the instant each 440 ms burst ends.
e = new_engine(beacon_hz=406_025_000, band=406.0,
               effects={"burst_cadence": True, "terrain_masking": False})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_517)
xp.write("cap/df/active_freq_hz", 406_025_000)
xp.write("cap/df/scan_enable", 1)
xp.write("cap/df/timehold_sec", 30.0)
force_burst(e, True)
settle_burst(e, 12)
check("406 burst acquired with scan enabled", bool(xp.read("cap/df/valid")))
held_bearing = xp.read("cap/df/bearing_rel")

force_burst(e, False)          # burst over; scan steps to a continuous channel
clock.advance(mod.LOOP_S)
e.compute()
check("scan steps off 406 between bursts",
      abs(xp.read("cap/df/band") - 406.025) > 0.01,
      "listening on %.3f MHz" % xp.read("cap/df/band"))
check("bearing is held while scan is stepped away",
      bool(xp.read("cap/df/valid")) and
      abs(mod.ang_diff(xp.read("cap/df/bearing_rel"), held_bearing)) < 1.0,
      "valid=%d bearing %.1f vs held %.1f"
      % (xp.read("cap/df/valid"), xp.read("cap/df/bearing_rel"), held_bearing))
check("audio does not follow the held bearing while stepped away",
      xp.read("cap/df/rx_open") == 0)

# Past TIMEHOLD it must still give up.
for _ in range(4):
    clock.advance(10.0)
    e.compute()
check("held bearing is dropped once TIMEHOLD expires",
      not bool(xp.read("cap/df/valid")))

# A head genuinely parked on the wrong channel still gets nothing held.
e = new_engine(beacon_hz=406_025_000, band=406.0,
               effects={"burst_cadence": True, "terrain_masking": False})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_517)
xp.write("cap/df/active_freq_hz", 406_025_000)
xp.write("cap/df/scan_enable", 1)
xp.write("cap/df/timehold_sec", 30.0)
force_burst(e, True)
settle_burst(e, 12)
xp.write("cap/df/active_freq_hz", 121_500_000)   # crew tunes away deliberately
xp.write("cap/df/scan_enable", 0)
clock.advance(mod.LOOP_S)
e.compute()
check("tuning away by hand drops the bearing rather than holding it",
      not bool(xp.read("cap/df/valid")))

print("\n== radio horizon has two ends (P-4) ==")
# Aircraft in a valley 500 ft BELOW a ridge-top beacon, 1 NM away. The old
# one-sided form used height above the beacon, so this collapsed to a zero-mile
# horizon and the set heard nothing at all.
e = new_engine(beacon_lat=39.0, beacon_lon=-105.0, beacon_ft=9000.0,
               beacon_hz=121_500_000, band=121.5,
               effects={"radio_horizon": True, "terrain_masking": False,
                        "burst_cadence": False})
xp.SIM.update({"lat": 39.0 + 0.0167, "lon": -105.0,      # ~1 NM north
               "elev_m": 8500.0 / 3.28084, "psi": 180.0,
               "phi": 0.0, "theta": 0.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_517)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e, 20)
check("aircraft below a ridge-top beacon at 1 NM still hears it",
      bool(xp.read("cap/df/valid")) and xp.read("cap/df/signal") > 0.0,
      "signal %.3f" % xp.read("cap/df/signal"))

# ...and the horizon still bites at long range.
xp.SIM.update({"lat": 39.0 + 6.0, "lon": -105.0,          # ~360 NM north
               "elev_m": 1000.0 / 3.28084})
settle(e, 20)
check("beyond the two-ended horizon it is still silent",
      not bool(xp.read("cap/df/valid")),
      "signal %.3f at %.0f NM" % (xp.read("cap/df/signal"), xp.read("cap/df/distance_nm")))

print("\n== per-station config: capvsar_station.ini (O-2) ==")
import tempfile
check("no ini on disk falls back to the historical single-station defaults",
      mod._load_station_config("/nonexistent/capvsar_station.ini") ==
      ("http://192.0.2.151:8700", "CAP-1", os.environ.get("CAPVSAR_TOKEN_PLUGIN", "")))

with tempfile.TemporaryDirectory() as d:
    ini = os.path.join(d, "capvsar_station.ini")
    with open(ini, "w") as f:
        f.write("[station]\nconsole = http://10.0.0.5:8700\ncallsign = CAP-3\nplugin_key = stationkey\n")
    console, callsign, key = mod._load_station_config(ini)
    check("console overridden by the ini", console == "http://10.0.0.5:8700", console)
    check("callsign overridden by the ini", callsign == "CAP-3", callsign)
    check("plugin_key read from the ini when no env var is set", key == "stationkey", key)

    with open(ini, "w") as f:
        f.write("[station]\ncallsign = CAP-3\n")
    console, callsign, key = mod._load_station_config(ini)
    check("an ini overriding only callsign leaves console at its default",
          console == "http://192.0.2.151:8700", console)
    check("...and leaves plugin_key at its default too", key == os.environ.get("CAPVSAR_TOKEN_PLUGIN", ""))

    old_env = os.environ.get("CAPVSAR_TOKEN_PLUGIN")
    os.environ["CAPVSAR_TOKEN_PLUGIN"] = "envkey"
    try:
        with open(ini, "w") as f:
            f.write("[station]\nplugin_key = inikey\n")
        _, _, key = mod._load_station_config(ini)
        check("CAPVSAR_TOKEN_PLUGIN env var wins over the ini's plugin_key", key == "envkey", key)
    finally:
        if old_env is None:
            del os.environ["CAPVSAR_TOKEN_PLUGIN"]
        else:
            os.environ["CAPVSAR_TOKEN_PLUGIN"] = old_env

print("\n== a 121.5 beacon carries no COSPAS-SARSAT frame (P-6) ==")
# An analog beacon has no identity in it at all. Decoding one showed SYNC OK
# and a 15-hex ident on the page, which teaches the crew the exact opposite of
# what the 406 half of the exercise exists to demonstrate.
e = new_engine(beacon_hz=121_500_000, band=121.5,
               effects={"terrain_masking": False, "cone_of_confusion": False})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
check("121.5 with a good bearing still shows no decode",
      bool(xp.read("cap/df/valid")) and xp.read("cap/df/cs_sync") == 0,
      "valid=%d cs_sync=%d" % (xp.read("cap/df/valid"), xp.read("cap/df/cs_sync")))

# ...including from inside the cone of confusion, which is the path that was
# actually wrong: the cone branch called decode_tick without the 406 gate.
e = new_engine(beacon_lat=39.0, beacon_lon=-105.0, beacon_ft=9000.0,
               beacon_hz=121_500_000, band=121.5,
               effects={"terrain_masking": False, "cone_of_confusion": True})
xp.SIM.update({"lat": 39.0 + 0.0004, "lon": -105.0,       # directly overhead
               "elev_m": 12000.0 / 3.28084, "psi": 0.0, "phi": 0.0, "theta": 0.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
check("overhead a 121.5 beacon: in the cone, and still no decode",
      xp.read("cap/df/in_cone") == 1 and xp.read("cap/df/cs_sync") == 0,
      "in_cone=%d cs_sync=%d" % (xp.read("cap/df/in_cone"), xp.read("cap/df/cs_sync")))

# The same geometry on 406 must still decode, or the gate is simply too tight.
e = new_engine(beacon_lat=39.0, beacon_lon=-105.0, beacon_ft=9000.0,
               beacon_hz=406_025_000, band=406.0,
               effects={"terrain_masking": False, "cone_of_confusion": True})
xp.SIM.update({"lat": 39.0 + 0.0004, "lon": -105.0,
               "elev_m": 12000.0 / 3.28084, "psi": 0.0, "phi": 0.0, "theta": 0.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 406_025_000)
force_burst(e, True)
settle_burst(e, 8)
check("406 in the cone of confusion still decodes its frame",
      xp.read("cap/df/in_cone") == 1 and xp.read("cap/df/cs_sync") == 1,
      "in_cone=%d cs_sync=%d" % (xp.read("cap/df/in_cone"), xp.read("cap/df/cs_sync")))

print("\n== the signal bar follows the 406 burst (P-7) ==")
# 406 radiates for 440 ms in every 50 s. The bar showed the continuous field
# strength, so it sat pegged for the 49.5 s the beacon was silent - and the
# squelch was deciding on a signal that was not being received.
e = new_engine(beacon_hz=406_025_000, band=406.0,
               effects={"burst_cadence": True, "terrain_masking": False})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 406_025_000)
xp.write("cap/df/timehold_sec", 30.0)
force_burst(e, True)
settle_burst(e, 8)
in_burst = xp.read("cap/df/signal")
check("signal is up during the burst", in_burst > 0.5, "signal %.2f" % in_burst)

force_burst(e, False)
clock.advance(mod.LOOP_S)
e.compute()
between = xp.read("cap/df/signal")
check("signal drops to the noise floor between bursts", between == 0.0,
      "signal %.2f" % between)
check("...while TIMEHOLD keeps the bearing on the display",
      bool(xp.read("cap/df/valid")) and xp.read("cap/df/rx_open") == 0)

# A 121.5 beacon is continuous, so its bar must not pulse.
e = new_engine(beacon_hz=121_500_000, band=121.5,
               effects={"burst_cadence": True, "terrain_masking": False})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
force_burst(e, False)
settle(e)
check("121.5 is continuous and its bar does not pulse",
      xp.read("cap/df/signal") > 0.1, "signal %.2f" % xp.read("cap/df/signal"))

print("\n== terrain masking is a real shadow (P-8) ==")
# The old -12 dB left a fully masked beacon at 2 NM reading 0.375 with a
# perfectly good bearing, so the masking the terrain probe exists to produce
# taught nothing at all inside about 4 NM.
def masked_engine(d_deg=0.0333, terrain_ft=20000.0, hz=121_500_000, band=121.5):
    eng = new_engine(beacon_lat=39.0, beacon_lon=-105.0, beacon_ft=9000.0,
                     beacon_hz=hz, band=band,
                     effects={"terrain_masking": True, "radio_horizon": False,
                              "cone_of_confusion": False, "burst_cadence": False})
    xp.SIM.update({"lat": 39.0 + d_deg, "lon": -105.0,
                   "elev_m": 12000.0 / 3.28084, "psi": 180.0,
                   "phi": 0.0, "theta": 0.0})
    xp.write("cap/df/power", 1)
    xp.write("cap/df/head_type", mod.HEAD_RT600)
    xp.write("cap/df/active_freq_hz", hz)
    xp.TERRAIN_FT = terrain_ft
    settle(eng, 60)
    return eng

e = masked_engine()                     # ~2 NM, ridge far above the ray
check("a deeply masked beacon at 2 NM falls below squelch",
      xp.read("cap/df/blocked") == 1 and not bool(xp.read("cap/df/valid")),
      "blocked=%d signal %.3f" % (xp.read("cap/df/blocked"), xp.read("cap/df/signal")))
xp.TERRAIN_FT = 0.0

e = masked_engine(terrain_ft=0.0)       # same range, clear path
check("...and the same beacon on a clear path is loud",
      xp.read("cap/df/blocked") == 0 and xp.read("cap/df/signal") > 0.5,
      "signal %.2f" % xp.read("cap/df/signal"))

# Grazing the ridge is not the same as being behind it: the crew should hear a
# degraded signal, not silence, and the two cases must sound different.
graze = mod.terrain_loss_db(False, 400.0)
deep = mod.terrain_loss_db(True, -3000.0)
edge = mod.terrain_loss_db(True, -10.0)
check("diffraction loss grades with obstruction depth",
      0.0 < graze < mod.TERRAIN_MASK_LOSS_DB <= edge < deep <= mod.TERRAIN_MASK_LOSS_MAX_DB,
      "graze %.1f dB, just-blocked %.1f dB, deep %.1f dB" % (graze, edge, deep))
check("a wide-open path costs nothing", mod.terrain_loss_db(False, 5000.0) == 0.0)

print("\n== probe density and earth curvature (P-9) ==")
# 24 fixed probes is 1.25 NM apart at 30 NM, which steps straight over the kind
# of narrow ridge that actually masks a beacon.
check("short paths keep the historical 24 probes",
      e.los_sample_count(2.0) == 24 and e.los_sample_count(6.0) == 24,
      "2 NM -> %d, 6 NM -> %d" % (e.los_sample_count(2.0), e.los_sample_count(6.0)))
check("a long path is sampled far more finely than 24",
      e.los_sample_count(25.0) == mod.LOS_SAMPLES_MAX,
      "25 NM -> %d probes" % e.los_sample_count(25.0))
check("the probe count is bounded",
      e.los_sample_count(300.0) == mod.LOS_SAMPLES_MAX)

# A ridge 0.5 NM wide at 25 NM, sitting between two of the old fixed probes
# (fr 6/24 = 0.2500 and 7/24 = 0.2917) and caught by the new spacing.
ac_lat25, b_lat25 = 39.0 + 0.4167, 39.0


def narrow_ridge(lat, lon):
    fr = (ac_lat25 - lat) / (ac_lat25 - b_lat25)
    return 14000.0 if 0.260 <= fr <= 0.280 else 1000.0


e = new_engine(beacon_lat=b_lat25, beacon_lon=-105.0, beacon_ft=1000.0,
               beacon_hz=121_500_000, band=121.5,
               effects={"terrain_masking": True, "radio_horizon": False,
                        "cone_of_confusion": False})
xp.SIM.update({"lat": ac_lat25, "lon": -105.0, "elev_m": 12000.0 / 3.28084,
               "psi": 180.0, "phi": 0.0, "theta": 0.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
xp.TERRAIN_FN = narrow_ridge
e.compute()
check("a narrow ridge at 25 NM blocks", xp.read("cap/df/blocked") == 1,
      "blocked=%d at %.1f NM" % (xp.read("cap/df/blocked"), xp.read("cap/df/distance_nm")))
# The same ridge is missed at the old fixed spacing, which is the whole point.
missed = [k for k in range(1, 24) if 0.260 <= k / 24.0 <= 0.280]
check("...and the old fixed 24 probes would have stepped over it", not missed,
      "old probes inside the ridge: %r" % missed)
xp.TERRAIN_FN = None

# The straight ray sits above the curved earth, by about 150 ft at mid-path
# over 30 NM. Ignoring it handed every long path a free ridge's worth of
# clearance.
mid = e.earth_bulge_ft(30.0, 0.5)
check("mid-path earth bulge over 30 NM is about 150 ft", 130.0 < mid < 170.0,
      "%.0f ft" % mid)
check("the bulge vanishes at both ends",
      e.earth_bulge_ft(30.0, 0.0) == 0.0 and e.earth_bulge_ft(30.0, 1.0) < 1e-9)
check("a short path is barely affected", e.earth_bulge_ft(2.0, 0.5) < 1.0,
      "%.2f ft at 2 NM" % e.earth_bulge_ft(2.0, 0.5))

print("\n== reporting cadence, heading source and null handling (P-12) ==")
check("the report loop ticks faster than either deadline it serves",
      mod.NET_TICK_S < mod.REPORT_S and mod.NET_TICK_S < mod.POLL_S,
      "tick %.2f s, report %.1f s, poll %.1f s"
      % (mod.NET_TICK_S, mod.REPORT_S, mod.POLL_S))

e = new_engine()
check("no position is reported before the flight loop has run once",
      e.pos_seen is False)
e.compute()
check("...and one is once it has", e.pos_seen is True)

# psi is the local OpenGL-frame heading and diverges from true north away from
# the scenery origin; true_psi is true heading. The bearing the needle shows is
# computed against it, so the wrong one is a silent, position-dependent error.
e = new_engine(beacon_hz=121_500_000, band=121.5,
               effects={"terrain_masking": False, "cone_of_confusion": False})
xp.SIM.update({"psi": 150.0, "true_psi": 180.0})
xp.write("cap/df/power", 1)
xp.write("cap/df/head_type", mod.HEAD_RT600)
xp.write("cap/df/active_freq_hz", 121_500_000)
settle(e)
# psi and true_psi are set 30 deg apart, so the two possible answers are ~0
# (true_psi, correct) and ~30 (psi, the bug). 10 deg separates them cleanly
# without pretending the bearing is noise-free at this range.
check("relative bearing is taken from true heading, not the OpenGL frame",
      abs(mod.ang_diff(xp.read("cap/df/bearing_rel"), 0.0)) < 10.0,
      "bearing_rel %.1f (about 30 would mean psi was used)"
      % xp.read("cap/df/bearing_rel"))
del xp.SIM["true_psi"]

check("a null scenario value coerces instead of raising",
      mod.as_float(None) == 0.0 and mod.as_float(None, 121.5) == 121.5
      and mod.as_float("406.0") == 406.0 and mod.as_float("", 1.0) == 1.0)
e = new_engine()
e.scn["elev_ft"] = mod.as_float(None)
check("...so the elevation dataref still reads rather than dying",
      xp.read("cap/scenario/beacon_elev") == 0.0)

print("\n== link budget: the bands differ in range (P-13) ==")
# The old model saturated inside 5 NM on every band, so a 0.1 W 121.5 ELT and a
# 5 W 406 beacon differed only in cadence and decode - never in how far away
# the crew could hear them, which is the fact the fleet argument rests on.
def detection_range_nm(hz, target):
    lo, hi = 0.05, 600.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        prx = (mod.beacon_erp_dbm(hz) - mod.BEACON_GROUND_LOSS_DB
               - mod.free_space_loss_db(hz, mid))
        level = max(0.0, min(1.0, (prx - mod.RX_FLOOR_DBM) / mod.RX_SPAN_DB))
        if level > target:
            lo = mid
        else:
            hi = mid
    return lo


r121 = detection_range_nm(121_500_000, mod.SQUELCH_FLOOR)
r406 = detection_range_nm(406_025_000, mod.SQUELCH_FLOOR)
d406 = detection_range_nm(406_025_000, mod.DECODE_MIN_SIGNAL)
check("121.5 is heard to about 50 NM on a clear path", 40.0 < r121 < 60.0,
      "%.0f NM" % r121)
check("406 is heard roughly twice as far", 1.8 < r406 / r121 < 2.5,
      "406 %.0f NM vs 121.5 %.0f NM" % (r406, r121))
check("a 406 frame decodes well inside the range it is heard at",
      d406 < r406 * 0.6, "decode %.0f NM, bearing %.0f NM" % (d406, r406))
check("243.0 is the same power on a higher frequency, so it is heard less far",
      detection_range_nm(243_000_000, mod.SQUELCH_FLOOR) < r121)
check("the scenario power knob is dB, and 1.0 is the rated beacon",
      mod.power_ratio_db(1.0) == 0.0 and abs(mod.power_ratio_db(0.5) + 3.01) < 0.02)
check("a zero-power beacon is silent rather than a maths error",
      mod.power_ratio_db(0.0) == -math.inf)

# Multipath used to be a 40 deg step for 12 s in every 36, independent of
# terrain and range: crews learned its rhythm rather than its cause.
e = new_engine()
check("no multipath on a wide-open path",
      e.multipath_error_deg(5000.0, 39.0, -105.0, clock.now, 40.0) == 0.0)
check("...and none at all where the probe saw nothing",
      e.multipath_error_deg(None, 39.0, -105.0, clock.now, 40.0) == 0.0)
grazing = abs(e.multipath_error_deg(200.0, 39.0, -105.0, clock.now, 40.0))
blocked_mp = abs(e.multipath_error_deg(-100.0, 39.0, -105.0, clock.now, 40.0))
check("a blocked path reflects harder than a grazing one",
      blocked_mp > grazing > 0.0,
      "grazing %.1f deg, blocked %.1f deg" % (grazing, blocked_mp))
check("the error is bounded by the scenario's amplitude",
      blocked_mp <= 40.0, "%.1f deg" % blocked_mp)
moved = e.multipath_error_deg(-100.0, 39.05, -105.0, clock.now, 40.0)
check("the reflection moves with the aircraft rather than on a timer",
      abs(moved - e.multipath_error_deg(-100.0, 39.0, -105.0, clock.now, 40.0)) > 1.0,
      "%.1f deg vs %.1f deg half a mile away"
      % (moved, e.multipath_error_deg(-100.0, 39.0, -105.0, clock.now, 40.0)))

print("\n== the dataref contract matches the engine (P-10) ==")
# The contract is the interface every faceplate is written against, and it had
# drifted in six places. A doc fix alone would drift again, so this is the
# guard: everything the engine publishes, and every effect switch it reads,
# has to appear in DATAREF_CONTRACT.md.
import re

CONTRACT = os.path.join(os.path.dirname(HERE), "docs", "DATAREF_CONTRACT.md")
with open(CONTRACT, encoding="utf-8") as fh:
    contract = fh.read()
with open(PLUGIN, encoding="utf-8") as fh:
    source = fh.read()

published = set(re.findall(r'registerDataAccessor\(\s*"([^"]+)"', source))
published |= set(re.findall(r'^\s+[ifb]\("([^"]+)"', source, re.M))
# cs_lat and cs_lon share one row, written as `cap/df/cs_lat` / `cs_lon`, so
# that one name is allowed to appear in its short form. Everything else must
# appear in full - matching on the leaf name alone would let any dataref pass
# on a chance mention in the prose.
SHORT_FORM = {"cap/df/cs_lon": "`cs_lon`"}
undocumented = sorted(
    d for d in published
    if d not in contract and SHORT_FORM.get(d, "\0") not in contract)
check("every published dataref is in DATAREF_CONTRACT.md", not undocumented,
      "%d published, missing: %s" % (len(published), undocumented or "none"))

effects = set(re.findall(r'eff(?:ects)?\.get\("([a-z_0-9]+)"', source))
effects |= set(re.findall(r'^\s+"(df_antenna_location|wing_null_[a-z_]+)":', source, re.M))
effects |= {"beacon_has_gps", "error_code"}
missing_fx = sorted(k for k in effects
                    if ("effects." + k) not in contract
                    and ("`%s`" % k) not in contract
                    and not (k.startswith("wing_null_")
                             and ("..._" + k[len("wing_null_"):]) in contract))
check("every effect switch the engine reads is in the contract", not missing_fx,
      "%d effects, missing: %s" % (len(effects), missing_fx or "none"))

# The two claims the contract makes about values, not names.
check("the contract no longer calls cap/scenario/active read-only",
      "INT (read-only)" not in contract)
check("the contract describes spread as peak to peak",
      "peak to peak" in contract)

print("\n" + ("ALL PASS" if not FAILED else "FAILURES: " + ", ".join(FAILED)))


def test_engine_checks_pass():
    """The checks above run at import time; this reports them to pytest."""
    assert not FAILED, "FAILURES: " + ", ".join(FAILED)


if __name__ == "__main__":
    sys.exit(1 if FAILED else 0)
