"""A2-10: the ACF the builder writes is pinned to the sourced 182T values.

`ACF_PATCHES` and `scripts/c182t_dimension_master.json` both carry 182T numbers
and nothing used to check that they agree. That is how the propeller kept the
C172's 76.8-inch disc while the dimension master said 79 in (A2-2) and the
engine kept four cylinders (A2-1). These tests read only the patch table and the
JSON, so they run without X-Plane; the last one also inspects the installed
Laminar C172 when present and lists every engine, propeller, blade and gear
field the build still inherits unchanged, so the next unpatched inheritance is
visible rather than silent.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from build_c182t_package import ACF_PATCHES, DEFAULT_SOURCE_DIR  # noqa: E402

MASTER = json.loads((REPO / "scripts" / "c182t_dimension_master.json").read_text())
TARGETS = {t["id"]: t for t in MASTER["targets"]}


def patched(record: str) -> float:
    wanted = "P %s " % record
    hits = [r for r in ACF_PATCHES.values() if r.startswith(wanted)]
    assert len(hits) == 1, "expected one ACF patch writing %s, found %d" % (record, len(hits))
    return float(hits[0][len(wanted):])


def test_physics_propeller_diameter_is_the_sourced_one():
    radius_in = patched("_blad/0/_semilen_SEG") * 12.0
    prop = TARGETS["propeller_diameter"]
    assert prop["limit_min_in"] <= 2 * radius_in <= prop["limit_max_in"]
    assert 2 * radius_in == pytest.approx(prop["value_in"], abs=0.05)


def test_propeller_pitch_stops_are_the_tcds_30_inch_station_values():
    # TCDS 3A13 Rev 66 p.32, B3D36C431/80VSA-1: Low 14.9 deg, High 31.7 deg.
    assert patched("_prop/0/_min_pitch") == pytest.approx(14.9)
    assert patched("_prop/0/_max_pitch") == pytest.approx(31.7)
    assert patched("_prop/0/_num_blades") == 3
    assert patched("_prop/0/_prop_type") == 1


def test_engine_matches_the_io540_ab1a5():
    assert patched("acf/_num_cylinders") == 6
    assert patched("acf/_power_max_limit") == 230
    assert patched("_engn/0/_RSC_redline_ENGN") == 2400


def test_va_is_set():
    assert patched("acf/_Va_kts") == 110


# Wheel positions X-Plane 12.4.3 reported for the C172 gear attach points
# (sim/flightmodel/parts/tire_[xz]_no_deflection, 2026-10-11, metres).
MEASURED_C172_GEAR = {"main_x": 1.2516422, "main_z": 0.44212228, "nose_z": -1.22536564,
                      "attach_x_ft": 1.600000024, "nose_attach_z_ft": -0.600000024}


def test_main_gear_track_and_wheelbase_are_patched_to_the_master():
    """A2-3: a moved attach point moves its wheel by the same amount, so the
    patched attach points must put the measured wheels on the POH dimensions."""
    shift_x = (abs(patched("_gear/2/_gear_x")) - MEASURED_C172_GEAR["attach_x_ft"]) * .3048
    shift_nose = (patched("_gear/0/_gear_z") - MEASURED_C172_GEAR["nose_attach_z_ft"]) * .3048
    track_m = 2 * (MEASURED_C172_GEAR["main_x"] + shift_x)
    wheelbase_m = MEASURED_C172_GEAR["main_z"] - (MEASURED_C172_GEAR["nose_z"] + shift_nose)
    assert track_m == pytest.approx(TARGETS["main_wheel_track"]["value_m"], abs=.003)
    assert wheelbase_m == pytest.approx(TARGETS["wheel_base"]["value_m"], abs=.003)
    assert patched("_gear/1/_gear_x") == pytest.approx(-patched("_gear/2/_gear_x"))


C172_ACF = DEFAULT_SOURCE_DIR / "Cessna_172SP_G1000.acf"

# The physical engine, propeller and gear fields that decide performance and
# ground handling. Each must either be patched by the builder or appear in
# INHERITED_ON_PURPOSE with the reason the C172 value is acceptable.
WATCHLIST = (
    ["_blad/0/_semilen_SEG", "_blad/0/_Croot", "_blad/0/_Ctip"]
    + ["_prop/0/_%s" % k for k in ("num_blades", "prop_type", "min_pitch", "max_pitch",
                                    "des_rpm_prp", "des_kts_acf", "prop_dir")]
    + ["_engn/0/_%s" % k for k in ("power_max_limit", "RSC_max_pwr_ENGN", "RSC_redline_ENGN")]
    + ["acf/_%s" % k for k in ("num_cylinders", "power_max_limit", "max_MP_limit",
                                "engine_friction_ratio", "Va_kts", "m_empty", "m_max",
                                "m_fuel_max_tot")]
    + ["_gear/%d/_%s" % (g, k) for g in (0, 1, 2)
       for k in ("gear_x", "gear_y", "gear_z", "leg_len", "latE", "lonE", "tire_radius")]
)

INHERITED_ON_PURPOSE = {
    "_blad/0/_Croot": "no source for the B3D36C431 planform",
    "_blad/0/_Ctip": "no source for the B3D36C431 planform",
    "_prop/0/_prop_dir": "same rotation as the C172 (clockwise from the seat)",
    "acf/_max_MP_limit": "29.9 in.hg is a sea-level full-throttle limit for both normally aspirated engines",
    "acf/_engine_friction_ratio": "X-Plane default; revisit only if C1 power stays short (A2-4)",
    "_gear/0/_gear_x": "nose gear on the centreline",
    "_gear/0/_gear_y": "vertical attach: ground attitude not re-posed (dimension master: attitude unknown)",
    "_gear/1/_gear_y": "vertical attach: as above",
    "_gear/2/_gear_y": "vertical attach: as above",
    "_gear/1/_gear_z": "main contact station kept: it fixes CG-to-main-wheel distance; the nose moves instead",
    "_gear/2/_gear_z": "as above",
}
for _g in (0, 1, 2):
    for _k in ("leg_len", "latE", "lonE", "tire_radius"):
        INHERITED_ON_PURPOSE["_gear/%d/_%s" % (_g, _k)] = (
            "strut and tyre geometry not sourced for the 182T; contact points are set by attach position")


@pytest.mark.skipif(not C172_ACF.is_file(), reason="Laminar C172SP not installed")
def test_every_watched_field_is_patched_or_inherited_by_decision():
    c172 = {}
    for line in C172_ACF.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "P":
            c172[parts[1]] = parts[2]
    patched_records = {r.split()[1] for r in ACF_PATCHES.values()}
    missing = [f for f in WATCHLIST if f not in c172]
    assert not missing, "watched fields absent from the C172 ACF: %s" % missing
    unexplained = ["%s = %s" % (f, c172[f]) for f in WATCHLIST
                   if f not in patched_records and f not in INHERITED_ON_PURPOSE]
    assert not unexplained, "C172 values inherited without a decision:\n" + "\n".join(unexplained)
    overlap = sorted(set(INHERITED_ON_PURPOSE) & patched_records)
    assert not overlap, "fields both patched and listed as inherited: %s" % overlap
