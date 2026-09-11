#!/usr/bin/env python3
"""Convert the pinned FlightGear C182 exterior from AC3D to X-Plane OBJ8.

This is a local prototype path.  The generated meshes and derived texture are
GPL donor material and must not be committed to or released as part of the
Apache-2.0 CAP V-SAR repository.  See docs/FLIGHTGEAR_C182_GPL_PLAN.md.
"""

from __future__ import annotations

import json
import math
import shutil
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from fetch_flightgear_c182 import (
    DONOR_ARCHIVE_SHA256,
    DONOR_COMMIT,
    DONOR_REPOSITORY,
    REQUIRED_FILE_SHA256,
    sha256,
    validate_donor,
)


@dataclass(frozen=True)
class ACRef:
    vertex: int
    u: float
    v: float


@dataclass(frozen=True)
class ACSurface:
    flags: int
    material: int
    refs: tuple[ACRef, ...]


@dataclass
class ACObject:
    kind: str
    name: str = ""
    texture: str | None = None
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    surfaces: list[ACSurface] = field(default_factory=list)
    children: list["ACObject"] = field(default_factory=list)


class AC3DParser:
    """Small strict parser for the subset used by the pinned donor."""

    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.index = 0

    def _line(self) -> str:
        if self.index >= len(self.lines):
            raise ValueError("Unexpected end of AC3D file")
        line = self.lines[self.index].strip()
        self.index += 1
        return line

    def parse(self) -> ACObject:
        if self._line() != "AC3Db":
            raise ValueError("Expected AC3Db header")
        while self.index < len(self.lines) and self.lines[self.index].startswith(
            "MATERIAL "
        ):
            self.index += 1
        root = self._object()
        if any(line.strip() for line in self.lines[self.index :]):
            raise ValueError("Unexpected content after AC3D root object")
        return root

    def _object(self) -> ACObject:
        header = self._line().split()
        if len(header) != 2 or header[0] != "OBJECT":
            raise ValueError(f"Expected OBJECT, got {' '.join(header)!r}")
        obj = ACObject(kind=header[1])

        while True:
            line = self._line()
            key, _, value = line.partition(" ")
            if key == "name":
                obj.name = shlex.split(value)[0]
            elif key == "texture":
                obj.texture = shlex.split(value)[0]
            elif key == "data":
                byte_count = int(value)
                payload = self._line()
                if len(payload.encode()) != byte_count:
                    raise ValueError(f"Unsupported multiline data on {obj.name!r}")
            elif key in {"crease", "texrep", "url", "subdiv"}:
                continue
            elif key == "loc":
                loc = tuple(float(part) for part in value.split())
                if loc != (0.0, 0.0, 0.0):
                    raise ValueError(f"Unsupported AC3D location on {obj.name!r}: {loc}")
            elif key == "rot":
                rot = tuple(float(part) for part in value.split())
                identity = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
                if rot != identity:
                    raise ValueError(f"Unsupported AC3D rotation on {obj.name!r}")
            elif key == "numvert":
                obj.vertices = [
                    tuple(float(part) for part in self._line().split()[:3])
                    for _ in range(int(value))
                ]
            elif key == "numsurf":
                obj.surfaces = [self._surface() for _ in range(int(value))]
            elif key == "kids":
                obj.children = [self._object() for _ in range(int(value))]
                return obj
            else:
                raise ValueError(f"Unsupported AC3D directive {key!r} on {obj.name!r}")

    def _surface(self) -> ACSurface:
        line = self._line()
        if not line.startswith("SURF "):
            raise ValueError(f"Expected SURF, got {line!r}")
        flags = int(line.split()[1], 0)
        material = 0
        while True:
            line = self._line()
            key, _, value = line.partition(" ")
            if key == "mat":
                material = int(value)
            elif key == "refs":
                refs = []
                for _ in range(int(value)):
                    parts = self._line().split()
                    refs.append(ACRef(int(parts[0]), float(parts[1]), float(parts[2])))
                return ACSurface(flags=flags, material=material, refs=tuple(refs))
            else:
                raise ValueError(f"Unsupported surface directive {key!r}")


@dataclass(frozen=True)
class DrawGroup:
    name: str
    start: int
    count: int


