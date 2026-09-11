#!/usr/bin/env python3
"""
Register or update the Civil Air Patrol Cessna 182T MO Station panel into Air Manager's config.sqlite3.

Single source of truth for panel geometry is panels/cap-c182t-mo-station/info.xml via
panel_geometry.py. Handles:
1. Parameterization of DB and executable paths via capvsar_station.ini, environment, or CLI flags.
2. Confirmation prompt before terminating a running Air Manager instance.
3. In-place updates for existing registered layouts so geometry/property changes propagate.
4. Correct sqlite_sequence synchronization across all four modified tables.
5. Launching Air Manager from configured/detected path rather than hardcoded path.
"""

from __future__ import annotations

import argparse
import configparser
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "panels" / "cap-c182t-mo-station"))
from panel_geometry import load_panel_geometry, KNOWN_INSTRUMENTS


def find_station_ini(cli_path: Path | None = None) -> Path | None:
    """Locate capvsar_station.ini from CLI, env var, repo root, or standard plugin location."""
    candidates = []
    if cli_path:
        candidates.append(cli_path)
    if "CAPVSAR_STATION_INI" in os.environ:
        candidates.append(Path(os.environ["CAPVSAR_STATION_INI"]))
    candidates.extend([
        REPO_ROOT / "capvsar_station.ini",
        Path(__file__).resolve().parent / "capvsar_station.ini",
        Path.home() / "X-Plane 12" / "Resources" / "plugins" / "PythonPlugins" / "capvsar_station.ini",
    ])
    for c in candidates:
        p = Path(c).expanduser()
        if p.is_file():
            return p
    return None


def load_station_config(ini_path: Path | None) -> dict[str, str]:
    """Read key-value pairs from [airmanager] and [station] sections of station ini."""
    config: dict[str, str] = {}
    if ini_path and ini_path.is_file():
        cfg = configparser.ConfigParser()
        cfg.read(str(ini_path))
        for sec in ["airmanager", "station"]:
            if cfg.has_section(sec):
                for k, v in cfg.items(sec):
                    config[k.lower()] = v
    return config


def resolve_db_path(cli_db: Path | None, station_cfg: dict[str, str]) -> Path:
    """Resolve path to Air Manager config.sqlite3."""
    if cli_db:
        return Path(cli_db).expanduser()
    if "db_path" in station_cfg:
        return Path(station_cfg["db_path"]).expanduser()
    if "airmanager_db" in station_cfg:
        return Path(station_cfg["airmanager_db"]).expanduser()
    if "AIR_MANAGER_DB" in os.environ:
        return Path(os.environ["AIR_MANAGER_DB"]).expanduser()

    candidates = [
        Path.home() / "Air Manager" / "config.sqlite3",
        Path.home() / ".local" / "share" / "sim_innovations" / "Air Manager" / "config.sqlite3",
    ]
    if os.name == "nt":
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            candidates.append(Path(localappdata) / "Sim Innovations" / "Air Manager" / "config.sqlite3")
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


