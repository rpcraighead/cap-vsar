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


if __name__ == "__main__":
    unittest.main()
