#!/usr/bin/env python3
"""Deploy the tracked Becker and RT-600 instruments to Air Manager."""

from __future__ import annotations

import argparse
import filecmp
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = Path.home() / "Air Manager/instruments/OPEN_DIRECTORY"
INSTRUMENTS = {
    "becker-sar-df-517": "faefb90d-5704-48c7-8deb-c683d94b4eb3",
    "rhotheta-rt-600": "d783d409-9bfa-49f2-ad5d-883af29848d6",
}


def files_match(source: Path, target: Path) -> bool:
    for item in source.rglob("*"):
        if item.is_file():
            installed = target / item.relative_to(source)
            if not installed.is_file() or not filecmp.cmp(item, installed, shallow=False):
                return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check", action="store_true",
                        help="compare tracked files without writing")
    args = parser.parse_args()

    stale = []
    for name, uuid in INSTRUMENTS.items():
        source = ROOT / "instruments" / name
        target = args.target / uuid
        if args.check:
            current = files_match(source, target)
            print(f"{name}: {'current' if current else 'needs deployment'}")
            if not current:
                stale.append(name)
        else:
            target.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target, dirs_exist_ok=True)
            if not files_match(source, target):
                raise RuntimeError(f"deployment verification failed: {name}")
            print(f"deployed {name} -> {target}")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
