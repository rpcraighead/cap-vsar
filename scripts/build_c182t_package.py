#!/usr/bin/env python3
"""
Build the Civil Air Patrol Cessna 182T NAV III (G1000) Aircraft Package for X-Plane 12.

Combines the locally installed Laminar Research Cessna 172SP G1000 cockpit and
systems with a locally converted, pinned GPL FlightGear C182 exterior. The
result is a dedicated Cessna 182T Skylane NAV III prototype with Lycoming
IO-540-AB1A5 performance, a 3-blade constant-speed McCauley propeller, Garmin
G1000 Manifold Pressure EIS, C182T weights, 87 gal fuel capacity, V-speeds and
Civil Air Patrol branding (CAP 487). The generated package is for local use;
it must not be redistributed. See docs/FLIGHTGEAR_C182_GPL_PLAN.md.

The simulated aircraft is CAP 487. It deliberately does NOT carry N499CP: that
is a real Cessna 172S on the squadron's line, and stamping a real aircraft's
registration onto a different simulated type confuses a crew about what they
are flying and is not ours to do. The flight planner's 172S profile that once
carried that registration was removed under L-7, so the planner now computes
CAP 487 182T figures only. N499CP survives in CHANGELOG.md and the bug tracker,
which record what was true when written.
"""

from __future__ import annotations

import argparse
import atexit
import colorsys
import os
import re
import shutil
import sys
import uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from convert_flightgear_c182 import build_flightgear_objects
from fetch_flightgear_c182 import DEFAULT_DONOR, DONOR_COMMIT, validate_donor


# A2-9: the X-Plane folder comes from XPLANE_ROOT; the workstation path is only
# the fallback, so the build runs unchanged on another machine.
XPLANE_ROOT = Path(os.environ.get("XPLANE_ROOT", str(Path.home() / "X-Plane 12")))
DEFAULT_SOURCE_DIR = XPLANE_ROOT / "Aircraft/Laminar Research/Cessna 172 SP"
DEFAULT_TARGET_DIR = XPLANE_ROOT / "Aircraft/CAP/Cessna 182T NAV III"
DEFAULT_DONOR_DIR = Path(
    os.environ.get(
        "CAPVSAR_FLIGHTGEAR_C182_SOURCE",
        str(DEFAULT_DONOR),
    )
)

