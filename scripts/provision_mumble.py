#!/usr/bin/env python3
"""
Idempotently provision the CAP V-SAR Mumble channel tree and the
Instructor/SET ACL directly in mumble-server.sqlite (O-4).

Murmur has no config-file channel definition. The tree documented in
docs/MUMBLE_CHANNELS.md was originally created by hand, server stopped, by
inserting rows into mumble-server.sqlite. This script does the same thing,
reading the tree from services/exercise/app/mumble_channels.py so it can
never independently drift from what radio.py expects to find there - which
was O-4's actual complaint, not that the tree was undocumented.

It also finishes MUMBLE_CHANNELS.md's one remaining manual step: an ACL on
"Instructor - SET" denying Enter to everyone, with an "instructor" group
carved out to grant it back to. Adding real people to that group still has
to happen by hand (a SuperUser adding registered users to a group) - nothing
short of a live admin session can do that part.

The server MUST be stopped while this runs: Murmur caches channel/ACL state
in memory and won't notice a raw sqlite edit underneath it. Every write here
first checks whether the exact row it would create already exists, so running
this against an already-provisioned database - or running it twice - changes
nothing on the second pass.

Usage:
    docker compose stop mumble
    python3 scripts/provision_mumble.py mumble/data/mumble-server.sqlite
    docker compose start mumble
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "exercise"))
from app.mumble_channels import INSTRUCTOR_CHANNEL, walk_tree  # noqa: E402

SERVER_ID = 1  # Murmur's default single virtual server

# Murmur ChanACL::Perm bits, from src/ACL.h in mumble-voip/mumble.
PERM_ENTER = 0x4
PERM_SPEAK = 0x8

INSTRUCTOR_GROUP = "instructor"


def find_channel_id(cur, name, parent_id):
    cur.execute(
        "SELECT channel_id FROM channels WHERE server_id=? AND name=? AND parent_id IS ?",
        (SERVER_ID, name, parent_id),
    )
    row = cur.fetchone()
    return row[0] if row else None


def root_channel_id(cur):
    cur.execute("SELECT channel_id FROM channels WHERE server_id=? AND parent_id IS NULL", (SERVER_ID,))
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("No root channel found - is this really a Murmur mumble-server.sqlite?")
    return row[0]


def next_channel_id(cur):
    cur.execute("SELECT COALESCE(MAX(channel_id), 0) FROM channels WHERE server_id=?", (SERVER_ID,))
    return cur.fetchone()[0] + 1


def ensure_channel(cur, name, parent_id):
    existing = find_channel_id(cur, name, parent_id)
    if existing is not None:
        return existing, False
    cid = next_channel_id(cur)
    cur.execute(
        "INSERT INTO channels (server_id, channel_id, parent_id, name, inheritacl) VALUES (?, ?, ?, ?, 1)",
        (SERVER_ID, cid, parent_id, name),
    )
    return cid, True


def ensure_group(cur, name, channel_id):
    cur.execute(
        "SELECT group_id FROM groups WHERE server_id=? AND name=? AND channel_id=?",
        (SERVER_ID, name, channel_id),
    )
    row = cur.fetchone()
    if row:
        return row[0], False
    cur.execute(
        "INSERT INTO groups (server_id, name, channel_id, inherit, inheritable) VALUES (?, ?, ?, 1, 1)",
        (SERVER_ID, name, channel_id),
    )
    return cur.lastrowid, True


def ensure_acl(cur, channel_id, group_name, priority, grantpriv, revokepriv, apply_here=1, apply_sub=1):
    cur.execute(
        "SELECT 1 FROM acl WHERE server_id=? AND channel_id=? AND group_name=? AND user_id IS NULL",
        (SERVER_ID, channel_id, group_name),
    )
    if cur.fetchone():
        return False
    cur.execute(
        "INSERT INTO acl (server_id, channel_id, priority, user_id, group_name, apply_here, apply_sub, "
        "grantpriv, revokepriv) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?)",
        (SERVER_ID, channel_id, priority, group_name, apply_here, apply_sub, grantpriv, revokepriv),
    )
    return True


def provision(db_path: Path) -> None:
    if not db_path.exists():
        raise SystemExit(f"{db_path} does not exist - is this the right mumble/data volume?")
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    try:
        root = root_channel_id(cur)

        created_channels = []
        for name, parent_path in walk_tree():
            parent_id = root
            for ancestor in parent_path:
                found = find_channel_id(cur, ancestor, parent_id)
                if found is None:
                    raise RuntimeError(f"Expected ancestor channel {ancestor!r} to already exist")
                parent_id = found
            _, made = ensure_channel(cur, name, parent_id)
            if made:
                created_channels.append(name)

        instructor_id = find_channel_id(cur, INSTRUCTOR_CHANNEL, root)
        if instructor_id is None:
            raise RuntimeError(f"{INSTRUCTOR_CHANNEL!r} was not created - tree/provisioning mismatch")

        _, group_made = ensure_group(cur, INSTRUCTOR_GROUP, root)
        # Priority matters here: a lower-priority broad deny, overridden for
        # the higher-priority group an instructor is actually a member of -
        # per mumble.info/documentation/administration/acl, later (higher
        # priority) rules override earlier ones for the same permission bit.
        deny_made = ensure_acl(cur, instructor_id, "all", priority=0, grantpriv=0, revokepriv=PERM_ENTER)
        grant_made = ensure_acl(cur, instructor_id, INSTRUCTOR_GROUP, priority=1,
                                 grantpriv=PERM_ENTER | PERM_SPEAK, revokepriv=0)

        con.commit()
    finally:
        con.close()

    print(f"Channels created: {created_channels or '(none - already provisioned)'}")
    print(f"'{INSTRUCTOR_GROUP}' group: {'created' if group_made else 'already existed'}")
    print(f"{INSTRUCTOR_CHANNEL!r} ACL, deny Enter to @all: {'added' if deny_made else 'already present'}")
    print(f"{INSTRUCTOR_CHANNEL!r} ACL, grant Enter+Speak to @{INSTRUCTOR_GROUP}: "
          f"{'added' if grant_made else 'already present'}")
    print()
    print("Remaining manual step, cannot be automated: a SuperUser must add the")
    print(f"actual instructor accounts to the '{INSTRUCTOR_GROUP}' group after they")
    print("first connect and register. See docs/MUMBLE_CHANNELS.md.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("database", type=Path, help="path to mumble-server.sqlite, server stopped")
    args = parser.parse_args()
    provision(args.database)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
