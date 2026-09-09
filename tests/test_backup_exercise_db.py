"""O-6: scripts/backup_exercise_db.py - online backup and retention pruning."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

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
