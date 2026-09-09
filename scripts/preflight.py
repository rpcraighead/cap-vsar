#!/usr/bin/env python3
"""
Pre-exercise smoke check for the CAP V-SAR stack (O-6).

Checks the four things that can quietly be broken on exercise morning with
nothing loud enough to notice beforehand: the exercise console's own health
endpoint, the Mumble channel tree, the flight planner's map tile source, and
the browser radio's CA certificate. Exits 0 only if every check passes; each
failure prints exactly what's wrong and, where there's an obvious one, the
fix.

Usage:
    python3 scripts/preflight.py [--host HOST] [--mumble-db PATH]

Run this from ms01 (or anywhere on the LAN, with --host) before an exercise,
and again if anything about the stack changes mid-day.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "exercise"))
from app.mumble_channels import INSTRUCTOR_CHANNEL, walk_tree  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "", fix: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)
        if fix:
            print(f"        fix: {fix}")


def check_console_health(host: str) -> None:
    url = f"http://{host}:8700/api/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            check("exercise console /api/health", resp.status == 200, f"HTTP {resp.status}")
    except (urllib.error.URLError, OSError) as exc:
        check("exercise console /api/health", False, str(exc),
              fix="docker compose ps exercise; docker compose logs exercise")


def check_mumble_channels(db_path: Path) -> None:
    if not db_path.exists():
        check("mumble channel tree", False, f"{db_path} does not exist",
              fix="docker compose up -d mumble, then scripts/provision_mumble.py")
        return
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        cur = con.cursor()
        cur.execute("SELECT name FROM channels WHERE server_id=1")
        present = {row[0] for row in cur.fetchall()}
        con.close()
    except sqlite3.OperationalError as exc:
        check("mumble channel tree", False, f"could not read {db_path}: {exc}",
              fix="is Mumble mid-write? re-run in a few seconds")
        return
    expected = {name for name, _ in walk_tree()}
    missing = expected - present
    check("mumble channel tree", not missing,
          "all channels present" if not missing else f"missing: {sorted(missing)}",
          fix="scripts/provision_mumble.py (server stopped)")
    check(f"{INSTRUCTOR_CHANNEL!r} ACL provisioned", INSTRUCTOR_CHANNEL not in missing and _has_instructor_acl(db_path),
          fix="scripts/provision_mumble.py (server stopped)")


def _has_instructor_acl(db_path: Path) -> bool:
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        cur = con.cursor()
        cur.execute("SELECT channel_id FROM channels WHERE server_id=1 AND name=?", (INSTRUCTOR_CHANNEL,))
        row = cur.fetchone()
        if row is None:
            return False
        cur.execute("SELECT 1 FROM acl WHERE server_id=1 AND channel_id=? AND group_name='all'", (row[0],))
        found = cur.fetchone() is not None
        con.close()
        return found
    except sqlite3.OperationalError:
        return False


def check_tile_reachability() -> None:
    # The service's own tile pyramid doesn't necessarily include z/y/x=0/0/0
    # (a 404 there doesn't mean the service is down), so this hits the
    # MapServer's metadata endpoint instead - always present if the service
    # is up, regardless of what zoom levels its cache actually covers.
    url = "https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services/VFR_Sectional/MapServer?f=json"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            check("VFR sectional tile source reachable", resp.status == 200, f"HTTP {resp.status}")
    except (urllib.error.URLError, OSError) as exc:
        check("VFR sectional tile source reachable", False, str(exc),
              fix="check this host's internet egress; charts render blank without it")


def check_ca_cert() -> None:
    cert = ROOT / "services" / "exercise" / "radio-public" / "mission-base-ca.crt"
    ok = cert.exists() and cert.stat().st_size > 0
    check("browser radio CA certificate published", ok, str(cert),
          fix="scripts/deploy.sh (publishes it from the running radio-https container)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1", help="exercise console host (default: 127.0.0.1)")
    parser.add_argument("--mumble-db", type=Path, default=ROOT / "mumble" / "data" / "mumble-server.sqlite")
    args = parser.parse_args()

    print("== CAP V-SAR preflight ==")
    check_console_health(args.host)
    check_mumble_channels(args.mumble_db)
    check_tile_reachability()
    check_ca_cert()

    print()
    if FAILURES:
        print(f"FAILED: {', '.join(FAILURES)}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
