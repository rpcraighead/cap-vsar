#!/usr/bin/env python3
"""Read-only flight-test telemetry capture for CAP 487.

Records the observable set required by `docs/C182T_HANDLING_TEST_MATRIX.md` and
`docs/C182T_FLIGHT_TEST_CARD.md` while a human pilot flies the test points, and
writes a JSONL trace plus a data-quality summary.

This script NEVER writes to the simulator. It sends RREF subscriptions and reads
the replies; it issues no DREF writes and no commands. Live aircraft control is
reserved for `services.ai_pilot.maneuver_server` and its serialized maneuver gate
per tracker items AI-1 and AI-2.

TWO RULES THIS TOOL ENFORCES, because both have already bitten this project:

1. **Every dataref name is validated against X-Plane's own DataRefs.txt before
   use.** X-Plane replies `0.0` to an unrecognised name, so an unvalidated name
   produces silent zeros that look exactly like measurements. Three such names
   were found during preparation
   (`flightmodel2/controls/{elevator,aileron,rudder}_ratio` do not exist).

2. **A channel that does not reply is recorded as `null`, never as 0.** Missing
   observables are UNMEASURED and must not be inferred. A genuine zero and an
   absent channel are different facts.

Usage:
    python3 scripts/capture_flight_test.py --card H1 --run 1 --seconds 120
    python3 scripts/capture_flight_test.py --card H6 --run 3 --seconds 300 --hz 20
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "services" / "ai_pilot"))

from xplane_udp import XPlaneUDPClient  # noqa: E402


DATAREFS_TXT = Path("/home/ron/X-Plane 12/Resources/plugins/DataRefs.txt")
TRACE_DIR = Path.home() / ".cache" / "capvsar" / "flight-tests"

# Grouped for the report; every name verified present in DataRefs.txt.
CHANNELS = {
    # --- airspeed / altitude ---
    "kias": "sim/flightmodel/position/indicated_airspeed",
    "ktas": "sim/flightmodel/position/true_airspeed",
    "alt_msl_ft": "sim/cockpit2/gauges/indicators/altitude_ft_pilot",
    "alt_press_m": "sim/flightmodel2/position/pressure_altitude",
    "agl_m": "sim/flightmodel/position/y_agl",
    "vs_fpm": "sim/flightmodel/position/vh_ind_fpm",
    # --- attitude and body rates ---
    "pitch_deg": "sim/flightmodel/position/theta",
    "bank_deg": "sim/flightmodel/position/phi",
    "hdg_mag": "sim/flightmodel/position/mag_psi",
    "roll_rate": "sim/flightmodel/position/P",
    "pitch_rate": "sim/flightmodel/position/Q",
    "yaw_rate": "sim/flightmodel/position/R",
    # --- aerodynamic state ---
    "alpha_deg": "sim/flightmodel/position/alpha",
    "beta_deg": "sim/flightmodel/position/beta",
    "slip_deg": "sim/cockpit2/gauges/indicators/slip_deg",
    "g_normal": "sim/flightmodel/forces/g_nrml",
    "stall_warn": "sim/cockpit2/annunciators/stall_warning",
    "stall_warn_ratio": "sim/cockpit2/annunciators/stall_warning_ratio",
    # --- powerplant ---
    "throttle": "sim/cockpit2/engine/actuators/throttle_ratio[0]",
    "manifold_inhg": "sim/cockpit2/engine/indicators/MPR_in_hg[0]",
    "rpm": "sim/cockpit2/engine/indicators/engine_speed_rpm[0]",
    "fuel_flow_kgs": "sim/cockpit2/engine/indicators/fuel_flow_kg_sec[0]",
    # --- configuration ---
    "flap_handle": "sim/cockpit2/controls/flap_ratio",
    "flap_actual": "sim/flightmodel2/controls/flap1_deploy_ratio",
    # --- commanded inputs (yoke ratios) ---
    "yoke_pitch": "sim/cockpit2/controls/yoke_pitch_ratio",
    "yoke_roll": "sim/cockpit2/controls/yoke_roll_ratio",
    "yoke_hdg": "sim/cockpit2/controls/yoke_heading_ratio",
    "elev_trim": "sim/cockpit2/controls/elevator_trim",
    # --- ACTUAL surface deflection, degrees ---
    # NOT flightmodel2/controls/*_ratio: those names do not exist.
    "elev_deg": "sim/flightmodel2/wing/elevator1_deg[8]",
    "ail_L_deg": "sim/flightmodel2/wing/aileron1_deg[2]",
    "ail_R_deg": "sim/flightmodel2/wing/aileron1_deg[3]",
    "rud_deg": "sim/flightmodel2/wing/rudder1_deg[10]",
    # --- mass and balance ---
    "weight_kg": "sim/flightmodel/weight/m_total",
    # m_fuel is float[9]; read bare it returns tank 0, which is empty on this
    # aircraft. The C182T's usable fuel is the two wing tanks.
    "fuel_L_kg": "sim/flightmodel/weight/m_fuel1",
    "fuel_R_kg": "sim/flightmodel/weight/m_fuel2",
    # cg_offset_z is the CURRENT CG including payload and fuel. The older
    # cgz_ref_to_default is ZFW CG - the CG with NO fuel - and X-Plane marks it
    # REPLACED. They differ by the fuel moment, which drifts as fuel burns, so
    # logging the deprecated one would record a number that wanders away from the
    # real CG during a run while still being labelled CG. Both are kept so the
    # difference stays visible in the trace.
    "cg_offset_z_m": "sim/flightmodel2/misc/cg_offset_z",
    "cg_zfw_ref_m": "sim/flightmodel/misc/cgz_ref_to_default",
    "payload_kg": "sim/flightmodel/weight/m_fixed",
    # --- atmosphere and sim state ---
    "oat_c": "sim/weather/aircraft/temperature_ambient_deg_c",
    "wind_kt": "sim/weather/aircraft/wind_speed_kts",
    "wind_dir_degt": "sim/weather/aircraft/wind_now_direction_degt",
    "baro_pas": "sim/weather/aircraft/barometer_current_pas",
    "sim_speed": "sim/time/sim_speed",
    "paused": "sim/time/paused",
}

# Channels that are expected to read exactly 0 in normal flight. Used only to
# keep the quality report readable; it never changes what is recorded.
LEGITIMATELY_ZERO = {"stall_warn", "stall_warn_ratio", "flap_handle", "flap_actual",
                     "paused", "yoke_pitch", "yoke_roll", "yoke_hdg",
                     # zero in calm air and while the sim is paused, respectively
                     "wind_kt", "wind_dir_degt", "sim_speed"}

LB_PER_KG = 2.2046226218
FT_PER_M = 3.280839895


def validate_names(channels: dict) -> tuple[dict, list]:
    """Drop any dataref X-Plane does not define, and say so loudly."""
    if not DATAREFS_TXT.exists():
        print("WARNING: %s not found; cannot validate dataref names." % DATAREFS_TXT)
        return channels, []
    known = set()
    for line in DATAREFS_TXT.read_text(errors="replace").splitlines():
        if line.startswith("sim/"):
            known.add(line.split()[0])
    good, bad = {}, []
    for name, ref in channels.items():
        base = ref.split("[")[0]
        if base in known:
            good[name] = ref
        else:
            bad.append((name, ref))
    return good, bad


def capture(args) -> Path:
    channels, invalid = validate_names(CHANNELS)
    if invalid:
        print("REFUSING these channels - name not in DataRefs.txt "
              "(X-Plane would reply 0.0 and it would look like data):")
        for name, ref in invalid:
            print("   %-22s %s" % (name, ref))
        print()

    client = XPlaneUDPClient(host=args.xp_host, port=args.xp_port,
                             receive_port=args.receive_port, timeout=1.0)
    samples: list[dict] = []
    try:
        for ref in channels.values():
            client.subscribe_dref(ref, freq_hz=args.hz)
        time.sleep(2.5)
        cached = client.get_all_cached()
        if not cached:
            raise SystemExit(
                "no dataref replies on port %d.\n"
                "Check X-Plane is running with UDP enabled and that only ONE copy is\n"
                "running - a second instance fails RakNet init and never binds the port.\n"
                "Verify with: pgrep -f 'X-Plane 12/X-Plane-x86_64'" % args.xp_port
            )
        silent = [n for n, r in channels.items() if r not in cached]
        if silent:
            print("channels valid but not replying (recorded as null, NOT zero): %s\n"
                  % ", ".join(silent))

        print("capturing card %s run %s for %.0f s at %d Hz - fly the point now\n"
              % (args.card, args.run, args.seconds, args.hz))
        period = 1.0 / args.hz
        deadline = time.time() + args.seconds
        while time.time() < deadline:
            now = time.time()
            cached = client.get_all_cached()
            row = {"t": round(now, 4)}
            for name, ref in channels.items():
                # Absent key => no reply => UNMEASURED. Never coerced to 0.
                row[name] = cached.get(ref, None)
            samples.append(row)
            time.sleep(max(0.0, period - (time.time() - now)))
    finally:
        for ref in channels.values():
            try:
                client.unsubscribe_dref(ref)
            except Exception:
                pass
        time.sleep(0.3)
        client.stop()

    return write_trace(args, channels, invalid, samples)


def write_trace(args, channels, invalid, samples) -> Path:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = TRACE_DIR / ("%s_run%s_%s.jsonl" % (args.card, args.run, stamp))

    intervals = [round(b["t"] - a["t"], 4) for a, b in zip(samples, samples[1:])]
    nominal = 1.0 / args.hz
    gaps = [i for i, dt in enumerate(intervals) if dt > nominal * 2.0]

    with path.open("w") as handle:
        handle.write(json.dumps({
            "record": "header",
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "card": args.card,
            "run": args.run,
            "note": args.note,
            "control_mode": "manual pilot; capture is read-only",
            "requested_hz": args.hz,
            "channels": channels,
            "channels_refused_invalid_name": dict(invalid),
        }) + "\n")
        for row in samples:
            handle.write(json.dumps({"record": "sample", **row}) + "\n")
        handle.write(json.dumps({
            "record": "quality",
            "samples": len(samples),
            "interval_mean_s": round(statistics.fmean(intervals), 4) if intervals else None,
            "interval_median_s": round(statistics.median(intervals), 4) if intervals else None,
            "interval_max_s": max(intervals) if intervals else None,
            "effective_hz": round(1.0 / statistics.fmean(intervals), 2) if intervals else None,
            "gap_count": len(gaps),
            "gap_indices": gaps[:50],
        }) + "\n")

    summarise(args, channels, samples, intervals, gaps)
    return path


def summarise(args, channels, samples, intervals, gaps) -> None:
    def series(key):
        return [s[key] for s in samples if isinstance(s.get(key), (int, float))]

    print("--- card %s run %s: %d samples ---" % (args.card, args.run, len(samples)))
    if intervals:
        print("  rate         %.1f Hz effective (requested %d), max interval %.3f s, %d gaps"
              % (1.0 / statistics.fmean(intervals), args.hz, max(intervals), len(gaps)))

    unmeasured = [n for n in channels
                  if not any(isinstance(s.get(n), (int, float)) for s in samples)]
    if unmeasured:
        print("  UNMEASURED   %s" % ", ".join(unmeasured))

    allzero = [n for n in channels
               if n not in LEGITIMATELY_ZERO and n not in unmeasured
               and all(s.get(n) == 0 for s in samples if s.get(n) is not None)]
    if allzero:
        print("  ALL ZERO     %s   <- verify these are genuinely zero" % ", ".join(allzero))

    weight = series("weight_kg")
    if weight:
        print("  weight       %.0f lb" % (max(weight) * LB_PER_KG))
    for key, label, fmt in [("kias", "KIAS", "%.1f"), ("alt_msl_ft", "alt ft", "%.0f"),
                            ("agl_m", "AGL ft", None), ("alpha_deg", "alpha deg", "%.2f"),
                            ("g_normal", "Nz g", "%.3f"), ("flap_actual", "flap actual", "%.3f")]:
        values = series(key)
        if not values:
            continue
        if key == "agl_m":
            values = [v * FT_PER_M for v in values]
            fmt = "%.0f"
        print("  %-12s min %s  max %s" % (label, fmt % min(values), fmt % max(values)))

    warn = series("stall_warn")
    if warn and max(warn) > 0:
        first = next(s["t"] for s in samples if isinstance(s.get("stall_warn"), (int, float))
                     and s["stall_warn"] > 0)
        at = [s["kias"] for s in samples
              if isinstance(s.get("stall_warn"), (int, float)) and s["stall_warn"] > 0
              and isinstance(s.get("kias"), (int, float))]
        print("  STALL WARNING fired at t=%.2f, first at %.1f KIAS" % (first, at[0] if at else -1))

    print("\nReduce against docs/C182T_FLIGHT_TEST_CARD.md and record the real numbers,\n"
          "including misses, in CHANGELOG.md.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", required=True, help="card id, e.g. H1")
    parser.add_argument("--run", default="1", help="run id within the card")
    parser.add_argument("--note", default="", help="free-text condition note")
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--hz", type=int, default=20, help="sample rate (card prefers 20)")
    parser.add_argument("--xp-host", default="127.0.0.1")
    parser.add_argument("--xp-port", type=int, default=49000)
    parser.add_argument("--receive-port", type=int, default=49200)
    args = parser.parse_args()
    path = capture(args)
    print("trace: %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