# Complete dictionary of regex pattern -> replacement line for Cessna_182T_G1000.acf
ACF_PATCHES = {
    # Metadata & Identification
    r"^P acf/_name .*": "P acf/_name Cessna Skylane 182T NAV III (G1000 CAP)",
    r"^P acf/_descrip .*": "P acf/_descrip Cessna 182T Skylane NAV III - 230HP Lycoming IO-540-AB1A5 - Garmin G1000 (Civil Air Patrol)",
    r"^P acf/_tailnum .*": "P acf/_tailnum CAP 487",
    r"^P acf/_ICAO .*": "P acf/_ICAO C182",
    r"^P acf/_author .*": "P acf/_author Laminar Research / CAP V-SAR Project",
    r"^P acf/_studio .*": "P acf/_studio Civil Air Patrol",
    r"^P _obja/0/_v10_att_file_stl .*": "P _obja/0/_v10_att_file_stl ../Cessna_182T_G1000_cockpit.obj",

    # Exterior prototype: replace every visible/crash C172 attachment.  These
    # paths are generated locally from the pinned GPL FlightGear C182 donor.
    r"^P _obja/15/_v10_att_file_stl .*": "P _obja/15/_v10_att_file_stl flightgear_c182t.obj",
    r"^P _obja/16/_v10_att_file_stl .*": "P _obja/16/_v10_att_file_stl flightgear_blank.obj",
    r"^P _obja/17/_v10_att_file_stl .*": "P _obja/17/_v10_att_file_stl flightgear_c182t_propeller.obj",
    r"^P _obja/18/_v10_att_file_stl .*": "P _obja/18/_v10_att_file_stl flightgear_c182t_prop_blur.obj",
    r"^P _obja/19/_v10_att_file_stl .*": "P _obja/19/_v10_att_file_stl flightgear_c182t_glass.obj",
    r"^P _obja/22/_v10_att_file_stl .*": "P _obja/22/_v10_att_file_stl flightgear_c182t_lights.obj",
    r"^P _obja/23/_v10_att_file_stl .*": "P _obja/23/_v10_att_file_stl flightgear_blank.obj",
    r"^P _obja/24/_v10_att_file_stl .*": "P _obja/24/_v10_att_file_stl flightgear_blank.obj",
    r"^P _obja/25/_v10_att_file_stl .*": "P _obja/25/_v10_att_file_stl flightgear_blank.obj",
    r"^P _obja/26/_v10_att_file_stl .*": "P _obja/26/_v10_att_file_stl flightgear_blank.obj",

    # Powerplant: Lycoming IO-540-AB1A5 (230 HP @ 2,400 RPM, 541 cu in, Fuel Injected)
    r"^P acf/_power_max_limit .*": "P acf/_power_max_limit 230.000000000",
    r"^P _engn/0/_power_max_limit .*": "P _engn/0/_power_max_limit 230.000000000",
    r"^P _engn/0/_RSC_max_pwr_ENGN .*": "P _engn/0/_RSC_max_pwr_ENGN 2400.000000000",
    r"^P _engn/0/_RSC_redline_ENGN .*": "P _engn/0/_RSC_redline_ENGN 2400.000000000",

    # Propeller: 3-Blade McCauley Constant-Speed Propeller (_prop_type 1 = Constant Speed)
    # Activates G1000 Manifold Pressure (MAN IN HG) gauge on EIS!
    r"^P _prop/0/_prop_type .*": "P _prop/0/_prop_type 1",
    r"^P _prop/0/_num_blades .*": "P _prop/0/_num_blades 3.000000000",
    r"^P _prop/0/_des_rpm_prp .*": "P _prop/0/_des_rpm_prp 2400.000000000",
    r"^P _prop/0/_des_kts_acf .*": "P _prop/0/_des_kts_acf 145.000000000",
    # A2-2: blade pitch stops from FAA TCDS 3A13 Rev 66 p.32, McCauley
    # B3D36C431/80VSA-1 (182S, 182T): "Pitch settings at 30 in. sta.: Low 14.9,
    # High 31.7". The 30-in station is 76 % of the 39.5-in blade radius, the
    # conventional reference station; no X-Plane document states the station
    # Plane Maker uses, so the TCDS acceptance check is what validates it:
    # static RPM at full throttle must be 2300-2400 (TCDS "Propeller limits").
    # The previous 10/40 were unsourced.
    r"^P _prop/0/_min_pitch .*": "P _prop/0/_min_pitch 14.900000000",
    r"^P _prop/0/_max_pitch .*": "P _prop/0/_max_pitch 31.700000000",

    # A2-2: blade radius. The stock C172 blade is 3.200 ft (76.8 in disc); the
    # TCDS and POH give 79.0 in for the 182T. The visual propeller was already
    # corrected to 79.0 in by c182t_corrections, so this brings the physics to
    # the same disc. Chords are left at the C172 values: no source gives the
    # B3D36C431 planform.
    r"^P _blad/0/_semilen_SEG .*": "P _blad/0/_semilen_SEG 3.291666660",

    # A2-1: the IO-540 has six cylinders; the C172 value (4) drove the engine
    # model and the G1000 lean-assist bars.
    r"^P acf/_num_cylinders .*": "P acf/_num_cylinders 6",

    # Weight & Balance. MTOW 3,100 lbs.
    #
    # L-7a: empty weight was 1,970 lb here while the flight planner used the POH
    # Figure 6-3 SAMPLE aircraft - 1,924 lb, moment/1000 70.9 - as its planning
    # baseline. A 46 lb disagreement in empty weight means planner and simulator
    # never agreed on takeoff weight, CG or performance for the same loading,
    # and the crew sees both numbers. The sample aircraft is not a measurement
    # of CAP 487; it is a shared, sourced baseline, and it must be the SAME
    # shared baseline on both sides. services/flightplanner/app.py is the other
    # half and carries the same values; tests/test_loading_baseline.py fails if
    # they drift apart again.
    r"^P acf/_m_empty .*": "P acf/_m_empty 1924.000000000",
    r"^P acf/_m_max .*": "P acf/_m_max 3100.000000000",

    # L-7a: the EMPTY CG was never patched at all. The stock C172SP ships
    # _cgZ 2.900095 - Laminar sets _cgZ to _cgZ_fwd on both aircraft checked -
    # and the builder moved the LIMITS to the C182T envelope below while leaving
    # the empty CG at the C172S value. It happened to land within 0.15 in of the
    # right answer, which is luck, not derivation, and luck does not survive the
    # next envelope change.
    #
    # Derived from the same POH sample and the same %MAC mapping used for the
    # limits below:
    #   empty arm = 70,900 lb-in / 1,924 lb = 36.850 in aft of datum
    #   %MAC      = (36.850 - 25.98) / 58.8 = 18.483%
    #   _cgZ      = 1.994 + 0.18483 * 4.837 = 2.888 ft
    r"^P acf/_cgZ .*": "P acf/_cgZ 2.888000000",

    # Fuel System: 87 gal usable (92 gal total) = 522 lbs fuel
    r"^P acf/_m_fuel_max_tot .*": "P acf/_m_fuel_max_tot 522.000000000",

    # Cowl Flaps: Manual Cowl Flaps Equipped
    r"^P acf/_cowl_flaps_EQ .*": "P acf/_cowl_flaps_EQ 1",

    # Flight Envelope & Standard V-Speeds (KIAS)
    r"^P acf/_Vs_kts .*": "P acf/_Vs_kts 51.000000000",
    r"^P acf/_Vso_kts .*": "P acf/_Vso_kts 41.000000000",
    r"^P acf/_Vx_kts .*": "P acf/_Vx_kts 65.000000000",
    r"^P acf/_Vy_kts .*": "P acf/_Vy_kts 80.000000000",
    r"^P acf/_Vbg_kts .*": "P acf/_Vbg_kts 76.000000000",
    r"^P acf/_Vfe1_kts .*": "P acf/_Vfe1_kts 140.000000000",
    r"^P acf/_Vfem_kts .*": "P acf/_Vfem_kts 100.000000000",
    r"^P acf/_Vno_kts .*": "P acf/_Vno_kts 140.000000000",
    r"^P acf/_Vne_kts .*": "P acf/_Vne_kts 175.000000000",
    # A2-8: manoeuvring speed at 3,100 lb, POH Figure 2-1 / TCDS (was 0).
    r"^P acf/_Va_kts .*": "P acf/_Va_kts 110.000000000",

    # Control surface travel, from FAA TCDS 3A13 Rev 66 page 33 (Models 182S and
    # 182T, "Control surface movements").  The stock C172S values that shipped in
    # this package are materially smaller than the certificated C182T travels, so
    # pitch authority, flap drag/lift and yaw authority were all short.
    #
    #   surface        stock C172S   TCDS 3A13 C182T
    #   elevator up        20 deg      28 deg +/-1
    #   elevator down      15 deg      21 deg +/-1   (relative to stabilizer)
    #   rudder L/R         20 deg      24 deg +0/-1  (parallel to 0.00 W.L.)
    #   flap full down     30 deg      38 deg +0/-1
    #
    # Ailerons already matched at 20 up / 15 down and are deliberately not patched.
    # Flap detent 3 is the FULL position; detents 1 and 2 stay at 10 and 20, which
    # match the 182T POH flap settings.
    r"^P acf/_elev1_up .*": "P acf/_elev1_up 28.000000000",
    r"^P acf/_elev1_dn .*": "P acf/_elev1_dn 21.000000000",
    r"^P acf/_rudd1_lf .*": "P acf/_rudd1_lf 24.000000000",
    r"^P acf/_rudd1_rt .*": "P acf/_rudd1_rt 24.000000000",
    r"^P acf/_flap1_dn/3 .*": "P acf/_flap1_dn/3 38.000000000",

    # Centre-of-gravity envelope, from TCDS 3A13 Rev 66 page 33 (C.G. Range,
    # Model 182T) placed by percentage of MAC, which is datum independent.
    #
    # The ACF frame's origin is not the Cessna reference datum (lower front face
    # of the firewall), and no consulted source locates the firewall in X-Plane's
    # frame, so the limits are placed via %MAC instead:
    #
    #   TCDS  MAC = 58.8 in, leading edge of MAC at FS 25.98 in
    #   ACF   _wing/0/_part_z is the root QUARTER-CHORD, confirmed against the
    #         donor mesh: predicted vs measured wing leading edge agrees within
    #         ~12 mm at two clean spanwise stations, against a 396 mm difference
    #         between the quarter-chord and leading-edge readings.
    #   so    root LE = 3.200 - 0.25*5.200 = 1.900 ft, MAC LE = 1.994 ft,
    #         MAC = 4.837 ft (vs the TCDS 58.8 in, -1.3%)
    #
    #   FS 33.0 in -> 11.94% MAC -> 2.571 ft    (stock C172S value was 2.900)
    #   FS 46.0 in -> 34.05% MAC -> 3.641 ft    (stock C172S value was 3.900)
    #
    # The stock aft limit sat at 39.40% MAC, 5.35% MAC (about 3.1 in) aft of the
    # C182T's certificated aft limit - the stability-reducing direction.
    #
    # LIMITATION: the TCDS forward limit is weight-scheduled (33.0 in at 2,250 lb
    # and below, 35.5 in at 2,700 lb, 40.9 in at 3,100 lb) while X-Plane takes a
    # single forward value. The most forward certificated point is used, so the
    # envelope is correct at light weights and permissive at heavy ones. Modelling
    # the taper would need a loading-system change, not an ACF constant.
    r"^P acf/_cgZ_fwd .*": "P acf/_cgZ_fwd 2.571000000",
    r"^P acf/_cgZ_aft .*": "P acf/_cgZ_aft 3.641000000",

    # Horizontal tail span, from the POH three-view (Figure 1-1 Sheet 1, page 1-3,
    # top view, "11'-8""), the same sourced drawing used for span and length in
    # docs/C182T_DIMENSION_MASTER.md.
    #
    #   span = 2 * (|_part_x| + _semilen_SEG) = 2 * (0.300 + 5.300) = 11.200 ft
    #   POH target 11 ft 8 in = 11.6667 ft, so the stock C172S tail is 4.0% short
    #   required semilen = 11.6667/2 - 0.300 = 5.53333 ft
    #
    # This is the surface the elevator acts on, and the elevator was separately
    # given its certificated 28/21 degree travel above; leaving the surface 4%
    # undersized would have kept pitch authority short by a different route.
    #
    # Chords are unchanged, so per-side area rises 20.70 -> 21.55 ft2 (+4.1%).
    # That direction is right - the 182's tail is genuinely larger than the 172's -
    # but note that NO consulted source publishes a C182T horizontal tail AREA, so
    # only the span is verified. The area is a consequence, not a sourced target.
    # A2-3: wheel positions. Measured in X-Plane 12.4.3 on 2026-10-11 from
    # sim/flightmodel/parts/tire_[xz]_no_deflection with the stock C172 gear:
    # track 98.55 in, wheelbase 65.65 in. POH Figure 1-1: track 9 ft 0 in
    # (108.0 in), wheelbase 66.5 in. Moving an attach point translates its wheel
    # by the same amount, so the mains move out 0.11996 m each side and the
    # nose forward 0.02161 m. The main-wheel station is kept (it fixes the
    # CG-to-main distance the take-off rotation depends on); leg length, angles
    # and tyres are left as the C172's (no 182T source).
    r"^P _gear/1/_gear_x .*": "P _gear/1/_gear_x -1.993562200",
    r"^P _gear/2/_gear_x .*": "P _gear/2/_gear_x 1.993562200",
    r"^P _gear/0/_gear_z .*": "P _gear/0/_gear_z -0.670905800",

    r"^P _wing/8/_semilen_SEG .*": "P _wing/8/_semilen_SEG 5.533330000",
    r"^P _wing/9/_semilen_SEG .*": "P _wing/9/_semilen_SEG 5.533330000",
}