@dataclass(frozen=True)
class Rotation:
    center: tuple[float, float, float]
    axis: tuple[float, float, float]
    angle_min: float
    angle_max: float
    value_min: float
    value_max: float
    dataref: str


def flatten(root: ACObject) -> list[ACObject]:
    result: list[ACObject] = []

    def visit(obj: ACObject) -> None:
        result.append(obj)
        for child in obj.children:
            visit(child)

    visit(root)
    return result


def ac_to_xplane(point: tuple[float, float, float]) -> tuple[float, float, float]:
    """AC3D (longitudinal, vertical, left) -> OBJ8 (right, up, aft)."""
    x, y, z = point
    return (-z, y, x)


def fg_to_xplane(point: tuple[float, float, float]) -> tuple[float, float, float]:
    """FlightGear model (longitudinal, right, up) -> OBJ8 (right, up, aft)."""
    x, y, z = point
    return (y, z, x)


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _add(a: tuple[float, float, float], b: tuple[float, float, float]):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _normal(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(part * part for part in v))
    if length <= 1e-12:
        return (0.0, 1.0, 0.0)
    return tuple(part / length for part in v)


def _triangles(surface: ACSurface) -> Iterable[tuple[ACRef, ACRef, ACRef]]:
    if len(surface.refs) < 3:
        return
    first = surface.refs[0]
    for offset in range(1, len(surface.refs) - 1):
        yield first, surface.refs[offset], surface.refs[offset + 1]


def _build_mesh(objects: Iterable[ACObject]):
    vertices: list[tuple[float, ...]] = []
    indices: list[int] = []
    groups: list[DrawGroup] = []
    vertex_map: dict[tuple[float, ...], int] = {}

    for obj in objects:
        positions = [ac_to_xplane(vertex) for vertex in obj.vertices]
        smooth: dict[int, tuple[float, float, float]] = {}
        face_data = []
        for surface in obj.surfaces:
            for tri in _triangles(surface):
                p0, p1, p2 = (positions[ref.vertex] for ref in tri)
                raw = _cross(_sub(p1, p0), _sub(p2, p0))
                face_data.append((surface, tri, raw))
                if surface.flags & 0x10:
                    for ref in tri:
                        smooth[ref.vertex] = _add(
                            smooth.get(ref.vertex, (0.0, 0.0, 0.0)), raw
                        )

        start = len(indices)
        for surface, tri, raw in face_data:
            face_normal = _normal(raw)
            # X-Plane winds triangles OPPOSITE to the stored vertex normal.
            # Measured on Laminar's own Cessna_172SP objects/fuselage.obj: across
            # 752 cabin-side and 212 tailcone faces, the winding-derived normal
            # agrees with the stored normal 0.0% of the time - the winding points
            # inboard while the stored normals point outboard. AC3D winds the
            # other way, so the refs are emitted reversed here.
            #
            # `raw`, and therefore every stored normal, is still computed from the
            # ORIGINAL AC3D order, so normals keep pointing outboard; only the
            # index order flips. Emitting AC3D order directly makes X-Plane cull
            # the near-side skin, which renders as a see-through cabin while solid
            # regions such as the tailcone still look correct, because there you
            # see the inside of the far wall.
            for ref in reversed(tri):
                normal = (
                    _normal(smooth[ref.vertex])
                    if surface.flags & 0x10
                    else face_normal
                )
                entry = (*positions[ref.vertex], *normal, ref.u, ref.v)
                index = vertex_map.get(entry)
                if index is None:
                    index = len(vertices)
                    vertex_map[entry] = index
                    vertices.append(entry)
                indices.append(index)
        groups.append(DrawGroup(obj.name, start, len(indices) - start))
    return vertices, indices, groups


