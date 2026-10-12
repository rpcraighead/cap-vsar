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
import sys
import tempfile
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


# B2-10: KNOWN-OPEN, deliberately not fixed in code. This render shows
# Laminar's stock Cessna 172SP mesh in an N429CP livery - the same category of
# question as D-5's stock-MFD tile - and no longer depicts the aircraft the
# package ships. Whether it stays is the maintainer's call; until then it is
# listed here so it is a recorded decision rather than an oversight. Resolving
# it (replace or remove the figure) means deleting the entry, and the test
# below then insists the list is kept honest.
KNOWN_OPEN_THIRD_PARTY_ARTWORK = {
    "docs/figures/manual/fig_c182t_aircraft.png":
        "B2-10: render of Laminar's C172SP mesh; handbook figure 8",
    "website/images/fig_c182t_aircraft.png":
        "B2-10: same render, used by website/index.html",
}


class KnownOpenItems(unittest.TestCase):
    def test_known_open_artwork_is_listed_and_still_tracked(self):
        files = set(tracked_files())
        for path, why in KNOWN_OPEN_THIRD_PARTY_ARTWORK.items():
            self.assertIn(path, files, f"{path} is gone - resolved? remove it from the list ({why})")


class DocsSiteDoesNotRepublishVendorManuals(unittest.TestCase):
    """B2-9: the site is served to participants; the manuals are not ours."""

    VENDOR_NAME = re.compile(r"(RT600|TDFM136|GMA1347|Becker|SARDF517)", re.I)

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_docs_site
        self.site = build_docs_site

    def test_no_vendor_manual_is_in_any_copied_list(self):
        for rel, _label in self.site.PROJECT_PDFS:
            self.assertIsNone(self.VENDOR_NAME.search(rel), f"{rel} is a vendor document")

    def test_every_vendor_manual_has_a_source_url_in_sources_md(self):
        urls = self.site.source_urls(ROOT / "docs" / "SOURCES.md")
        for rel, _label in self.site.VENDOR_PDFS:
            self.assertIn(Path(rel).name, urls, f"docs/SOURCES.md has no URL for {rel}")
            self.assertTrue(urls[Path(rel).name].startswith("https://"))

    def test_built_site_has_no_vendor_pdf_even_when_the_files_are_on_disk(self):
        with tempfile.TemporaryDirectory() as t:
            fake = Path(t, "repo")
            (fake / "docs").mkdir(parents=True)
            for rel, _ in self.site.VENDOR_PDFS + self.site.PROJECT_PDFS:
                (fake / rel).write_bytes(b"%PDF-1.4 fake")
            (fake / "docs" / "SOURCES.md").write_text(
                (ROOT / "docs" / "SOURCES.md").read_text(encoding="utf-8"), encoding="utf-8")
            out = Path(t, "site")
            original = (self.site.REPO, self.site.SECTIONS)
            self.site.REPO, self.site.SECTIONS = fake, []
            try:
                self.site.build(out)
            finally:
                self.site.REPO, self.site.SECTIONS = original
            copied = [p.name for p in out.rglob("*") if p.is_file()]
            self.assertEqual([n for n in copied if self.VENDOR_NAME.search(n)], [], copied)
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("Third-party documents, not hosted here", index)
            self.assertIn("https://rhothetaamerica.com/pdfs/RT-600_Manual.pdf", index)
            # project PDFs are still hosted
            self.assertIn("CAP_V-SAR_AI_Mission_Pilot_CONOPS.pdf", copied)


if __name__ == "__main__":
    unittest.main()
