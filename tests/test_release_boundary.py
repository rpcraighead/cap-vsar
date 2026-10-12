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


# D-5 / B2-10, resolved 2026-10-12: third-party artwork that used to be tracked.
# The Laminar C172SP render (handbook figure 8, website), the CAP iCUT review PDF
# and any composite that embeds the stock Air Manager G1000 tile are gone, and the
# documents that embedded the render were regenerated without it.
REMOVED_THIRD_PARTY = (
    "docs/figures/manual/fig_c182t_aircraft.png",
    "website/images/fig_c182t_aircraft.png",
    "docs/mission-base-radio/icut-review.pdf",
)


class ThirdPartyArtworkIsGone(unittest.TestCase):
    def test_the_files_are_not_tracked(self):
        files = set(tracked_files())
        for path in REMOVED_THIRD_PARTY:
            self.assertNotIn(path, files, f"{path} is third-party material (D-5/B2-10)")

    def test_nothing_still_points_at_them(self):
        needles = ("fig_c182t_aircraft", "icut-review.pdf")
        for path in tracked_files():
            if not path.endswith((".html", ".md", ".py", ".js", ".css")):
                continue
            if path in ("CHANGELOG.md", "docs/BUG_TRACKER.md", "tests/test_release_boundary.py") \
                    or path.startswith("docs/PROJECT_REVIEW"):
                continue            # the record may name what was removed
            text = (ROOT / path).read_text(errors="ignore")
            for needle in needles:
                self.assertNotIn(needle, text, f"{path} still references {needle}")

    def test_generated_documents_do_not_embed_the_render(self):
        import hashlib, zipfile
        removed = {REMOVED_RENDER_SHA256}
        for path in tracked_files():
            if path.endswith((".docx", ".pptx")):
                with zipfile.ZipFile(ROOT / path) as z:
                    for name in z.namelist():
                        if "/media/" in name:
                            self.assertNotIn(hashlib.sha256(z.read(name)).hexdigest(), removed,
                                             f"{path}:{name} embeds a removed third-party image")


# sha-256 of the removed render is enough to recognise it; the bytes are not kept.
REMOVED_RENDER_SHA256 = "037e7304d83aacf835bf753c79d7b3ff601a96482d9a991248d9764deecd176d"


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