# Centers and axes below are from Models/c182t.xml at the pinned donor commit.
# Flight-surface datarefs and their units are X-Plane 12's public stock datarefs.
MAIN_ROTATIONS = {
    "Aileron.L": Rotation(
        fg_to_xplane((1.656383, -3.900922, 0.892718)),
        _normal(fg_to_xplane((0.237831, 2.720408, -0.124793))),
        -20,
        20,
        -20,
        20,
        "sim/flightmodel2/wing/aileron1_deg[2]",
    ),
    "Aileron.R": Rotation(
        fg_to_xplane((1.656383, 3.900922, 0.892718)),
        _normal(fg_to_xplane((0.237831, -2.720408, -0.124793))),
        -20,
        20,
        -20,
        20,
        "sim/flightmodel2/wing/aileron1_deg[3]",
    ),
    "Flap.L": Rotation(
        fg_to_xplane((1.665323, -1.595262, 0.763406)),
        (1.0, 0.0, 0.0),
        0,
        38,
        0,
        40,
        "sim/flightmodel2/wing/flap1_deg[0]",
    ),
    "Flap.R": Rotation(
        fg_to_xplane((1.665323, 1.595262, 0.763406)),
        (1.0, 0.0, 0.0),
        0,
        38,
        0,
        40,
        "sim/flightmodel2/wing/flap1_deg[1]",
    ),
    "Elevator": Rotation(
        fg_to_xplane((5.591823, 0.000001, 0.423554)),
        (1.0, 0.0, 0.0),
        -30,
        30,
        -30,
        30,
        "sim/flightmodel2/wing/elevator1_deg[8]",
    ),
    "ElevatorTrim": Rotation(
        fg_to_xplane((5.591823, 0.000001, 0.423554)),
        (1.0, 0.0, 0.0),
        -30,
        30,
        -30,
        30,
        "sim/flightmodel2/wing/elevator1_deg[8]",
    ),
    "Rudder": Rotation(
        fg_to_xplane((6.015226, 0.00263, 1.158865)),
        _normal(fg_to_xplane((0.165473, 0.000093, 0.284685))),
        -30,
        30,
        -30,
        30,
        "sim/flightmodel2/wing/rudder1_deg[10]",
    ),
}

PROP_ROTATION = Rotation(
    fg_to_xplane((-1.462241, 0.001089, 0.011581)),
    _normal(fg_to_xplane((0.468632, 0.00018, 0.019567))),
    0,
    360,
    0,
    360,
    "sim/flightmodel2/engines/prop_rotation_angle_deg[0]",
)


def _fmt(value: float) -> str:
    value = 0.0 if abs(value) < 0.0000005 else value
    return f"{value:.6f}"


def _animation_lines(rotation: Rotation) -> list[str]:
    center = " ".join(_fmt(value) for value in rotation.center)
    inverse = " ".join(_fmt(-value) for value in rotation.center)
    axis = " ".join(_fmt(value) for value in rotation.axis)
    return [
        f"ANIM_trans {center} {center} 0.000000 0.000000 none",
        f"ANIM_rotate {axis} {_fmt(rotation.angle_min)} {_fmt(rotation.angle_max)} "
        f"{_fmt(rotation.value_min)} {_fmt(rotation.value_max)} {rotation.dataref}",
        f"ANIM_trans {inverse} {inverse} 0.000000 0.000000 none",
    ]


