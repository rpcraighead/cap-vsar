"""L-7a: the simulator and the flight planner must share one loading baseline.

The planner plans the sortie and the simulator flies it, and the crew reads
both. If they disagree about empty weight or empty CG then every takeoff
weight, every CG position and every performance number differs between the
two, silently, for the same loading. They were 46 lb apart.

Neither number is a measurement of CAP 487. Both are the POH Figure 6-3 SAMPLE
aircraft, used deliberately as a shared sourced baseline - which only works if
it is the SAME baseline on both sides. This suite is what keeps them together.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_c182t_package import ACF_PATCHES  # noqa: E402

PLANNER_SOURCE = ROOT / "services/flightplanner/app.py"


def planner_aircraft(name: str = "CAP 487") -> dict:
    """Read AIRCRAFT_DATABASE out of the planner without importing it.

    Deliberately not an import. services/flightplanner/app.py would shadow the
    exercise service's `app` PACKAGE on sys.path, which breaks tests/test_radio.py
    and tests/test_provision_mumble.py when pytest collects this directory in one
    process. Booting a Flask app to read a literal is also more than this needs.
    """
    tree = ast.parse(PLANNER_SOURCE.read_text())
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(t, "id", None) == "AIRCRAFT_DATABASE" for t in node.targets):
            continue
        database = ast.literal_eval(node.value)
        return database[name]
    raise AssertionError("AIRCRAFT_DATABASE not found in the planner")

# The %MAC mapping the builder derives its CG numbers with, from the TCDS.
# Repeated here on purpose: if someone edits one of these constants in the
# builder without re-deriving, this suite should fail rather than follow along.
MAC_LE_FT, MAC_FT = 1.994, 4.837
MAC_LE_FS_IN, MAC_IN = 25.98, 58.8


def fs_to_acf_z(station_in: float) -> float:
    """Fuselage station (in aft of the Cessna datum) -> ACF frame Z (ft)."""
    return MAC_LE_FT + ((station_in - MAC_LE_FS_IN) / MAC_IN) * MAC_FT


def patched(parameter: str) -> float:
    """The value the builder writes for one ACF parameter."""
    pattern = rf"^P acf/{parameter} .*"
    value = ACF_PATCHES[pattern]
    return float(value.rsplit(" ", 1)[1])


class SharedLoadingBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ac = planner_aircraft()

    def test_the_mapping_reproduces_the_builders_own_cg_limits(self):
        """If this fails, the mapping below is not the one the builder used."""
        self.assertAlmostEqual(fs_to_acf_z(33.0), patched("_cgZ_fwd"), places=3)
        self.assertAlmostEqual(fs_to_acf_z(46.0), patched("_cgZ_aft"), places=3)

    def test_simulator_and_planner_agree_on_empty_weight(self):
        """They were 1970 vs 1924 - 46 lb that showed up in every calculation."""
        self.assertEqual(patched("_m_empty"), float(self.ac["empty_weight"]))

    def test_simulator_and_planner_agree_on_empty_cg(self):
        """The empty CG was never patched; it was the stock C172SP's 2.900095."""
        arm_in = self.ac["empty_weight_moment"] * 1000.0 / self.ac["empty_weight"]
        self.assertAlmostEqual(patched("_cgZ"), fs_to_acf_z(arm_in), places=3)

    def test_the_empty_cg_is_derived_not_inherited(self):
        """A regression guard with a name: 2.900095 is the C172SP value."""
        self.assertNotAlmostEqual(patched("_cgZ"), 2.900095, places=4)

    def test_the_empty_cg_sits_inside_the_certificated_envelope(self):
        self.assertGreaterEqual(patched("_cgZ"), patched("_cgZ_fwd"))
        self.assertLessEqual(patched("_cgZ"), patched("_cgZ_aft"))

    def test_simulator_and_planner_agree_on_maximum_weight(self):
        self.assertEqual(patched("_m_max"), float(self.ac["max_takeoff_weight"]))

    def test_the_forward_limit_is_the_most_forward_scheduled_point(self):
        """X-Plane takes one forward limit; the TCDS schedules it by weight.
        The builder documents using the most forward point, so the envelope is
        correct when light and permissive when heavy. Hold it to that."""
        most_forward = min(station for _, station in self.ac["cg_fwd_points"])
        self.assertAlmostEqual(patched("_cgZ_fwd"), fs_to_acf_z(most_forward), places=3)

    def test_the_planner_comment_no_longer_claims_the_builder_disagrees(self):
        """app.py told the reader the builder still used 1970 lb. It does not."""
        source = (ROOT / "services/flightplanner/app.py").read_text()
        self.assertNotIn("The builder still", source)


if __name__ == "__main__":
    unittest.main()
