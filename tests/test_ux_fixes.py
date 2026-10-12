"""Defects found in the 2026-10-11 UI walkthrough (docs/UX_REVIEW_2026-10-11.md §2)."""
import os
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_console import BEACON, INSTRUCTOR, PLUGIN, build_app, run_sortie  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class _Nesting(HTMLParser):
    """Parent id of every element that has an id, following the parser's own nesting."""
    VOID = {"meta", "link", "br", "img", "input", "hr", "source", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack, self.parent_of = [], {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.parent_of[a["id"]] = next((i for t, i in reversed(self.stack) if i), None)
        if tag not in self.VOID:
            self.stack.append((tag, a.get("id")))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


class PlannerModalsAreSiblings(unittest.TestCase):
    def test_sar_modal_is_not_inside_the_hidden_db_modal(self):
        """U-1: an unclosed div nested the SAR generator in a display:none modal,
        so the SAR button did nothing."""
        p = _Nesting()
        p.feed((ROOT / "services/flightplanner/templates/index.html").read_text())
        for modal in ("modal-sar", "modal-db", "modal-perf", "modal-wb", "modal-ref"):
            self.assertIsNone(p.parent_of.get(modal, "missing"),
                              f"{modal} is nested inside #{p.parent_of.get(modal)}")


class BadgesRender(unittest.TestCase):
    def setUp(self):
        self.main, self.client, self.db = build_app(instructor=INSTRUCTOR)
        self.instr = {"X-CAPVSAR-Token": INSTRUCTOR}

    def tearDown(self):
        os.unlink(self.db)

    def seat(self):
        r = self.client.post("/api/setup", headers=self.instr, json={
            "exercise_name": "Badge test",
            "aircraft": [{"callsign": "CAP 487", "crew": ["observer"]}], "staff": []})
        self.assertEqual(r.status_code, 200, r.text)
        return [x for x in r.json()["roster"] if x["role"] == "aircrew"][0]

    def test_badge_is_an_svg_qr_of_the_join_link(self):
        seat = self.seat()
        r = self.client.get(f"/api/setup/badge/{seat['id']}.svg",
                            params={"origin": "http://testserver"}, headers=self.instr)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["content-type"].split(";")[0], "image/svg+xml")
        self.assertIn("<svg", r.text)
        self.assertIn("no-store", r.headers["cache-control"])

    def test_badge_needs_the_instructor_and_a_matching_origin(self):
        seat = self.seat()
        self.assertIn(self.client.get(f"/api/setup/badge/{seat['id']}.svg",
                                      params={"origin": "http://testserver"}).status_code, (401, 403))
        self.assertEqual(self.client.get(f"/api/setup/badge/{seat['id']}.svg",
                                         params={"origin": "https://attacker.example"},
                                         headers=self.instr).status_code, 400)
        self.assertEqual(self.client.get("/api/setup/badge/nope.svg",
                                         params={"origin": "http://testserver"},
                                         headers=self.instr).status_code, 404)

    def test_the_page_asks_the_server_for_badges(self):
        js = (ROOT / "services/exercise/app/static/setup.js").read_text()
        self.assertIn("/api/setup/badge/", js)
        self.assertNotIn("new QRCode", js)
        self.assertFalse((ROOT / "services/exercise/app/static/vendor/qrcode.min.js").exists())


class RedactedDfRendersCleanly(unittest.TestCase):
    """U-3: an anonymous viewer on an open dev console is still not the
    instructor (X-1's invariant), so it receives a redacted DF dictionary; the
    instructor page must render that without NaN."""

    def test_anonymous_dev_viewer_stays_redacted(self):
        main, client, db = build_app()                    # no tokens at all: an open dev console
        try:
            run_sortie(main, client)
            r = client.post("/api/positions", json={
                "callsign": "CAP-1", "lat": 33.1, "lon": -117.2, "alt_ft": 5500.0,
                "hdg_true": 90.0, "df": {"valid": True, "bearing_rel": 12.5,
                                          "bearing_true": 102.5, "signal": 0.4,
                                          "distance_nm": 9.2, "head_type": 1}})
            self.assertEqual(r.status_code, 200, r.text)
            ac = client.get("/api/state").json()["aircraft"][0]
            self.assertNotIn("bearing_rel", ac["df"])
            self.assertTrue(ac["df"]["valid"])
        finally:
            os.unlink(db)

    def test_the_instructor_page_never_prints_nan(self):
        js = (ROOT / "services/exercise/app/static/app.js").read_text()
        self.assertIn("Number.isFinite(d.bearing_rel)", js)
        self.assertIn("d.distance_nm ?", js)
        self.assertIn("bearing withheld", js)


if __name__ == "__main__":
    unittest.main()
