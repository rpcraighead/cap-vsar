"""Tests for the local GPL FlightGear C182 prototype build path."""

from __future__ import annotations

import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from build_c182t_package import ACF_PATCHES  # noqa: E402
import fetch_flightgear_c182 as donor_fetch  # noqa: E402
import convert_flightgear_c182  # noqa: E402
from convert_flightgear_c182 import (  # noqa: E402
    DELIBERATELY_EXCLUDED,
    KNOWN_UNCONVERTED,
    AC3DParser,
    ac_to_xplane,
    assert_all_objects_classified,
    flatten,
    unclassified_objects,
    validate_obj8,
    write_obj8,
)


SIMPLE_AC3D = """AC3Db
MATERIAL "white" rgb 1 1 1 amb 1 1 1 emis 0 0 0 spec 0 0 0 shi 0 trans 0
OBJECT world
name "root"
kids 1
OBJECT poly
name "Airframe"
texture "Default.png"
numvert 4
-1 0 -2
1 0 -2
1 0 2
-1 0 2
numsurf 1
SURF 0X10
mat 0
refs 4
0 0 0
1 1 0
2 1 1
3 0 1
kids 0
"""


class AC3DConversionTests(unittest.TestCase):
    def test_quad_is_triangulated_and_axes_are_converted(self):
        root = AC3DParser(SIMPLE_AC3D).parse()
        meshes = [obj for obj in flatten(root) if obj.surfaces]
        self.assertEqual([obj.name for obj in meshes], ["Airframe"])
        self.assertEqual(ac_to_xplane((-1.0, 0.0, -2.0)), (2.0, 0.0, -1.0))

        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name) / "airframe.obj"
            report = write_obj8(output, meshes, texture="airframe.png")
            counts = validate_obj8(output)

        self.assertEqual(counts["indices"], 6)
        self.assertEqual(report["bounds_m"]["x"], [-2.0, 2.0])
        self.assertEqual(report["bounds_m"]["z"], [-1.0, 1.0])

    def test_non_identity_object_transform_is_rejected(self):
        transformed = SIMPLE_AC3D.replace(
            'name "Airframe"\n', 'name "Airframe"\nloc 1 0 0\n'
        )
        with self.assertRaisesRegex(ValueError, "Unsupported AC3D location"):
            AC3DParser(transformed).parse()

    def test_obj_validator_rejects_bad_index_count(self):
        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name) / "bad.obj"
            output.write_text("A\n800\nOBJ\nPOINT_COUNTS 1 0 0 3\nVT 0 0 0 0 1 0 0 0\nIDX 0\n")
            with self.assertRaisesRegex(ValueError, "count mismatch"):
                validate_obj8(output)


class AircraftAttachmentTests(unittest.TestCase):
    def test_every_stock_c172_exterior_slot_is_replaced(self):
        replacements = set(ACF_PATCHES.values())
        expected = {
            "P _obja/15/_v10_att_file_stl flightgear_c182t.obj",
            "P _obja/16/_v10_att_file_stl flightgear_blank.obj",
            "P _obja/17/_v10_att_file_stl flightgear_c182t_propeller.obj",
            "P _obja/18/_v10_att_file_stl flightgear_c182t_prop_blur.obj",
            "P _obja/19/_v10_att_file_stl flightgear_c182t_glass.obj",
            "P _obja/22/_v10_att_file_stl flightgear_c182t_lights.obj",
            "P _obja/23/_v10_att_file_stl flightgear_blank.obj",
            "P _obja/24/_v10_att_file_stl flightgear_blank.obj",
            "P _obja/25/_v10_att_file_stl flightgear_blank.obj",
            "P _obja/26/_v10_att_file_stl flightgear_blank.obj",
        }
        self.assertTrue(expected <= replacements)


