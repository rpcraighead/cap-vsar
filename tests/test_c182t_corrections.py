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

        self.assertAlmostEqual(2 * prop_radius(blades) / 0.0254, 79.255, places=2)
        corrections.apply_corrections(blades + inert, converter)
        corrected_in = 2 * prop_radius(blades) / 0.0254
        self.assertLessEqual(corrected_in, 79.0)
        self.assertGreaterEqual(corrected_in, 77.5)

    def test_a_blocked_correction_is_never_applied(self):
        """Blocked entries carry a ready transform. It must stay inert."""
        blocked = [c for c in corrections.load_profile()["corrections"]
                   if c.get("status") == "blocked"]
        self.assertTrue(blocked, "expected the profile to record blocked work")
        for c in blocked:
            # Named objects exist in the donor, so a typo does not hide here
            # until the day someone flips the status to active.
            self.assertTrue(c["objects"])
            stub = [Stub(n, [(1.0, 2.0, 3.0)]) for n in ("Blade1", "Blade2", "Blade3", "FastProp")]
            before = [tuple(v) for o in stub for v in o.vertices]
            corrections.apply_corrections(stub, converter, {"corrections": [c]})
            after = [tuple(v) for o in stub for v in o.vertices]
            self.assertEqual(before, after, f"{c['id']} moved geometry while blocked")

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
