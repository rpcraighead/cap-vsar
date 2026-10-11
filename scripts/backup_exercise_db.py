#!/usr/bin/env python3
"""
Back up, and restore, the exercise console's SQLite database (O-6, O2-8).

ms01 carries exercise.db - scenarios, bearing logs, recorded tracks, the
whole exercise record - with no backup at all; a bad exercise-day failure
loses the record with no warning. Uses SQLite's own online backup API
(`Connection.backup`), not a raw file copy, so this is safe to run against a
database the exercise console has open and is actively writing to (WAL mode
or not) - a plain `cp` on a live SQLite file can capture a torn, inconsistent
snapshot.

O2-7/O2-8: the same run also backs up the Mumble server database
(mumble/data/mumble-server.sqlite: the channel tree, ACLs and the SuperUser
hash) into backups/mumble-db/. That file is owned by the container's uid with
mode 640, so the Mumble half needs sudo; if it cannot be read the exercise
backup still completes and the script exits 2 so cron's log shows it.

Usage:
    python3 scripts/backup_exercise_db.py [--source PATH] [--dest-dir DIR] [--keep-days N]
    python3 scripts/backup_exercise_db.py --restore FILE [--target PATH] [--force]

Paths default under $CAPVSAR_STATE_DIR when it is set (see docker-compose.yml),
otherwise under this checkout.

Restore (stop the console first: `docker compose stop exercise`):
  - refuses while a capvsar-exercise container is running, unless --force;
  - checks FILE is a healthy SQLite database before touching anything;
  - copies it with the SQLite backup API into a temp file beside the target
    and renames it into place, so a failed restore never leaves a half file;
  - moves the old database aside as <target>.pre-restore-<stamp> (kept, never
    deleted) and removes its stale -wal/-shm files;
  - run as root it chowns the result to the old file's owner (or the data
    directory's owner), so the non-root container can still write it.

Intended to run nightly via cron - not installed by this script itself:

    0 3 * * * cd /srv/capvsar && sudo python3 scripts/backup_exercise_db.py \
        >> /var/log/capvsar-backup.log 2>&1
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.environ.get("CAPVSAR_STATE_DIR") or ROOT)
DEFAULT_SOURCE = STATE / "services" / "exercise" / "data" / "exercise.db"
DEFAULT_DEST_DIR = ROOT / "backups" / "exercise-db"
DEFAULT_MUMBLE_SOURCE = STATE / "mumble" / "data" / "mumble-server.sqlite"
DEFAULT_MUMBLE_DEST_DIR = ROOT / "backups" / "mumble-db"
CONSOLE_CONTAINER = "capvsar-exercise"
DEFAULT_KEEP_DAYS = 14


def backup(source: Path, dest_dir: Path, retries: int = 2, prefix: str = "exercise") -> Path:
    if not source.exists():
        raise SystemExit(f"{source} does not exist - nothing to back up")
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Microsecond resolution: two backups in the same second (as this
    # script's own tests do) must not silently collide on the same filename
    # and overwrite one of them - the one failure mode worse than no backup.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    dest = dest_dir / f"{prefix}-{stamp}.db"

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
        except sqlite3.DatabaseError:
            # Not a database at all: retrying cannot help, and the empty
            # destination must not be left behind looking like a backup.
            dest.unlink(missing_ok=True)
            raise
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


def prune(dest_dir: Path, keep_days: int, prefix: str = "exercise") -> list[Path]:
    cutoff = time.time() - keep_days * 86400
    removed = []
    for f in dest_dir.glob(f"{prefix}-*.db"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed.append(f)
    return removed


def running_console_containers() -> list[str]:
    """Names of running console containers; [] if none or Docker is absent."""
    try:
        out = subprocess.run(
            ["docker", "ps", "--filter", f"name={CONSOLE_CONTAINER}", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [n for n in out.stdout.split() if n]


def _check_database(path: Path) -> None:
    """Refuse anything that is not a healthy SQLite database."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            result = con.execute("PRAGMA integrity_check").fetchall()
        finally:
            con.close()
    except sqlite3.DatabaseError as exc:
        raise SystemExit(f"{path} is not a usable SQLite database: {exc}")
    if result != [("ok",)]:
        raise SystemExit(f"{path} failed integrity_check: {result[:3]}")


