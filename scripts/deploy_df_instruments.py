#!/usr/bin/env python3
"""Deploy the tracked Becker 517, RT-600, TDFM-136B, and GMA 1347 instruments to Air Manager."""

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
    "cap-fm-tdfm-136b": "26df5da8-8ce7-4255-bb0e-520453134609",
    "mo-audio-panel-gma1347": "1337420b-7420-4843-80eb-9d10c57a97d1",
    "cap-mission-master-switch": "d285e0f7-b787-42c7-85fd-ec8990f6db33",
    "cap-mission-cb-panel": "aa9851bc-5ba6-4f5e-a465-d456403fbfc8",
}

SHARED_TO_INSTRUMENTS = {
    "becker-sar-df-517": {
        "lib": ["lcd.lua", "cap_df.lua", "cap_df_audio.lua", "dcu.lua", "cap_power.lua"],
        "resources": [
            "elt_analog_clean.wav",
            "elt_analog_df.wav",
            "elt_noise.wav",
            "elt_406_burst.wav",
        ],
    },
    "rhotheta-rt-600": {
        "lib": ["lcd.lua", "cap_df.lua", "cap_df_audio.lua", "dcu.lua", "cap_power.lua"],
        "resources": [
            "elt_analog_clean.wav",
            "elt_analog_df.wav",
            "elt_noise.wav",
            "elt_406_burst.wav",
        ],
    },
    "cap-fm-tdfm-136b": {
        "lib": ["lcd.lua", "knob_push.lua", "cap_power.lua"],
        "resources": [],
    },
    "mo-audio-panel-gma1347": {
        "lib": ["knob_push.lua", "cap_power.lua"],
        "resources": [],
    },
}


def is_shared_synced(repo_root: Path, inst_name: str) -> bool:
    shared_dir = repo_root / "instruments" / "_shared"
    if inst_name not in SHARED_TO_INSTRUMENTS:
        return True
    for sub, fnames in SHARED_TO_INSTRUMENTS[inst_name].items():
        for fname in fnames:
            src = shared_dir / sub / fname
            dst = repo_root / "instruments" / inst_name / sub / fname
            if not dst.is_file() or not filecmp.cmp(src, dst, shallow=False):
                return False
    return True


def sync_shared_files(repo_root: Path) -> None:
    shared_dir = repo_root / "instruments" / "_shared"
    for inst_name, mapping in SHARED_TO_INSTRUMENTS.items():
        for sub, fnames in mapping.items():
            for fname in fnames:
                src = shared_dir / sub / fname
                dst = repo_root / "instruments" / inst_name / sub / fname
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.is_file() or not filecmp.cmp(src, dst, shallow=False):
                    shutil.copy2(src, dst)


def files_match(source: Path, target: Path) -> bool:
    if not target.exists():
        return False
    for item in source.rglob("*"):
        if item.is_file():
            installed = target / item.relative_to(source)
            if not installed.is_file() or not filecmp.cmp(item, installed, shallow=False):
                return False
    for item in target.rglob("*"):
        if item.is_file():
            src = source / item.relative_to(target)
            if not src.is_file():
                return False
    return True


def deploy_instrument(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    # Copy new / updated files
    for item in source.rglob("*"):
        if item.is_file():
            rel = item.relative_to(source)
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.is_file() or not filecmp.cmp(item, dest, shallow=False):
                shutil.copy2(item, dest)
    # Prune stale files in target
    for item in list(target.rglob("*")):
        if item.is_file():
            rel = item.relative_to(target)
            src = source / rel
            if not src.is_file():
                item.unlink()
    # Prune empty directories in target
    for item in sorted(target.rglob("*"), reverse=True):
        if item.is_dir() and not any(item.iterdir()):
            item.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check", action="store_true",
                        help="compare tracked files without writing")
    args = parser.parse_args()

    stale = []
    if not args.check:
        sync_shared_files(ROOT)

    for name, uuid in INSTRUMENTS.items():
        source = ROOT / "instruments" / name
        target = args.target / uuid
        if args.check:
            current = is_shared_synced(ROOT, name) and files_match(source, target)
            print(f"{name}: {'current' if current else 'needs deployment'}")
            if not current:
                stale.append(name)
        else:
            deploy_instrument(source, target)
            if not files_match(source, target):
                raise RuntimeError(f"deployment verification failed: {name}")
            print(f"deployed {name} -> {target}")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