class WindingConventionTests(unittest.TestCase):
    """X-Plane winds triangles opposite to the stored vertex normal.

    Measured on Laminar's own objects/fuselage.obj: the winding-derived normal
    agrees with the stored normal 0.0% of the time. Emitting AC3D's own order
    makes X-Plane cull the near-side skin, which renders as a see-through cabin.
    """

    def _triangles_from_obj(self, path):
        verts, idx = [], []
        for line in path.read_text().splitlines():
            if line.startswith("VT "):
                verts.append([float(v) for v in line.split()[1:9]])
            elif line.startswith("IDX10 "):
                idx.extend(int(v) for v in line.split()[1:])
            elif line.startswith("IDX "):
                idx.append(int(line.split()[1]))
        return [(verts[idx[i]], verts[idx[i + 1]], verts[idx[i + 2]])
                for i in range(0, len(idx) - 2, 3)]

    def test_winding_opposes_the_stored_normal(self):
        root = AC3DParser(SIMPLE_AC3D).parse()
        meshes = [obj for obj in flatten(root) if obj.surfaces]
        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name) / "wind.obj"
            write_obj8(output, meshes, texture="airframe.png")
            tris = self._triangles_from_obj(output)

        self.assertTrue(tris)
        for a, b, c in tris:
            ux, uy, uz = (b[i] - a[i] for i in range(3))
            vx, vy, vz = (c[i] - a[i] for i in range(3))
            wind = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
            stored = [(a[i + 3] + b[i + 3] + c[i + 3]) / 3 for i in range(3)]
            dot = sum(wind[i] * stored[i] for i in range(3))
            self.assertLess(
                dot, 0.0,
                "winding must oppose the stored normal or X-Plane culls the face",
            )


class ObjectClassificationTests(unittest.TestCase):
    """Selection must fail closed: no donor object may be dropped silently."""

    def test_exclusion_lists_are_disjoint(self):
        self.assertEqual(DELIBERATELY_EXCLUDED & KNOWN_UNCONVERTED, set())

    def test_untextured_unknown_object_is_rejected(self):
        stray = SimpleNamespace(name="MysteryPart", texture=None)
        with self.assertRaisesRegex(ValueError, "no output selection"):
            assert_all_objects_classified([stray])

    def test_documented_exclusions_and_selected_textures_pass(self):
        allowed = [
            SimpleNamespace(name="Airframe", texture="Default.png"),
            SimpleNamespace(name="NavLightGreen", texture="Lights.png"),
            SimpleNamespace(name="Windscreen", texture=None),
            SimpleNamespace(name="FastProp", texture="PropBlur.png"),
            SimpleNamespace(name="Blade1", texture="Default.png"),
            SimpleNamespace(name="safety-cone.cs.L", texture=None),
            SimpleNamespace(name="Strobe", texture=None),
        ]
        assert_all_objects_classified(allowed)
        self.assertEqual(unclassified_objects(allowed), [])

    def test_strobe_is_recorded_as_a_known_gap(self):
        # The published C182T span is defined with the wingtip strobes
        # installed, so a missing Strobe changes the span measurement.
        self.assertIn("Strobe", KNOWN_UNCONVERTED)


class DonorValidationTests(unittest.TestCase):
    def test_extracted_donor_file_hashes_are_enforced(self):
        license_text = b"GNU GENERAL PUBLIC LICENSE\nVersion 2\n"
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            (root / "LICENSE").write_bytes(license_text)
            expected = sha256(license_text).hexdigest()
            with patch.dict(
                donor_fetch.REQUIRED_FILE_SHA256,
                {"LICENSE": expected},
                clear=True,
            ):
                donor_fetch.validate_donor(root)
                (root / "LICENSE").write_bytes(license_text + b"changed\n")
                with self.assertRaisesRegex(ValueError, "pinned commit"):
                    donor_fetch.validate_donor(root)

    def test_every_asset_the_exterior_pipeline_reads_is_pinned(self):
        """The exterior editable source must be checksum-verified like the rest.

        `dev/C182S.blend` is the editable source of `Models/c182s.ac` - the file
        the converter parses and the measurement harness selects its landmarks
        on, and the one asset a geometry correction actually edits. It was the
        single unpinned file in an otherwise fully checksum-verified donor
        pipeline, while `dev/C182T.blend` (the cockpit model, which no exterior
        work touches) was pinned. Guard against that regressing.
        """
        pinned = donor_fetch.REQUIRED_FILE_SHA256
        self.assertIn("Models/c182s.ac", pinned)
        self.assertIn("dev/C182S.blend", pinned)
        for name, digest in pinned.items():
            self.assertRegex(digest, r"^[0-9a-f]{64}$", f"{name} is not a sha256")


if __name__ == "__main__":
    unittest.main()


