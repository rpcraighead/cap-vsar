"""Offline tests for the flight-test profiles.

The stall profile deliberately flies to the edge of controlled flight, so the
emphasis here is on the guardrails: every abort path, recovery ordering, and the
data reduction. Pure state machine, so no simulator and no threads.
"""

from __future__ import annotations

import unittest

from services.ai_pilot.flight_test import (
    Phase,
    StallLimits,
    StallTestProfile,
    compare_to_target,
    scale_stall_speed,
)
from services.ai_pilot.maneuvers import Observation


def obs(**overrides):
    frame = {
        "heading_mag": 90.0,
        "altitude_indicated_ft": 5000.0,
        "agl_ft": 3500.0,
        "kias": 75.0,
        "roll_deg": 0.0,
        "vvi_fpm": 0.0,
        "age_seconds": 0.1,
    }
    frame.update(overrides)
    return Observation(**frame)


def profile(**kwargs):
    return StallTestProfile(entry_altitude_ft=5000.0, entry_heading_deg=90.0, **kwargs)


def stabilize(p, t0=0.0):
    """Walk the profile through STABILIZE into DECELERATE."""
    p.step(obs(), pitch_deg=2.0, now=t0)
    p.step(obs(), pitch_deg=2.0, now=t0 + p.limits.stabilize_seconds + 0.1)
    return p


class StabilizeTests(unittest.TestCase):
    def test_does_not_start_below_the_entry_floor(self):
        p = profile()
        p.step(obs(agl_ft=1500.0), pitch_deg=2.0, now=0.0)
        # too low to even begin: abort floor catches it first
        self.assertEqual(p.phase, Phase.ABORTED)

    def test_does_not_start_until_wings_are_level(self):
        # 8 deg is inside the 10 deg ABORT limit but outside the 3 deg ENTRY
        # limit. Entry must be tighter, or a point can begin at the edge of its
        # own tolerance - and entry bank changes the measured stall speed.
        p = profile()
        p.step(obs(roll_deg=8.0), pitch_deg=2.0, now=0.0)
        p.step(obs(roll_deg=8.0), pitch_deg=2.0, now=60.0)
        self.assertEqual(p.phase, Phase.STABILIZE, "wings must settle before the point starts")

    def test_does_not_start_while_still_climbing_or_descending(self):
        p = profile()
        p.step(obs(vvi_fpm=400.0), pitch_deg=2.0, now=0.0)
        p.step(obs(vvi_fpm=400.0), pitch_deg=2.0, now=60.0)
        self.assertEqual(p.phase, Phase.STABILIZE)

    def test_entry_criteria_are_stricter_than_abort_criteria(self):
        limits = StallLimits()
        self.assertLess(limits.entry_max_bank_deg, limits.max_bank_deg)
        self.assertGreater(limits.entry_agl_ft, limits.abort_agl_ft)

    def test_enters_decelerate_after_the_settle_time(self):
        p = stabilize(profile())
        self.assertEqual(p.phase, Phase.DECELERATE)

    def test_throttle_goes_to_idle_on_entry(self):
        p = profile()
        p.step(obs(), pitch_deg=2.0, now=0.0)
        commands = p.step(obs(), pitch_deg=2.0, now=p.limits.stabilize_seconds + 0.1)
        self.assertEqual(commands.throttle, 0.0, "power-off stall starts at idle")


class BreakDetectionTests(unittest.TestCase):
    def test_slow_flight_alone_is_not_a_break(self):
        p = stabilize(profile())
        p.step(obs(kias=48.0, vvi_fpm=-50.0), pitch_deg=10.0, now=20.0)
        self.assertEqual(p.phase, Phase.DECELERATE)
        self.assertIsNone(p.break_kias)

    def test_sink_at_low_pitch_is_not_a_break(self):
        # A descent with the nose down is not a stall.
        p = stabilize(profile())
        p.step(obs(kias=70.0, vvi_fpm=-800.0), pitch_deg=1.0, now=20.0)
        self.assertEqual(p.phase, Phase.DECELERATE)

    def test_sharp_sink_at_high_pitch_is_a_break(self):
        p = stabilize(profile())
        p.step(obs(kias=41.0, vvi_fpm=-100.0), pitch_deg=12.0, now=20.0)
        p.step(obs(kias=41.0, vvi_fpm=-700.0), pitch_deg=12.0, now=21.0)
        self.assertEqual(p.phase, Phase.RECOVER)
        self.assertAlmostEqual(p.break_kias, 41.0, places=3)

    def test_break_speed_is_the_minimum_seen_not_the_instant_value(self):
        p = stabilize(profile())
        p.step(obs(kias=42.0, vvi_fpm=-50.0), pitch_deg=11.0, now=20.0)
        p.step(obs(kias=40.5, vvi_fpm=-80.0), pitch_deg=12.0, now=21.0)
        p.step(obs(kias=44.0, vvi_fpm=-900.0), pitch_deg=13.0, now=22.0)
        self.assertAlmostEqual(p.break_kias, 40.5, places=3)


