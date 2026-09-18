#!/usr/bin/env python3
"""Fail on the two X-Plane load regressions AI-4 is about.

AI-4's fix is already built and installed: the builder's IDX10 remainder
encoding was corrected and the prop texture was resampled 194x87 -> 256x128.
What kept the item open is that neither had been confirmed against a fresh
X-Plane load, and a human reading a log is not a check that can be re-run.

This reads a Log.txt and fails on exactly two things:

  * an index-out-of-range or IDX10 complaint naming prop_lever.obj
  * a non-power-of-two texture warning naming prop_lever.png

It deliberately does NOT treat a clean log as proof the item is closed. The
cockpit lever also has to render and move, and a log cannot say whether it
did - see AI-4 in docs/bugs/tracker.json.

One trap is worth naming, because it cost a session once: X-Plane keeps
writing to Log.txt across reloads, so a log can be clean only because it
predates the aircraft you think you are testing. --require-aircraft fails
unless the log actually loaded the package you name.

Usage:
    python3 scripts/check_xplane_log.py
    python3 scripts/check_xplane_log.py --log "~/X-Plane 12/Log.txt"
    python3 scripts/check_xplane_log.py --require-aircraft "Cessna_182T_G1000.acf"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

DEFAULT_LOG = "~/X-Plane 12/Log.txt"

# Both patterns require the offending FILE to be named on the line. A bare
# "index out of range" from some other object is not this defect, and failing
# on it would train whoever runs this to ignore the output.
FAILURES = (
    ("prop lever index encoding (IDX10 remainder)",
     re.compile(r"prop_lever\.obj", re.I),
     re.compile(r"idx10|index out of range|out-of-range", re.I)),
    ("prop lever texture is not a power of two",
     re.compile(r"prop_lever\.png", re.I),
     re.compile(r"not a power|non[- ]power|power.of.two", re.I)),
)

LOADED = re.compile(r"Loading airplane number \d+ with (.+)$", re.I)


def read_log(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"X-Plane log not found: {path}")
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def aircraft_loaded(lines) -> list[str]:
    return [m.group(1).strip() for line in lines for m in [LOADED.search(line)] if m]


def scan(lines) -> list[tuple[str, int, str]]:
    """Every line that trips one of the two regressions."""
    hits = []
    for number, line in enumerate(lines, start=1):
        for label, file_pat, fault_pat in FAILURES:
            if file_pat.search(line) and fault_pat.search(line):
                hits.append((label, number, line.strip()))
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--require-aircraft", default=None,
                    help="fail unless the log shows this aircraft being loaded")
    args = ap.parse_args(argv)

    path = Path(os.path.expanduser(args.log))
    try:
        lines = read_log(path)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"{path}: {len(lines)} lines")
    loaded = aircraft_loaded(lines)
    if loaded:
        print(f"aircraft loaded: {loaded[-1]}")
    else:
        print("aircraft loaded: none recorded")

    if args.require_aircraft:
        if not any(args.require_aircraft in name for name in loaded):
            print(f"error: this log never loaded {args.require_aircraft!r}, so a clean "
                  f"result would say nothing about it", file=sys.stderr)
            return 3

    hits = scan(lines)
    if hits:
        print(f"\nFAILED: {len(hits)} regression line(s)", file=sys.stderr)
        for label, number, text in hits:
            print(f"  [{label}] line {number}: {text}", file=sys.stderr)
        return 1

    print("\nno prop-lever index or texture regression in this log")
    print("NOT sufficient to close AI-4: the cockpit lever must also be seen to "
          "render and move through its travel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
