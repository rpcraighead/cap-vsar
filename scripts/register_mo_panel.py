#!/usr/bin/env python3
"""
Register the Civil Air Patrol Cessna 182T MO Station panel into Air Manager's config.sqlite3.

Injects:
1. Panel entries for:
   - Cessna 182T MO Station (Becker 517)
   - Cessna 182T MO Station (RT-600)
2. Corresponding instrument placements:
   - Garmin G1000 MFD (with 'Display unit function' = 'MFD' and 'Streaming' = 'true')
   - Garmin GMA 1347 Audio Panel
   - Becker SAR-DF 517 or RHOTHETA RT-600
   - Technisonic TDFM-136B VHF-FM Radio
3. Development objects for the Create / Edit tab.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import uuid

DB_PATH = os.path.expanduser("~/Air Manager/config.sqlite3")
BACKUP_PATH = os.path.expanduser("~/Air Manager/config.sqlite3.bak")

PANEL_PLUGIN_UUID = "a4c8e710-5646-49e1-931f-4aeeb51e4490"
LAYOUT_BECKER_UUID = "e1c8e710-5646-49e1-931f-4aeeb51e4491"
LAYOUT_RT600_UUID = "e2c8e710-5646-49e1-931f-4aeeb51e4492"

G1000_UUID = "0b852ee1-6006-4e2b-9cdf-e397b3f16ab1"
GMA1347_UUID = "1337420b-7420-4843-80eb-9d10c57a97d1"
BECKER517_UUID = "faefb90d-5704-48c7-8deb-c683d94b4eb3"
RT600_UUID = "d783d409-9bfa-49f2-ad5d-883af29848d6"
TDFM136B_UUID = "26df5da8-8ce7-4255-bb0e-520453134609"


def main():
    if not os.path.exists(DB_PATH):
        print(f"[-] Database not found at {DB_PATH}")
        return 1

    # Check if Air Manager is running
    p = subprocess.run(["pgrep", "-f", "com.siminnovations.airmanager.AirManager"], capture_output=True, text=True)
    is_running = bool(p.stdout.strip())
    if is_running:
        print("[!] Air Manager is currently running.")
        print("[*] Terminating Air Manager process to safely update database...")
        subprocess.run(["pkill", "-f", "com.siminnovations.airmanager.AirManager"])
        import time
        time.sleep(1.5)

    # Make backup
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"[+] Backed up config.sqlite3 to {BACKUP_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Find next panel id
    cur.execute("SELECT MAX(id) FROM panel")
    max_panel_id = cur.fetchone()[0] or 0

    # Find next instrument id
    cur.execute("SELECT MAX(id) FROM instrument")
    max_inst_id = cur.fetchone()[0] or 0

    # Find next instrument_property id
    cur.execute("SELECT MAX(id) FROM instrument_property")
    max_prop_id = cur.fetchone()[0] or 0

    # Find next development_object id
    cur.execute("SELECT MAX(id) FROM development_object")
    max_dev_id = cur.fetchone()[0] or 0

    # Check existing panels
    cur.execute("SELECT id, name, layout_uuid FROM panel WHERE plugin_uuid = ?", (PANEL_PLUGIN_UUID,))
    existing_panels = {row[2]: row[0] for row in cur.fetchall()}

    layouts_to_register = [
        (
            LAYOUT_BECKER_UUID,
            "Cessna 182T MO Station (Becker 517)",
            BECKER517_UUID,
            "Becker SAR-DF 517"
        ),
        (
            LAYOUT_RT600_UUID,
            "Cessna 182T MO Station (RT-600)",
            RT600_UUID,
            "RHOTHETA RT-600"
        ),
    ]

    for layout_uuid, panel_name, df_uuid, df_name in layouts_to_register:
        if layout_uuid in existing_panels:
            panel_id = existing_panels[layout_uuid]
            print(f"[*] Panel already registered: '{panel_name}' (id={panel_id})")
            continue

        max_panel_id += 1
        panel_id = max_panel_id
        inst_panel_uuid = str(uuid.uuid4())

        # Insert Panel
        cur.execute("""
            INSERT INTO panel (
                id, layout_uuid, name, aircraft, description,
                x, y, w, h, locked,
                background_mode, background_color, background_image_path,
                always_on_top, project_id, uuid, auto_start_mode,
                knobster_id, plugin_uuid, click_thru, editable,
                input_mode, headless, "order", background_image, focussable
            ) VALUES (
                ?, ?, ?, 'Cessna 182T', 'Civil Air Patrol Mission Observer Station',
                0, 0, 1920, 1080, 0,
                '3', '#00000000', NULL,
                0, 1, ?, 0,
                NULL, ?, 0, 1,
                3, 0, ?, X'', 0
            )
        """, (panel_id, layout_uuid, panel_name, inst_panel_uuid, PANEL_PLUGIN_UUID, panel_id))
        print(f"[+] Added Panel #{panel_id}: '{panel_name}'")

        # Instruments for this layout:
        # 1. G1000 MFD (1100x715 at x=40, y=100)
        # 2. GMA 1347 Audio (121x715 at x=1155, y=100)
        # 3. DF Head (460x460 at x=1360, y=100)
        # 4. TDFM-136B Radio (560x294 at x=1310, y=580)
        inst_defs = [
            (G1000_UUID, "Generic - Garmin G1000 PFD-MFD overlay", 40, 100, 1100, 715, 1, [
                ("Display unit function", "5", '{\n\t"number_min":\t0,\n\t"number_max":\t0,\n\t"possible_values":\t"Pilot PFD,Copilot PFD,MFD,Aerobask DA62 PFD,Aerobask DA62 MFD",\n\t"columns":\t[]\n}', "MFD", "Select unit functional position", 1),
                ("Streaming", "6", '{\n\t"number_min":\t0,\n\t"number_max":\t0,\n\t"columns":\t[]\n}', "true", "Enable video streaming with X-Plane 12", 2),
                ("Night lighting effect", "6", '{\n\t"number_min":\t0,\n\t"number_max":\t0,\n\t"columns":\t[]\n}', "false", "Dimming effect in combination with Air Manager backlight setting", 3),
            ]),
            (GMA1347_UUID, "CAP Garmin GMA 1347 Audio Panel", 1155, 100, 121, 715, 2, []),
            (df_uuid, df_name, 1360, 100, 460, 460, 3, []),
            (TDFM136B_UUID, "CAP FM Radio (TDFM-136B)", 1310, 580, 560, 294, 4, []),
        ]

        for p_uuid, name, x, y, w, h, order, props in inst_defs:
            max_inst_id += 1
            inst_id = max_inst_id
            inst_inst_uuid = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO instrument (
                    id, uuid, plugin_uuid, name, description,
                    x, y, w, h, aspect_ratio, panel_id, "order"
                ) VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, 1, ?, ?)
            """, (inst_id, inst_inst_uuid, p_uuid, name, x, y, w, h, panel_id, order))

            for prop_name, prop_type, prop_details, prop_val, prop_desc, prop_order in props:
                max_prop_id += 1
                cur.execute("""
                    INSERT INTO instrument_property (
                        id, instrument_id, name, type, type_details, value, description, "order"
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (max_prop_id, inst_id, prop_name, prop_type, prop_details, prop_val, prop_desc, prop_order))

        # Also add to development_object for Create / Edit tab
        max_dev_id += 1
        cur.execute("""
            INSERT OR IGNORE INTO development_object (
                id, plugin_uuid, plugin_type, panel_layout_uuid, name,
                x, y, w, h, pinned, project_id, zoom
            ) VALUES (?, ?, 1, ?, ?, 0, 0, 1920, 1080, 0, 1, 1.0)
        """, (max_dev_id, PANEL_PLUGIN_UUID, layout_uuid, panel_name))

    # Update sequence tables
    cur.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'instrument_property'", (max_prop_id,))
    cur.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'development_object'", (max_dev_id,))

    conn.commit()
    conn.close()

    print("[+] config.sqlite3 successfully updated with MO Station panels!")

    if is_running:
        print("[*] Re-launching Air Manager with new panel configuration...")
        subprocess.Popen(
            ["/home/ron/Documents/Air Manager 4.2 Home use/AirManager.sh"],
            cwd="/home/ron/Documents/Air Manager 4.2 Home use",
            start_new_session=True
        )
        print("[✓] Air Manager launched.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

