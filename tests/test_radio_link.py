"""
Link quality on the tactical net (T33): signal margin from reach geometry,
the static/dropout impairment it maps to, the seeded dropout gate, the frame
processing, and the choice of path between stations. Pure Python, no server.
"""
import math
import os
import sys
import unittest
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "exercise"))

from app import radio_link, radio_sites, settings            # noqa: E402

SITES = radio_sites.load_sites(settings.RADIO_SITES)
BASE = next(s for s in SITES if s.role == "base_antenna")
RPT = next(s for s in SITES if s.role == "repeater")


def flat_300(lat, lon):
    return 300.0


def ridge_east_of_jli(lat, lon):
    return 7000.0 if -116.55 < lon < -116.45 else 300.0


def ridge_between_search_area_and_base(lat, lon):
    if -116.82 < lon < -116.78 and lat > 33.03:
        return 6000.0
    return ridge_east_of_jli(lat, lon)


def aircraft(lat, lon, alt_ft):
    return {"kind": "aircraft", "lat": lat, "lon": lon, "alt_ft": alt_ft}


class Margin(unittest.TestCase):
    def test_horizon_score_is_one_inside_then_falls_smoothly_to_zero_beyond(self):
        h = 100.0
        self.assertEqual(radio_link.horizon_score(0.0, h), 1.0)
        self.assertEqual(radio_link.horizon_score(60.0, h), 1.0)
        self.assertEqual(radio_link.horizon_score(115.0, h), 0.0)
        self.assertEqual(radio_link.horizon_score(300.0, h), 0.0)
        last = 1.0
        for d in range(60, 116):
            score = radio_link.horizon_score(float(d), h)
            self.assertLessEqual(score, last + 1e-12, d)
            self.assertTrue(0.0 <= score <= 1.0)
            last = score
        self.assertGreater(radio_link.horizon_score(99.0, h), 0.05)     # just inside: weak, not gone
        self.assertLess(radio_link.horizon_score(99.0, h), 0.5)

    def test_terrain_score_follows_the_engine_loss_shape(self):
        self.assertEqual(radio_link.terrain_score(None), 1.0)
        self.assertEqual(radio_link.terrain_score(5000.0), 1.0)
        self.assertEqual(radio_link.terrain_score(1000.0), 1.0)
        self.assertAlmostEqual(radio_link.terrain_score(0.0), 0.5)
        self.assertAlmostEqual(radio_link.terrain_score(-500.0), 0.0)
        self.assertEqual(radio_link.terrain_score(-5000.0), 0.0)
        last = 0.0
        for c in range(-600, 1200, 10):
            score = radio_link.terrain_score(float(c))
            self.assertGreaterEqual(score, last - 1e-12, c)
            last = score

    def test_margin_combines_horizon_terrain_and_conditions(self):
        self.assertEqual(radio_link.margin(10.0, 100.0), 1.0)
        self.assertAlmostEqual(radio_link.margin(10.0, 100.0, 0.0), 0.5)
        self.assertAlmostEqual(radio_link.margin(10.0, 100.0, conditions=0.5), 0.5)
        self.assertEqual(radio_link.margin(10.0, 100.0, conditions=7.0), 1.0)       # clamped
        self.assertEqual(radio_link.margin(200.0, 100.0), 0.0)
        self.assertEqual(radio_link.margin(200.0, 100.0, radio_horizon=False), 1.0)
        # the adapter reads radio_sites' dict shape
        p = radio_sites.path(33.14, -116.75, 4500.0, RPT, terrain_ft=flat_300)
        self.assertEqual(radio_link.link_margin(p), 1.0)
        p["terrain_checked"], p["clearance_ft"] = True, -250.0
        self.assertAlmostEqual(radio_link.link_margin(p), 0.25)
        # Fresnel-aware: an elevated antenna over flat ground is clear, a ground-level ray grazes
        self.assertEqual(radio_link.terrain_loss_along(33.14, -116.75, 4500.0, BASE.lat, BASE.lon,
                                                       BASE.antenna_msl_ft, flat_300), 0.0)
        # a 1,900 ft rise where the ray is about 2,000 ft sits inside the first Fresnel zone
        # there (~480 ft) without touching the ray: grazing, not blocked
        bump = lambda lat, lon: 1900.0 if 32.95 < lat < 32.98 else 300.0
        graze = radio_link.terrain_loss_along(33.14, -116.75, 4500.0, BASE.lat, BASE.lon, BASE.antenna_msl_ft, bump)
        self.assertTrue(10.0 < graze < 20.0, graze)
        self.assertLess(radio_link.fresnel_radius_ft(0.25, 23.75), 110.0)
        self.assertGreater(radio_link.fresnel_radius_ft(12.0, 12.0), 450.0)


