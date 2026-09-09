"""O-6: scripts/backup_exercise_db.py - online backup and retention pruning."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import backup_exercise_db as bx  # noqa: E402


class BackupExerciseDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.source = self.tmp / "exercise.db"
        self.dest_dir = self.tmp / "backups"
        con = sqlite3.connect(self.source)
        con.execute("CREATE TABLE bearings (id INTEGER PRIMARY KEY, callsign TEXT)")
        con.execute("INSERT INTO bearings (callsign) VALUES ('CAP-1')")
        con.commit()
        con.close()

    def tearDown(self):
        for f in self.tmp.rglob("*"):
            if f.is_file():
                f.unlink()
        for d in sorted(self.tmp.rglob("*"), reverse=True):
            if d.is_dir():
                d.rmdir()
        self.tmp.rmdir()

    def test_backup_is_a_real_readable_copy_not_a_stub(self):
        dest = bx.backup(self.source, self.dest_dir)
        self.assertTrue(dest.exists())
        con = sqlite3.connect(dest)
        rows = con.execute("SELECT callsign FROM bearings").fetchall()
        con.close()
        self.assertEqual(rows, [("CAP-1",)])

    def test_missing_source_is_a_loud_error_not_a_silent_no_op(self):
        with self.assertRaises(SystemExit):
            bx.backup(self.tmp / "does-not-exist.db", self.dest_dir)

    def test_backup_survives_concurrent_writes(self):
        """The whole reason this uses sqlite3's backup API instead of a file
        copy: a live writer must not produce a torn snapshot."""
        con = sqlite3.connect(self.source)
        con.execute("INSERT INTO bearings (callsign) VALUES ('CAP-2')")
        con.commit()  # still open, uncommitted next write in flight conceptually
        dest = bx.backup(self.source, self.dest_dir)
        con.close()
        check = sqlite3.connect(dest)
        count = check.execute("SELECT COUNT(*) FROM bearings").fetchone()[0]
        check.close()
        self.assertEqual(count, 2)

    def test_transient_failure_is_retried_and_leaves_no_debris(self):
        """Caught live against ms01's real NFS3 mount: the first attempt at a
        freshly-touched destination directory raised sqlite3.OperationalError
        with no retry of its own; the very next attempt succeeded clean.
        sqlite3.Connection is a C type and can't be monkeypatched directly,
        so this fails the connection itself the first time round instead."""
        real_connect = sqlite3.connect
        # backup()'s destination path is timestamped and unknown in advance,
        # so intercept at the sqlite3.connect layer generically: each attempt
        # makes two connect() calls (source, then destination) - fail only
        # the destination connect of the first attempt.
        connect_calls = []

        def flaky_connect(target, *a, **kw):
            connect_calls.append(target)
            if len(connect_calls) == 2:
                raise sqlite3.OperationalError("disk I/O error")
            return real_connect(target, *a, **kw)

        with patch.object(bx.sqlite3, "connect", flaky_connect), \
                patch.object(bx.time, "sleep"):
            dest = bx.backup(self.source, self.dest_dir, retries=2)

        self.assertTrue(dest.exists())
        self.assertGreater(dest.stat().st_size, 0)
        # No stale 0-byte file left behind from the failed first attempt.
        self.assertEqual(len(list(self.dest_dir.glob("exercise-*.db"))), 1)

    def test_exhausting_all_retries_is_a_loud_error_with_no_debris(self):
        def always_fails(target, *a, **kw):
            raise sqlite3.OperationalError("disk I/O error")

        with patch.object(bx.sqlite3, "connect", always_fails), \
                patch.object(bx.time, "sleep"):
            with self.assertRaises(SystemExit):
                bx.backup(self.source, self.dest_dir, retries=1)

        self.assertEqual(list(self.dest_dir.glob("exercise-*.db")), [])

    def test_prune_removes_only_backups_older_than_the_window(self):
        old = bx.backup(self.source, self.dest_dir)
        os.utime(old, (time.time() - 20 * 86400, time.time() - 20 * 86400))
        time.sleep(0.01)
        recent = bx.backup(self.source, self.dest_dir)

        removed = bx.prune(self.dest_dir, keep_days=14)

        self.assertEqual(removed, [old])
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())


if __name__ == "__main__":
    unittest.main()