def write_obj8(
    destination: Path,
    objects: Iterable[ACObject],
    *,
    texture: str,
    rotations: dict[str, Rotation] | None = None,
    mode: str = "opaque",
    propeller: bool = False,
    prop_blur: bool = False,
) -> dict[str, object]:
    selected = list(objects)
    vertices, indices, groups = _build_mesh(selected)
    if not indices:
        raise ValueError(f"No triangles selected for {destination.name}")

    lines = [
        "A",
        "800",
        "OBJ",
        "",
        f"# Generated from {DONOR_REPOSITORY} commit {DONOR_COMMIT}",
        "# GPL donor material; see the generated package notice and license.",
        f"TEXTURE {texture}",
        "GLOBAL_specular 0.650000",
    ]
    if mode == "glass":
        lines.extend(("BLEND_GLASS", "ATTR_no_cull"))
    elif mode in {"lights", "prop_blur"}:
        lines.append("ATTR_no_cull")
    lines.extend(("", f"POINT_COUNTS {len(vertices)} 0 0 {len(indices)}"))
    lines.extend("VT " + " ".join(_fmt(value) for value in vertex) for vertex in vertices)
    for offset in range(0, len(indices), 10):
        chunk = indices[offset : offset + 10]
        if len(chunk) == 10:
            lines.append("IDX10 " + " ".join(str(index) for index in chunk))
        else:
            lines.extend(f"IDX {index}" for index in chunk)

    rotations = rotations or {}
    for group in groups:
        if not group.count:
            continue
        lines.extend(("", f"# {group.name}"))
        if mode == "lights":
            name = group.name.lower()
            if "taxi" in name:
                dataref = "sim/flightmodel2/lights/taxi_lights_brightness_ratio[0]"
            elif "landing" in name:
                dataref = "sim/flightmodel2/lights/landing_lights_brightness_ratio[0]"
            elif "beacon" in name:
                dataref = "sim/flightmodel2/lights/beacon_brightness_ratio[0]"
            elif "strobe" in name:
                dataref = "sim/flightmodel2/lights/strobe_flash_now"
            else:
                dataref = "sim/flightmodel2/lights/nav_lights_brightness_ratio[0]"
            lines.append(f"ATTR_light_level 0.000000 1.000000 {dataref}")

        rotation = PROP_ROTATION if propeller else rotations.get(group.name)
        if rotation or prop_blur:
            lines.append("ANIM_begin")
            if propeller:
                lines.append(
                    "ANIM_hide 1.000000 1.000000 "
                    "sim/flightmodel2/engines/prop_is_disc[0]"
                )
            if prop_blur:
                lines.append(
                    "ANIM_hide 0.000000 0.000000 "
                    "sim/flightmodel2/engines/prop_is_disc[0]"
                )
            if rotation:
                lines.extend(_animation_lines(rotation))
        lines.append(f"TRIS {group.start} {group.count}")
        if rotation or prop_blur:
            lines.append("ANIM_end")
    destination.write_text("\n".join(lines) + "\n")

    xs = [vertex[0] for vertex in vertices]
    ys = [vertex[1] for vertex in vertices]
    zs = [vertex[2] for vertex in vertices]
    return {
        "file": destination.name,
        "objects": [group.name for group in groups if group.count],
        "vertices": len(vertices),
        "indices": len(indices),
        "bounds_m": {
            "x": [min(xs), max(xs)],
            "y": [min(ys), max(ys)],
            "z": [min(zs), max(zs)],
        },
    }


def write_blank_obj(destination: Path) -> None:
    destination.write_text("A\n800\nOBJ\n\nPOINT_COUNTS 0 0 0 0\n")


def create_cap_texture(source: Path, destination: Path) -> None:
    """Create a restrained CAP 487 prototype marking on the donor's blank livery."""
    image = Image.open(source).convert("RGBA")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 138)
    except OSError:
        font = ImageFont.load_default(size=138)
    fill = (13, 36, 77, 255)
    stroke = (235, 240, 246, 255)
    label = "CAP 487"

    # The pinned donor's UV atlas gives each fuselage side its own region, so the
    # label is stamped twice rather than shared. Measured from the donor's Door.L
    # and Door.R UVs: both sides run aft with increasing u, but the right side's v
    # axis is inverted (up is LOWER v) while the left side's is not. The right-hand
    # stamp therefore needs a vertical flip only. Using rotate(180) here would also
    # flip it horizontally and render the registration mirrored on that side.
    draw.text((1590, 505), label, font=font, fill=fill, stroke_width=4, stroke_fill=stroke)
    flipped = Image.new("RGBA", (950, 210), (0, 0, 0, 0))
    flipped_draw = ImageDraw.Draw(flipped)
    flipped_draw.text((10, 10), label, font=font, fill=fill, stroke_width=4, stroke_fill=stroke)
    flipped = flipped.transpose(Image.FLIP_TOP_BOTTOM)
    image.alpha_composite(flipped, (1530, 1120))
    image.save(destination)


def validate_obj8(path: Path) -> dict[str, object]:
    lines = path.read_text().splitlines()
    if lines[:3] != ["A", "800", "OBJ"]:
        raise ValueError(f"Invalid OBJ8 header: {path}")
    point_line = next((line for line in lines if line.startswith("POINT_COUNTS ")), None)
    if point_line is None:
        raise ValueError(f"Missing POINT_COUNTS: {path}")
    vertex_count, line_count, light_count, index_count = map(int, point_line.split()[1:])
    actual_vertices = sum(line.startswith("VT ") for line in lines)
    actual_indices = sum(
        len(line.split()) - 1 for line in lines if line.startswith(("IDX ", "IDX10 "))
    )
    if actual_vertices != vertex_count or actual_indices != index_count:
        raise ValueError(
            f"OBJ8 count mismatch in {path}: declared {vertex_count}/{index_count}, "
            f"found {actual_vertices}/{actual_indices}"
        )
    for line in lines:
        if line.startswith("TRIS "):
            start, count = map(int, line.split()[1:])
            if start < 0 or count < 0 or start + count > index_count or count % 3:
                raise ValueError(f"Invalid TRIS range in {path}: {line}")
    return {
        "vertices": vertex_count,
        "lines": line_count,
        "lights": light_count,
        "indices": index_count,
    }


