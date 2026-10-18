"""
Link quality on the radio pages (T38): the Base Radio page shows how each
station is heard, in plain CAP words, from the server's `link` message; the
instructor console exposes the two radio-reach settings. Source-level and
node-run checks in the style of tests/test_console_frontend.py.
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_console_frontend import NODE, block, run, run_block, src   # noqa: E402

JARGON = ("dB", "SNR", "margin", "Fresnel", "signal margin", "link budget", "attenuation")
LABELS = {"clear": "Clear", "weak": "Some static", "broken": "Weak and choppy", "unusable": "Barely readable"}


def link(**fields):
    return {"type": "link", "speaker": "CAP 487", "receiver": "main", "path": "direct", "via": None,
            "via_name": None, "to_base": True, "margin": 1.0, "quality": "clear", "heard": "x", **fields}


class LinkQualityOnTheRadioPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = src("mission-radio.js")
        cls.html = src("mission-radio.html")
        cls.pure = block("mission-radio.js", "T38 PURE LINK QUALITY")

    def test_the_page_has_a_pill_by_the_speaker_line_announced_politely(self):
        self.assertIn('id="linkQuality"', self.html)
        self.assertRegex(self.html, r'id="linkQuality"[^>]*aria-live="polite"')
        self.assertRegex(self.html, r'id="linkQuality"[^>]*\bhidden\b')
        self.assertIn('id="speaker"', self.html)

    def test_the_handler_exists_and_updates_only_on_change(self):
        handler = self.js[self.js.index("message.type==='link'"):self.js.index("message.type==='pong'")]
        self.assertIn("state.links[message.speaker]=message", handler)
        self.assertIn("showLinkQuality(message)", handler)
        self.assertIn("entry.link=linkText(message)", handler)
        shower = self.js[self.js.index("function showLinkQuality"):self.js.index("function failureScope")]
        self.assertIn("if (el.textContent === text", shower, "aria-live region must not be rewritten with the same text")
        # the rx handler shows the pill and writes the note into the Form 110 entry
        rx = self.js[self.js.index("message.type==='rx'"):self.js.index("message.type==='link'")]
        self.assertIn("showLinkQuality(state.links[message.speaker])", rx)
        self.assertIn("link:receiver==='main'?linkText(state.links[message.speaker]):''", rx)
        # a new net forgets the old links
        self.assertIn("state.links={};state.currentSpeaker=null;showLinkQuality(null);", self.js)

    def test_the_log_row_carries_the_note_and_the_store_keeps_it(self):
        self.assertIn("note.className = 'link-note'", self.js)
        self.assertIn("note.textContent = entry.link", self.js)
        self.assertIn("typeof r.link === 'string' && r.link ? {link: r.link} : {}", self.js)
        self.assertIn("link = ''}) {", self.js)

    @unittest.skipIf(NODE is None, "node is not installed")
    def test_labels_are_plain_words_and_paths_are_named(self):
        cases = {
            "direct_clear": link(),
            "direct_weak": link(quality="weak", margin=.5),
            "via_broken": link(path="repeater", via="RPT-JLI", via_name="Julian (JLI VORTAC)", quality="broken"),
            "via_noname": link(path="repeater", via="RPT-X", via_name="", quality="weak"),
            "none": link(path="none", quality="unusable", margin=0),
            "air_air": link(path="direct", to_base=False, quality="clear"),
            "nominal": link(path="nominal", quality="clear"),
            "no_quality": link(quality=None),
        }
        out = run_block(self.pure, "Object.fromEntries(Object.entries(%s).map(([k, v]) => [k, [linkText(v), linkTone(v)]]))"
                        % json.dumps(cases))
        self.assertEqual(out["direct_clear"], ["Clear · direct to base", "good"])
        self.assertEqual(out["direct_weak"], ["Some static · direct to base", "warn"])
        self.assertEqual(out["via_broken"], ["Weak and choppy · via Julian repeater", "warn"])
        self.assertEqual(out["via_noname"], ["Some static · via the repeater", "warn"])
        self.assertEqual(out["none"], ["Barely readable · out of range of base and repeater", "bad"])
        self.assertEqual(out["air_air"], ["Clear · aircraft to aircraft", "good"])
        self.assertEqual(out["nominal"], ["", ""], "no position known: show nothing")
        self.assertEqual(out["no_quality"], ["", ""])
        self.assertEqual(run_block(self.pure, "LINK_QUALITY_LABELS"), LABELS)

    def test_no_jargon_reaches_the_screen(self):
        for word in JARGON:
            self.assertNotIn(word, self.pure, word)
            self.assertNotIn(word, self.html, word)
        for word in ("dB", "SNR", "Fresnel", "signal margin", "link budget"):
            self.assertNotIn(word, self.js, word)
        # the only "margin" in the radio script is CSS layout, never shown text
        for m in re.finditer(r"margin", self.js):
            line = self.js[self.js.rfind("\n", 0, m.start()) + 1:self.js.find("\n", m.end())]
            self.assertRegex(line, r"style\.margin|margin(Left|Right|Top|Bottom)|margin:", line)

    def test_tone_classes_exist_with_colour_and_text_together(self):
        css = src("mission-radio.css")
        for cls in (".link-quality", ".link-quality.good", ".link-quality.warn", ".link-quality.bad", ".link-note"):
            self.assertIn(cls, css, cls)


class InstructorRadioControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = src("app.js")

    def test_radio_reach_is_an_injected_effect_with_a_plain_label(self):
        self.assertRegex(self.js, r"\['radio_reach',\s*'Radio reach',")
        self.assertIn("radio_reach: true", self.js, "new scenarios default the effect on")
        for word in JARGON:
            effects = self.js[self.js.index("const EFFECTS = ["):self.js.index("];", self.js.index("const EFFECTS = ["))]
            self.assertNotIn(word, effects, word)

    def test_radio_conditions_is_a_plain_language_selector_that_posts_the_number(self):
        self.assertIn('id="liveRadioConditions"', self.js)
        self.assertIn("JSON.stringify({radio_conditions: parseFloat(e.target.value)})", self.js)
        self.assertIn("radio_conditions: 1.0", self.js, "new scenarios start on a clear day")
        self.assertIn("[[1, 'Normal'], [0.75, 'Light static'], [0.5, 'Poor'], [0.25, 'Very poor']]", self.js)
        self.assertIn("radioConditionOption(parseFloat(sc.effects.radio_conditions))", self.js)

    @unittest.skipIf(NODE is None, "node is not installed")
    def test_the_selector_snaps_to_the_nearest_step(self):
        out = run(["charts.js", "geodesy.js", "app.js"],
                  "return [radioConditionOption(1), radioConditionOption(.9), radioConditionOption(.6), "
                  "radioConditionOption(.3), radioConditionOption(0), radioConditionOption(undefined), radioConditionOption(NaN)];")
        self.assertEqual(out, [1, 1, 0.5, 0.25, 0.25, 1, 1])


if __name__ == "__main__":
    unittest.main()
