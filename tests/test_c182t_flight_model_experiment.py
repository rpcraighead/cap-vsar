"""Safety checks for isolated ACF calibration candidates."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from c182t_flight_model_experiment import make_candidate  # noqa: E402


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "baseline.acf"
        self.output = self.root / "candidate.acf"
        self.original = (b"I\n1200 Version\nP acf/_tailnum CAP 487\n"
                         b"P _body/0/_part_cd 0.120000000\n"
                         b"P acf/_m_max 3100.000000000\n")
        self.source.write_bytes(self.original)

    def test_candidate_changes_only_the_fuselage_drag_record(self):
        report = make_candidate(self.source, self.output, 0.1)
        self.assertEqual(self.source.read_bytes(), self.original)
        expected = self.original.replace(b"_part_cd 0.120000000", b"_part_cd 0.100000000")
        self.assertEqual(self.output.read_bytes(), expected)
        self.assertEqual(report["status"], "experimental; no flight-model validation")
        with self.assertRaisesRegex(ValueError, "already exists"):
            make_candidate(self.source, self.output, 0.1)

    def test_refuses_a_missing_or_already_modified_baseline(self):
        for data in (self.original.replace(b"CAP 487", b"N499CP"),
                     self.original.replace(b"0.120000000", b"0.150000000"),
                     self.original + b"P _body/0/_part_cd 0.120000000\n"):
            self.source.write_bytes(data)
            with self.assertRaises(ValueError):
                make_candidate(self.source, self.output, 0.1)
            self.assertFalse(self.output.exists())

    def test_refuses_same_path_and_invalid_coefficients(self):
        with self.assertRaisesRegex(ValueError, "differ"):
            make_candidate(self.source, self.source, 0.1)
        for cd in (float("nan"), 0.01, 0.26):
            with self.assertRaises(ValueError):
                make_candidate(self.source, self.output, cd)
            self.assertFalse(self.output.exists())

    def test_refuses_dangling_output_symlink(self):
        self.output.symlink_to(self.root / "missing.acf")
        with self.assertRaisesRegex(ValueError, "already exists"):
            make_candidate(self.source, self.output, 0.1)
        self.assertFalse((self.root / "missing.acf").exists())


if __name__ == "__main__":
    unittest.main()
