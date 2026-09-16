"""A-1 stage 3: the geometry corrections applied to the pinned donor."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import c182t_corrections as corrections  # noqa: E402
import convert_flightgear_c182 as converter  # noqa: E402


class Stub:
    """Minimal stand-in for a parsed donor object."""
    def __init__(self, name, vertices):
        self.name = name
        self.vertices = list(vertices)


def prop_radius(objects):
    rot = converter.PROP_ROTATION
    hub, axis = rot.center, rot.axis
    radius = 0.0
    for obj in objects:
        for vertex in obj.vertices:
            p = converter.ac_to_xplane(vertex)
            d = [p[i] - hub[i] for i in range(3)]
            along = sum(d[i] * axis[i] for i in range(3))
            radius = max(radius, math.sqrt(max(0.0, sum(x * x for x in d) - along ** 2)))
    return radius


class CoordinateRoundTrip(unittest.TestCase):
    def test_xplane_to_ac_inverts_the_converter(self):
        for point in [(1.0, 2.0, 3.0), (-0.5, 0.0, 7.25), (0.0, 0.0, 0.0)]:
            back = corrections.xplane_to_ac(converter.ac_to_xplane(point))
            for a, b in zip(point, back):
                self.assertAlmostEqual(a, b, places=12)


class RadialScale(unittest.TestCase):
    def test_hub_is_a_fixed_point(self):
        """No animation pivot may move; PROP_ROTATION must stay valid."""
        rot = converter.PROP_ROTATION
        moved = corrections._radial_scale_about_axis(
            rot.center, rot.center, rot.axis, 0.5)
        for a, b in zip(moved, rot.center):
            self.assertAlmostEqual(a, b, places=12)

    def test_points_on_the_axis_do_not_move(self):
        rot = converter.PROP_ROTATION
        on_axis = tuple(rot.center[i] + 0.3 * rot.axis[i] for i in range(3))
        moved = corrections._radial_scale_about_axis(on_axis, rot.center, rot.axis, 0.5)
        for a, b in zip(moved, on_axis):
            self.assertAlmostEqual(a, b, places=12)

    def test_axial_distance_is_preserved_while_radius_scales(self):
        rot = converter.PROP_ROTATION
        hub, axis = rot.center, rot.axis
        # A point 0.4 m along the axis and 1.0 m off it.
        perp = (axis[1], -axis[0], 0.0)
        norm = math.sqrt(sum(x * x for x in perp))
        perp = tuple(x / norm for x in perp)
        point = tuple(hub[i] + 0.4 * axis[i] + 1.0 * perp[i] for i in range(3))

        moved = corrections._radial_scale_about_axis(point, hub, axis, 0.25)
        delta = [moved[i] - hub[i] for i in range(3)]
        along = sum(delta[i] * axis[i] for i in range(3))
        radial = math.sqrt(max(0.0, sum(x * x for x in delta) - along ** 2))
        self.assertAlmostEqual(along, 0.4, places=12)
        self.assertAlmostEqual(radial, 0.25, places=12)


class Profile(unittest.TestCase):
    def test_every_active_correction_is_sourced_and_explained(self):
        for c in corrections.load_profile()["corrections"]:
            if c.get("status") != "active":
                continue
            for field in ("id", "closes", "type", "objects", "rationale", "source"):
                self.assertTrue(c.get(field), f"{c.get('id')} missing {field}")

    def test_a_correction_naming_an_absent_object_fails_loudly(self):
        """Silently matching nothing would leave geometry wrong but look fine."""
        profile = {"corrections": [{
            "id": "bogus", "closes": "x", "status": "active",
            "type": "radial_scale_about_axis", "objects": ["NoSuchObject"],
            "scale": 0.5}]}
        with self.assertRaisesRegex(ValueError, "absent objects"):
            corrections.apply_corrections([Stub("Blade1", [(0, 0, 0)])],
                                          converter, profile)

    def test_unknown_correction_type_is_refused(self):
        profile = {"corrections": [{
            "id": "bogus", "closes": "x", "status": "active",
            "type": "shear_everything", "objects": ["Blade1"], "scale": 1.0}]}
        with self.assertRaisesRegex(ValueError, "Unknown correction type"):
            corrections.apply_corrections([Stub("Blade1", [(0, 0, 0)])],
                                          converter, profile)

    def test_the_prop_correction_brings_the_diameter_inside_the_tcds_band(self):
        """The whole point of the stage-3 propeller correction."""
        rot = converter.PROP_ROTATION
        hub, axis = rot.center, rot.axis
        perp = (axis[1], -axis[0], 0.0)
        norm = math.sqrt(sum(x * x for x in perp))
        perp = tuple(x / norm for x in perp)
        # A synthetic blade tip at exactly the measured stage-2 radius.
        tip_m = 79.25502 * 0.0254 / 2
        tip_xp = tuple(hub[i] + tip_m * perp[i] for i in range(3))
        blades = [Stub(n, [corrections.xplane_to_ac(tip_xp)])
                  for n in ("Blade1", "Blade2", "Blade3", "FastProp")]
        # Every active correction must find its objects or apply_corrections
        # fails loudly, so the tail objects are present but placed inboard of
        # the root where the span transform leaves them alone.
        inert = [Stub(n, [corrections.xplane_to_ac((0.0, 0.4, 5.5))])
                 for n in ("Airframe", "Elevator", "ElevatorTrim")]
        # Gear objects too: the track correction is active and would otherwise
        # fail loudly for naming absent objects. Placed on the centreline, so
        # the rigid translation moves them without affecting the prop radius.
        inert += [Stub(n, [corrections.xplane_to_ac((0.0, -0.8, 1.4))])
                  for n in ("MainStrut.L", "MainStrut.R", "MainWheel.L",
                            "MainWheel.R", "WheelFairing.L", "WheelFairing.R")]

        self.assertAlmostEqual(2 * prop_radius(blades) / 0.0254, 79.255, places=2)
        corrections.apply_corrections(blades + inert, converter)
        corrected_in = 2 * prop_radius(blades) / 0.0254
        self.assertLessEqual(corrected_in, 79.0)
        self.assertGreaterEqual(corrected_in, 77.5)

    def test_a_blocked_correction_is_never_applied(self):
        """Blocked entries carry a ready transform. It must stay inert.

        The profile no longer HOLDS a blocked correction - all three are active
        as of 2026-09-15 - so this drives the mechanism with a synthetic one.
        Asserting that blocked work exists would have made this test fail on
        the day the last blocker was cleared, which is the wrong signal.
        """
        blocked = dict(corrections.load_profile()["corrections"][0])
        blocked["status"] = "blocked"
        stub = [Stub(n, [(1.0, 2.0, 3.0)])
                for n in ("Blade1", "Blade2", "Blade3", "FastProp")]
        before = [tuple(v) for o in stub for v in o.vertices]
        corrections.apply_corrections(stub, converter, {"corrections": [blocked]})
        after = [tuple(v) for o in stub for v in o.vertices]
        self.assertEqual(before, after, "a blocked correction moved geometry")

    def test_every_blocked_correction_says_what_it_is_waiting_for(self):
        """A blocked item with no stated blocker is indistinguishable from
        abandoned work, and the next reader will re-derive the analysis."""
        for c in corrections.load_profile()["corrections"]:
            if c.get("status") != "blocked":
                continue
            for field in ("blocked_on", "rationale", "source"):
                self.assertTrue(c.get(field), f"{c['id']} missing {field}")

    def test_the_spinner_is_deliberately_not_scaled(self):
        """Spinner diameter is not propeller diameter."""
        active = [c for c in corrections.load_profile()["corrections"]
                  if c.get("status") == "active"]
        for c in active:
            self.assertNotIn("chrome_spinner", c["objects"])


if __name__ == "__main__":
    unittest.main()


class SpanBlend(unittest.TestCase):
    """A-1 stage 3: the horizontal tail span, corrected by a region transform.

    The earlier blocking note said the stabiliser lives inside Airframe with
    the wings, so a spanwise scale would shrink the wings. It does not:
    Airframe carries only the tip caps, the surface is the Elevator object,
    and the wings are 3 metres forward of any window that selects the tail.
    """

    def test_the_root_station_does_not_move(self):
        # If it did, the junction with the tailcone would tear.
        root = 0.51
        self.assertEqual(corrections._span_blend((root, 0.4, 5.5), root, 0.9),
                         (root, 0.4, 5.5))

    def test_vertices_inboard_of_the_root_are_untouched(self):
        self.assertEqual(corrections._span_blend((0.2, 0.4, 5.5), 0.51, 0.9),
                         (0.2, 0.4, 5.5))

    def test_the_tip_lands_on_the_target_span(self):
        root, measured, target = 0.51, 1.8164, 1.778
        ratio = (target - root) / (measured - root)
        moved = corrections._span_blend((measured, 0.4, 5.5), root, ratio)
        self.assertAlmostEqual(moved[0], target, places=6)

    def test_both_sides_move_symmetrically(self):
        a = corrections._span_blend((1.8164, 0.4, 5.5), 0.51, 0.97)
        b = corrections._span_blend((-1.8164, 0.4, 5.5), 0.51, 0.97)
        self.assertAlmostEqual(a[0], -b[0], places=9)

    def test_height_and_station_are_preserved(self):
        moved = corrections._span_blend((1.8164, 0.42, 5.55), 0.51, 0.97)
        self.assertEqual((moved[1], moved[2]), (0.42, 5.55))

    def test_the_window_excludes_the_wings(self):
        # The wings sit at z 0.548..1.815 on this donor. Selecting the tail by
        # a z-window is only safe because of that separation, so pin it.
        region = None
        for c in corrections.load_profile()["corrections"]:
            if c["id"] == "horizontal_tail_span_to_poh":
                region = c["region"]
        self.assertIsNotNone(region)
        self.assertGreater(region["z_min"], 2.0, "window must clear the wings")
        self.assertFalse(corrections._in_region((5.4558, 0.5, 1.0), region),
                         "a wingtip must never be selected")
        self.assertTrue(corrections._in_region((1.8164, 0.42, 5.5), region))

    def test_the_correction_closes_the_span_to_the_poh(self):
        profile = corrections.load_profile()
        c = [x for x in profile["corrections"]
             if x["id"] == "horizontal_tail_span_to_poh"][0]
        self.assertEqual(c["status"], "active")
        self.assertAlmostEqual(c["target_half_span_m"] * 2 / 0.0254, 140.0, places=3)


class GearTrackWiden(unittest.TestCase):
    """A-1 stage 3: main wheel track, widened to the POH.

    The reading was settled as centre-to-centre by inference, not by reading
    the drawing - see the correction's own rationale. These tests are about
    the TRANSFORM being right, which is a separate question from the reading
    being right.
    """

    ROOT, TIP, DELTA = 0.938, 1.235, 0.0636

    def test_a_rigid_part_moves_without_changing_width(self):
        # The whole reason wheel and fairing translate instead of scaling: a
        # scale about an inboard root widens the TYRE as well as moving it.
        inner = corrections._track_widen((1.226, -0.8, 1.4), self.ROOT, self.TIP,
                                         self.DELTA, rigid=True)
        outer = corrections._track_widen((1.390, -0.8, 1.4), self.ROOT, self.TIP,
                                         self.DELTA, rigid=True)
        self.assertAlmostEqual(outer[0] - inner[0], 1.390 - 1.226, places=9)

    def test_a_rigid_part_moves_by_exactly_the_delta(self):
        moved = corrections._track_widen((1.308, -0.8, 1.4), self.ROOT, self.TIP,
                                         self.DELTA, rigid=True)
        self.assertAlmostEqual(moved[0], 1.308 + self.DELTA, places=9)

    def test_the_strut_attachment_is_a_fixed_point(self):
        # If it moved, the leg would part company with the fuselage.
        at_root = corrections._track_widen((self.ROOT, -0.7, 1.4), self.ROOT,
                                           self.TIP, self.DELTA, rigid=False)
        self.assertAlmostEqual(at_root[0], self.ROOT, places=9)

    def test_strut_material_inboard_of_the_root_does_not_move(self):
        # MainStrut reaches |x| 0.398, well inside the fuselage.
        self.assertEqual(corrections._track_widen((0.398, -0.7, 1.4), self.ROOT,
                                                  self.TIP, self.DELTA, rigid=False),
                         (0.398, -0.7, 1.4))

    def test_the_strut_tip_takes_the_full_delta(self):
        tip = corrections._track_widen((self.TIP, -0.88, 1.4), self.ROOT, self.TIP,
                                       self.DELTA, rigid=False)
        self.assertAlmostEqual(tip[0], self.TIP + self.DELTA, places=9)

    def test_the_strut_ramp_is_monotonic_between_root_and_tip(self):
        xs = [self.ROOT + i * (self.TIP - self.ROOT) / 10 for i in range(11)]
        moved = [corrections._track_widen((x, -0.7, 1.4), self.ROOT, self.TIP,
                                          self.DELTA, rigid=False)[0] for x in xs]
        self.assertEqual(moved, sorted(moved))

    def test_both_sides_widen_outward_not_both_one_way(self):
        left = corrections._track_widen((-1.308, -0.8, 1.4), self.ROOT, self.TIP,
                                        self.DELTA, rigid=True)
        right = corrections._track_widen((1.308, -0.8, 1.4), self.ROOT, self.TIP,
                                         self.DELTA, rigid=True)
        self.assertAlmostEqual(left[0], -right[0], places=9)
        self.assertLess(left[0], -1.308)
        self.assertGreater(right[0], 1.308)

    def test_height_and_station_are_untouched(self):
        moved = corrections._track_widen((1.308, -0.83, 1.41), self.ROOT, self.TIP,
                                         self.DELTA, rigid=True)
        self.assertEqual((moved[1], moved[2]), (-0.83, 1.41))

    def test_the_profile_targets_nine_feet_centre_to_centre(self):
        c = [x for x in corrections.load_profile()["corrections"]
             if x["id"] == "main_wheel_track_to_poh"][0]
        self.assertEqual(c["status"], "active")
        self.assertAlmostEqual(c["target_track_m"] / 0.0254, 108.0, places=3)
        self.assertIn("centre", c["reading"])

    def test_the_record_admits_the_reading_is_inferred(self):
        # It was not read off the drawing, and a later reader must not mistake
        # it for the propeller's certification bound.
        c = [x for x in corrections.load_profile()["corrections"]
             if x["id"] == "main_wheel_track_to_poh"][0]
        self.assertIn("INFERRED", c["evidence_strength"])

    def test_wheel_and_fairing_are_rigid_and_the_strut_is_not(self):
        c = [x for x in corrections.load_profile()["corrections"]
             if x["id"] == "main_wheel_track_to_poh"][0]
        rigid = set(c["rigid_objects"])
        self.assertEqual(rigid, {"MainWheel.L", "MainWheel.R",
                                 "WheelFairing.L", "WheelFairing.R"})
        self.assertNotIn("MainStrut.L", rigid)