BADGE_FONT_CANDIDATES = (
    "DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
)


def _glyph_renders(font, ch: str) -> bool:
    """Whether `font` has a real glyph for ch, not its missing-glyph box.

    Pillow draws an absent character as the font's notdef shape and raises
    nothing, so the only way to know is to compare against a code point that no
    font assigns.
    """
    def render(c):
        im = Image.new("L", (40, 40), 0)
        ImageDraw.Draw(im).text((5, 5), c, fill=255, font=font)
        return im.tobytes()
    return render(ch) != render("\ufffe")


def badge_font_and_bullet(size: int = 11):
    """A font for the icon banners and the separator character it can draw.

    B2-3: the banners used an HTML bullet entity as literal text - ImageDraw.text
    does not decode entities - and Pillow's default font has no U+2022 either, so
    the real bullet came out as a missing-glyph box. Prefer a TrueType face that
    has the bullet; failing that, the middle dot, which the default font does
    draw; failing that, a hyphen.
    """
    for name in BADGE_FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(name, size)
        except OSError:
            continue
        if _glyph_renders(font, "\u2022"):
            return font, "\u2022"
    font = ImageFont.load_default()
    for ch in ("\u2022", "\u00b7"):
        if _glyph_renders(font, ch):
            return font, ch
    return font, "-"


