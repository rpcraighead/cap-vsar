"""A-1 stage 3: exterior geometry corrections applied to the pinned donor.

The donor mesh is GPL and lives outside this repository, so a corrected mesh
cannot be committed here. The corrections are therefore parametric and
version-controlled as data (`c182t_dimension_master.json` says what is wrong,
`c182t_corrections.json` says what to do about it), applied at load time by
both the converter and the measurement harness so that what is measured and
what is emitted are the same geometry.

Region-by-region, per `docs/bugs/CLAUDE_RESUME_C182_DIMENSIONS.md` section 3.
A whole-model non-uniform scale is explicitly not what this is: the measured
errors run -4.64 to +2.16 percent with differing signs, which rules out a
single global scale factor and is why each correction names its own objects.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

PROFILE = Path(__file__).with_name("c182t_corrections.json")


def load_profile(path: Path | None = None) -> dict:
    return json.loads((path or PROFILE).read_text(encoding="utf-8"))


def xplane_to_ac(point):
    """Inverse of converter.ac_to_xplane, which maps (x,y,z) -> (-z, y, x)."""
    return (point[2], point[1], -point[0])


def _radial_scale_about_axis(vertex_xp, hub, axis, scale):
    """Scale only the component perpendicular to `axis`, about `hub`.

    The axial component is untouched, so the hub and the axis itself are
    fixed points of the transform and no animation pivot moves.
    """
    delta = tuple(vertex_xp[i] - hub[i] for i in range(3))
    along = sum(delta[i] * axis[i] for i in range(3))
    axial = tuple(along * axis[i] for i in range(3))
    radial = tuple(delta[i] - axial[i] for i in range(3))
    return tuple(hub[i] + axial[i] + scale * radial[i] for i in range(3))


def apply_corrections(objects, converter, profile: dict | None = None) -> list[dict]:
    """Mutate parsed donor objects in place. Returns a record of what was applied.

    `converter` is passed in rather than imported to avoid a circular import:
    the converter itself calls this during its own module-level build.
    """
    profile = profile or load_profile()
    by_name = {obj.name: obj for obj in objects}
    applied = []

    for correction in profile["corrections"]:
        if correction.get("status") != "active":
            continue
        if correction["type"] != "radial_scale_about_axis":
            raise ValueError(f"Unknown correction type: {correction['type']}")

        missing = [n for n in correction["objects"] if n not in by_name]
        if missing:
            # Fail loudly: a correction that silently matches nothing would
            # leave the geometry wrong while reporting success.
            raise ValueError(
                f"Correction {correction['id']} names absent objects: {missing}")

        rotation = converter.PROP_ROTATION
        hub, axis = rotation.center, rotation.axis
        norm = math.sqrt(sum(a * a for a in axis))
        if abs(norm - 1.0) > 1e-9:
            raise ValueError("Correction axis must be unit length")
        scale = float(correction["scale"])

        touched = 0
        for name in correction["objects"]:
            obj = by_name[name]
            corrected = []
            for vertex in obj.vertices:
                moved = _radial_scale_about_axis(
                    converter.ac_to_xplane(vertex), hub, axis, scale)
                corrected.append(xplane_to_ac(moved))
            obj.vertices = corrected
            touched += len(corrected)

        applied.append({"id": correction["id"], "closes": correction["closes"],
                        "scale": scale, "objects": list(correction["objects"]),
                        "vertices": touched})
    return applied