# Exterior glazing. Windscreen is the greenhouse shell (z 0.01-2.85, y 0.27-0.82)
# and is 494/12 outward-facing; Window.L/R are the door panes; llglas is the wing
# landing-light lens.
GLASS_NAMES = {"Windscreen", "Window.L", "Window.R", "llglas"}

# Interior-only surfaces. Measured face winding is overwhelmingly INWARD
# (Windscreen.Int 2 outward / 320 inward, .Int.Back 2/66, both .Side panels 0/49),
# which is what the donor's .Int naming implies: FlightGear draws these from inside
# the cabin. They are not missing exterior skin, and attaching them to the exterior
# glass object puts inward-facing translucent surfaces in the external view.
INTERIOR_ONLY = {
    "Windscreen.Int",
    "Windscreen.Int.Back",
    "Windscreen.Side.Left",
    "Windscreen.Side.Right",
}

# Donor objects deliberately left out of the X-Plane package.
# Ground-service props and the cold-weather kit are modelled parked-only clutter
# in the FlightGear aircraft; the duplicates are alternate LODs or second copies
# of geometry already emitted elsewhere.
DELIBERATELY_EXCLUDED = {
    # Ground-service clutter and external kit.
    "chokes.cs.001", "chokes.cs.002", "chokes.cs.003",
    "FuelSelectorDrain.cs", "FuelStrainerDrain.cs",
    "LeftTank.cs", "LeftTankDrain.cs", "RightTank.cs", "RightTankDrain.cs",
    "Oil.cs", "pitotcover.cs", "StallVane.cs",
    "safety-cone.cs.L", "safety-cone.cs.R",
    "TiedownHotSpotLeft", "TiedownHotSpotRight", "TiedownHotSpotTail",
    "TieDownLeft", "TieDownRight",
    "winterkit.cs", "WinterKit",
    # Duplicates / alternate LODs of geometry emitted from another object.
    "Spinner",            # duplicate of chrome_spinner, which the prop group uses
    "Blade1.001", "Blade2.001", "Blade3.001",
    "SlowProp",           # low-RPM disc; FastProp drives the blurred disc
    "Window.L.001", "Window.R.001",
}

# Donor objects that are visible features but are NOT yet converted. These are
# real gaps, not decisions: the wingtip strobe in particular matters because the
# published C182T span (36 ft 0 in) is defined WITH the strobes installed, and
# the beacon sits at the fin tip that the published height is measured to.
# Tracked under A-1; see docs/C182T_DIMENSION_MASTER.md.
KNOWN_UNCONVERTED = {
    "Strobe",
    "NavLight.L", "NavLight.R", "NavlightTransp",
    "BeaconOff",
}


PROP_NAMES = {"Blade1", "Blade2", "Blade3", "chrome_spinner"}
PROP_BLUR_NAME = "FastProp"
SELECTED_TEXTURES = {"Default.png", "Lights.png"}


def unclassified_objects(objects: Iterable[ACObject]) -> list[str]:
    """Donor objects that no output selection and no documented exclusion covers.

    Bucket selection is by texture name, so any donor object with no texture
    falls through every bucket. Returning them by name lets the caller fail
    closed instead of silently shipping an aircraft that is missing geometry.
    """
    return sorted(
        obj.name
        for obj in objects
        if obj.name not in DELIBERATELY_EXCLUDED
        and obj.name not in INTERIOR_ONLY
        and obj.name not in KNOWN_UNCONVERTED
        and obj.name not in PROP_NAMES
        and obj.name not in GLASS_NAMES
        and obj.name != PROP_BLUR_NAME
        and obj.texture not in SELECTED_TEXTURES
    )


def assert_all_objects_classified(objects: Iterable[ACObject]) -> None:
    missing = unclassified_objects(objects)
    if missing:
        raise ValueError(
            "Donor objects match no output selection and no documented exclusion: "
            + ", ".join(missing)
            + ". Classify each one before building; selection must never drop a "
            "donor object silently."
        )


