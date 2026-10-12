"""Docs and artwork generators must not depend on one machine (B2-7, B2-8, B2-9)."""
from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def tracked(prefix: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", prefix], cwd=ROOT, capture_output=True, text=True)
    return out.stdout.splitlines()


# Engineering notes, resume prompts and the review itself quote local paths
# ("the file lives at /home/ron/..."). They are not published or generated, so
# they are KNOWN-OPEN rather than fixed here; the list may only shrink. Anything
# new under docs/ that bakes in a workstation path fails the test below.
KNOWN_LOCAL_PATH_DOCS = {
    "docs/BUG_TRACKER.md",
    "docs/FLIGHT_MODES_IMPLEMENTATION_STATUS.md",
    "docs/FLIGHT_MODE_ARCHITECTURE_REVIEW_2026-09-17.md",
    "docs/PHASE0_DF_PLUGIN.md",
    "docs/PROJECT_REVIEW_2026-10-10.md",
    "docs/RADIO_FIDELITY_AUDIT.md",
    "docs/bugs/CLAUDE_RESUME_C182_DIMENSIONS.md",
    "docs/bugs/CODEX_RESUME_C182_HARNESS.md",
    "docs/bugs/FLIGHT_MODES_OVERNIGHT_PROMPT.md",
    "docs/bugs/tracker.json",
    "docs/ragd/ragd_ingest.py",
    "docs/ragd/vaultnotes/AsBuilt_CAPVSAR.md",
    # Hash-chained trial records: the KSAN proceed record cites the landing
    # record's SHA-256 and the restart record cites proceed's, so these two
    # cannot be edited without breaking that chain. Every other evidence file
    # had its workstation paths rewritten to ~/ on 2026-10-12.
    "docs/evidence/ai_pilot_ksan_landing_20261010.json",
    "docs/evidence/ai_pilot_ksan_proceed_20261010.json",
}


class NoWorkstationPathsInDocs(unittest.TestCase):
    def contains(self, rel):
        return "/home/ron/" in (ROOT / rel).read_text(encoding="utf-8", errors="replace")

    def test_no_tracked_doc_outside_the_known_list_names_a_home_directory(self):
        offenders = [f for f in tracked("docs") if f not in KNOWN_LOCAL_PATH_DOCS and self.contains(f)]
        self.assertEqual(offenders, [], "a workstation path was baked into a doc")

    def test_the_published_documents_are_clean(self):
        """The handbook and radio reference are handed to other people."""
        for rel in ("docs/manual/CAP_VSAR_Flight_Operations_Handbook.html",
                    "docs/RADIO_FEATURES_AND_USE_CASES.md"):
            self.assertFalse(self.contains(rel), rel)

    def test_the_known_list_only_shrinks(self):
        stale = [f for f in sorted(KNOWN_LOCAL_PATH_DOCS) if not (ROOT / f).exists() or not self.contains(f)]
        self.assertEqual(stale, [], "fixed? then remove it from KNOWN_LOCAL_PATH_DOCS")

    def test_the_generators_do_not_bake_a_path_into_their_output(self):
        for name in ("generate_manual.py", "build_radio_reference_doc.py", "build_docs_site.py"):
            self.assertNotIn("/home/ron/", (SCRIPTS / name).read_text(), name)


class GenerateManual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.gm = importlib.import_module("generate_manual")
        except ModuleNotFoundError as exc:      # Pillow
            raise unittest.SkipTest(str(exc))

    def test_paths_are_relative_to_this_checkout(self):
        self.assertEqual(Path(self.gm.REPO_ROOT), ROOT)
        self.assertEqual(Path(self.gm.MANUAL_DIR), ROOT / "docs" / "manual")
        self.assertEqual(Path(self.gm.FIGURES_DIR), ROOT / "docs" / "figures" / "manual")

    def test_html_figure_links_are_relative_and_resolve(self):
        srcs = re.findall(r'<img[^>]+src="([^"]+)"', self.gm.HTML_CONTENT)
        self.assertGreaterEqual(len(srcs), 7)       # 7 since the Laminar render (figure 8) was removed
        for src in srcs:
            self.assertFalse(src.startswith("/"), src)
            self.assertNotIn("://", src)
            self.assertTrue((ROOT / "docs" / "manual" / src).resolve().is_file(), src)

    def test_tracked_html_is_what_the_script_generates(self):
        tracked_html = (ROOT / "docs/manual/CAP_VSAR_Flight_Operations_Handbook.html").read_text()
        self.assertEqual(tracked_html, self.gm.HTML_CONTENT,
                         "regenerate: python3 scripts/generate_manual.py --html-only")

    def test_no_copy_to_a_personal_folder_unless_asked(self):
        with tempfile.TemporaryDirectory() as d, \
                patch.object(self.gm, "HTML_PATH", os.path.join(d, "m.html")), \
                patch.dict(os.environ, {}, clear=False), \
                patch.object(self.gm.shutil, "copy2") as copy:
            os.environ.pop("CAPVSAR_MANUAL_COPY_DIR", None)
            self.gm.main(["--html-only"])
            copy.assert_not_called()
            self.assertTrue(Path(d, "m.html").is_file())

    def test_copy_target_is_an_explicit_flag(self):
        source = (SCRIPTS / "generate_manual.py").read_text()
        self.assertIn("--copy-to", source)
        self.assertIn("CAPVSAR_MANUAL_COPY_DIR", source)


class FontLookup(unittest.TestCase):
    """B2-8: no hard-coded Debian font paths."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.art = importlib.import_module("make_df_artwork")
        except (ModuleNotFoundError, SystemExit) as exc:
            raise unittest.SkipTest(f"make_df_artwork not importable here: {exc}")

    def test_first_existing_candidate_wins(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            Path(b, "Arimo-Bold.ttf").write_bytes(b"x")
            got = self.art.find_font(("LiberationSans-Bold.ttf", "Arimo-Bold.ttf"), "NOPE_ENV", dirs=(a, b))
            self.assertEqual(got, os.path.join(b, "Arimo-Bold.ttf"))

    def test_env_override_wins_and_must_exist(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "my.ttf")
            f.write_bytes(b"x")
            with patch.dict(os.environ, {"FONT_T": str(f)}):
                self.assertEqual(self.art.find_font(("a.ttf",), "FONT_T", dirs=()), str(f))
            with patch.dict(os.environ, {"FONT_T": str(f) + ".missing"}):
                with self.assertRaises(SystemExit):
                    self.art.find_font(("a.ttf",), "FONT_T", dirs=())

    def test_missing_font_error_says_what_to_install(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as cm:
                self.art.find_font(("LiberationSans-Bold.ttf",), "NOPE_ENV", dirs=(d,))
        msg = str(cm.exception)
        self.assertIn("fonts-liberation", msg)
        self.assertIn("NOPE_ENV", msg)
        self.assertIn(os.path.join(d, "LiberationSans-Bold.ttf"), msg)

    def test_no_hardcoded_font_path_remains_outside_the_candidate_list(self):
        source = (SCRIPTS / "make_df_artwork.py").read_text()
        self.assertNotRegex(source, r'(?m)^FONT_(BOLD|REG)\s*=\s*"/usr')


class DocsDependenciesAreDeclared(unittest.TestCase):
    def test_generator_imports_appear_in_requirements_docs(self):
        reqs = (ROOT / "requirements-docs.txt").read_text().lower()
        for needed in ("python-docx", "markdown", "pillow"):
            self.assertIn(needed, reqs)

    def test_dev_requirements_pull_in_every_service_and_the_test_tools(self):
        reqs = (ROOT / "requirements-dev.txt").read_text()
        for svc in ("exercise", "flightplanner", "board"):
            self.assertIn(f"-r services/{svc}/requirements.txt", reqs)
            self.assertTrue((ROOT / "services" / svc / "requirements.txt").is_file())
        for pkg in ("pytest", "httpx", "numpy", "Pillow"):
            self.assertRegex(reqs, rf"(?m)^{pkg}\b")


if __name__ == "__main__":
    unittest.main()
