#!/usr/bin/env python3
"""Build and print an offline airport/runway-end record with validation."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.ai_pilot.airports.builder import (  # noqa: E402
    AirportRecordBuilder, GLOBAL_APT, DEFAULT_CIFP, DEFAULT_EARTH_NAV,
    DEFAULT_NASR, DEFAULT_CHART,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("icao", help="four-character airport ICAO, e.g. KSEE")
    parser.add_argument("--runway", help="limit output to a runway end, e.g. 27R")
    parser.add_argument("--json", dest="json_path", type=Path,
                        help="also write the complete JSON record and validation report")
    parser.add_argument("--apt", action="append", type=Path,
                        help="apt.dat source; may be repeated base-to-overlay (default: installed base + KSAN overlay)")
    parser.add_argument("--cifp-dir", type=Path, default=DEFAULT_CIFP)
    parser.add_argument("--earth-nav", type=Path, default=DEFAULT_EARTH_NAV)
    parser.add_argument("--nasr-dir", type=Path, default=DEFAULT_NASR)
    parser.add_argument("--chart-supplement", type=Path, default=DEFAULT_CHART)
    args = parser.parse_args(argv)

    # Parsing the installed Global Airports apt.dat is a read-only, sequential
    # pass. Lower the process priority on POSIX so a running simulator keeps
    # foreground scheduling preference.
    if hasattr(os, "nice"):
        try:
            os.nice(10)
        except OSError:
            pass
    builder = AirportRecordBuilder(
        apt_paths=args.apt, cifp_dir=args.cifp_dir, earth_nav_path=args.earth_nav,
        nasr_dir=args.nasr_dir, chart_supplement=args.chart_supplement)
    result = builder.build(args.icao).to_dict()
    if args.runway:
        runway = args.runway.upper()
        result["runway_ends"] = [entry for entry in result["runway_ends"]
                                 if entry["runway_end"] == runway]
        if not result["runway_ends"]:
            parser.error(f"runway end {runway} not found for {args.icao.upper()}")
        validation = result["validation_report"]
        validation["runway_ends"] = [entry for entry in validation["runway_ends"]
                                     if entry["runway_end"] == runway]
        validation["aim_point_comparison"] = [entry for entry in validation["aim_point_comparison"]
                                              if entry["runway_end"] == runway]
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    print(rendered)
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
