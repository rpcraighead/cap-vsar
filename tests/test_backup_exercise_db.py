"""O-6: scripts/backup_exercise_db.py - online backup and retention pruning."""
from __future__ import annotations

import importlib
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


class MumbleBackupTests(unittest.TestCase):
    """O2-7: the Mumble database (channel tree, ACLs, SuperUser hash) is in scope."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.exercise = self.tmp / "exercise.db"
        self.mumble = self.tmp / "mumble-server.sqlite"
        for path, table in ((self.exercise, "bearings"), (self.mumble, "channels")):
            con = sqlite3.connect(path)
            con.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, name TEXT)")
            con.execute(f"INSERT INTO {table} (name) VALUES ('x')")
            con.commit()
            con.close()

    def run_main(self, *extra):
        argv = ["backup_exercise_db.py", "--source", str(self.exercise),
                "--dest-dir", str(self.tmp / "ex"), "--mumble-source", str(self.mumble),
                "--mumble-dest-dir", str(self.tmp / "mu"), *extra]
        with patch.object(sys, "argv", argv):
            return bx.main()

    def test_default_mumble_source_is_under_the_mumble_data_directory(self):
        self.assertEqual(bx.DEFAULT_MUMBLE_SOURCE.parts[-3:], ("mumble", "data", "mumble-server.sqlite"))

    def test_a_run_backs_up_both_databases(self):
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(len(list((self.tmp / "ex").glob("exercise-*.db"))), 1)
        (mdump,) = (self.tmp / "mu").glob("mumble-*.db")
        con = sqlite3.connect(mdump)
        self.assertEqual(con.execute("SELECT name FROM channels").fetchall(), [("x",)])
        con.close()

    def test_a_missing_mumble_database_is_skipped_not_fatal(self):
        self.mumble.unlink()
        self.assertEqual(self.run_main(), 0)
        self.assertFalse((self.tmp / "mu").exists())

    def test_an_unreadable_mumble_database_fails_the_run_but_keeps_the_exercise_backup(self):
        self.mumble.write_bytes(b"not a database" * 100)  # present but unusable
        self.assertEqual(self.run_main(), 2)
        self.assertEqual(len(list((self.tmp / "ex").glob("exercise-*.db"))), 1)
        self.assertEqual(list((self.tmp / "mu").glob("mumble-*.db")), [])  # no debris


class RestoreTests(unittest.TestCase):
    """O2-8: backups were write-only. Restore, and prove a backup opens."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.live = self.tmp / "data" / "exercise.db"
        self.live.parent.mkdir()
        con = sqlite3.connect(self.live)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE t (v TEXT)")
        con.execute("INSERT INTO t VALUES ('good')")
        con.commit()
        con.close()
        self.backup = bx.backup(self.live, self.tmp / "backups")
        # Now the live database "gets damaged": different content plus stale WAL/SHM.
        con = sqlite3.connect(self.live)
        con.execute("UPDATE t SET v='bad'")
        con.commit()
        con.close()
        for suffix in ("-wal", "-shm"):
            Path(str(self.live) + suffix).write_bytes(b"stale")

    def read(self, path):
        con = sqlite3.connect(path)
        try:
            return con.execute("SELECT v FROM t").fetchall()
        finally:
            con.close()

    def test_restore_replaces_the_database_and_removes_stale_wal_files(self):
        with patch.object(bx, "running_console_containers", return_value=[]):
            log = bx.restore(self.backup, self.live)
        self.assertEqual(self.read(self.live), [("good",)])
        self.assertFalse(Path(str(self.live) + "-wal").exists())
        self.assertFalse(Path(str(self.live) + "-shm").exists())
        self.assertFalse(self.live.with_name("exercise.db.restore-tmp").exists())
        self.assertTrue(any("removed stale exercise.db-wal" in line for line in log))

    def test_the_old_database_is_kept_aside_not_deleted(self):
        with patch.object(bx, "running_console_containers", return_value=[]):
            bx.restore(self.backup, self.live)
        (aside,) = self.live.parent.glob("exercise.db.pre-restore-*")
        self.assertEqual(self.read(aside), [("bad",)])

    def test_restore_refuses_while_the_console_container_is_running(self):
        with patch.object(bx, "running_console_containers", return_value=["capvsar-exercise"]):
            with self.assertRaises(SystemExit) as cm:
                bx.restore(self.backup, self.live)
        self.assertIn("docker compose stop exercise", str(cm.exception))
        self.assertEqual(self.read(self.live), [("bad",)])  # untouched

    def test_force_overrides_the_running_container_check(self):
        with patch.object(bx, "running_console_containers", return_value=["capvsar-exercise"]):
            log = bx.restore(self.backup, self.live, force=True)
        self.assertEqual(self.read(self.live), [("good",)])
        self.assertTrue(any(line.startswith("WARNING") for line in log))

    def test_a_corrupt_backup_is_refused_before_anything_is_touched(self):
        junk = self.tmp / "junk.db"
        junk.write_bytes(b"this is not sqlite" * 50)
        with patch.object(bx, "running_console_containers", return_value=[]):
            with self.assertRaises(SystemExit):
                bx.restore(junk, self.live)
        self.assertEqual(self.read(self.live), [("bad",)])
        self.assertEqual(list(self.live.parent.glob("*.restore-tmp")), [])

    def test_restore_into_a_fresh_path_needs_no_existing_database(self):
        target = self.tmp / "new" / "exercise.db"
        with patch.object(bx, "running_console_containers", return_value=[]):
            bx.restore(self.backup, target)
        self.assertEqual(self.read(target), [("good",)])

    def test_command_line_restore(self):
        argv = ["backup_exercise_db.py", "--restore", str(self.backup),
                "--target", str(self.live)]
        with patch.object(sys, "argv", argv), \
                patch.object(bx, "running_console_containers", return_value=[]):
            self.assertEqual(bx.main(), 0)
        self.assertEqual(self.read(self.live), [("good",)])

    def test_missing_docker_does_not_block_a_restore(self):
        with patch.object(bx.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(bx.running_console_containers(), [])


class BackupOpensAgainstCurrentSchemaTests(unittest.TestCase):
    """O2-8: a backup is only worth having if today's console can open it."""

    @classmethod
    def setUpClass(cls):
        pytest = __import__("pytest")
        pytest.importorskip("fastapi")
        sys.path.insert(0, str(REPO / "services" / "exercise"))

    def console_store(self, db_path):
        os.environ["CAPVSAR_DB"] = str(db_path)
        os.environ.setdefault("CAPVSAR_DEV_OPEN", "1")
        for mod in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
            sys.modules.pop(mod, None)
        return importlib.import_module("app.store")

    def tearDown(self):
        os.environ.pop("CAPVSAR_DB", None)
        for mod in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
            sys.modules.pop(mod, None)

    def test_a_backup_of_a_current_database_restores_and_reads(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        live = tmp / "exercise.db"
        store = self.console_store(live)
        store.init_db()
        with store.db() as c:
            c.execute("INSERT INTO scenarios (id, name, created) VALUES ('s1', 'Backup me', 1.0)")
        dump = bx.backup(live, tmp / "backups")

        restored = tmp / "restored" / "exercise.db"
        with patch.object(bx, "running_console_containers", return_value=[]):
            bx.restore(dump, restored)
        store = self.console_store(restored)
        store.init_db()  # the real startup path: idempotent, migrates if needed
        with store.db() as c:
            row = c.execute("SELECT name FROM scenarios WHERE id='s1'").fetchone()
        self.assertEqual(row["name"], "Backup me")

    def test_a_backup_from_before_the_alert_columns_is_migrated_on_open(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        old = tmp / "old.db"
        con = sqlite3.connect(old)
        con.executescript("""
            CREATE TABLE scenarios (id TEXT PRIMARY KEY, name TEXT NOT NULL, notes TEXT,
                beacon_lat REAL, beacon_lon REAL, beacon_elev_ft REAL,
                band TEXT, power REAL, effects TEXT, created REAL);
            CREATE TABLE sorties (id TEXT PRIMARY KEY, scenario_id TEXT, name TEXT,
                started REAL, stopped REAL, revealed INTEGER DEFAULT 0);
            INSERT INTO scenarios (id, name, created) VALUES ('s0', 'Legacy', 1.0);
        """)
        con.commit()
        con.close()
        dump = bx.backup(old, tmp / "backups")
        target = tmp / "restored.db"
        with patch.object(bx, "running_console_containers", return_value=[]):
            bx.restore(dump, target)
        store = self.console_store(target)
        store.init_db()
        with store.db() as c:
            cols = {r["name"] for r in c.execute("PRAGMA table_info(sorties)")}
            name = c.execute("SELECT name FROM scenarios WHERE id='s0'").fetchone()["name"]
        self.assertIn("truth", cols)
        self.assertEqual(name, "Legacy")


if __name__ == "__main__":
    unittest.main()
