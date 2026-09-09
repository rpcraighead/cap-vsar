#!/usr/bin/env python3
"""Validate and atomically deploy the tracked CAP V-SAR XPPython3 plugin."""

from __future__ import annotations

import argparse
import hashlib
import os
import py_compile
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "xplane" / "PI_capvsar_df.py"
DEFAULT_TARGET = Path.home() / "X-Plane 12/Resources/plugins/PythonPlugins/PI_capvsar_df.py"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check", action="store_true",
                        help="validate and compare without writing")
    args = parser.parse_args()

    py_compile.compile(str(SOURCE), doraise=True)
    source_hash = digest(SOURCE)
    target_hash = digest(args.target) if args.target.exists() else None

    if args.check:
        state = "current" if source_hash == target_hash else "needs deployment"
        print(f"source {source_hash}")
        print(f"target {target_hash or 'missing'}")
        print(state)
        return 0 if source_hash == target_hash else 1

    args.target.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.target.with_name(args.target.name + ".cap-vsar-new")
    try:
        shutil.copy2(SOURCE, temporary)
        os.replace(temporary, args.target)
    finally:
        if temporary.exists():
            temporary.unlink()

    deployed_hash = digest(args.target)
    if deployed_hash != source_hash:
        raise RuntimeError("deployed plugin does not match the tracked source")
    print(f"deployed {args.target}")
    print(f"sha256 {deployed_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
