"""Aircraft build pipeline hardening: B2-3, B2-5, B2-6, B2-11 and the section 8
improvements (exclusions on every bucket, line / two-sided surfaces, an end to
end converter run on a synthetic donor, an add_prop_lever test, the OBJ8 index
range check, fetcher polish).

Nothing here touches the real donor cache or any X-Plane install: the donor and
the cockpit OBJ are synthetic and live in temporary directories.
"""
from __future__ import annotations

import math
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_c182t_package as builder  # noqa: E402
import c182t_corrections as corrections  # noqa: E402
import convert_flightgear_c182 as conv  # noqa: E402
import fetch_flightgear_c182 as fetch  # noqa: E402

TMP_ROOT = None


@pytest.fixture
def tmp(tmp_path):
    return tmp_path


# ------------------------------------------------------------------- B2-3
def test_b2_3_the_banner_source_has_no_literal_entity():
    assert "&bull;" not in Path(builder.__file__).read_text()


def test_b2_3_the_chosen_font_really_draws_the_separator():
    font, dot = builder.badge_font_and_bullet()
    assert builder._glyph_renders(font, dot), "the separator would print as a box"
    assert dot in ("•", "·", "-")
    # Where a TrueType face with a bullet exists (any desktop), the real bullet
    # is what gets used.
    if any(_loads(name) for name in builder.BADGE_FONT_CANDIDATES):
        assert dot == "•"


def _loads(name):
    from PIL import ImageFont
    try:
        ImageFont.truetype(name, 11)
        return True
    except OSError:
        return False


def test_b2_3_default_font_alone_cannot_draw_u2022():
    """Why the font search exists: the default font renders U+2022 as notdef."""
    from PIL import ImageFont
    assert not builder._glyph_renders(ImageFont.load_default(), "•")


def test_b2_3_banner_renders_to_a_file(tmp):
    src = tmp / "src.png"
    Image.new("RGBA", (800, 450), (255, 255, 255, 255)).save(src)
    out = tmp / "icon.png"
    builder.create_cap_badge_icon(src, out, registration="N429CP")
    banner = Image.open(out).convert("RGB").crop((0, 0, 800, 72))
    # The top banner is navy with white text: some pixels must be light, and the
    # text must not be the 6-character literal (which would be much wider).
    light = [x for x in range(800) for y in range(72) if sum(banner.getpixel((x, y))) > 600]
    assert light
    # "CIVIL AIR PATROL . USAF AUXILIARY" at 11 px is well under 300 px wide.
    left = [x for x in light if x < 500]
    assert max(left) < 330


# ------------------------------------------------------------------- B2-5
UV_R = 0.04