class Impairment(unittest.TestCase):
    def test_boundaries(self):
        clear = radio_link.impairment(1.0)
        self.assertEqual((clear["noise"], clear["speech_gain"], clear["dropout_rate"], clear["usable"]),
                         (0.0, 1.0, 0.0, True))
        dead = radio_link.impairment(0.0)
        self.assertEqual((dead["noise"], dead["dropout_rate"], dead["usable"]), (1.0, 0.9, False))
        self.assertAlmostEqual(dead["speech_gain"], 0.35)
        self.assertEqual(radio_link.impairment(1.7)["noise"], 0.0)               # clamped
        self.assertEqual(radio_link.impairment(-3.0)["noise"], 1.0)

    def test_every_field_is_monotonic_and_gradual_in_the_margin(self):
        steps = [i / 100 for i in range(101)]
        imps = [radio_link.impairment(m) for m in steps]
        for a, b in zip(imps, imps[1:]):
            self.assertLessEqual(b["noise"], a["noise"] + 1e-12)
            self.assertGreaterEqual(b["speech_gain"], a["speech_gain"] - 1e-12)
            self.assertLessEqual(b["dropout_rate"], a["dropout_rate"] + 1e-12)
            self.assertLessEqual(b["dropout_s"], a["dropout_s"] + 1e-12)
            self.assertLess(abs(b["noise"] - a["noise"]), 0.05, "no cliff")
            self.assertLess(abs(b["dropout_rate"] - a["dropout_rate"]), 0.05, "no cliff")
        # comfortably inside: nothing audible; near the horizon: noisy before choppy
        self.assertEqual(radio_link.impairment(0.95)["dropout_rate"], 0.0)
        self.assertLess(radio_link.impairment(0.95)["noise"], 0.02)
        self.assertGreater(radio_link.impairment(0.5)["noise"], 0.3)
        self.assertGreater(radio_link.impairment(0.5)["dropout_rate"], 0.0)

    def test_quality_words(self):
        self.assertEqual([radio_link.quality_word(m) for m in (1.0, 0.8, 0.6, 0.2, 0.05, 0.0)],
                         ["clear", "clear", "weak", "broken", "unusable", "unusable"])


class Dropouts(unittest.TestCase):
    def fraction(self, rate, mean_s, seed=1, frames=20000):
        gate = radio_link.DropoutGate(rate, mean_s, seed)
        return sum(gate.next() for _ in range(frames)) / frames

    def test_rate_zero_never_drops_and_sequences_are_deterministic(self):
        self.assertEqual(self.fraction(0.0, 0.3), 0.0)
        def sequence(seed):
            gate = radio_link.DropoutGate(0.4, 0.3, seed)
            return [gate.next() for _ in range(500)]
        a, b, c = sequence("seed-A"), sequence("seed-A"), sequence("seed-B")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(any(a) and not all(a))

    def test_long_run_fraction_matches_the_rate_and_dropouts_last_about_the_mean(self):
        for rate in (0.1, 0.4, 0.8):
            self.assertAlmostEqual(self.fraction(rate, 0.3), rate, delta=0.06, msg=rate)
        gate = radio_link.DropoutGate(0.3, 0.4, 7)
        runs, current = [], 0
        for _ in range(20000):
            if gate.next():
                current += 1
            elif current:
                runs.append(current)
                current = 0
        self.assertAlmostEqual(sum(runs) / len(runs) * radio_link.FRAME_S, 0.4, delta=0.08)

    def test_more_impairment_means_more_dropped_frames(self):
        fractions = [self.fraction(radio_link.impairment(m)["dropout_rate"],
                                   radio_link.impairment(m)["dropout_s"]) for m in (1.0, 0.6, 0.3, 0.0)]
        self.assertEqual(fractions[0], 0.0)
        for a, b in zip(fractions, fractions[1:]):
            self.assertLess(a, b + 0.03)


