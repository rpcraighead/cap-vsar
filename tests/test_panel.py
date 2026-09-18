"""
Tests for the Civil Air Patrol C182T Mission Observer (MO) Air Manager panel.
Validates XML schema, instrument references, geometry, and layout integrity.
"""

import os
import unittest
import xml.etree.ElementTree as ET

PANEL_XML_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "panels",
    "cap-c182t-mo-station",
    "info.xml",
)
AIR_MANAGER_INST_DIR = "/home/ron/Air Manager/instruments/OPEN_DIRECTORY"

EXPECTED_INSTRUMENTS = {
    "MFD": "0b852ee1-6006-4e2b-9cdf-e397b3f16ab1",
    "GMA1347": "1337420b-7420-4843-80eb-9d10c57a97d1",
    "Becker517": "faefb90d-5704-48c7-8deb-c683d94b4eb3",
    "RT600": "d783d409-9bfa-49f2-ad5d-883af29848d6",
    "TDFM136B": "26df5da8-8ce7-4255-bb0e-520453134609",
    "MissionMaster": "d285e0f7-b787-42c7-85fd-ec8990f6db33",
    "MissionCBPanel": "aa9851bc-5ba6-4f5e-a465-d456403fbfc8",
}

class TestMOPanel(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.exists(PANEL_XML_PATH), f"Panel XML not found at {PANEL_XML_PATH}")
        self.tree = ET.parse(PANEL_XML_PATH)
        self.root = self.tree.getroot()

    def test_root_elements(self):
        """Verify panel metadata and essential tags."""
        self.assertEqual(self.root.tag, "panel")
        self.assertEqual(self.root.find("uuid").text, "a4c8e710-5646-49e1-931f-4aeeb51e4490")
        self.assertEqual(self.root.find("position").text, "RIGHT")
        self.assertEqual(self.root.find("aircraftType").text, "PROP")
        self.assertEqual(self.root.find("cockpitType").text, "GLASS")
        self.assertEqual(self.root.find("engineCount").text, "1")

    def test_tier_matches_personal_source(self):
        """PERSONAL (locally-authored) content must declare HOME_USE_STANDARD.

        HOME_USE_PAID / PROFESSIONAL_PAID gate a purchased marketplace
        entitlement - every one of the project's own four instruments uses
        HOME_USE_STANDARD for exactly this reason. A PERSONAL-sourced panel
        that copies the PAID tiers from a licensed reference (e.g. Sim
        Innovations' own 172SP panel) risks Air Manager treating it as
        premium content the Home Use licence doesn't cover.
        """
        source = self.root.find("source").text
        tiers = [t.text for t in self.root.findall(".//tiers/tier")]
        if source == "PERSONAL":
            self.assertEqual(tiers, ["HOME_USE_STANDARD"],
                             f"PERSONAL content should declare HOME_USE_STANDARD, found {tiers}")

    def test_aircraft_model(self):
        """Verify Cessna 182T mapping."""
        aircraft_model = self.root.find(".//aircraftModel")
        self.assertIsNotNone(aircraft_model)
        self.assertEqual(aircraft_model.find("make").text, "Cessna")
        self.assertEqual(aircraft_model.find("model").text, "182T")

    def test_simulator_compatibility_xplane_only(self):
        """Verify panel only declares XPLANE support, not legacy FSX/P3D/FS2020."""
        sims = [s.text for s in self.root.findall(".//flightSimulators/flightSimulator")]
        self.assertEqual(sims, ["XPLANE"], f"Expected only ['XPLANE'], found {sims}")

    def test_layouts_presence(self):
        """Verify Becker 517 and RT-600 layouts exist."""
        layouts = self.root.findall(".//layout")
        self.assertEqual(len(layouts), 2, "Expected exactly 2 layouts")
        layout_uuids = [l.find("uuid").text for l in layouts]
        self.assertIn("e1c8e710-5646-49e1-931f-4aeeb51e4491", layout_uuids)
        self.assertIn("e2c8e710-5646-49e1-931f-4aeeb51e4492", layout_uuids)

    def test_layout_geometry_and_bounds(self):
        """Verify layout dimensions, boundaries, and that instruments don't overlap."""
        layouts = self.root.findall(".//layout")
        for layout in layouts:
            layout_name = layout.find("name").text
            width = int(layout.find("width").text)
            height = int(layout.find("height").text)
            self.assertEqual(width, 1920)
            self.assertEqual(height, 1080)

            inst_boxes = []
            for inst in layout.findall(".//instrument"):
                uuid = inst.find("uuid").text
                x = int(inst.find("x").text)
                y = int(inst.find("y").text)
                w = int(inst.find("width").text)
                h = int(inst.find("height").text)

                # Check inside canvas bounds
                self.assertGreaterEqual(x, 0, f"{uuid} x < 0 in {layout_name}")
                self.assertGreaterEqual(y, 0, f"{uuid} y < 0 in {layout_name}")
                self.assertLessEqual(x + w, width, f"{uuid} exceeds width in {layout_name}")
                self.assertLessEqual(y + h, height, f"{uuid} exceeds height in {layout_name}")

                inst_boxes.append((uuid, x, y, w, h))

            # Test non-overlapping between any pair of instruments
            for i in range(len(inst_boxes)):
                for j in range(i + 1, len(inst_boxes)):
                    u1, x1, y1, w1, h1 = inst_boxes[i]
                    u2, x2, y2, w2, h2 = inst_boxes[j]
                    overlap = (x1 < x2 + w2) and (x1 + w1 > x2) and (y1 < y2 + h2) and (y1 + h1 > y2)
                    self.assertFalse(overlap, f"Instruments {u1} and {u2} overlap in layout {layout_name}!")

    def test_cockpit_authenticity_placement(self):
        """Verify G1000 MFD and Audio Panel positioning relationship."""
        layouts = self.root.findall(".//layout")
        for layout in layouts:
            mfd = None
            audio = None
            for inst in layout.findall(".//instrument"):
                uuid = inst.find("uuid").text
                if uuid == EXPECTED_INSTRUMENTS["MFD"]:
                    mfd = inst
                elif uuid == EXPECTED_INSTRUMENTS["GMA1347"]:
                    audio = inst

            self.assertIsNotNone(mfd, "MFD missing")
            self.assertIsNotNone(audio, "Audio panel missing")

            mfd_x = int(mfd.find("x").text)
            mfd_w = int(mfd.find("width").text)
            audio_x = int(audio.find("x").text)

            # Audio panel must be immediately to the right of MFD
            self.assertGreater(audio_x, mfd_x + mfd_w, "Audio panel must be to the right of MFD")
            # Gap should be small and realistic (< 50px)
            gap = audio_x - (mfd_x + mfd_w)
            self.assertLess(gap, 50, f"Gap between MFD and Audio panel is too large: {gap}px")

            # MFD must have Display unit function = MFD property
            prop_found = False
            streaming_found = False
            for prop in mfd.findall(".//property"):
                name = prop.find("name")
                val = prop.find("value")
                if name is not None and name.text == "Display unit function" and val is not None and val.text == "MFD":
                    prop_found = True
                if name is not None and name.text == "Streaming" and val is not None and val.text == "true":
                    streaming_found = True
            self.assertTrue(prop_found, "MFD must specify 'Display unit function' = 'MFD'")
            self.assertTrue(streaming_found, "MFD must specify 'Streaming' = 'true' in info.xml")

    def test_panel_geometry_cross_check(self):
        """Verify panel_geometry.load_panel_geometry parses info.xml accurately and matches assets generator."""
        import sys
        panel_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "panels", "cap-c182t-mo-station")
        sys.path.insert(0, panel_dir)
        import panel_geometry
        geom = panel_geometry.load_panel_geometry(PANEL_XML_PATH)
        self.assertEqual(geom["uuid"], "a4c8e710-5646-49e1-931f-4aeeb51e4490")
        self.assertEqual(len(geom["layouts"]), 2)
        for layout in geom["layouts"]:
            self.assertEqual(layout["width"], 1920)
            self.assertEqual(layout["height"], 1080)
            self.assertEqual(len(layout["instruments"]), 6)
            mfd = [i for i in layout["instruments"] if i["uuid"] == EXPECTED_INSTRUMENTS["MFD"]][0]
            self.assertEqual(mfd["properties"].get("Streaming"), "true")
            self.assertEqual(mfd["properties"].get("Display unit function"), "MFD")

    def test_installed_instrument_uuids_exist(self):
        """Verify all referenced instruments exist in Air Manager's library."""
        if not os.path.isdir(AIR_MANAGER_INST_DIR):
            self.skipTest(f"Air Manager instruments dir not found at {AIR_MANAGER_INST_DIR}")

        layouts = self.root.findall(".//layout")
        for layout in layouts:
            for inst in layout.findall(".//instrument"):
                uuid = inst.find("uuid").text
                inst_dir = os.path.join(AIR_MANAGER_INST_DIR, uuid)
                self.assertTrue(os.path.isdir(inst_dir), f"Referenced instrument UUID {uuid} does not exist in {AIR_MANAGER_INST_DIR}")

if __name__ == "__main__":
    unittest.main()

