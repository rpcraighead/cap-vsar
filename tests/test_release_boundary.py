"""D-4/D-5: third-party artwork must not be tracked or embedded.

Untracking the manuals (D-4) closed only half the question. The page extracts
in docs/figures are the same copyrighted pages, cropped, and the generated
radio reference document embedded four of them into something meant to be
handed to squadron members. The panel preview additionally composited a stock
Sim Innovations instrument straight out of an Air Manager installation.

These checks are the durable half of that fix: the decision is recorded in
docs/FLIGHTGEAR_C182_GPL_PLAN.md and .gitignore, but a decision nothing
enforces is one `git add -f` away from being undone.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The -pNN- in each of these names is the source page of a vendor document.
EXTRACT_RE = re.compile(r"(?:_p\d+|_panel)-?\d*\.png$")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return out.stdout.splitlines()


class ReleaseBoundary(unittest.TestCase):
    def test_no_manufacturer_page_extract_is_tracked(self):
        offenders = [
            f for f in tracked_files()
            if f.startswith("docs/figures/") and "/manual/" not in f
            and EXTRACT_RE.search(f)
        ]
        self.assertEqual(offenders, [], f"vendor page extracts are tracked: {offenders}")

    def test_no_vendor_manual_is_tracked(self):
        offenders = [
            f for f in tracked_files()
            if re.search(r"(RT600|TDFM136|GMA1347|Becker|SARDF517).*\.pdf$", f, re.I)
        ]
        self.assertEqual(offenders, [], f"vendor manuals are tracked: {offenders}")

    def test_the_reference_document_embeds_only_our_own_artwork(self):
        """It cited four manual pages by figure number; now it draws our own."""
        source = (ROOT / "scripts" / "build_radio_reference_doc.py").read_text()
        embedded = re.findall(r'DOCS_DIR / "(figures/[^"]+)"', source)
        for path in embedded:
            self.assertIn("figures/manual/", path,
                          f"reference doc embeds a vendor extract: {path}")

    def test_the_panel_preview_does_not_composite_a_stock_instrument(self):
        """The stock MFD tile came from the operator's Air Manager install."""
        source = (ROOT / "panels" / "cap-c182t-mo-station" / "generate_assets.py").read_text()
        composite = re.search(r"if os\.path\.exists\(inst_prev_path\):", source)
        self.assertIsNotNone(composite, "preview compositing block not found")
        # Whatever it composites must be resolved under instruments/, never the
        # Air Manager instrument base.
        head = source[:composite.start()]
        self.assertNotIn("INST_BASE / uuid", head,
                         "preview still composites from the Air Manager install")
        self.assertIn("_draw_stock_placeholder", head,
                      "non-local instruments must get a placeholder, not vendor art")

    def test_our_own_faceplates_are_still_tracked(self):
        """The replacement artwork has to actually be in the repo."""
        for name in ("becker-sar-df-517", "rhotheta-rt-600",
                     "cap-fm-tdfm-136b", "mo-audio-panel-gma1347"):
            self.assertIn(f"instruments/{name}/resources/faceplate.png", tracked_files())


if __name__ == "__main__":
    unittest.main()