class Frames(unittest.TestCase):
    def tone(self, n=960, amp=8000):
        return array("h", (int(amp * math.sin(2 * math.pi * 440 * i / 48000)) for i in range(n))).tobytes()

    def test_a_clear_link_returns_the_frame_untouched(self):
        pcm = self.tone()
        out, phase = radio_link.impair_frame(pcm, radio_link.impairment(1.0), 0, False)
        self.assertIs(out, pcm)
        self.assertEqual(phase, 0)

    def test_a_dropped_frame_is_silence_of_the_same_length(self):
        out, phase = radio_link.impair_frame(self.tone(), radio_link.impairment(0.5), 123, True)
        self.assertEqual(out, bytes(1920))
        self.assertEqual(phase, 123)

    def test_a_weak_link_adds_seeded_static_and_lowers_the_speech(self):
        pcm = self.tone()
        imp = radio_link.impairment(0.4)
        out1, phase1 = radio_link.impair_frame(pcm, imp, 0, False)
        out2, _ = radio_link.impair_frame(pcm, imp, 0, False)
        self.assertEqual(out1, out2, "deterministic for the same phase")
        self.assertNotEqual(out1, pcm)
        self.assertEqual(phase1, 960)
        samples = array("h"); samples.frombytes(out1)
        self.assertTrue(all(-32768 <= s <= 32767 for s in samples))
        # the static is there: a silent input comes out non-silent
        quiet, _ = radio_link.impair_frame(bytes(1920), imp, 0, False)
        self.assertNotEqual(quiet, bytes(1920))
        # and louder at a worse margin
        def power(b):
            a = array("h"); a.frombytes(b); return sum(x * x for x in a) / len(a)
        worse, _ = radio_link.impair_frame(bytes(1920), radio_link.impairment(0.1), 0, False)
        self.assertGreater(power(worse), power(quiet))
        # the noise phase carries on across frames, so the static is continuous
        nxt, phase2 = radio_link.impair_frame(bytes(1920), imp, phase1, False)
        self.assertEqual(phase2, 1920)
        self.assertNotEqual(nxt[:40], quiet[:40])

    def test_clipping_is_bounded(self):
        loud = array("h", [32000] * 960).tobytes()
        out, _ = radio_link.impair_frame(loud, radio_link.impairment(0.0), 0, False)
        samples = array("h"); samples.frombytes(out)
        self.assertTrue(all(-32768 <= s <= 32767 for s in samples))


