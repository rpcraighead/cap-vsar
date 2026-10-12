"""The X-Plane name allowlist (tests/fixtures/xplane_names.json) stays honest (D3 item 2).

Offline, this checks that the fixture and the Lua under instruments/ agree. On a
machine with X-Plane installed it also checks every name against Laminar's own
DataRefs.txt / Commands.txt, which is what stops an invented dataref (I2-1,
I2-2) from ever reaching the fixture.
"""
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "check_xplane_names", ROOT / "scripts" / "check_xplane_names.py")
check = importlib.util.module_from_spec(spec)
sys.modules["check_xplane_names"] = check
spec.loader.exec_module(check)

XPLANE = Path(os.environ.get("X_PLANE_DIR", Path.home() / "X-Plane 12"))


class OfflineConsistency(unittest.TestCase):
    def test_lua_and_fixture_agree_without_x_plane(self):
        missing = XPLANE / "does-not-exist"
        self.assertEqual(check.main(["--check", "--xplane", str(missing)]), 0)

    def test_fixture_is_only_the_names_we_use(self):
        """Laminar's lists are not committed: the fixture is tiny and has no descriptions."""
        doc = json.loads(check.FIXTURE.read_text())
        self.assertLess(len(doc["datarefs"]) + len(doc["commands"]), 60)
        for meta in doc["datarefs"].values():
            self.assertEqual(set(meta), {"type", "writable"})

    def test_removed_phantom_names_stay_out(self):
        doc = json.loads(check.FIXTURE.read_text())
        for phantom in ("sim/cockpit2/radios/indicators/com1_receiving",
                        "sim/cockpit2/radios/indicators/com2_receiving",
                        "sim/cockpit2/radios/actuators/audio_panel_copilot_ptt"):
            self.assertNotIn(phantom, doc["datarefs"])
        self.assertIn("sim/atc/com1_rx", doc["datarefs"])
        self.assertIn("sim/atc/com2_rx", doc["datarefs"])

    def test_scanner_ignores_comments(self):
        src = '-- "sim/in/a/comment"\nlocal x = "sim/real/name" --[[ "sim/block" ]]\n'
        self.assertEqual(check.lua_strings(src), ["sim/real/name"])


@unittest.skipUnless((XPLANE / "Resources/plugins/DataRefs.txt").is_file(),
                     "X-Plane DataRefs.txt not installed here")
class AgainstXPlane(unittest.TestCase):
    def test_every_name_exists_and_fixture_is_current(self):
        self.assertEqual(check.main(["--check", "--xplane", str(XPLANE)]), 0)


if __name__ == "__main__":
    unittest.main()