def create_cap_badge_icon(src_icon_path: Path, dst_icon_path: Path, is_thumb: bool = False,
                          registration: str = "CAP 487"):
    """Overlay an authentic Civil Air Patrol banner and registration on the selection icon."""
    try:
        with Image.open(src_icon_path) as im:
            im = im.convert("RGBA")
            w, h = im.size
            draw = ImageDraw.Draw(im)
            font, dot = badge_font_and_bullet()

            banner_h = int(h * 0.16) if not is_thumb else int(h * 0.22)
            # Top Banner: Dark Navy (#00204E) with gold/white text
            draw.rectangle([(0, 0), (w, banner_h)], fill=(0, 32, 78, 235))
            # Gold stripe
            draw.line([(0, banner_h), (w, banner_h)], fill=(212, 160, 23, 255), width=2 if not is_thumb else 1)

            # Bottom Banner: Subdued status
            draw.rectangle([(0, h - banner_h), (w, h)], fill=(0, 20, 48, 235))
            draw.line([(0, h - banner_h), (w, h - banner_h)], fill=(186, 12, 47, 255), width=2 if not is_thumb else 1)

            if not is_thumb:
                draw.text((16, 8), f"CIVIL AIR PATROL {dot} USAF AUXILIARY",
                          fill=(255, 255, 255, 255), font=font)
                draw.text((16, banner_h - 22), f"CESSNA 182T NAV III {dot} LYCOMING IO-540 (230 HP)",
                          fill=(212, 160, 23, 255), font=font)
                draw.text((w - 140, 10), registration, fill=(255, 255, 255, 255), font=font)
                draw.text((16, h - banner_h + 8),
                          f"GARMIN G1000 SVT {dot} CONSTANT SPEED {dot} SAR MISSION READY",
                          fill=(200, 220, 245, 255), font=font)
            else:
                draw.text((4, 2), registration, fill=(255, 255, 255, 255), font=font)
                draw.text((4, h - banner_h + 2), "C182T G1000", fill=(212, 160, 23, 255), font=font)

            im.save(dst_icon_path, "PNG")
    except Exception as e:
        print(f"    [!] Warning creating custom badge icon: {e}")
        shutil.copy2(src_icon_path, dst_icon_path)


class ObjLayoutError(RuntimeError):
    """The donor cockpit OBJ is not laid out the way the lever extraction needs."""


# What the Laminar C172SP G1000 cockpit OBJ holds for the two knobs the prop
# lever is built from: (ANIM_trans dataref, TRIS vertex-index count). The start
# offsets are looked up in the file, never hard-coded: any X-Plane re-export
# shuffles them, and the old fixed offsets then built the lever from whatever
# geometry sat there while printing success (B2-5). The counts are the
# fingerprint of the knob mesh itself, so a changed count means different
# geometry and the build stops.
THROTTLE_DATAREF = "sim/cockpit2/engine/actuators/throttle_ratio[0]"
MIXTURE_DATAREF = "sim/cockpit2/engine/actuators/mixture_ratio[0]"
THROTTLE_TRIS_COUNT = 534
MIXTURE_TRIS_COUNT = 450


def find_knob_tris(lines: list[str], dataref: str, expect_count: int) -> tuple[int, int]:
    """(start, count) of the TRIS run animated by the ANIM_trans on `dataref`.

    Expects the donor's shape: one ANIM_begin ... ANIM_end block holding a single
    ANIM_trans on the dataref and a single TRIS. Anything else raises
    ObjLayoutError naming what was found, rather than guessing.
    """
    hits = [i for i, l in enumerate(lines)
            if l.startswith("ANIM_trans ") and l.split()[-1] == dataref]
    if len(hits) != 1:
        raise ObjLayoutError(
            f"expected exactly one 'ANIM_trans ... {dataref}' line in the cockpit OBJ, "
            f"found {len(hits)}; the donor layout has changed - re-derive the lever "
            f"extraction before building")
    tris = []
    for j in range(hits[0] + 1, len(lines)):
        tok = lines[j].split()
        if not tok:
            continue
        if tok[0] == "ANIM_end":
            break
        if tok[0] == "ANIM_begin":
            raise ObjLayoutError(f"{dataref}: block ended without ANIM_end")
        if tok[0] == "TRIS":
            tris.append((int(tok[1]), int(tok[2])))
    else:
        raise ObjLayoutError(f"{dataref}: no ANIM_end after the ANIM_trans")
    if len(tris) != 1:
        raise ObjLayoutError(
            f"{dataref}: expected one TRIS in its animation block, found {len(tris)}")
    start, count = tris[0]
    if count != expect_count:
        raise ObjLayoutError(
            f"{dataref}: TRIS run is {count} indices, expected {expect_count} - the "
            f"donor knob mesh is not the one this extraction was written against")
    return start, count


