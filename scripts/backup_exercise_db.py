#!/usr/bin/env python3
"""
Back up the exercise console's SQLite database (O-6).

ms01 carries exercise.db - scenarios, bearing logs, recorded tracks, the
whole exercise record - with no backup at all; a bad exercise-day failure
loses the record with no warning. Uses SQLite's own online backup API
(`Connection.backup`), not a raw file copy, so this is safe to run against a
database the exercise console has open and is actively writing to (WAL mode
or not) - a plain `cp` on a live SQLite file can capture a torn, inconsistent
snapshot.

Usage:
    python3 scripts/backup_exercise_db.py [--source PATH] [--dest-dir DIR] [--keep-days N]

Intended to run nightly via cron - not installed by this script itself:

    0 3 * * * cd /srv/capvsar && python3 scripts/backup_exercise_db.py \
        >> /var/log/capvsar-backup.log 2>&1
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "services" / "exercise" / "data" / "exercise.db"
DEFAULT_DEST_DIR = ROOT / "backups" / "exercise-db"
DEFAULT_KEEP_DAYS = 14


def backup(source: Path, dest_dir: Path) -> Path:
    if not source.exists():
        raise SystemExit(f"{source} does not exist - nothing to back up")
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Microsecond resolution: two backups in the same second (as this
    # script's own tests do) must not silently collide on the same filename
    # and overwrite one of them - the one failure mode worse than no backup.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    dest = dest_dir / f"exercise-{stamp}.db"

    src_con = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst_con = sqlite3.connect(str(dest))
    try:
        src_con.backup(dst_con)
    finally:
        dst_con.close()
        src_con.close()

    # A backup that didn't actually copy anything is worse than none - it
    # looks like success right up until it's needed.
    if dest.stat().st_size == 0:
        dest.unlink()
        raise SystemExit(f"backup of {source} produced a 0-byte file; aborted")
    return dest


def prune(dest_dir: Path, keep_days: int) -> list[Path]:
    cutoff = time.time() - keep_days * 86400
    removed = []
    for f in dest_dir.glob("exercise-*.db"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed.append(f)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest-dir", type=Path, default=DEFAULT_DEST_DIR)
    parser.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS)
    args = parser.parse_args()

    dest = backup(args.source, args.dest_dir)
    size_kb = dest.stat().st_size / 1024
    print(f"backed up {args.source} -> {dest} ({size_kb:.1f} KiB)")

    removed = prune(args.dest_dir, args.keep_days)
    if removed:
        print(f"pruned {len(removed)} backup(s) older than {args.keep_days} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
