"""Offline checks for the generated C182T prop-governor control."""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import build_c182t_package as builder  # noqa: E402


def _synthetic_target(root: Path) -> Path:
    objects = root / "objects"
    objects.mkdir()
    # Tiny radial knob meshes with the same index fingerprints as the donor;
    # the repeated triangles are sufficient to exercise extraction and output.
    vertices = []
    for cx, z in ((-1.0, .5), (1.0, .5)):
        base = len(vertices)
        vertices.append((cx, 0., z, 0., 1., 0., .2, .2))
        for i in range(12):
            a = i * 2 * math.pi / 12
            vertices.append((cx + .02 * math.cos(a), .02 * math.sin(a), z,
                             0., 1., 0., .2 + .04 * math.cos(a), .2 + .04 * math.sin(a)))
    indices = []
    indices += [0, 1, 2]  # filler run
    mixture_start = len(indices)
    for i in range(builder.MIXTURE_TRIS_COUNT // 3):
        indices += [13, 14 + i % 12, 14 + (i + 1) % 12]
    throttle_start = len(indices)
    for i in range(builder.THROTTLE_TRIS_COUNT // 3):
        indices += [0, 1 + i % 12, 1 + (i + 1) % 12]
    obj = ["A", "800", "OBJ", "", "TEXTURE cockpit.dds",
           f"POINT_COUNTS {len(vertices)} 0 0 {len(indices)}"]
    obj += ["VT " + " ".join(map(str, v)) for v in vertices]
    for i in range(0, len(indices), 10):
        chunk = indices[i:i + 10]
        obj.append(("IDX10 " if len(chunk) == 10 else "IDX ") + " ".join(map(str, chunk)))
    obj += ["ANIM_begin", "ANIM_trans 0 0 0 0 0 -0.07 0 1 " + builder.MIXTURE_DATAREF,
            f"TRIS {mixture_start} {builder.MIXTURE_TRIS_COUNT}", "ANIM_end",
            "ANIM_begin", "ANIM_trans 0 0 0 0 0 -0.09 0 1 " + builder.THROTTLE_DATAREF,
            f"TRIS {throttle_start} {builder.THROTTLE_TRIS_COUNT}", "ANIM_end"]
    (objects / "cockpit_panel_G1000.obj").write_text("\n".join(obj) + "\n")
    Image.new("RGB", (256, 256), (120, 110, 100)).save(objects / "cockpit.dds", format="PNG")
    (root / "Cessna_182T_G1000.acf").write_text(
        "P acf/_RSC_mingov_ENGN 1800.0\nP _engn/0/_RSC_redline_ENGN 2500.0\n")
    return root


def test_prop_lever_animation_and_manipulator_use_acf_governor_range(tmp_path):
    target = _synthetic_target(tmp_path)
    builder.add_prop_lever(target)
    obj = (target / "objects/prop_lever.obj").read_text()
    low = 1800 * builder.RPM_TO_RAD_S
    high = 2500 * builder.RPM_TO_RAD_S
    assert f"ANIM_trans 0.000000 0.000000 0.000000 0.000000 0.000000 -0.089700 {low:.6f} {high:.6f} {builder.PROP_SPEED_DATAREF}" in obj
    assert f"ATTR_manip_drag_axis hand 0.000000 0.000000 -0.060000 {low:.6f} {high:.6f} {builder.PROP_SPEED_DATAREF} PROP" in obj
    assert not any("prop_ratio[0]" in line and not line.startswith("#")
                   for line in obj.splitlines())
    assert "TRIS 0 534" in obj
    # The independent texture carries the legend and push direction; shared
    # cockpit artwork remains only the source crop and is never overwritten.
    texture = Image.open(target / "objects/prop_lever.png")
    assert texture.size == (128, 64)


def test_governor_range_rejects_ambiguous_acf_fields(tmp_path):
    acf = tmp_path / "bad.acf"
    acf.write_text("P acf/_RSC_mingov_ENGN 2000\nP acf/_RSC_mingov_ENGN 2050\n"
                   "P _engn/0/_RSC_redline_ENGN 2400\n")
    try:
        builder.prop_governor_range_rad_s(acf)
    except builder.ObjLayoutError as exc:
        assert "found 2" in str(exc)
    else:
        raise AssertionError("ambiguous governor source should stop the build")