def add_prop_lever(target_dir: Path):
    """Add a blue constant-speed prop lever to the 3D cockpit's throttle quadrant.

    The base C172SP has a fixed-pitch prop and no prop lever in its 3D cockpit
    model, even though _prop_type is patched to 1 (constant-speed) above. This
    duplicates the existing throttle knob's mesh (same shape, per the CAP V-SAR
    design), moves the copy to the midpoint between the throttle and mixture
    levers (matching the real-world Throttle / Prop / Mixture quadrant order),
    and recolors its texture to the same blue Laminar's Baron 58 uses for its
    prop levers (HSV hue ~205 deg, sampled from B58_panelback.png) while keeping
    the throttle knob's own baked shading/highlight pattern for the shape cues.
    Ships as its own small self-contained object (own texture, own manipulator
    bound to sim/cockpit2/engine/actuators/prop_ratio[0]) registered as a new
    _obja slot in the .acf, so it never touches the shared cockpit.dds atlas
    or the existing throttle/mixture geometry.
    """
    objects_dir = target_dir / "objects"
    src_obj_path = objects_dir / "cockpit_panel_G1000.obj"
    atlas_path = objects_dir / "cockpit.dds"
    out_obj_path = objects_dir / "prop_lever.obj"
    out_png_path = objects_dir / "prop_lever.png"

    with src_obj_path.open() as f:
        lines = f.read().splitlines()

    pc_idx = next((i for i, l in enumerate(lines) if l.startswith("POINT_COUNTS")), None)
    if pc_idx is None:
        raise ObjLayoutError("cockpit OBJ has no POINT_COUNTS line")
    n_vt, n_lines, n_lights, n_idx = map(int, lines[pc_idx].split()[1:])
    if n_lines or n_lights:
        # The reader below walks straight from the VT block to the IDX block.
        raise ObjLayoutError(
            f"cockpit OBJ has {n_lines} line and {n_lights} light vertices; "
            f"the lever extraction assumes none")
    vt_start = pc_idx + 1
    vt = []
    for l in lines[vt_start:vt_start + n_vt]:
        vt.append(list(map(float, l.split()[1:])))  # x y z nx ny nz u v

    idx_flat: list[int] = []
    i = vt_start + n_vt
    while len(idx_flat) < n_idx:
        toks = lines[i].split() if i < len(lines) else []
        if not toks or toks[0] not in ("IDX", "IDX10"):
            raise ObjLayoutError(
                f"expected IDX/IDX10 at cockpit OBJ line {i + 1} "
                f"({len(idx_flat)} of {n_idx} indices read), found {lines[i:i + 1]!r}")
        idx_flat.extend(int(t) for t in toks[1:])
        i += 1
    idx_flat = idx_flat[:n_idx]

    if len(idx_flat) < n_idx:
        raise ObjLayoutError(f"cockpit OBJ declares {n_idx} indices but holds {len(idx_flat)}")

    # Start/count of the throttle and mixture knobs, read from the TRIS lines in
    # the ANIM_trans blocks for throttle_ratio[0] and mixture_ratio[0].
    THROTTLE_START, THROTTLE_COUNT = find_knob_tris(lines, THROTTLE_DATAREF, THROTTLE_TRIS_COUNT)
    MIXTURE_START, MIXTURE_COUNT = find_knob_tris(lines, MIXTURE_DATAREF, MIXTURE_TRIS_COUNT)
    for name, start, count in (("throttle", THROTTLE_START, THROTTLE_COUNT),
                               ("mixture", MIXTURE_START, MIXTURE_COUNT)):
        if start < 0 or start + count > n_idx or count % 3:
            raise ObjLayoutError(f"{name} TRIS {start}+{count} does not fit {n_idx} indices")

    throttle_idx = idx_flat[THROTTLE_START:THROTTLE_START + THROTTLE_COUNT]
    mixture_idx = idx_flat[MIXTURE_START:MIXTURE_START + MIXTURE_COUNT]
    if max(throttle_idx + mixture_idx) >= n_vt:
        raise ObjLayoutError("knob indices point past the vertex table")

    def centroid(idx_list):
        uniq = sorted(set(idx_list))
        xs = [vt[i][0] for i in uniq]
        ys = [vt[i][1] for i in uniq]
        zs = [vt[i][2] for i in uniq]
        return (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))

    throttle_centroid = centroid(throttle_idx)
    mixture_centroid = centroid(mixture_idx)
    target = tuple((a + b) / 2 for a, b in zip(throttle_centroid, mixture_centroid))
    delta = tuple(t - c for t, c in zip(target, throttle_centroid))

    throttle_uniq = sorted(set(throttle_idx))
    us = [vt[i][6] for i in throttle_uniq]
    vs = [vt[i][7] for i in throttle_uniq]
    min_u, max_u = min(us), max(us)
    min_v, max_v = min(vs), max(vs)
    if not (max_u > min_u and max_v > min_v):
        # The UV rescale below divides by these. A zero span means the knob has
        # no area on the atlas - the wrong mesh, not a thin one.
        raise ObjLayoutError(
            f"throttle knob has a degenerate UV span (u {min_u}..{max_u}, v {min_v}..{max_v})")

    atlas = Image.open(atlas_path).convert("RGB")
    W, H = atlas.size
    px_left = round(min_u * W)
    px_right = round(max_u * W)
    px_top = round((1 - max_v) * H)
    px_bottom = round((1 - min_v) * H)
    crop = atlas.crop((px_left, px_top, px_right, px_bottom))
    crop_w, crop_h = crop.size

    # Recolor to "Baron blue" (hue ~205 deg, sampled from Laminar's Baron 58 prop
    # lever texture) while keeping the throttle knob's own luminance-driven
    # shading, so the recolored knob still reads as a shaded 3D shape rather
    # than a flat cutout.
    TARGET_H = 205.0 / 360.0
    S_LO, S_HI = 0.78, 0.88
    V_LO, V_HI = 0.36, 0.72

    px = crop.load()
    out_img = Image.new("RGB", crop.size)
    opx = out_img.load()
    lum_vals = [
        (0.299 * px[x, y][0] + 0.587 * px[x, y][1] + 0.114 * px[x, y][2]) / 255.0
        for y in range(crop_h) for x in range(crop_w)
    ]
    lmin, lmax = min(lum_vals), max(lum_vals)
    lspan = max(lmax - lmin, 1e-6)
    for y in range(crop_h):
        for x in range(crop_w):
            r, g, b = px[x, y]
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            t = (lum - lmin) / lspan
            v = V_LO + t * (V_HI - V_LO)
            s = S_LO + t * (S_HI - S_LO)
            rr, gg, bb = colorsys.hsv_to_rgb(TARGET_H, s, v)
            opx[x, y] = (round(rr * 255), round(gg * 255), round(bb * 255))
    # X-Plane warned on the atlas crop's 194x87 dimensions. Resample to
    # power-of-two dimensions; normalized UVs below still span the whole image.
    texture_size = tuple(1 << (size - 1).bit_length() for size in out_img.size)
    out_img = out_img.resize(texture_size, Image.Resampling.LANCZOS)
    out_img.save(out_png_path)

    local_map: dict[int, int] = {}
    local_verts = []
    for gi in throttle_idx:
        if gi not in local_map:
            local_map[gi] = len(local_verts)
            x, y, z, nx, ny, nz, u, v = vt[gi]
            nu = (u - min_u) / (max_u - min_u)
            nv = (v - min_v) / (max_v - min_v)
            local_verts.append((x + delta[0], y + delta[1], z + delta[2], nx, ny, nz, nu, nv))
    local_idx = [local_map[gi] for gi in throttle_idx]

    def fmt(v):
        return f"{v:.6f}"

    out_lines = [
        "A", "800", "OBJ", "",
        "TEXTURE prop_lever.png",
        "GLOBAL_specular 0.500000", "",
        f"POINT_COUNTS {len(local_verts)} 0 0 {len(local_idx)}",
    ]
    for v in local_verts:
        out_lines.append("VT " + " ".join(fmt(c) for c in v))
    for i in range(0, len(local_idx), 10):
        chunk = local_idx[i:i + 10]
        # OBJ8 IDX10 requires exactly ten indices. Emit the remainder as IDX.
        # https://developer.x-plane.com/article/obj8-file-format-specification/
        if len(chunk) == 10:
            out_lines.append("IDX10 " + " ".join(str(c) for c in chunk))
        else:
            out_lines.extend(f"IDX {c}" for c in chunk)
    out_lines += [
        "ANIM_begin",
        "ANIM_trans 0.000000 0.000000 0.000000 0.000000 0.000000 -0.089700 0.000000 1.000000 "
        "sim/cockpit2/engine/actuators/prop_ratio[0]",
        "ATTR_manip_drag_axis hand 0.000000 0.000000 -0.060000 0.000000 1.000000 "
        "sim/cockpit2/engine/actuators/prop_ratio[0] Prop",
        f"TRIS 0 {len(local_idx)}",
        "ANIM_end", "",
    ]
    out_obj_path.write_text("\n".join(out_lines))
    print(f"[+] Prop lever object: {out_obj_path.name} ({len(local_verts)} verts), "
          f"texture {out_png_path.name} ({texture_size[0]}x{texture_size[1]}, Baron blue)")