class RecoveryTests(unittest.TestCase):
    def test_recovery_reduces_angle_of_attack_before_anything_else(self):
        p = stabilize(profile())
        commands = p.step(obs(kias=41.0, vvi_fpm=-700.0), pitch_deg=12.0, now=20.0)
        self.assertLessEqual(commands.target_pitch_deg, 0.0,
                             "unload first; power at high AoA invites a secondary stall")
        self.assertEqual(commands.throttle, 1.0)
        self.assertEqual(commands.target_roll_deg, 0.0)

    def test_completes_only_after_a_real_speed_margin(self):
        p = stabilize(profile())
        p.step(obs(kias=41.0, vvi_fpm=-700.0), pitch_deg=12.0, now=20.0)
        p.step(obs(kias=45.0, vvi_fpm=-50.0), pitch_deg=0.0, now=22.0)
        self.assertEqual(p.phase, Phase.RECOVER, "4 kt is not a recovery")
        p.step(obs(kias=60.0, vvi_fpm=50.0), pitch_deg=2.0, now=25.0)
        self.assertEqual(p.phase, Phase.COMPLETE)


class AbortTests(unittest.TestCase):
    def _decelerating(self):
        return stabilize(profile())

    def test_aborts_below_the_agl_floor(self):
        p = self._decelerating()
        p.step(obs(agl_ft=1500.0), pitch_deg=10.0, now=20.0)
        self.assertEqual(p.phase, Phase.ABORTED)
        self.assertEqual(p.abort_reason, "AGL below abort floor")

    def test_aborts_on_excessive_bank(self):
        p = self._decelerating()
        p.step(obs(roll_deg=25.0), pitch_deg=10.0, now=20.0)
        self.assertEqual(p.phase, Phase.ABORTED)
        self.assertEqual(p.abort_reason, "Bank exceeded test limit")

    def test_aborts_on_altitude_loss(self):
        p = self._decelerating()
        p.step(obs(altitude_indicated_ft=4000.0), pitch_deg=10.0, now=20.0)
        self.assertEqual(p.phase, Phase.ABORTED)
        self.assertEqual(p.abort_reason, "Altitude loss exceeded limit")

    def test_aborts_on_timeout(self):
        p = self._decelerating()
        p.step(obs(), pitch_deg=10.0, now=1000.0)
        self.assertEqual(p.phase, Phase.ABORTED)
        self.assertEqual(p.abort_reason, "Test point exceeded time limit")

    def test_aborts_if_pitch_runs_away_without_a_break(self):
        p = self._decelerating()
        p.step(obs(kias=45.0, vvi_fpm=0.0), pitch_deg=30.0, now=20.0)
        self.assertEqual(p.phase, Phase.ABORTED)

    def test_every_abort_still_commands_a_recovery(self):
        for override in ({"agl_ft": 1500.0}, {"roll_deg": 25.0},
                         {"altitude_indicated_ft": 4000.0}):
            p = self._decelerating()
            commands = p.step(obs(**override), pitch_deg=10.0, now=20.0)
            self.assertEqual(p.phase, Phase.ABORTED)
            self.assertEqual(commands.throttle, 1.0, override)
            self.assertLessEqual(commands.target_pitch_deg, 0.0, override)

    def test_aborted_point_reports_no_break_speed(self):
        p = self._decelerating()
        p.step(obs(agl_ft=1500.0), pitch_deg=10.0, now=20.0)
        self.assertIsNone(p.result()["break_kias"])
        self.assertTrue(p.result()["aborted"])


class DataReductionTests(unittest.TestCase):
    def test_pass_within_tolerance(self):
        self.assertEqual(compare_to_target(41.0, 41.0)["verdict"], "pass")
        self.assertEqual(compare_to_target(43.5, 41.0)["verdict"], "pass")

    def test_fail_outside_tolerance(self):
        self.assertEqual(compare_to_target(46.0, 41.0)["verdict"], "fail")

    def test_unmeasured_when_the_point_aborted(self):
        result = compare_to_target(None, 41.0)
        self.assertEqual(result["verdict"], "unmeasured")
        self.assertIsNone(result["error_kias"])

    def test_stall_speed_scales_with_root_weight(self):
        # 2,775 lb against the POH's 3,100 lb reference
        scaled = scale_stall_speed(41.0, 2775.0)
        self.assertAlmostEqual(scaled, 41.0 * (2775.0 / 3100.0) ** 0.5, places=6)
        self.assertLess(scaled, 41.0)

    def test_reference_weight_is_a_no_op(self):
        self.assertAlmostEqual(scale_stall_speed(41.0, 3100.0), 41.0, places=6)

    def test_rejects_nonsense_weights(self):
        with self.assertRaises(ValueError):
            scale_stall_speed(41.0, 0.0)


if __name__ == "__main__":
    unittest.main()
