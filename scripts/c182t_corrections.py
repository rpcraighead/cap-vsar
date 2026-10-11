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


def _span_blend(vertex_xp, root_abs_x, ratio):
    """Scale spanwise about the centreline, anchored at the root.

    x' = sign(x) * (root + (|x| - root) * ratio), so the root station is a
    fixed point and everything outboard of it closes proportionally. Vertices
    inboard of the root do not move at all. That is the "root blend": the
    stabiliser meets the tailcone at the root, and a scale about the
    centreline instead of the root would drag that junction inboard and tear
    the skin where the two meet.
    """
    x, y, z = vertex_xp
    if abs(x) <= root_abs_x:
        return vertex_xp
    moved = root_abs_x + (abs(x) - root_abs_x) * ratio
    return (math.copysign(moved, x), y, z)


def _track_widen(vertex_xp, root_abs_x, tip_abs_x, delta, rigid):
    """Move a main gear outboard: the wheel rigidly, the leg by bending.

    A single spanwise SCALE is wrong here. Scaling the wheel about a root
    inboard of it widens the TYRE as well as moving it - the donor's 164 mm
    wheel would come out 193 mm wide. So the wheel and its fairing translate
    rigidly by the full delta, keeping their own dimensions, and only the
    strut ramps: its inboard attachment is a fixed point and its outboard end
    takes the full delta, which is the leg flexing outward rather than growing.
    """
    x, y, z = vertex_xp
    if rigid:
        return (math.copysign(abs(x) + delta, x), y, z)
    if abs(x) <= root_abs_x:
        return vertex_xp
    span = tip_abs_x - root_abs_x
    ramp = 1.0 if span <= 0 else min(1.0, (abs(x) - root_abs_x) / span)
    return (math.copysign(abs(x) + delta * ramp, x), y, z)


def _apply_track_widen(correction, by_name, converter):
    root = float(correction["root_abs_x"])
    tip = float(correction["ramp_tip_abs_x"])
    measured = float(correction["measured_track_m"])
    target = float(correction["target_track_m"])
    delta = (target - measured) / 2.0
    rigid_names = set(correction["rigid_objects"])

    touched = 0
    for name in correction["objects"]:
        obj = by_name[name]
        rigid = name in rigid_names
        corrected = []
        for vertex in obj.vertices:
            point = converter.ac_to_xplane(vertex)
            moved = _track_widen(point, root, tip, delta, rigid)
            if moved != point:
                touched += 1
            corrected.append(xplane_to_ac(moved))
        obj.vertices = corrected
    return delta, touched


def _in_region(vertex_xp, region):
    """Is this vertex inside the correction's selection window?"""
    x, _, z = vertex_xp
    if region is None:
        return True
    if not (region["z_min"] <= z <= region["z_max"]):
        return False
    return abs(x) >= region.get("abs_x_min", 0.0)


def _apply_region_scale(correction, by_name, converter):
    region = correction.get("region")
    root = float(correction["root_abs_x"])
    measured = float(correction["measured_half_span_m"])
    target = float(correction["target_half_span_m"])
    if measured <= root or target <= root:
        raise ValueError(f"{correction['id']}: root must lie inboard of the span")
    ratio = (target - root) / (measured - root)

    touched = 0
    for name in correction["objects"]:
        obj = by_name[name]
        corrected = []
        for vertex in obj.vertices:
            point = converter.ac_to_xplane(vertex)
            if _in_region(point, region if name in correction.get(
                    "region_objects", correction["objects"]) else None):
                moved = _span_blend(point, root, ratio)
                if moved != point:
                    touched += 1
                corrected.append(xplane_to_ac(moved))
            else:
                corrected.append(vertex)
        obj.vertices = corrected
    return ratio, touched


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
        if correction["type"] not in ("radial_scale_about_axis",
                                      "region_scale_with_root_blend",
                                      "gear_track_widen"):
            raise ValueError(f"Unknown correction type: {correction['type']}")

        missing = [n for n in correction["objects"] if n not in by_name]
        if missing:
            # Fail loudly: a correction that silently matches nothing would
            # leave the geometry wrong while reporting success.
            raise ValueError(
                f"Correction {correction['id']} names absent objects: {missing}")

        if correction["type"] == "gear_track_widen":
            delta, touched = _apply_track_widen(correction, by_name, converter)
            applied.append({"id": correction["id"], "closes": correction["closes"],
                            "scale": delta, "objects": list(correction["objects"]),
                            "vertices": touched})
            continue

        if correction["type"] == "region_scale_with_root_blend":
            ratio, touched = _apply_region_scale(correction, by_name, converter)
            applied.append({"id": correction["id"], "closes": correction["closes"],
                            "scale": ratio, "objects": list(correction["objects"]),
                            "vertices": touched})
            continue

        # B2-11: this branch scales about the propeller's rotation axis and
        # nothing else. The profile names its axis (`axis_from`); anything other
        # than the one this code implements used to be ignored and the blades
        # were scaled about PROP_ROTATION regardless. Fail instead.
        axis_from = correction.get("axis_from")
        if axis_from != "converter.PROP_ROTATION":
            raise ValueError(
                f"Correction {correction['id']}: axis_from {axis_from!r} is not "
                f"supported; radial_scale_about_axis only scales about "
                f"'converter.PROP_ROTATION'")
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