def register_prop_lever_obja(acf_path: Path):
    """Register objects/prop_lever.obj as a new _obja slot in the .acf, cloning
    the flags/placement fields from the existing cockpit_panel_G1000.obj slot
    (_obja/6) so it renders in the same interior-only context."""
    with acf_path.open() as f:
        lines = f.read().split("\n")

    existing = set()
    for l in lines:
        if l.startswith("P _obja/"):
            m = re.match(r"_obja/(\d+)/", l[2:])
            if m:
                existing.add(int(m.group(1)))
    new_index = max(existing) + 1

    anchor = f"P _obja/{new_index - 1}/_v10_steers_with_gear 0"
    insert_at = next(i for i, l in enumerate(lines) if l.strip() == anchor) + 1

    new_block = [
        f"P _obja/{new_index}/_obj_flags 1033",
        f"P _obja/{new_index}/_v10_att_body -1",
        f"P _obja/{new_index}/_v10_att_file_stl prop_lever.obj",
        f"P _obja/{new_index}/_v10_att_gear -1",
        f"P _obja/{new_index}/_v10_att_phi_ref 0.000000000",
        f"P _obja/{new_index}/_v10_att_psi_ref 0.000000000",
        f"P _obja/{new_index}/_v10_att_the_ref 0.000000000",
        f"P _obja/{new_index}/_v10_att_wing -1",
        f"P _obja/{new_index}/_v10_att_x_acf_prt_ref 0.000000000",
        f"P _obja/{new_index}/_v10_att_y_acf_prt_ref 0.000000000",
        f"P _obja/{new_index}/_v10_att_z_acf_prt_ref 0.000000000",
        f"P _obja/{new_index}/_v10_is_internal 419430400",
        f"P _obja/{new_index}/_v10_steers_with_gear 0",
    ]
    lines = lines[:insert_at] + new_block + lines[insert_at:]
    for i, l in enumerate(lines):
        if l.startswith("P _obja/count "):
            lines[i] = f"P _obja/count {new_index + 1}"
            break
    acf_path.write_text("\n".join(lines))
    print(f"[+] Registered prop_lever.obj as _obja/{new_index} in {acf_path.name}")


def patch_acf_lines(lines: list[str]) -> list[str]:
    """Require each reviewed source parameter exactly once before changing an ACF."""
    counts = {pattern: 0 for pattern in ACF_PATCHES}
    patched = []
    for line in lines:
        matches = [pattern for pattern in ACF_PATCHES if re.match(pattern, line.strip())]
        if len(matches) > 1:
            raise ValueError(f"Overlapping ACF patches for {line.strip()}")
        if matches:
            pattern = matches[0]
            counts[pattern] += 1
            patched.append(ACF_PATCHES[pattern] + "\n")
        else:
            patched.append(line)
    wrong = {pattern: count for pattern, count in counts.items() if count != 1}
    if wrong:
        raise ValueError(f"ACF patch source fields must occur exactly once: {wrong}")
    return patched