def resolve_airmanager_path(cli_path: Path | None, station_cfg: dict[str, str]) -> Path | None:
    """Resolve path to Air Manager launch executable or script."""
    if cli_path:
        return Path(cli_path).expanduser()
    if "airmanager_path" in station_cfg:
        return Path(station_cfg["airmanager_path"]).expanduser()
    if "airmanager_bin" in station_cfg:
        return Path(station_cfg["airmanager_bin"]).expanduser()
    if "AIRMANAGER_BIN" in os.environ:
        return Path(os.environ["AIRMANAGER_BIN"]).expanduser()

    which_bin = shutil.which("AirManager") or shutil.which("airmanager")
    if which_bin:
        return Path(which_bin)

    candidates = [
        Path.home() / "Documents" / "Air Manager 4.2 Home use" / "AirManager.sh",
        Path("/opt/AirManager/AirManager"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def is_air_manager_running() -> bool:
    """Check if Air Manager process is running."""
    p = subprocess.run(["pgrep", "-f", "com.siminnovations.airmanager.AirManager"], capture_output=True, text=True)
    return bool(p.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="Path to Air Manager config.sqlite3")
    parser.add_argument("--airmanager-path", type=Path, help="Path to Air Manager launch executable or script")
    parser.add_argument("--station-ini", type=Path, help="Path to capvsar_station.ini")
    parser.add_argument("-y", "--yes", action="store_true", help="Do not prompt for confirmation before killing Air Manager")
    parser.add_argument("--check", action="store_true", help="Check registration status without modifying database")
    args = parser.parse_args()

    station_ini = find_station_ini(args.station_ini)
    station_cfg = load_station_config(station_ini)
    db_path = resolve_db_path(args.db, station_cfg)
    airmanager_path = resolve_airmanager_path(args.airmanager_path, station_cfg)

    if not db_path.is_file():
        print(f"[-] Database not found at {db_path}")
        return 1

    geom = load_panel_geometry()
    panel_uuid = geom["uuid"]

    # Check if Air Manager is running
    running = is_air_manager_running()
    if running and not args.check:
        print("[!] Air Manager is currently running.")
        if not args.yes:
            if not sys.stdin.isatty():
                print("[-] Air Manager is running and session is non-interactive. Pass -y / --yes to confirm termination.")
                return 1
            reply = input("Terminate Air Manager to safely update database? [y/N]: ").strip().lower()
            if reply not in ("y", "yes"):
                print("[-] Aborted by user.")
                return 1
        print("[*] Terminating Air Manager process...")
        subprocess.run(["pkill", "-f", "com.siminnovations.airmanager.AirManager"])
        time.sleep(1.5)

    if args.check:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT id, layout_uuid, name FROM panel WHERE plugin_uuid = ?", (panel_uuid,))
        existing = {row[1]: row[0] for row in cur.fetchall()}
        missing = [l["uuid"] for l in geom["layouts"] if l["uuid"] not in existing]
        conn.close()
        if missing:
            print(f"[-] Panel requires registration (missing layouts: {missing})")
            return 1
        print(f"[+] All {len(geom['layouts'])} MO Station layouts are registered in {db_path}")
        return 0

    # Backup database
    backup_path = db_path.with_suffix(".sqlite3.bak")
    shutil.copy2(db_path, backup_path)
    print(f"[+] Backed up config.sqlite3 to {backup_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Determine next IDs
    cur.execute("SELECT COALESCE(MAX(id), 0) FROM panel")
    max_panel_id = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(MAX(id), 0) FROM instrument")
    max_inst_id = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(MAX(id), 0) FROM instrument_property")
    max_prop_id = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(MAX(id), 0) FROM development_object")
    max_dev_id = cur.fetchone()[0]

    # Inspect panel table columns
    cur.execute("PRAGMA table_info(panel)")
    panel_table_cols = {row[1] for row in cur.fetchall()}

    cur.execute("SELECT id, layout_uuid FROM panel WHERE plugin_uuid = ?", (panel_uuid,))
    existing_panels = {row[1]: row[0] for row in cur.fetchall()}

    for layout in geom["layouts"]:
        layout_uuid = layout["uuid"]
        layout_name = layout["name"]

        if layout_uuid in existing_panels:
            panel_id = existing_panels[layout_uuid]
            cur.execute("""
                UPDATE panel
                SET name = ?, aircraft = ?, description = ?, w = ?, h = ?
                WHERE id = ?
            """, (layout_name, geom["aircraft"], geom["description"], layout["width"], layout["height"], panel_id))
            # Delete stale instruments & properties for this panel
            cur.execute("DELETE FROM instrument_property WHERE instrument_id IN (SELECT id FROM instrument WHERE panel_id = ?)", (panel_id,))
            cur.execute("DELETE FROM instrument WHERE panel_id = ?", (panel_id,))
            print(f"[*] Updated existing Panel #{panel_id}: '{layout_name}'")
        else:
            max_panel_id += 1
            panel_id = max_panel_id
            inst_panel_uuid = str(uuid.uuid4())

            panel_fields = {
                "id": panel_id,
                "layout_uuid": layout_uuid,
                "name": layout_name,
                "aircraft": geom["aircraft"],
                "description": geom["description"],
                "x": 0,
                "y": 0,
                "w": layout["width"],
                "h": layout["height"],
                "locked": 0,
                "background_mode": "3",
                "background_color": "#00000000",
                "background_image_path": None,
                "always_on_top": 0,
                "project_id": 1,
                "uuid": inst_panel_uuid,
                "auto_start_mode": 0,
                "knobster_id": None,
                "plugin_uuid": panel_uuid,
                "click_thru": 0,
                "editable": 1,
                "input_mode": 3,
                "headless": 0,
                "order": panel_id,
                "background_image": b"",
                "focussable": 0,
            }

            cols_to_insert = [c for c in panel_fields if c in panel_table_cols]
            col_sql = ", ".join(f'"{c}"' for c in cols_to_insert)
            placeholders = ", ".join("?" for _ in cols_to_insert)
            vals = [panel_fields[c] for c in cols_to_insert]

            cur.execute(f"INSERT INTO panel ({col_sql}) VALUES ({placeholders})", vals)
            print(f"[+] Added Panel #{panel_id}: '{layout_name}'")

        # Insert instruments and properties for this layout
        for inst in layout["instruments"]:
            max_inst_id += 1
            inst_id = max_inst_id
            inst_instance_uuid = str(uuid.uuid4())

            cur.execute("""
                INSERT INTO instrument (
                    id, uuid, plugin_uuid, name, description,
                    x, y, w, h, aspect_ratio, panel_id, "order"
                ) VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, 1, ?, ?)
            """, (inst_id, inst_instance_uuid, inst["uuid"], inst["name"],
                  inst["x"], inst["y"], inst["width"], inst["height"], panel_id, inst["order"]))

            known_info = KNOWN_INSTRUMENTS.get(inst["uuid"], {})
            prop_meta = known_info.get("property_meta", {})

            for p_order, (p_name, p_val) in enumerate(inst["properties"].items(), start=1):
                max_prop_id += 1
                meta = prop_meta.get(p_name, {})
                p_type = meta.get("type", "6" if p_val in ("true", "false") else "5")
                p_details = meta.get("details", '{\n\t"number_min":\t0,\n\t"number_max":\t0,\n\t"columns":\t[]\n}')
                p_desc = meta.get("description", p_name)
                prop_order = meta.get("order", p_order)

                cur.execute("""
                    INSERT INTO instrument_property (
                        id, instrument_id, name, type, type_details, value, description, "order"
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (max_prop_id, inst_id, p_name, p_type, p_details, p_val, p_desc, prop_order))

        # Update or insert development_object
        cur.execute("SELECT id FROM development_object WHERE panel_layout_uuid = ?", (layout_uuid,))
        dev_row = cur.fetchone()
        if dev_row:
            cur.execute("""
                UPDATE development_object
                SET name = ?, w = ?, h = ?
                WHERE panel_layout_uuid = ?
            """, (layout_name, layout["width"], layout["height"], layout_uuid))
        else:
            max_dev_id += 1
            cur.execute("""
                INSERT INTO development_object (
                    id, plugin_uuid, plugin_type, panel_layout_uuid, name,
                    x, y, w, h, pinned, project_id, zoom
                ) VALUES (?, ?, 1, ?, ?, 0, 0, ?, ?, 0, 1, 1.0)
            """, (max_dev_id, panel_uuid, layout_uuid, layout_name, layout["width"], layout["height"]))

    # Synchronize sqlite_sequence for all 4 tables
    for table, max_id in [
        ("panel", max_panel_id),
        ("instrument", max_inst_id),
        ("instrument_property", max_prop_id),
        ("development_object", max_dev_id),
    ]:
        cur.execute("SELECT 1 FROM sqlite_sequence WHERE name = ?", (table,))
        if cur.fetchone():
            cur.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (max_id, table))
        else:
            cur.execute("INSERT OR REPLACE INTO sqlite_sequence (name, seq) VALUES (?, ?)", (table, max_id))

    conn.commit()
    conn.close()

    print("[+] config.sqlite3 successfully updated with MO Station panels!")

    if running:
        if airmanager_path and airmanager_path.is_file():
            print(f"[*] Re-launching Air Manager ({airmanager_path})...")
            subprocess.Popen(
                [str(airmanager_path)],
                cwd=str(airmanager_path.parent),
                start_new_session=True
            )
            print("[✓] Air Manager launched.")
        else:
            print("[*] Air Manager was terminated; please restart Air Manager manually.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
