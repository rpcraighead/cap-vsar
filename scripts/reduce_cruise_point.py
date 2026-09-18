#!/usr/bin/env python3
"""Reduce a cruise trace to a card result: steadiest 60-second window.

Read-only. Takes a JSONL trace from scripts/capture_flight_test.py.

The card's cruise points are TRUE airspeed and ask for at least 60 seconds of
stabilisation, so this reports KTAS over the steadiest 60-second window and
says how much the speed was still drifting inside it. A max-speed point that
has not stopped accelerating is not a max-speed point, and the drift figure is
what lets a reader see that for themselves.

Usage:
    python3 scripts/reduce_cruise_point.py TRACE.jsonl --target-ktas 150 --tol 5
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

WINDOW = 60.0
KT_PER_MS = 1.94384


def num(row, key):
    v = row.get(key)
    return v if isinstance(v, (int, float)) else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace", type=Path)
    ap.add_argument("--target-ktas", type=float, required=True)
    ap.add_argument("--tol", type=float, default=5.0, help="tolerance in KTAS")
    args = ap.parse_args(argv)

    rows = [json.loads(l) for l in args.trace.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if num(r, "ktas") is not None and num(r, "alt_msl_ft") is not None]
    if not rows:
        print("no usable samples")
        return 2
    t0 = rows[0]["t"]
    for r in rows:
        r["_t"] = r["t"] - t0
        # Traces store true airspeed in m/s; the card is in knots.
        r["_ktas"] = num(r, "ktas") * (KT_PER_MS if num(r, "ktas") < 200 else 1.0)

    best = None
    for start in rows:
        win = [r for r in rows if start["_t"] <= r["_t"] <= start["_t"] + WINDOW]
        if len(win) < 200 or win[-1]["_t"] - win[0]["_t"] < WINDOW * 0.95:
            continue
        spread = max(r["_ktas"] for r in win) - min(r["_ktas"] for r in win)
        if best is None or spread < best[0]:
            best = (spread, win)
    if best is None:
        print("no %.0f s window in this trace" % WINDOW)
        return 2

    spread, win = best
    ktas = [r["_ktas"] for r in win]
    alt = [num(r, "alt_msl_ft") for r in win]
    vs = [num(r, "vs_fpm") for r in win if num(r, "vs_fpm") is not None]
    drift = ktas[-1] - ktas[0]
    got = statistics.fmean(ktas)
    lo, hi = args.target_ktas - args.tol, args.target_ktas + args.tol

    print("cruise reduction from %s" % args.trace.name)
    print("  window       t %.1f..%.1f s, %d samples" % (win[0]["_t"], win[-1]["_t"], len(win)))
    print("  altitude     %.0f..%.0f ft MSL" % (min(alt), max(alt)))
    if vs:
        print("  vertical     %+.0f fpm mean   <- must be ~0 for a level point"
              % statistics.fmean(vs))
    print("  KTAS         mean %.1f   spread %.1f   drift %+.1f over the window"
          % (got, spread, drift))
    print("  target       %.0f +/-%.0f KTAS  =  %.0f..%.0f"
          % (args.target_ktas, args.tol, lo, hi))
    print("  error        %+.1f KTAS  (%+.1f%%)"
          % (got - args.target_ktas, 100 * (got - args.target_ktas) / args.target_ktas))
    print("  VERDICT      %s" % ("PASS" if lo <= got <= hi else "MISS"))
    if abs(drift) > 1.0:
        print("\n  CAUTION: speed drifted %+.1f KTAS across the window, so it had not"
              % drift)
        print("  fully stabilised. A max-speed point still accelerating reads LOW.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