def publish_staged_package(stage: Path, target: Path) -> Path | None:
    """Replace the installed package only after a complete build; roll back on rename failure."""
    backup = None
    if target.exists():
        # Keep the old aircraft outside Aircraft/ so X-Plane does not list it.
        if target.parent.name == "CAP" and target.parent.parent.name == "Aircraft":
            backup_root = target.parents[2] / "Output/capvsar-backups"
        else:
            backup_root = target.parent / ".capvsar-build-backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / f"{target.name}-{uuid.uuid4().hex[:12]}"
        target.rename(backup)
    try:
        stage.rename(target)
    except Exception:
        if backup is not None:
            backup.rename(target)
        raise
    return backup


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="installed Laminar C172SP directory supplying the cockpit and systems",
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=DEFAULT_TARGET_DIR,
        help="aircraft package directory to replace",
    )
    parser.add_argument(
        "--flightgear-donor",
        type=Path,
        default=DEFAULT_DONOR_DIR,
        help="pinned HHS81 FlightGear C182 source directory",
    )
    parser.add_argument("--cap-c172-livery", type=Path,
                        default=Path.home() / "Documents/Civil Air Patrol",
                        help="local downloaded N429CP CAP C172 paint to remap (when present)")
    parser.add_argument("--default-livery", choices=("cap487", "n429cp"), default="cap487",
                        help="paint on the aircraft's base texture. cap487 (default) matches the "
                             "ACF tail number and ATC identity; n429cp makes the adapted C172 "
                             "artwork the default. The N429CP livery is installed as a named "
                             "livery either way when its source artwork is present (A2-5).")
    parser.add_argument("--cap-icon-dir", type=Path,
                        default=DEFAULT_TARGET_DIR / "liveries/Civil Air Patrol (N429CP - C172 Adapted)",
                        help="approved C182 N429CP icon pair, when present")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    source_dir = args.source_dir.expanduser().resolve()
    requested_target = args.target_dir.expanduser()
    if requested_target.is_symlink():
        raise ValueError("Target aircraft directory must not be a symlink")
    target_dir = requested_target.resolve()
    donor_dir = args.flightgear_donor.expanduser().resolve()
    cap_source = args.cap_c172_livery.expanduser().resolve()
    cap_icons = args.cap_icon_dir.expanduser().resolve()

    print("=" * 78)
    print("CAP V-SAR: Cessna 182T NAV III (G1000) Aircraft Package Builder")
    print("=" * 78)

    if not source_dir.is_dir():
        print(f"[-] Source aircraft directory not found: {source_dir}")
        sys.exit(1)
    for protected in (source_dir, donor_dir):
        if protected == target_dir or protected in target_dir.parents or target_dir in protected.parents:
            raise ValueError(f"Target and protected source directories overlap: {target_dir}, {protected}")
    required = ("Cessna_172SP_G1000.acf", "Cessna_172SP_G1000_cockpit.obj",
                "Cessna_172SP_G1000_icon11.png", "Cessna_172SP_G1000_icon11_thumb.png",
                "objects/cockpit_panel_G1000.obj", "objects/cockpit.dds")
    missing = [name for name in required if not (source_dir / name).is_file()]
    if missing:
        raise ValueError(f"Source aircraft is incomplete: {missing}")
    # A source drift or malformed ACF must fail while the installed target is intact.
    patch_acf_lines((source_dir / required[0]).read_text(encoding="utf-8", errors="replace").splitlines(keepends=True))
    try:
        validate_donor(donor_dir)
    except ValueError as exc:
        print(f"[-] {exc}")
        print("[*] Fetch the reviewed donor first with:")
        print(f"    python3 scripts/fetch_flightgear_c182.py {donor_dir}")
        sys.exit(1)

    print(f"[*] Cockpit/systems source: {source_dir}")
    print(f"[*] GPL exterior donor: {donor_dir} (commit {DONOR_COMMIT})")
    print(f"[*] Target: {target_dir}")

    final_target = target_dir
    final_target.parent.mkdir(parents=True, exist_ok=True)
    target_dir = final_target.parent / f".{final_target.name}.staging-{uuid.uuid4().hex[:12]}"
    atexit.register(shutil.rmtree, target_dir, ignore_errors=True)

    # Build away from the installed aircraft; no existing target is removed here.
    print(f"[*] Cloning base airframe directory tree (~284 MB)...")
    shutil.copytree(source_dir, target_dir)
    print(f"[+] Cloned successfully into {target_dir}")

    # 2. Remove non-G1000 airframe files (C172 analogue and seaplane variants)
    redundant_files = [
        "Cessna_172SP.acf",
        "Cessna_172SP_cockpit.obj",
        "Cessna_172SP_icon11.png",
        "Cessna_172SP_icon11_thumb.png",
        "Cessna_172SP_prop_disc_2.png",
        "Cessna_172SP_vrconfig.txt",
        "Cessna_172SP_seaplane.acf",
        "Cessna_172SP_seaplane_cockpit.obj",
        "Cessna_172SP_seaplane_icon11.png",
        "Cessna_172SP_seaplane_icon11_thumb.png",
        "Cessna_172SP_seaplane_prop_disc_2.png",
        "Cessna_172SP_seaplane_vrconfig.txt",
        # A2-6: manuals for equipment this aircraft does not have, and the C172
        # handbook whose speeds it must not be flown by. The G1000 manual stays.
        "X-Plane_C172_Pilot_Operating_Manual.pdf",
        "X-Plane G430 Manual.pdf",
        "X-Plane G530 Manual.pdf",
        "S-TEC Autopilot Manual.pdf",
    ]
    for rf in redundant_files:
        p = target_dir / rf
        if p.exists():
            p.unlink()

    # 3. Rename G1000 files to Cessna_182T_G1000.*
    rename_map = {
        "Cessna_172SP_G1000.acf": "Cessna_182T_G1000.acf",
        "Cessna_172SP_G1000_cockpit.obj": "Cessna_182T_G1000_cockpit.obj",
        "Cessna_172SP_G1000_icon11.png": "Cessna_182T_G1000_icon11.png",
        "Cessna_172SP_G1000_icon11_thumb.png": "Cessna_182T_G1000_icon11_thumb.png",
        "Cessna_172SP_G1000_prop_disc_2.png": "Cessna_182T_G1000_prop_disc_2.png",
        "Cessna_172SP_G1000_vrconfig.txt": "Cessna_182T_G1000_vrconfig.txt",
    }
    for old_name, new_name in rename_map.items():
        src = target_dir / old_name
        dst = target_dir / new_name
        if src.exists():
            src.rename(dst)

    # 4. Patch Cessna_182T_G1000.acf
    print("[*] Converting pinned FlightGear C182 exterior to X-Plane OBJ8...")
    exterior_manifest = build_flightgear_objects(donor_dir, target_dir)
    print(
        "[+] C182 exterior converted: "
        f"{sum(item['indices'] // 3 for item in exterior_manifest['generated_objects'])} triangles"
    )

    acf_path = target_dir / "Cessna_182T_G1000.acf"
    print(f"[*] Patching aircraft flight dynamics and engine in {acf_path.name}...")

    with acf_path.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    patched_lines = patch_acf_lines(lines)

    with acf_path.open("w", encoding="utf-8") as f:
        f.writelines(patched_lines)

    print(f"[+] Applied all {len(ACF_PATCHES)} aircraft parameters exactly once.")

    # 4b. Add a blue constant-speed prop lever to the 3D cockpit (the base C172SP
    # has no prop lever at all, since it's fixed-pitch) and register it in the acf.
    print(f"[*] Adding prop lever to 3D cockpit (blue, matches Baron 58 prop knob color)...")
    add_prop_lever(target_dir)
    register_prop_lever_obja(acf_path)

    # 5. Clean up liveries and rename icon files
    liveries_dir = target_dir / "liveries"
    if liveries_dir.exists():
        for liv in liveries_dir.iterdir():
            if liv.is_dir():
                # Rename livery icons
                old_liv_icon = liv / "Cessna_172SP_G1000_icon11.png"
                new_liv_icon = liv / "Cessna_182T_G1000_icon11.png"
                if old_liv_icon.exists():
                    old_liv_icon.rename(new_liv_icon)

                old_liv_thumb = liv / "Cessna_172SP_G1000_icon11_thumb.png"
                new_liv_thumb = liv / "Cessna_182T_G1000_icon11_thumb.png"
                if old_liv_thumb.exists():
                    old_liv_thumb.rename(new_liv_thumb)

                # Remove legacy analog / seaplane icons inside liveries
                for f in liv.glob("Cessna_172SP_icon11*"):
                    f.unlink()
                for f in liv.glob("Cessna_172SP_seaplane*"):
                    f.unlink()

    # 6. Create dedicated Civil Air Patrol CAP 487 livery
    cap_livery_dir = liveries_dir / "Civil Air Patrol (CAP 487)"
    print(f"[*] Building dedicated Civil Air Patrol livery in {cap_livery_dir.name}...")
    cap_livery_dir.mkdir(parents=True, exist_ok=True)

    # Use full_white textures as clean baseline
    white_objs = liveries_dir / "full_white" / "objects"
    if white_objs.is_dir():
        shutil.copytree(white_objs, cap_livery_dir / "objects", dirs_exist_ok=True)

    # The donor UV atlas has a new filename, so the old C172 full-white files
    # cannot override it.  Install the generated CAP 487 texture explicitly.
    cap_objects = cap_livery_dir / "objects"
    cap_objects.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        target_dir / "objects" / "flightgear_c182t.png",
        cap_objects / "flightgear_c182t.png",
    )

    # 7. Generate CAP Badge Icons
    icon_dst = target_dir / "Cessna_182T_G1000_icon11.png"
    thumb_dst = target_dir / "Cessna_182T_G1000_icon11_thumb.png"
    create_cap_badge_icon(icon_dst, icon_dst, is_thumb=False)
    create_cap_badge_icon(thumb_dst, thumb_dst, is_thumb=True)

    # Also copy badged icons to the CAP livery folder
    shutil.copy2(icon_dst, cap_livery_dir / "Cessna_182T_G1000_icon11.png")
    shutil.copy2(thumb_dst, cap_livery_dir / "Cessna_182T_G1000_icon11_thumb.png")

    print(f"[+] Civil Air Patrol livery and icons configured.")

    # Keep the approved downloaded artwork in the reproducible build path.
    # The mapper uses local licensed assets; no Laminar or donor texture enters Git.
    if cap_source.is_dir():
        from types import SimpleNamespace
        from adapt_cap_livery import adapt
        named = liveries_dir / "Civil Air Patrol (N429CP - C172 Adapted)"
        if named.exists():
            shutil.rmtree(named)
        # The approved adaptation starts from the pinned donor's Default.png;
        # starting from the generated CAP 487 repaint changes untouched pixels.
        base_texture = donor_dir / "Models/Liveries/Default.png"
        adapt(SimpleNamespace(source=cap_source, c172=source_dir, aircraft=target_dir,
                              base=base_texture, output=named))
        # The projection diagnostics belong in the output workspace, not an
        # aircraft livery folder scanned by X-Plane.
        for diagnostic in named.glob("donor-*.png"):
            diagnostic.unlink()
        manifest_path = named / "adaptation.json"
        manifest_path.write_text(
            manifest_path.read_text().replace(str(target_dir), str(final_target)))
        if args.default_livery == "n429cp":
            shutil.copy2(named / "objects/flightgear_c182t.png",
                         target_dir / "objects/flightgear_c182t.png")
        for icon in ("Cessna_182T_G1000_icon11.png", "Cessna_182T_G1000_icon11_thumb.png"):
            approved = cap_icons / icon
            if approved.is_file():
                shutil.copy2(approved, named / icon)
            else:
                stock = source_dir / icon.replace("182T", "172SP")
                create_cap_badge_icon(stock, named / icon,
                                      is_thumb=icon.endswith("_thumb.png"), registration="N429CP")
        if args.default_livery == "n429cp":
            for icon in ("Cessna_182T_G1000_icon11.png", "Cessna_182T_G1000_icon11_thumb.png"):
                shutil.copy2(named / icon, target_dir / icon)
        readme = cap_icons / "README.txt"
        if readme.is_file():
            shutil.copy2(readme, named / "README.txt")
        else:
            (named / "README.txt").write_text(
                "N429CP CAP artwork remapped from the locally downloaded C172 livery.\n"
                "See adaptation.json for source and texture hashes.\n")
        if args.default_livery == "n429cp":
            print(f"[+] N429CP paint installed as aircraft default and named livery.")
        else:
            print(f"[+] N429CP paint installed as a named livery; CAP 487 stays the default (A2-5).")
    else:
        print(f"[*] No local N429CP source at {cap_source}; retaining CAP 487 paint.")

    # 8. Summary Verification
    print("\n" + "=" * 78)
    print("VERIFICATION SUMMARY — CESSNA 182T NAV III (G1000 CAP)")
    print("=" * 78)
    with acf_path.open("r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    checks = [
        ("Aircraft Name", r"P acf/_name (.*)"),
        ("ICAO Code", r"P acf/_ICAO (.*)"),
        ("Tail Number", r"P acf/_tailnum (.*)"),
        ("Engine Max Power", r"P acf/_power_max_limit (.*)"),
        ("Propeller Type", r"P _prop/0/_prop_type (.*)"),
        ("Propeller Blades", r"P _prop/0/_num_blades (.*)"),
        ("Design Prop RPM", r"P _prop/0/_des_rpm_prp (.*)"),
        ("Empty Weight (lbs)", r"P acf/_m_empty (.*)"),
        ("Max Takeoff Weight (lbs)", r"P acf/_m_max (.*)"),
        ("Total Usable Fuel (lbs)", r"P acf/_m_fuel_max_tot (.*)"),
        ("Cowl Flaps Equipped", r"P acf/_cowl_flaps_EQ (.*)"),
        ("Never Exceed Speed (Vne)", r"P acf/_Vne_kts (.*)"),
    ]

    for label, pattern in checks:
        m = re.search(pattern, content)
        val = m.group(1).strip() if m else "NOT FOUND"
        print(f"    - {label.ljust(26)}: {val}")

    # Validate the staged package immediately before publication.
    if not (target_dir / "objects/flightgear_c182t.obj").is_file():
        raise RuntimeError("Staged exterior object missing")
    if not (target_dir / "objects/flightgear_c182t.png").is_file():
        raise RuntimeError("Staged exterior texture missing")
    user_prefs = final_target / "Cessna_182T_G1000_prefs.txt"
    if user_prefs.is_file():
        shutil.copy2(user_prefs, target_dir / user_prefs.name)
    backup = publish_staged_package(target_dir, final_target)
    print("\n[✓] Cessna 182T NAV III CAP package built successfully!")
    print(f"[✓] Location: {final_target}")
    if backup:
        print(f"[✓] Previous aircraft backup: {backup}")


if __name__ == "__main__":
    main()
