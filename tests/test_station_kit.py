"""
Station-kit builder safety (V2-9) and repository hygiene (B1).

`build_station_kit.py --out X` used to run `shutil.rmtree(X)` on whatever X
named. `--out ~` erased a home directory. Deleting a tree is the only
irreversible thing this repo's tooling does, so it gets a test.

    python3 -m pytest tests/test_station_kit.py
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build_station_kit.py"

spec = importlib.util.spec_from_file_location("build_station_kit", SCRIPT)
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


class OutputDirectoryGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_refuses_home(self):
        with self.assertRaises(SystemExit):
            kit.prepare_out_dir(Path.home())

    def test_refuses_the_repo_itself(self):
        with self.assertRaises(SystemExit):
            kit.prepare_out_dir(ROOT)

    def test_refuses_a_populated_directory_it_did_not_create(self):
        target = self.tmp / "precious"
        target.mkdir()
        (target / "data.txt").write_text("someone's work")
        with self.assertRaises(SystemExit):
            kit.prepare_out_dir(target)
        self.assertEqual((target / "data.txt").read_text(), "someone's work",
                         "the guard deleted a directory it should have refused")

    def test_accepts_a_new_directory_and_leaves_a_marker(self):
        target = self.tmp / "kit"
        out = kit.prepare_out_dir(target)
        self.assertTrue(out.is_dir())
        self.assertTrue((out / kit.KIT_MARKER).exists())

    def test_accepts_an_empty_directory(self):
        target = self.tmp / "empty"
        target.mkdir()
        self.assertTrue(kit.prepare_out_dir(target).is_dir())

    def test_replaces_its_own_previous_kit(self):
        target = self.tmp / "kit"
        kit.prepare_out_dir(target)
        (target / "stale.txt").write_text("from the last build")
        kit.prepare_out_dir(target)
        self.assertFalse((target / "stale.txt").exists(),
                         "a rebuild must start from a clean kit directory")
        self.assertTrue((target / kit.KIT_MARKER).exists())

    def test_end_to_end_build_still_works(self):
        target = self.tmp / "cap2"
        kit.build("CAP-2", "http://192.0.2.10:8700", "", target, make_zip=False)
        self.assertTrue((target / "PI_capvsar_df.py").exists())
        ini = (target / "capvsar_station.ini").read_text()
        self.assertIn("callsign = CAP-2", ini)
        self.assertIn("console = http://192.0.2.10:8700", ini)


class VendorManualsAreNotTracked(unittest.TestCase):
    """B1: NOTICE says the manufacturers' manuals are not in the repository.

    They were, for the whole life of the project - .gitignore was added but the
    already-committed files were never removed from the index. This test is
    what makes the NOTICE claim true from here on.
    """

    def test_no_manufacturer_manual_is_tracked(self):
        try:
            out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                                 text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:  # pragma: no cover
            self.skipTest(f"git unavailable: {e}")
        if out.returncode != 0:
            self.skipTest("not a git checkout")
        tracked = out.stdout.splitlines()

        vendor_markers = ("Becker_SARDF517", "RT600_", "TDFM136", "GMA1347_",
                          "docs/gma.txt")
        offenders = [p for p in tracked
                     if any(m in p for m in vendor_markers)
                     and (p.endswith(".pdf") or p.endswith(".txt"))]
        self.assertEqual(offenders, [],
                         "manufacturer documentation is tracked again; NOTICE "
                         "says it is not, and it is not ours to redistribute")


if __name__ == "__main__":
    unittest.main()