class Routing(unittest.TestCase):
    def test_aircraft_near_julian_is_heard_direct_in_open_country(self):
        link = radio_link.link_between(aircraft(33.14, -116.75, 4500.0), {"kind": "base"}, SITES,
                                       terrain_ft=flat_300)
        self.assertEqual((link["path"], link["via"], link["margin"]), ("direct", None, 1.0))
        self.assertEqual(link["heard"], "heard direct at Mission Base, Gillespie Field (KSEE), clear")

    def test_a_ridge_toward_base_moves_the_same_aircraft_onto_the_repeater(self):
        link = radio_link.link_between({"kind": "base"}, aircraft(33.14, -116.75, 4500.0), SITES,
                                       terrain_ft=ridge_between_search_area_and_base)
        self.assertEqual((link["path"], link["via"]), ("repeater", "RPT-JLI"))
        self.assertEqual(link["margin"], 1.0)
        self.assertTrue(link["heard"].startswith("heard via Julian (JLI VORTAC) repeater"))

    def test_low_behind_the_ridge_east_of_julian_is_out_of_range(self):
        link = radio_link.link_between(aircraft(33.14, -116.35, 3000.0), {"kind": "base"}, SITES,
                                       terrain_ft=ridge_east_of_jli)
        self.assertEqual((link["path"], link["margin"]), ("none", 0.0))
        self.assertEqual(link["heard"], "out of range of base and repeater")

    def test_degradation_is_gradual_with_distance_and_altitude(self):
        # Base antenna only (the mountain-top repeater would keep a low aircraft covered 50 NM out).
        base_only = radio_sites.load_sites([settings.RADIO_SITES[0]])
        # Same track outbound from the base at 500 ft: the margin falls, never jumps.
        margins = [radio_link.link_between(aircraft(32.83 + 0.1 * k, -116.97, 500.0), {"kind": "base"},
                                           base_only, terrain_ft=flat_300)["margin"] for k in range(12)]
        self.assertEqual(margins[0], 1.0)
        for a, b in zip(margins, margins[1:]):
            self.assertLessEqual(b, a + 1e-9)
            self.assertLess(a - b, 0.4, "no cliff")
        self.assertLess(margins[-1], margins[0])
        # Higher is better at the same spot.
        low = radio_link.link_between(aircraft(33.6, -116.97, 500.0), {"kind": "base"}, base_only)["margin"]
        high = radio_link.link_between(aircraft(33.6, -116.97, 4500.0), {"kind": "base"}, base_only)["margin"]
        self.assertGreater(high, low)
        # and with the repeater in play the same low aircraft is covered via Julian
        via = radio_link.link_between(aircraft(33.6, -116.97, 500.0), {"kind": "base"}, SITES)
        self.assertEqual((via["path"], via["via"]), ("repeater", "RPT-JLI"))
        self.assertGreater(via["margin"], low)

    def test_conditions_scale_the_margin(self):
        clear = radio_link.link_between(aircraft(33.14, -116.75, 4500.0), {"kind": "base"}, SITES)
        murky = radio_link.link_between(aircraft(33.14, -116.75, 4500.0), {"kind": "base"}, SITES,
                                        conditions=0.3)
        self.assertEqual(clear["margin"], 1.0)
        self.assertAlmostEqual(murky["margin"], 0.3)

    def test_unknown_positions_and_ground_teams_get_a_nominal_link(self):
        for other in ({"kind": "ground"}, {"kind": "unknown"}, {"kind": "aircraft"}):
            link = radio_link.link_between({"kind": "base"}, other, SITES)
            self.assertEqual((link["path"], link["margin"]), ("nominal", 1.0))
            link = radio_link.link_between(aircraft(33.14, -116.75, 4500.0), other, SITES)
            self.assertEqual((link["path"], link["margin"]), ("nominal", 1.0))
        self.assertEqual(radio_link.link_between({"kind": "base"}, {"kind": "base"}, SITES)["path"], "nominal")

    def test_air_to_air_and_air_to_ground_are_direct_line_of_sight(self):
        a = aircraft(33.14, -116.75, 4500.0)
        b = aircraft(33.10, -117.05, 5500.0)
        link = radio_link.link_between(a, b, SITES, terrain_ft=flat_300)
        self.assertEqual((link["path"], link["margin"]), ("direct", 1.0))
        team = {"kind": "ground", "lat": 33.17, "lon": -117.08, "alt_ft": 710.0}
        self.assertEqual(radio_link.link_between(a, team, SITES)["path"], "direct")
        far = aircraft(30.0, -116.75, 50.0)
        self.assertEqual(radio_link.link_between(a, far, SITES)["path"], "none")


class LinkStateBehaviour(unittest.TestCase):
    def test_state_tracks_changes_and_processes_frames(self):
        link = radio_link.link_between(aircraft(33.14, -116.75, 4500.0), {"kind": "base"}, SITES)
        state = radio_link.LinkState(link, "seed")
        self.assertEqual(state.describe()["quality"], "clear")
        pcm = bytes(1920)
        self.assertIs(state.process(pcm), pcm)
        weak = dict(link, margin=0.3, heard="heard direct, broken")
        self.assertTrue(state.update(weak, "seed2"))
        self.assertFalse(state.update(dict(weak), "seed3"))
        self.assertEqual(state.describe()["quality"], "broken")
        outputs = [state.process(pcm) for _ in range(200)]
        self.assertTrue(any(o == pcm for o in outputs), "dropouts are silence")
        self.assertTrue(any(o != pcm for o in outputs), "static elsewhere")


class DirectionFindingIsSeparate(unittest.TestCase):
    def test_the_engine_and_the_df_stub_never_touch_the_sites_or_the_link_model(self):
        for rel in ("xplane/PI_capvsar_df.py", "services/exercise/app/propagation.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("radio_sites", text, rel)
            self.assertNotIn("radio_link", text, rel)
            self.assertNotIn("repeater", text.lower(), rel)


if __name__ == "__main__":
    unittest.main()
