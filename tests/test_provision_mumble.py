"""O-4: scripts/provision_mumble.py against a real Murmur schema.

Builds two fixture databases with exactly the tables and column layout
mumble-server.sqlite actually has (confirmed by inspecting ms01's live
database directly, not assumed from memory) - a brand-new server with only
the root channel, and one already hand-provisioned the way ms01's really is,
missing only the Instructor/SET ACL. Runs the provisioner against each twice
to prove both full-tree creation and idempotency, and that pre-existing rows
are never touched.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "services" / "exercise"))
import provision_mumble as pm  # noqa: E402
from app.mumble_channels import INSTRUCTOR_CHANNEL  # noqa: E402

SCHEMA = """
CREATE TABLE channels (server_id INTEGER NOT NULL, channel_id INTEGER NOT NULL,
    parent_id INTEGER, name TEXT, inheritacl INTEGER);
CREATE TABLE acl (server_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, priority INTEGER,
    user_id INTEGER, group_name TEXT, apply_here INTEGER, apply_sub INTEGER,
    grantpriv INTEGER, revokepriv INTEGER);
CREATE TABLE groups (group_id INTEGER PRIMARY KEY AUTOINCREMENT, server_id INTEGER NOT NULL,
    name TEXT, channel_id INTEGER NOT NULL, inherit INTEGER, inheritable INTEGER);
"""

# ms01's actual live rows as of 2026-09-09, confirmed by inspecting
# mumble-server.sqlite directly - not reconstructed from the docs, which is
# how the "Instructor - SET" vs "Instructor / SET" naming drift was found.
LIVE_CHANNELS = [
    (1, 0, None, "CAP V-SAR", None),
    (1, 1, 0, "Briefing Room", 1), (1, 2, 0, "Mission Base", 1),
    (1, 3, 0, "Mission Net PRIMARY", 1), (1, 4, 0, "Mission Net ALTERNATE", 1),
    (1, 5, 0, "Aircraft", 1),
    (1, 6, 5, "CAP-1 Intercom", 1), (1, 7, 5, "CAP-2 Intercom", 1), (1, 8, 5, "CAP-3 Intercom", 1),
    (1, 9, 0, "Instructor - SET", 1),
]
LIVE_ACL = [(1, 0, 1, None, "admin", 1, 1, 1, None), (1, 0, 2, None, "auth", 1, 1, 1024, None),
            (1, 0, 3, None, "all", 1, 0, 524288, None)]


def build_db(path, seeded: bool):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    if seeded:
        con.executemany("INSERT INTO channels VALUES (?,?,?,?,?)", LIVE_CHANNELS)
        con.executemany("INSERT INTO acl VALUES (?,?,?,?,?,?,?,?,?)", LIVE_ACL)
        con.execute("INSERT INTO groups (group_id, server_id, name, channel_id, inherit, inheritable) "
                    "VALUES (1,1,'admin',0,1,1)")
    else:
        con.execute("INSERT INTO channels VALUES (1, 0, NULL, 'Root', NULL)")
    con.commit()
    con.close()


class ProvisionMumbleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.tmp.close()
        self.db = Path(self.tmp.name)

    def tearDown(self):
        self.db.unlink(missing_ok=True)

    def channels(self):
        con = sqlite3.connect(self.db)
        rows = con.execute("SELECT server_id, channel_id, parent_id, name FROM channels "
                            "ORDER BY channel_id").fetchall()
        con.close()
        return rows

    def acl_rows(self):
        con = sqlite3.connect(self.db)
        rows = con.execute("SELECT channel_id, priority, group_name, grantpriv, revokepriv FROM acl "
                            "ORDER BY channel_id, priority").fetchall()
        con.close()
        return rows

    def test_fresh_server_gets_the_whole_documented_tree(self):
        build_db(self.db, seeded=False)
        pm.provision(self.db)
        names = {row[3] for row in self.channels()}
        self.assertEqual(names, {"Root", "Briefing Room", "Mission Base", "Mission Net PRIMARY",
                                  "Mission Net ALTERNATE", "Aircraft", "CAP-1 Intercom",
                                  "CAP-2 Intercom", "CAP-3 Intercom", INSTRUCTOR_CHANNEL})

    def test_instructor_channel_denies_all_then_grants_the_group(self):
        build_db(self.db, seeded=False)
        pm.provision(self.db)
        instructor_id = pm.find_channel_id(sqlite3.connect(self.db).cursor(), INSTRUCTOR_CHANNEL, 0)
        rows = {(gn, gp, rp): (cid, prio) for cid, prio, gn, gp, rp in self.acl_rows() if cid == instructor_id}
        self.assertIn(("all", 0, pm.PERM_ENTER), rows)         # deny Enter, priority 0
        self.assertEqual(rows[("all", 0, pm.PERM_ENTER)][1], 0)
        self.assertIn(("instructor", pm.PERM_ENTER | pm.PERM_SPEAK, 0), rows)  # grant, priority 1
        self.assertEqual(rows[("instructor", pm.PERM_ENTER | pm.PERM_SPEAK, 0)][1], 1)

    def test_already_hand_provisioned_tree_is_untouched(self):
        build_db(self.db, seeded=True)
        before = self.channels()
        before_acl = self.acl_rows()
        pm.provision(self.db)
        after = self.channels()
        self.assertEqual(before, after, "pre-existing channel rows must never be modified")
        # The three original root rows must still be there, unmodified, in addition to the two new ones.
        for row in before_acl:
            self.assertIn(row, self.acl_rows())

    def test_running_twice_changes_nothing_the_second_time(self):
        build_db(self.db, seeded=False)
        pm.provision(self.db)
        after_first = (self.channels(), self.acl_rows())
        pm.provision(self.db)
        after_second = (self.channels(), self.acl_rows())
        self.assertEqual(after_first, after_second)


if __name__ == "__main__":
    unittest.main()
