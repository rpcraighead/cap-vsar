"""
Single source of truth for MO Station panel geometry, parsed from info.xml.

Used by generate_assets.py, register_mo_panel.py, and test_panel.py so that
any layout or property change made in info.xml propagates consistently
across previews, SQLite registration, and tests.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

PANEL_DIR = Path(__file__).resolve().parent
INFO_XML = PANEL_DIR / "info.xml"

# Canonical instrument definitions and property metadata for Air Manager
KNOWN_INSTRUMENTS = {
    "0b852ee1-6006-4e2b-9cdf-e397b3f16ab1": {
        "short_name": "MFD",
        "name": "Generic - Garmin G1000 PFD-MFD overlay",
        "property_meta": {
            "Display unit function": {
                "type": "5",
                "details": '{\n\t"number_min":\t0,\n\t"number_max":\t0,\n\t"possible_values":\t"Pilot PFD,Copilot PFD,MFD,Aerobask DA62 PFD,Aerobask DA62 MFD",\n\t"columns":\t[]\n}',
                "description": "Select unit functional position",
                "order": 1,
            },
            "Streaming": {
                "type": "6",
                "details": '{\n\t"number_min":\t0,\n\t"number_max":\t0,\n\t"columns":\t[]\n}',
                "description": "Enable video streaming with X-Plane 12",
                "order": 2,
            },
            "Night lighting effect": {
                "type": "6",
                "details": '{\n\t"number_min":\t0,\n\t"number_max":\t0,\n\t"columns":\t[]\n}',
                "description": "Dimming effect in combination with Air Manager backlight setting",
                "order": 3,
            },
        },
    },
    "1337420b-7420-4843-80eb-9d10c57a97d1": {
        "short_name": "GMA1347",
        "name": "CAP Garmin GMA 1347 Audio Panel",
        "property_meta": {},
    },
    "faefb90d-5704-48c7-8deb-c683d94b4eb3": {
        "short_name": "Becker517",
        "name": "Becker SAR-DF 517",
        "property_meta": {},
    },
    "d783d409-9bfa-49f2-ad5d-883af29848d6": {
        "short_name": "RT600",
        "name": "RHOTHETA RT-600",
        "property_meta": {},
    },
    "26df5da8-8ce7-4255-bb0e-520453134609": {
        "short_name": "TDFM136B",
        "name": "CAP FM Radio (TDFM-136B)",
        "property_meta": {},
    },
}


def load_panel_geometry(xml_path: Path | str = INFO_XML) -> dict:
    """Parse panel info.xml and return structured panel geometry and metadata."""
    xml_path = Path(xml_path)
    if not xml_path.is_file():
        raise FileNotFoundError(f"Panel info.xml not found at {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    panel_uuid = root.findtext("uuid", "")
    panel_name = root.findtext("name", "")
    description = root.findtext("description", "")
    aircraft_elem = root.find(".//aircraftModel")
    aircraft_make = aircraft_elem.findtext("make", "Cessna") if aircraft_elem is not None else "Cessna"
    aircraft_model = aircraft_elem.findtext("model", "182T") if aircraft_elem is not None else "182T"
    aircraft = f"{aircraft_make} {aircraft_model}".strip()

    layouts = []
    for l_elem in root.findall(".//layout"):
        l_uuid = l_elem.findtext("uuid", "")
        l_name = l_elem.findtext("name", "")
        l_desc = l_elem.findtext("description", "")
        w = int(l_elem.findtext("width", "1920"))
        h = int(l_elem.findtext("height", "1080"))

        instruments = []
        for order, i_elem in enumerate(l_elem.findall(".//instrument"), start=1):
            i_uuid = i_elem.findtext("uuid", "")
            x = int(i_elem.findtext("x", "0"))
            y = int(i_elem.findtext("y", "0"))
            iw = int(i_elem.findtext("width", "0"))
            ih = int(i_elem.findtext("height", "0"))

            props = {}
            for p_elem in i_elem.findall(".//property"):
                p_name = p_elem.findtext("name", "")
                p_val = p_elem.findtext("value", "")
                if p_name:
                    props[p_name] = p_val

            known = KNOWN_INSTRUMENTS.get(i_uuid, {})
            name = known.get("name", f"Instrument {i_uuid[:8]}")
            short_name = known.get("short_name", i_uuid[:8])

            instruments.append({
                "uuid": i_uuid,
                "name": name,
                "short_name": short_name,
                "x": x,
                "y": y,
                "width": iw,
                "height": ih,
                "order": order,
                "properties": props,
            })

        layouts.append({
            "uuid": l_uuid,
            "name": l_name,
            "description": l_desc,
            "width": w,
            "height": h,
            "instruments": instruments,
        })

    return {
        "uuid": panel_uuid,
        "name": panel_name,
        "description": description,
        "aircraft": aircraft,
        "layouts": layouts,
    }