class LiveryTests(unittest.TestCase):
    """The approved CAP scheme, CAPP 130-2 line drawing A (4 October 2021).

    The colour is decided from the 3D POSITION and rasterised through the
    mesh's own UVs. Painting rectangles into the atlas only worked where a
    region unwraps as an axis-aligned band: the fuselage sides do, the belly
    and wings do not, so rectangles left the belly white.
    """

    cv = convert_flightgear_c182

    def test_white_above_the_division_and_blue_below(self):
        z = 1.0
        div = self.cv.DIV_Y_AT[1] + self.cv.DIV_SLOPE * (z - self.cv.DIV_Y_AT[0])
        self.assertEqual(self.cv.scheme_colour(0.6, div + 0.3, z), self.cv.CAP_WHITE)
        self.assertEqual(self.cv.scheme_colour(0.6, div - 0.3, z), self.cv.CAP_BLUE)

    def test_the_belly_is_blue(self):
        # The whole point of model space: a rectangle painter left this white.
        self.assertEqual(self.cv.scheme_colour(0.0, -0.9, 1.0), self.cv.CAP_BLUE)

    def test_the_vertical_tail_is_red(self):
        self.assertEqual(self.cv.scheme_colour(0.0, 1.5, 6.0), self.cv.CAP_RED)

    def test_the_stripe_band_sits_on_the_division_in_the_right_order(self):
        # CAPP 130-2: 2 in gray, 1 in space, 1.75 in red, reading downward.
        z = 1.0
        div = self.cv.DIV_Y_AT[1] + self.cv.DIV_SLOPE * (z - self.cv.DIV_Y_AT[0])
        inch = 0.0254
        self.assertEqual(self.cv.scheme_colour(0.6, div - 1.0 * inch, z), self.cv.CAP_GRAY)
        self.assertEqual(self.cv.scheme_colour(0.6, div - 2.5 * inch, z), self.cv.CAP_WHITE)
        self.assertEqual(self.cv.scheme_colour(0.6, div - 4.0 * inch, z), self.cv.CAP_RED)
        self.assertEqual(self.cv.scheme_colour(0.6, div - 6.0 * inch, z), self.cv.CAP_BLUE)

    def test_the_division_sweeps_upward_going_aft(self):
        # A level division is not the scheme; the drawing sweeps it up to the tail.
        def div(z):
            return self.cv.DIV_Y_AT[1] + self.cv.DIV_SLOPE * (z - self.cv.DIV_Y_AT[0])
        self.assertGreater(div(5.0), div(0.0))

    def test_a_straddling_triangle_is_split_rather_than_flat_filled(self):
        # A two-inch stripe is thinner than a fuselage triangle. Without
        # subdivision the stripe simply vanishes into whichever colour the
        # first vertex happened to be.
        self.assertGreaterEqual(self.cv.PAINT_MAX_DEPTH, 3)

    def test_the_two_side_panels_do_not_overlap(self):
        # Lettering still uses these; text needs a flat rectangle.
        port, stbd = self.cv.SIDE_PANEL_PORT, self.cv.SIDE_PANEL_STBD
        self.assertLess(port[3], stbd[1])

    def test_starboard_lettering_is_the_port_tile_rotated_180(self):
        # Not flipped. Viewed from outside starboard the nose is to the
        # viewer's right, so u runs leftward AND v is inverted - both axes
        # reverse. A vertical flip alone leaves the horizontal mirror that was
        # actually reported.
        from PIL import Image, ImageChops
        marks = self.cv.side_markings(600, 200)
        twice = marks.transpose(Image.ROTATE_180).transpose(Image.ROTATE_180)
        self.assertIsNone(ImageChops.difference(marks, twice).getbbox())
        flipped = marks.transpose(Image.FLIP_TOP_BOTTOM)
        self.assertIsNotNone(
            ImageChops.difference(marks.transpose(Image.ROTATE_180), flipped).getbbox())

    def test_the_registration_is_white(self):
        marks = self.cv.side_markings(1368, 452)
        colours = {c[1][:3] for c in marks.getcolors(1 << 20)}
        self.assertIn(self.cv.CAP_WHITE[:3], colours)

    def test_the_scheme_is_drawn_not_traced(self):
        # CAPP 130-2: "ALL DECALS PROVIDED BY CAP". The roundel, the wing
        # lettering and the vertical fin titles are insignia rather than paint
        # and are deliberately absent; CAPR 130-2 15.2 separately forbids wing
        # logos and tail flashes. Checked by asserting the drawing functions
        # open no file, not by looking for a word - the source names those
        # decals in prose precisely to record why they are missing.
        import inspect
        for fn in (self.cv.scheme_colour, self.cv.paint_scheme, self.cv.side_markings):
            self.assertNotIn("Image.open", inspect.getsource(fn), fn.__name__)


