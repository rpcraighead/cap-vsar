#!/usr/bin/env python3
"""Card H0 - control and trim confidence, 100 KIAS clean.

Establishes level flight, then applies small single-axis inputs one at a time,
returning to the reference condition between each, and records a phase-tagged
trace. Simulator engineering validation only.

Per the card: smallest useful input first, magnitude and duration recorded, one
axis at a time, checking control sign, response delay and persistent asymmetry.
Progression stops for reversed response, divergent motion or persistent saturation.

The aircraft must already be airborne and inside the exercise envelope. The
backend's own envelope watchdog runs throughout and neutralizes on a violation
independently of this script.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from services.ai_pilot.direct_backend import Gains, TestInput, XPlaneDirectBackend  # noqa: E402
from services.ai_pilot.maneuvers import Limits  # noqa: E402
from services.ai_pilot.xplane_udp import XPlaneUDPClient  # noqa: E402

TRACE_DIR = Path.home() / ".cache" / "capvsar" / "flight-tests"

EXTRA = {
    "pitch_deg": "sim/flightmodel/position/theta",
    "alpha_deg": "sim/flightmodel/position/alpha",
    "beta_deg": "sim/flightmodel/position/beta",
    "g_normal": "sim/flightmodel/forces/g_nrml",
    "roll_rate": "sim/flightmodel/position/P",
    "pitch_rate": "sim/flightmodel/position/Q",
    "yaw_rate": "sim/flightmodel/position/R",
    "elev_deg": "sim/flightmodel2/wing/elevator1_deg[8]",
    "ail_L_deg": "sim/flightmodel2/wing/aileron1_deg[2]",
    "rud_deg": "sim/flightmodel2/wing/rudder1_deg[10]",
    "slip_deg": "sim/cockpit2/gauges/indicators/slip_deg",
    "weight_kg": "sim/flightmodel/weight/m_total",
    "cg_offset_z": "sim/flightmodel2/misc/cg_offset_z",
}

# Reference condition tolerance. A point entered outside this is recorded as
# not attributable to the reference, not quietly averaged in with the rest.
TOLERANCE = {"kias": 2.0, "alt_ft": 60.0, "vs_fpm": 120.0, "bank_deg": 2.0}
STEADY_SECONDS = 4.0     # the condition must HOLD, not merely be passed through

# Smallest useful first, both directions, one axis at a time.
SEQUENCE = [
    ("pitch", +0.05), ("pitch", -0.05),
    ("pitch", +0.10), ("pitch", -0.10),
    ("roll", +0.05), ("roll", -0.05),
    ("roll", +0.10), ("roll", -0.10),
    ("yaw", +0.05), ("yaw", -0.05),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="1")
    parser.add_argument("--kias", type=float, default=100.0)
    parser.add_argument("--input-seconds", type=float, default=4.0)
    parser.add_argument("--ramp-seconds", type=float, default=1.0)
    parser.add_argument("--settle-seconds", type=float, default=7.0,
                        help="minimum hold after an input before re-checking the reference")
    parser.add_argument("--stabilize-timeout", type=float, default=120.0)
    parser.add_argument("--restabilize-timeout", type=float, default=45.0)
    parser.add_argument("--force", action="store_true",
                        help="fly the sequence even if the reference condition is never met")
    parser.add_argument("--hz", type=int, default=20)
    parser.add_argument("--receive-port", type=int, default=49410)
    args = parser.parse_args()

    client = XPlaneUDPClient(host="127.0.0.1", port=49000,
                             receive_port=args.receive_port, timeout=1.0)
    limits = Limits()
    backend = XPlaneDirectBackend(client, limits=limits, target_kias=args.kias)
    for ref in EXTRA.values():
        client.subscribe_dref(ref, freq_hz=args.hz)
    time.sleep(2.5)

    observation = backend.observe()
    if not (limits.min_kias <= observation.kias <= limits.max_kias
            and observation.agl_ft >= limits.min_agl_ft
            and limits.min_altitude_ft <= observation.altitude_indicated_ft <= limits.max_altitude_ft):
        print("outside the exercise envelope: %.0f KIAS, %.0f ft, %.0f AGL"
              % (observation.kias, observation.altitude_indicated_ft, observation.agl_ft))
        client.stop()
        return 2

    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    path = TRACE_DIR / ("H0_run%s_%s.jsonl" % (args.run, time.strftime("%Y%m%d-%H%M%S")))
    trace = path.open("w")
    trace.write(json.dumps({
        "record": "header", "card": "H0", "run": args.run,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reference_kias": args.kias,
        "input_seconds": args.input_seconds, "ramp_seconds": args.ramp_seconds,
        "settle_seconds": args.settle_seconds,
        "coordination": "beta feedback + adverse-yaw feedforward",
        "reference_tolerance": TOLERANCE, "steady_seconds": STEADY_SECONDS,
        "sequence": [{"axis": a, "magnitude": m} for a, m in SEQUENCE],
        "gains": {k: getattr(Gains, k) for k in dir(Gains) if k.isupper()},
        "entry": {"kias": observation.kias, "alt_ft": observation.altitude_indicated_ft,
                  "agl_ft": observation.agl_ft, "hdg": observation.heading_mag},
    }) + "\n")

    heading = observation.heading_mag
    altitude = observation.altitude_indicated_ft
    print("reference: %.0f KIAS, %.0f ft, hdg %.0f\n" % (args.kias, altitude, heading))

    def sample(phase, axis=None, magnitude=None):
        cached = client.get_all_cached()
        o = backend.observe()
        trace.write(json.dumps({
            "record": "sample", "t": round(time.time(), 4), "phase": phase,
            "input_axis": axis, "input_magnitude": magnitude,
            "kias": o.kias, "alt_ft": o.altitude_indicated_ft, "agl_ft": o.agl_ft,
            "hdg": o.heading_mag, "bank_deg": o.roll_deg, "vs_fpm": o.vvi_fpm,
            **{k: cached.get(r) for k, r in EXTRA.items()},
            "commands": backend.last_commands,
        }) + "\n")
        trace.flush()

    def hold(phase, seconds, axis=None, magnitude=None):
        end = time.time() + seconds
        while time.time() < end:
            sample(phase, axis, magnitude)
            time.sleep(1.0 / args.hz)

    def deviation(o):
        """How far the aircraft is from the reference condition, per criterion."""
        return {
            "kias": abs(o.kias - args.kias),
            "alt_ft": abs(o.altitude_indicated_ft - altitude),
            "vs_fpm": abs(o.vvi_fpm),
            "bank_deg": abs(o.roll_deg),
        }

    def on_condition(o):
        d = deviation(o)
        return (d["kias"] <= TOLERANCE["kias"] and d["alt_ft"] <= TOLERANCE["alt_ft"]
                and d["vs_fpm"] <= TOLERANCE["vs_fpm"]
                and d["bank_deg"] <= TOLERANCE["bank_deg"])

    def stabilize(phase, timeout, minimum=0.0, axis=None, magnitude=None):
        """Hold until the reference condition is met and STAYS met.

        A test point is only a test point if it starts from a known condition.
        Card H0 run 3 was flown after a fixed 15-second wait, during which the
        aircraft was still decelerating through the target from a 22-knot
        entry offset; it reached the first input at 94 KIAS in a 274 fpm
        descent against a 100 KIAS level reference, so none of that run's
        responses are attributable to the intended condition. Waiting on a
        criterion instead of a clock is the whole difference.

        Returns (stabilized, observation, seconds_taken).
        """
        start = time.time()
        floor = start + minimum
        steady_since = None
        while True:
            sample(phase, axis, magnitude)
            now = time.time()
            o = backend.observe()
            if on_condition(o):
                if steady_since is None:
                    steady_since = now
                if now - steady_since >= STEADY_SECONDS and now >= floor:
                    return True, o, now - start
            else:
                steady_since = None
            if now - start >= timeout:
                return False, o, now - start
            if backend.last_fault:
                return False, o, now - start
            time.sleep(1.0 / args.hz)

    def report_deviation(o):
        d = deviation(o)
        return "  ".join(
            "%s %.1f%s" % (k, v, "" if abs(v) < TOLERANCE[k] else " OUT")
            for k, v in d.items())

    try:
        backend.select(heading, altitude)
        print("stabilizing on the reference condition ...")
        print("  tolerance: %s" % ", ".join("%s +/-%g" % (k, v)
                                            for k, v in TOLERANCE.items()))
        stabilized, o, took = stabilize("stabilize", args.stabilize_timeout)
        print("  after %.0f s: %.1f KIAS  %.0f ft  bank %+.1f  vs %+.0f"
              % (took, o.kias, o.altitude_indicated_ft, o.roll_deg, o.vvi_fpm))
        trace.write(json.dumps({"record": "reference", "stabilized": stabilized,
                                "seconds": round(took, 1),
                                "deviation": deviation(o)}) + "\n")
        if not stabilized:
            print("  NOT STABILIZED: %s" % report_deviation(o))
            if not args.force:
                print("\nRefusing to fly the card off an unstabilized reference.\n"
                      "Responses taken from here are not attributable to a test\n"
                      "point. Re-enter closer to %.0f KIAS level, or pass --force\n"
                      "to record the run explicitly as invalid." % args.kias)
                return 3
            print("  --force: continuing. THIS RUN IS NOT A VALID TEST POINT.")
        else:
            print("  stabilized.")
        print()

        invalid = []
        for axis, magnitude in SEQUENCE:
            if backend.last_fault:
                print("backend fault: %s - stopping" % backend.last_fault)
                break
            before = backend.observe()
            backend.apply_test_input(
                TestInput(axis, magnitude, args.input_seconds, ramp_s=args.ramp_seconds))
            hold("input", args.input_seconds, axis, magnitude)
            after = backend.observe()
            ok, settled, took = stabilize(
                "recover", args.restabilize_timeout,
                minimum=args.settle_seconds, axis=axis, magnitude=magnitude)
            trace.write(json.dumps({
                "record": "point", "axis": axis, "magnitude": magnitude,
                "entry": {"kias": before.kias, "alt_ft": before.altitude_indicated_ft,
                          "bank_deg": before.roll_deg, "vs_fpm": before.vvi_fpm},
                "entry_on_condition": on_condition(before),
                "peak": {"bank_deg": after.roll_deg, "vs_fpm": after.vvi_fpm},
                "recovered": ok, "recovery_seconds": round(took, 1),
            }) + "\n")
            if not on_condition(before):
                invalid.append("%s %+.2f (entered off-condition)" % (axis, magnitude))
            print("  %-5s %+.2f  ->  bank %+6.1f -> %+6.1f   vs %+6.0f   "
                  "recovered in %4.0f s%s"
                  % (axis, magnitude, before.roll_deg, after.roll_deg,
                     after.vvi_fpm, took, "" if ok else "   NOT RECOVERED"))
        print("\nsequence complete")
        if invalid:
            print("\nPoints NOT attributable to the reference condition:")
            for entry in invalid:
                print("  " + entry)
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        backend.release()
        time.sleep(0.5)
        for ref in EXTRA.values():
            try:
                client.unsubscribe_dref(ref)
            except Exception:
                pass
        client.stop()
        trace.write(json.dumps({"record": "end",
                                "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
        trace.close()
        print("controls released; you have the aircraft")
        print("trace: %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
