"""Flight-model parameters for CAP 487, checked against their published sources.

These tests read only `ACF_PATCHES` from the package builder, so they need no
donor cache, no X-Plane install and no network.

Sources, recorded in full with page and SHA-256 in
``docs/C182T_DIMENSION_MASTER.md``:

* FAA TCDS 3A13 Revision 66, page 33, Models 182S and 182T.
* Cessna Model 182T NAV III GFC 700 AFCS POH, P/N 182TPHBUS-00/-01.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from build_c182t_package import ACF_PATCHES  # noqa: E402


def patched_record(record: str) -> float:
    """Return the numeric value ACF_PATCHES writes for a full record name."""
    wanted = "P %s " % record
    for replacement in ACF_PATCHES.values():
        if replacement.startswith(wanted):
            return float(replacement[len(wanted):])
    raise AssertionError("no ACF patch writes %s" % record)


def patched_value(key: str) -> float:
    """Return the numeric value ACF_PATCHES writes for an `acf/` key."""
    return patched_record("acf/%s" % key)


class ControlSurfaceTravelTests(unittest.TestCase):
    """TCDS 3A13 Rev 66 p.33, "Control surface movements", Models 182S/182T.

    The package is derived from Laminar's C172S, whose travels are materially
    smaller. Leaving them unpatched costs pitch authority, flap lift and drag,
    and yaw authority, all of which matter for approach and slow flight.
    """

    def test_elevator_travel_matches_tcds(self):
        # Up 28 deg +/-1, down 21 deg +/-1, relative to the stabilizer.
        self.assertAlmostEqual(patched_value("_elev1_up"), 28.0, places=3)
        self.assertAlmostEqual(patched_value("_elev1_dn"), 21.0, places=3)

    def test_rudder_travel_matches_tcds(self):
        # Right and left 24 deg +0/-1, measured parallel to 0.00 W.L.
        self.assertAlmostEqual(patched_value("_rudd1_lf"), 24.0, places=3)
        self.assertAlmostEqual(patched_value("_rudd1_rt"), 24.0, places=3)

    def test_full_flap_matches_tcds(self):
        # Wing flaps down 38 deg +0/-1. Detent 3 is the FULL position.
        self.assertAlmostEqual(patched_value("_flap1_dn/3"), 38.0, places=3)

    def test_aileron_travel_is_left_alone(self):
        # Ailerons are 20 up / 15 down on both the C172S and the C182T, so the
        # builder deliberately does not patch them. If a future change starts
        # patching them, it must still land on the TCDS values.
        for key in ("_ailn1_up", "_ailn1_dn"):
            try:
                value = patched_value(key)
            except AssertionError:
                continue
            expected = 20.0 if key.endswith("_up") else 15.0
            self.assertAlmostEqual(value, expected, places=3)


class WeightAndPowerplantTests(unittest.TestCase):
    """Values already carried by the builder, pinned so they cannot regress."""

    def test_weights_match_the_poh(self):
        # POH 1.3: standard empty 1,968 lb, max takeoff 3,100 lb. The builder
        # uses 1,970 lb for empty, within the POH's own rounding.
        self.assertAlmostEqual(patched_value("_m_empty"), 1970.0, places=3)
        self.assertAlmostEqual(patched_value("_m_max"), 3100.0, places=3)

    def test_vne_and_vno_match_the_tcds_airspeed_limits(self):
        # TCDS 3A13 p.32-33, Model 182T: never exceed 175 KIAS,
        # max structural cruising 140 KIAS.
        self.assertAlmostEqual(patched_value("_Vne_kts"), 175.0, places=3)
        self.assertAlmostEqual(patched_value("_Vno_kts"), 140.0, places=3)


class CentreOfGravityTests(unittest.TestCase):
    """TCDS 3A13 Rev 66 p.33, C.G. Range, Model 182T, placed by %MAC.

    The ACF frame's origin is not the Cessna reference datum and no consulted
    source locates the firewall in X-Plane's frame, so the limits are placed as a
    fraction of MAC, which is datum independent.

    `_wing/0/_part_z` is the root QUARTER-CHORD. That was confirmed against the
    donor mesh: the predicted and measured wing leading edge agree within ~12 mm
    at two clean spanwise stations, against a 396 mm difference between the
    quarter-chord and leading-edge interpretations. Getting this wrong moves the
    whole envelope by 27% MAC.
    """

    MAC_FT = 4.837
    MAC_LE_FT = 3.200 - 0.25 * 5.200 + 0.094   # root qc -> root LE -> MAC LE
    FS_LE_MAC_IN = 25.98
    MAC_IN = 58.8

    def _pct_mac(self, acf_ft: float) -> float:
        return (acf_ft - self.MAC_LE_FT) / self.MAC_FT * 100.0

    def _expected_ft(self, station_in: float) -> float:
        frac = (station_in - self.FS_LE_MAC_IN) / self.MAC_IN
        return self.MAC_LE_FT + frac * self.MAC_FT

    def test_aft_limit_matches_the_tcds_station(self):
        # Aft limit 46.0 in aft of datum at 3,100 lb and below = 34.05% MAC.
        self.assertAlmostEqual(
            patched_value("_cgZ_aft"), self._expected_ft(46.0), places=2
        )

    def test_forward_limit_uses_the_most_forward_certificated_station(self):
        # Forward limit is weight-scheduled; X-Plane takes one value, so the most
        # forward certificated point is used: 33.0 in at 2,250 lb and below.
        self.assertAlmostEqual(
            patched_value("_cgZ_fwd"), self._expected_ft(33.0), places=2
        )

    def test_envelope_sits_where_the_tcds_says_in_percent_mac(self):
        fwd = self._pct_mac(patched_value("_cgZ_fwd"))
        aft = self._pct_mac(patched_value("_cgZ_aft"))
        self.assertAlmostEqual(fwd, 11.94, delta=0.2)
        self.assertAlmostEqual(aft, 34.05, delta=0.2)
        self.assertLess(fwd, aft, "forward limit must be ahead of the aft limit")

    def test_stock_c172_aft_limit_is_not_still_present(self):
        # The C172S value of 3.900 ft sits at 39.40% MAC, about 3.1 in aft of the
        # C182T limit - the stability-reducing direction.
        self.assertNotAlmostEqual(patched_value("_cgZ_aft"), 3.900, places=2)


class HorizontalTailTests(unittest.TestCase):
    """POH Figure 1-1 Sheet 1, page 1-3, top view: horizontal tail span 11 ft 8 in.

    Same sourced three-view used for overall span and length in
    docs/C182T_DIMENSION_MASTER.md.
    """

    PART_X_FT = 0.300000012          # |_wing/8/_part_x|, root offset from centreline
    TARGET_SPAN_FT = 11.0 + 8.0 / 12.0

    def test_span_matches_the_poh_three_view(self):
        for part in (8, 9):
            semilen = patched_record("_wing/%d/_semilen_SEG" % part)
            span = 2.0 * (self.PART_X_FT + semilen)
            self.assertAlmostEqual(span, self.TARGET_SPAN_FT, places=3)

    def test_both_sides_are_symmetric(self):
        self.assertAlmostEqual(
            patched_record("_wing/8/_semilen_SEG"),
            patched_record("_wing/9/_semilen_SEG"),
            places=6,
        )

    def test_stock_c172_semilen_is_not_still_present(self):
        # The stock 5.300 ft gives an 11.20 ft span, 4.0% short of the C182T.
        self.assertNotAlmostEqual(
            patched_record("_wing/8/_semilen_SEG"), 5.300, places=2
        )


class PatchHygieneTests(unittest.TestCase):
    def test_every_patch_pattern_is_anchored_and_unique(self):
        seen = set()
        for pattern in ACF_PATCHES:
            self.assertTrue(
                pattern.startswith("^P "),
                "pattern must be anchored to a P record: %r" % pattern,
            )
            re.compile(pattern)  # must be a valid regex
            self.assertNotIn(pattern, seen, "duplicate pattern %r" % pattern)
            seen.add(pattern)


if __name__ == "__main__":
    unittest.main()
