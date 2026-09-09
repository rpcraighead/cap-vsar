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


def backup(source: Path, dest_dir: Path, retries: int = 2) -> Path:
    if not source.exists():
        raise SystemExit(f"{source} does not exist - nothing to back up")
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Microsecond resolution: two backups in the same second (as this
    # script's own tests do) must not silently collide on the same filename
    # and overwrite one of them - the one failure mode worse than no backup.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    dest = dest_dir / f"exercise-{stamp}.db"

    # A network destination (this is meant to run against NFS-mounted cold
    # storage) can hit a transient I/O error that a local disk essentially
    # never does - confirmed live against ms01's actual NFS3 mount: the
    # first attempt against a freshly-touched directory raised
    # "disk I/O error" from inside Connection.backup() with no retry of its
    # own, and the next two attempts immediately succeeded. A cron job with
    # no one watching needs to ride that out rather than leave a 0-byte file
    # and a bare traceback once a month.
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(2)
        dest.unlink(missing_ok=True)
        src_con = dst_con = None
        try:
            src_con = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
            dst_con = sqlite3.connect(str(dest))
            src_con.backup(dst_con)
            last_exc = None
            break
        except sqlite3.OperationalError as exc:
            last_exc = exc
        finally:
            if dst_con is not None:
                dst_con.close()
            if src_con is not None:
                src_con.close()
    if last_exc is not None:
        dest.unlink(missing_ok=True)
        raise SystemExit(f"backup of {source} failed after {retries + 1} attempts: {last_exc}")

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