def synthetic_cockpit_obj(
    *, throttle_first=False, filler=3, throttle_count=builder.THROTTLE_TRIS_COUNT,
    mixture_count=builder.MIXTURE_TRIS_COUNT, throttle_anim=True, mixture_anim=True,
    extra_throttle_tris=False, flat_uv=False, lines=0,
):
    """A cockpit OBJ8 laid out like Laminar's: VT block, IDX block, then ANIM
    blocks whose TRIS lines pick the knob runs out of the shared index buffer."""
    verts = []

    def ring(cx, radius, u0, v0):
        base = len(verts)
        verts.append((cx, 0.0, 0.0, 0, 1, 0, u0, v0))                      # centre
        for k in range(12):
            a = 2 * math.pi * k / 12
            verts.append((cx + radius * math.cos(a), radius * math.sin(a), 0.0, 0, 1, 0,
                          u0 if flat_uv else u0 + UV_R * math.cos(a),
                          v0 if flat_uv else v0 + UV_R * math.sin(a)))
        return base

    filler_base = len(verts)
    verts += [(9.0, 9.0, 9.0, 0, 1, 0, 0.9, 0.9)] * 3
    thr = ring(1.0, 0.02, 0.2, 0.4)
    mix = ring(-1.0, 0.03, 0.6, 0.4)

    def tris(base, count):
        out = []
        for k in range(count // 3):
            out += [base, base + 1 + k % 12, base + 1 + (k + 1) % 12]
        return out

    idx = list(range(filler_base, filler_base + filler))
    runs = {}
    order = [("thr", thr, throttle_count), ("mix", mix, mixture_count)]
    if not throttle_first:
        order.reverse()                      # donor order: mixture's run comes first
    for name, base, count in order:
        runs[name] = (len(idx), count)
        idx += tris(base, count)

    out = ["A", "800", "OBJ", "", "TEXTURE cockpit.dds", "",
           f"POINT_COUNTS {len(verts)} {lines} 0 {len(idx)}"]
    out += ["VT " + " ".join(str(c) for c in v) for v in verts]
    for i in range(0, len(idx), 10):
        chunk = idx[i:i + 10]
        if len(chunk) == 10:
            out.append("IDX10 " + " ".join(map(str, chunk)))
        else:
            out += [f"IDX {c}" for c in chunk]
    out += ["ANIM_begin", "ANIM_trans 0 0 0 0 0 0.1 0 1 sim/cockpit2/switches/alternate_static_air_ratio",
            f"TRIS 0 {filler}", "ANIM_end"]
    if mixture_anim:
        out += ["ANIM_begin", f"ANIM_trans 0 0 0 0 0 -0.07 0 1 {builder.MIXTURE_DATAREF}",
                f"TRIS {runs['mix'][0]} {runs['mix'][1]}", "ANIM_end"]
    if throttle_anim:
        out += ["ANIM_begin", f"ANIM_trans 0 0 0 0 0 -0.09 0 1 {builder.THROTTLE_DATAREF}",
                f"TRIS {runs['thr'][0]} {runs['thr'][1]}"]
        if extra_throttle_tris:
            out.append("TRIS 0 3")
        out.append("ANIM_end")
    return "\n".join(out) + "\n", runs


def make_target(tmp, **kw):
    text, runs = synthetic_cockpit_obj(**kw)
    objects = tmp / "objects"
    objects.mkdir()
    (objects / "cockpit_panel_G1000.obj").write_text(text)
    Image.new("RGB", (256, 256), (120, 110, 100)).save(objects / "cockpit.dds", format="PNG")
    return tmp, runs


def lever_verts(tmp):
    lines = (tmp / "objects" / "prop_lever.obj").read_text().splitlines()
    return [tuple(map(float, l.split()[1:])) for l in lines if l.startswith("VT ")]


@pytest.mark.parametrize("throttle_first", [False, True])
def test_b2_5_lever_is_built_from_the_throttle_knob_wherever_it_sits(tmp, throttle_first):
    target, _ = make_target(tmp, throttle_first=throttle_first, filler=6)
    builder.add_prop_lever(target)
    verts = lever_verts(target)
    assert len(verts) == 13                                  # 12 ring + centre
    xs = [v[0] for v in verts]
    # Centroid of the throttle (x=+1) and mixture (x=-1) knobs is x=0, and the
    # lever keeps the throttle knob's 0.02 radius, not the mixture's 0.03.
    assert sum(xs) / len(xs) == pytest.approx(0.0, abs=1e-6)
    assert max(xs) - min(xs) == pytest.approx(0.04, abs=1e-5)
    counts = conv.validate_obj8(target / "objects" / "prop_lever.obj")
    assert counts["indices"] == builder.THROTTLE_TRIS_COUNT
    text = (target / "objects" / "prop_lever.obj").read_text()
    assert "sim/cockpit2/engine/actuators/prop_ratio[0]" in text
    # UVs were renormalised onto the cropped texture.
    uvs = [(v[6], v[7]) for v in verts]
    assert min(u for u, _ in uvs) == pytest.approx(0.0) and max(u for u, _ in uvs) == pytest.approx(1.0)


def test_b2_5_a_changed_knob_mesh_stops_the_build(tmp):
    target, _ = make_target(tmp, throttle_count=300)
    with pytest.raises(builder.ObjLayoutError, match="534"):
        builder.add_prop_lever(target)
    assert not (target / "objects" / "prop_lever.obj").exists()


def test_b2_5_a_missing_animation_block_stops_the_build(tmp):
    target, _ = make_target(tmp, throttle_anim=False)
    with pytest.raises(builder.ObjLayoutError, match="throttle_ratio"):
        builder.add_prop_lever(target)


def test_b2_5_two_tris_in_the_block_is_not_guessed_at(tmp):
    target, _ = make_target(tmp, extra_throttle_tris=True)
    with pytest.raises(builder.ObjLayoutError, match="found 2"):
        builder.add_prop_lever(target)


def test_b2_5_a_knob_with_no_uv_area_is_refused_not_divided_by(tmp):
    target, _ = make_target(tmp, flat_uv=True)
    with pytest.raises(builder.ObjLayoutError, match="degenerate UV"):
        builder.add_prop_lever(target)


def test_b2_5_line_or_light_vertices_are_refused(tmp):
    target, _ = make_target(tmp, lines=2)
    with pytest.raises(builder.ObjLayoutError, match="line"):
        builder.add_prop_lever(target)


def test_b2_5_find_knob_tris_reads_offsets_from_the_file():
    text, runs = synthetic_cockpit_obj(filler=9)
    start, count = builder.find_knob_tris(text.splitlines(), builder.THROTTLE_DATAREF,
                                          builder.THROTTLE_TRIS_COUNT)
    assert (start, count) == runs["thr"]
    assert start != 19629, "the old hard-coded offset must not be what is returned"


# ------------------------------------------------------- AC3D surfaces / OBJ8
def ac3d(surf_flags="0X10", extra_surface=""):
    return f"""AC3Db
MATERIAL "w" rgb 1 1 1 amb 1 1 1 emis 0 0 0 spec 0 0 0 shi 0 trans 0
OBJECT world
name "root"
kids 1
OBJECT poly
name "Thing"
texture "Default.png"
numvert 3
0 0 0
1 0 0
0 1 0
numsurf 1
SURF {surf_flags}
mat 0
refs 3
0 0 0
1 1 0
2 0 1
kids 0
"""


def test_imp_surfaces_ordinary_polygons_still_parse():
    for flags in ("0X0", "0X10"):
        assert conv.AC3DParser(ac3d(flags)).parse()


@pytest.mark.parametrize("flags,word", [("0X11", "line"), ("0X12", "line"),
                                        ("0X20", "two-sided"), ("0X30", "two-sided")])
def test_imp_line_and_two_sided_surfaces_are_rejected_by_name(flags, word):
    with pytest.raises(ValueError, match=rf"{word}.*'Thing'"):
        conv.AC3DParser(ac3d(flags)).parse()


def test_imp_validate_obj8_rejects_an_index_past_the_vertex_table(tmp):
    path = tmp / "bad.obj"
    path.write_text("A\n800\nOBJ\nPOINT_COUNTS 3 0 0 3\n"
                    "VT 0 0 0 0 1 0 0 0\nVT 1 0 0 0 1 0 0 0\nVT 0 1 0 0 1 0 0 0\n"
                    "IDX 0\nIDX 1\nIDX 3\nTRIS 0 3\n")
    with pytest.raises(ValueError, match="out of range"):
        conv.validate_obj8(path)
    path.write_text(path.read_text().replace("IDX 3", "IDX 2"))
    assert conv.validate_obj8(path)["indices"] == 3


# ------------------------------------------------ exclusions on every bucket
def poly(name, texture, x=0.0):
    obj = conv.ACObject(kind="poly", name=name, texture=texture)
    obj.vertices = [(x, 0.0, 0.0), (x + 1, 0.0, 0.0), (x, 1.0, 0.0)]
    obj.surfaces = [conv.ACSurface(0, 0, tuple(conv.ACRef(i, 0.1, 0.1) for i in range(3)))]
    return obj


def test_imp_excluded_objects_are_kept_out_of_every_bucket():
    objs = [poly("Airframe", "Default.png"), poly("WinterKit", "Default.png"),
            poly("PlaneX", "Lights.png"), poly("Blade1", "Default.png"),
            poly("FastProp", "Default.png"), poly("Windscreen", "Default.png")]
    # Make a deliberately excluded object a member of buckets it could reach.
    with patch.object(conv, "DELIBERATELY_EXCLUDED",
                      conv.DELIBERATELY_EXCLUDED | {"Blade1", "FastProp", "Windscreen"}):
        buckets = conv.select_buckets(objs)
    names = {b: [o.name for o in v] for b, v in buckets.items()}
    assert names["main"] == ["Airframe"]
    assert names["propeller"] == []
    assert names["prop_blur"] == []
    assert names["glass"] == []
    assert names["lights"] == []


def test_imp_buckets_on_the_normal_lists():
    objs = [poly("Airframe", "Default.png"), poly("Blade1", "Default.png"),
            poly("chrome_spinner", "Default.png"), poly("FastProp", "PropBlur.png"),
            poly("Windscreen", None), poly("TaxiLight", "Lights.png"),
            poly("WinterKit", "Default.png")]
    names = {b: sorted(o.name for o in v) for b, v in conv.select_buckets(objs).items()}
    assert names == {"main": ["Airframe"], "propeller": ["Blade1", "chrome_spinner"],
                     "prop_blur": ["FastProp"], "lights": ["TaxiLight"],
                     "glass": ["Windscreen"]}


# ----------------------------------------------- end to end on a synthetic donor
def ac3d_object(name, texture, tris, *, xp=(0.0, 0.0, 0.0)):
    """One poly object of triangles given in OBJ8 coordinates, as AC3D text."""
    verts = []
    refs = []
    for tri in tris:
        base = len(verts)
        for p in tri:
            ac = corrections.xplane_to_ac((p[0] + xp[0], p[1] + xp[1], p[2] + xp[2]))
            verts.append(ac)
        refs.append(base)
    out = ["OBJECT poly", f'name "{name}"']
    if texture:
        out.append(f'texture "{texture}"')
    out.append(f"numvert {len(verts)}")
    out += [" ".join(f"{c:.6f}" for c in v) for v in verts]
    out.append(f"numsurf {len(tris)}")
    for base in refs:
        out += ["SURF 0X10", "mat 0", "refs 3"]
        out += [f"{base + k} {0.1 + 0.1 * k:.3f} {0.2:.3f}" for k in range(3)]
    out.append("kids 0")
    return "\n".join(out)


def small_tri(x=0.0, y=0.0, z=0.0, s=0.1):
    return [((x, y, z), (x + s, y, z), (x, y + s, z))]


def build_synthetic_donor(root: Path) -> None:
    (root / "Models" / "Liveries").mkdir(parents=True)
    (root / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE\n")
    Image.new("RGBA", (4096, 2048), (255, 255, 255, 255)).save(root / "Models/Liveries/Default.png")
    Image.new("RGBA", (16, 16), (1, 2, 3, 4)).save(root / "Models/PropBlur.png")
    Image.new("RGBA", (16, 16), (5, 6, 7, 8)).save(root / "Models/Lights.png")
    big = [((-3, 0, -1), (3, 0, -1), (0, 1, 2))]
    kids = [
        ac3d_object("Airframe", "Default.png", big),
        # A connected piece wholly inside the starboard windscreen-corner region.
        ac3d_object("Probe", "Default.png", small_tri(0.5, 0.3, 0.0, 0.05)),
        ac3d_object("Flap.L", "Default.png", small_tri(-2.0, 0.2, 0.7)),
        # Textured, and on the deliberate-exclusion list: must never ship.
        ac3d_object("WinterKit", "Default.png", small_tri(0.0, 0.5, 0.0)),
        ac3d_object("Blade1", "Default.png", small_tri(-1.4, 0.0, 0.1)),
        ac3d_object("Blade2", "Default.png", small_tri(-1.4, 0.1, 0.1)),
        ac3d_object("Blade3", "Default.png", small_tri(-1.4, -0.1, 0.1)),
        ac3d_object("chrome_spinner", "Default.png", small_tri(-1.5, 0.0, 0.0)),
        ac3d_object("FastProp", "PropBlur.png", small_tri(-1.4, 0.0, 0.0, 0.4)),
        ac3d_object("Windscreen", None, small_tri(0.0, 0.8, -0.3, 0.3)),
        ac3d_object("Window.L", None, small_tri(-0.6, 0.6, 0.0, 0.2)),
        ac3d_object("Window.R", None, small_tri(0.6, 0.6, 0.0, 0.2)),
        ac3d_object("llglas", None, small_tri(-3.0, 0.2, 0.0, 0.1)),
        ac3d_object("NavLightRed", "Lights.png", small_tri(-5.4, 0.3, 0.8, 0.05)),
        ac3d_object("NavLightGreen", "Lights.png", small_tri(5.4, 0.3, 0.8, 0.05)),
        ac3d_object("PlaneTailLight", "Lights.png", small_tri(0.0, 1.0, 6.0, 0.05)),
        ac3d_object("LandingLight", "Lights.png", small_tri(-2.6, 0.2, 0.0, 0.05)),
        ac3d_object("TaxiLight", "Lights.png", small_tri(2.6, 0.2, 0.0, 0.05)),
        ac3d_object("Strobe", None, [((-5.4, 0.3, 0.8), (5.4, 0.3, 0.8), (0.0, 0.4, 0.8))]),
        ac3d_object("BeaconOff", None, small_tri(0.0, 1.2, 6.0, 0.05)),
    ]
    text = ("AC3Db\nMATERIAL \"w\" rgb 1 1 1 amb 1 1 1 emis 0 0 0 spec 0 0 0 shi 0 trans 0\n"
            f"OBJECT world\nname \"root\"\nkids {len(kids)}\n" + "\n".join(kids) + "\n")
    (root / "Models" / "c182s.ac").write_text(text)


@pytest.fixture
def synthetic_build(tmp):
    donor = tmp / "donor"
    target = tmp / "aircraft"
    build_synthetic_donor(donor)
    target.mkdir()
    with patch.object(conv, "validate_donor", lambda d: None), \
            patch.object(conv, "REQUIRED_FILE_SHA256", {"LICENSE": ""}), \
            patch.object(corrections, "apply_corrections", lambda objs, c: []):
        manifest = conv.build_flightgear_objects(donor, target)
    return target, manifest


def test_e2e_synthetic_donor_builds_and_validates(synthetic_build):
    target, manifest = synthetic_build
    names = {r["file"] for r in manifest["generated_objects"]}
    assert names == {"flightgear_c182t.obj", "flightgear_c182t_propeller.obj",
                     "flightgear_c182t_prop_blur.obj", "flightgear_c182t_lights.obj",
                     "flightgear_c182t_glass.obj"}
    for report in manifest["generated_objects"]:
        conv.validate_obj8(target / "objects" / report["file"])      # incl. IDX range
    main = next(r for r in manifest["generated_objects"] if r["file"] == "flightgear_c182t.obj")
    assert "WinterKit" not in main["objects"], "an excluded object reached the main mesh"
    assert "Airframe" in main["objects"]


def test_e2e_cockpit_probe_is_split_and_hidden_from_the_seat(synthetic_build):
    target, _ = synthetic_build
    text = (target / "objects" / "flightgear_c182t.obj").read_text()
    assert f"# Probe.{conv.COCKPIT_HIDDEN_SUFFIX}" in text
    assert "ANIM_hide 0.000000 0.500000 sim/graphics/view/view_is_external" in text


def test_e2e_named_lights_land_on_the_lamps(synthetic_build):
    target, _ = synthetic_build
    text = (target / "objects" / "flightgear_c182t_lights.obj").read_text()
    lights = re.findall(r"^LIGHT_NAMED (\S+)", text, re.M)
    assert sorted(lights) == sorted(
        ["airplane_nav_left", "airplane_nav_right", "airplane_nav_tail", "airplane_strobe",
         "airplane_strobe", "airplane_beacon", "airplane_landing", "airplane_taxi"])


def test_e2e_flap_animation_ends_at_the_acf_travel(synthetic_build):
    target, _ = synthetic_build
    text = (target / "objects" / "flightgear_c182t.obj").read_text()
    m = re.search(r"^ANIM_rotate \S+ \S+ \S+ (\S+) (\S+) (\S+) (\S+) "
                  r"sim/flightmodel2/wing/flap1_deg\[0\]$", text, re.M)
    assert m, "Flap.L carries no flap1_deg animation"
    assert [float(v) for v in m.groups()] == [0.0, 38.0, 0.0, 38.0]


def test_e2e_an_unclassified_donor_object_fails_closed(tmp):
    donor = tmp / "donor"
    build_synthetic_donor(donor)
    text = (donor / "Models/c182s.ac").read_text()
    stray = ac3d_object("Mystery", None, small_tri())
    text = text.replace("kids 20", "kids 21") + stray + "\n"
    (donor / "Models/c182s.ac").write_text(text)
    target = tmp / "aircraft"
    target.mkdir()
    with patch.object(conv, "validate_donor", lambda d: None), \
            patch.object(conv, "REQUIRED_FILE_SHA256", {"LICENSE": ""}), \
            patch.object(corrections, "apply_corrections", lambda objs, c: []):
        with pytest.raises(ValueError, match="Mystery"):
            conv.build_flightgear_objects(donor, target)


# ------------------------------------------------------------------- B2-6
def test_b2_6_flap_visual_travel_equals_the_acf_patch():
    patched = [v for k, v in builder.ACF_PATCHES.items() if "_flap1_dn/3" in k]
    assert len(patched) == 1
    travel = float(patched[0].split()[-1])
    for name in ("Flap.L", "Flap.R"):
        rot = conv.MAIN_ROTATIONS[name]
        assert rot.value_max == travel, "visual flap would stop short of the .acf travel"
        assert rot.angle_max == travel


# ------------------------------------------------------------------ B2-11
class Stub:
    def __init__(self, name, vertices):
        self.name, self.vertices = name, vertices


def radial(**kw):
    c = {"id": "r", "closes": "x", "status": "active", "type": "radial_scale_about_axis",
         "objects": ["Blade1"], "scale": 0.5}
    c.update(kw)
    return {"corrections": [c]}


def test_b2_11_an_axis_other_than_the_prop_axis_fails_loudly():
    with pytest.raises(ValueError, match="axis_from"):
        corrections.apply_corrections([Stub("Blade1", [(0, 0, 0)])], conv,
                                      radial(axis_from="converter.MAIN_ROTATIONS['Rudder']"))


def test_b2_11_a_missing_axis_is_not_assumed():
    with pytest.raises(ValueError, match="axis_from"):
        corrections.apply_corrections([Stub("Blade1", [(0, 0, 0)])], conv, radial())


def test_b2_11_the_named_prop_axis_still_works():
    blade = Stub("Blade1", [corrections.xplane_to_ac((-1.4, 0.5, 0.0))])
    applied = corrections.apply_corrections([blade], conv,
                                            radial(axis_from="converter.PROP_ROTATION"))
    assert applied[0]["vertices"] == 1


# ----------------------------------------------------------- fetcher polish
def test_fetch_a_bad_existing_donor_says_to_use_force(tmp):
    bad = tmp / "donor"
    bad.mkdir()
    with pytest.raises(ValueError, match="--force"):
        fetch.fetch_donor(bad)


def test_fetch_download_has_a_timeout(tmp, monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return b""

    def urlopen(url, timeout=None):
        seen["timeout"] = timeout
        return Resp()

    monkeypatch.setattr(fetch.urllib.request, "urlopen", urlopen)
    fetch._download("https://example.invalid/x.tar.gz", tmp / "x.tar.gz")
    assert seen["timeout"] and seen["timeout"] > 0
    assert "urlretrieve" not in Path(fetch.__file__).read_text().replace(
        "urlretrieve has no timeout", "")