def build_flightgear_objects(donor: Path, target_aircraft: Path) -> dict[str, object]:
    validate_donor(donor)
    objects_dir = target_aircraft / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)
    root = AC3DParser((donor / "Models/c182s.ac").read_text(errors="strict")).parse()
    objects = [obj for obj in flatten(root) if obj.kind == "poly" and obj.surfaces]

    prop_names = {"Blade1", "Blade2", "Blade3", "chrome_spinner"}
    excluded_default = prop_names | {
        "Blade1.001",
        "Blade2.001",
        "Blade3.001",
        "Spinner",
        "WinterKit",
    }
    assert_all_objects_classified(objects)
    main = [
        obj
        for obj in objects
        if obj.texture == "Default.png" and obj.name not in excluded_default
    ]
    prop = [obj for obj in objects if obj.name in prop_names]
    prop_blur = [obj for obj in objects if obj.name == "FastProp"]
    lights = [obj for obj in objects if obj.texture == "Lights.png"]
    glass = [obj for obj in objects if obj.name in GLASS_NAMES]

    selections = {
        "main": main,
        "propeller": prop,
        "prop_blur": prop_blur,
        "lights": lights,
        "glass": glass,
    }
    missing = [name for name, selection in selections.items() if not selection]
    if missing:
        raise ValueError(f"Donor selections unexpectedly empty: {', '.join(missing)}")

    texture = objects_dir / "flightgear_c182t.png"
    create_cap_texture(donor / "Models/Liveries/Default.png", texture)
    shutil.copy2(donor / "Models/PropBlur.png", objects_dir / "flightgear_c182t_prop.png")
    shutil.copy2(donor / "Models/Lights.png", objects_dir / "flightgear_c182t_lights.png")
    Image.new("RGBA", (16, 16), (125, 170, 195, 72)).save(
        objects_dir / "flightgear_c182t_glass.png"
    )

    reports = [
        write_obj8(
            objects_dir / "flightgear_c182t.obj",
            main,
            texture=texture.name,
            rotations=MAIN_ROTATIONS,
        ),
        write_obj8(
            objects_dir / "flightgear_c182t_propeller.obj",
            prop,
            texture=texture.name,
            propeller=True,
        ),
        write_obj8(
            objects_dir / "flightgear_c182t_prop_blur.obj",
            prop_blur,
            texture="flightgear_c182t_prop.png",
            mode="prop_blur",
            prop_blur=True,
        ),
        write_obj8(
            objects_dir / "flightgear_c182t_lights.obj",
            lights,
            texture="flightgear_c182t_lights.png",
            mode="lights",
        ),
        write_obj8(
            objects_dir / "flightgear_c182t_glass.obj",
            glass,
            texture="flightgear_c182t_glass.png",
            mode="glass",
        ),
    ]
    write_blank_obj(objects_dir / "flightgear_blank.obj")
    for report in reports:
        validate_obj8(objects_dir / str(report["file"]))

    shutil.copy2(donor / "LICENSE", target_aircraft / "FLIGHTGEAR_C182_GPL-2.0.txt")
    notice = f"""CAP V-SAR FlightGear C182 local prototype

Exterior mesh and source textures:
  {DONOR_REPOSITORY}
  commit {DONOR_COMMIT}
  archive SHA-256 {DONOR_ARCHIVE_SHA256}

The generated exterior objects and derived CAP 487 texture are GPL donor
material.  They are produced for local evaluation and are not part of the
Apache-2.0 CAP V-SAR source distribution.  The accompanying GPL text applies
to those generated donor-derived files.  Do not redistribute the combined
aircraft package: it also contains locally copied Laminar Research files.
"""
    (target_aircraft / "FLIGHTGEAR_C182_PROTOTYPE_NOTICE.txt").write_text(notice)
    manifest = {
        "prototype_only": True,
        "donor_repository": DONOR_REPOSITORY,
        "donor_commit": DONOR_COMMIT,
        "donor_archive_sha256": DONOR_ARCHIVE_SHA256,
        "donor_files_sha256": {
            name: sha256(donor / name) for name in REQUIRED_FILE_SHA256
        },
        "generated_objects": reports,
    }
    (target_aircraft / "flightgear-c182-prototype.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    return manifest