def restore(backup_file: Path, target: Path, force: bool = False) -> list[str]:
    """Replace `target` with `backup_file`. Returns what was done, in order."""
    done: list[str] = []
    if not backup_file.is_file():
        raise SystemExit(f"{backup_file} does not exist - nothing to restore")
    running = running_console_containers()
    if running and not force:
        raise SystemExit(
            f"refusing to restore while {', '.join(running)} is running: the console "
            f"holds {target} open and would overwrite or corrupt the restored file. "
            "Run `docker compose stop exercise` first (or pass --force).")
    if running:
        done.append(f"WARNING: --force given while {', '.join(running)} is running")
    _check_database(backup_file)
    done.append(f"{backup_file} passed integrity_check")

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".restore-tmp")
    tmp.unlink(missing_ok=True)
    src_con = dst_con = None
    try:
        src_con = sqlite3.connect(f"file:{backup_file}?mode=ro", uri=True)
        dst_con = sqlite3.connect(str(tmp))
        src_con.backup(dst_con)
    except sqlite3.Error as exc:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"restore failed while copying {backup_file}: {exc}")
    finally:
        if dst_con is not None:
            dst_con.close()
        if src_con is not None:
            src_con.close()
    # The copy is a self-contained database in the source's journal mode; any
    # leftover journal files beside the temp file would be stale.
    for suffix in ("-wal", "-shm"):
        Path(str(tmp) + suffix).unlink(missing_ok=True)
    done.append(f"copied into {tmp.name} with the SQLite backup API")

    old_owner = None
    if target.exists():
        st = target.stat()
        old_owner = (st.st_uid, st.st_gid)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
        aside = target.with_name(f"{target.name}.pre-restore-{stamp}")
        os.replace(target, aside)
        done.append(f"moved the old database aside to {aside}")
    # Stale WAL/SHM belong to the database just moved away; left in place they
    # would be replayed over the restored file by the next SQLite open.
    for suffix in ("-wal", "-shm"):
        stale = Path(str(target) + suffix)
        if stale.exists():
            stale.unlink()
            done.append(f"removed stale {stale.name}")
    if os.geteuid() == 0:
        if old_owner is None:
            st = target.parent.stat()
            old_owner = (st.st_uid, st.st_gid)
        shutil.chown(tmp, old_owner[0], old_owner[1])
        done.append(f"chowned to {old_owner[0]}:{old_owner[1]}")
    os.replace(tmp, target)
    done.append(f"restored {target} ({target.stat().st_size / 1024:.1f} KiB)")
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest-dir", type=Path, default=DEFAULT_DEST_DIR)
    parser.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS)
    parser.add_argument("--mumble-source", type=Path, default=DEFAULT_MUMBLE_SOURCE,
                        help="Mumble server database (skipped if the file does not exist)")
    parser.add_argument("--mumble-dest-dir", type=Path, default=DEFAULT_MUMBLE_DEST_DIR)
    parser.add_argument("--no-mumble", action="store_true", help="back up the exercise database only")
    parser.add_argument("--restore", type=Path, metavar="FILE",
                        help="restore FILE over --target instead of taking a backup")
    parser.add_argument("--target", type=Path, default=None,
                        help="database to overwrite on --restore (default: --source)")
    parser.add_argument("--force", action="store_true",
                        help="restore even though the console container is running")
    args = parser.parse_args()

    if args.restore:
        for line in restore(args.restore, args.target or args.source, force=args.force):
            print(line)
        print("restore complete. Start the console: docker compose start exercise")
        return 0

    dest = backup(args.source, args.dest_dir)
    size_kb = dest.stat().st_size / 1024
    print(f"backed up {args.source} -> {dest} ({size_kb:.1f} KiB)")

    removed = prune(args.dest_dir, args.keep_days)
    if removed:
        print(f"pruned {len(removed)} backup(s) older than {args.keep_days} days")

    rc = 0
    if not args.no_mumble:
        if not args.mumble_source.exists():
            print(f"no Mumble database at {args.mumble_source}; skipped")
        else:
            try:
                mdest = backup(args.mumble_source, args.mumble_dest_dir, prefix="mumble")
            except (SystemExit, OSError, sqlite3.Error) as exc:
                print(f"WARNING: Mumble backup failed ({exc}); the file is owned by the "
                      "container uid, mode 640 - re-run with sudo", file=sys.stderr)
                rc = 2
            else:
                print(f"backed up {args.mumble_source} -> {mdest} ({mdest.stat().st_size / 1024:.1f} KiB)")
                removed = prune(args.mumble_dest_dir, args.keep_days, prefix="mumble")
                if removed:
                    print(f"pruned {len(removed)} Mumble backup(s) older than {args.keep_days} days")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
