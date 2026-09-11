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
import colorsys
import os
import re
import shutil
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from convert_flightgear_c182 import build_flightgear_objects
from fetch_flightgear_c182 import DONOR_COMMIT, validate_donor


DEFAULT_SOURCE_DIR = Path("/home/ron/X-Plane 12/Aircraft/Laminar Research/Cessna 172 SP")
DEFAULT_TARGET_DIR = Path("/home/ron/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III")
DEFAULT_DONOR_DIR = Path(
    os.environ.get(
        "CAPVSAR_FLIGHTGEAR_C182_SOURCE",
        str(Path.home() / ".cache" / "cap-vsar" / f"flightgear-c182-{DONOR_COMMIT}"),
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
    r"^P _prop/0/_min_pitch .*": "P _prop/0/_min_pitch 10.000000000",
    r"^P _prop/0/_max_pitch .*": "P _prop/0/_max_pitch 40.000000000",

    # Weight & Balance: Empty 1,970 lbs, MTOW 3,100 lbs
    r"^P acf/_m_empty .*": "P acf/_m_empty 1970.000000000",
    r"^P acf/_m_max .*": "P acf/_m_max 3100.000000000",

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
    r"^P _wing/8/_semilen_SEG .*": "P _wing/8/_semilen_SEG 5.533330000",
    r"^P _wing/9/_semilen_SEG .*": "P _wing/9/_semilen_SEG 5.533330000",
}


def create_cap_badge_icon(src_icon_path: Path, dst_icon_path: Path, is_thumb: bool = False):
    """Overlay an authentic Civil Air Patrol banner and registration on the selection icon."""
    try:
        with Image.open(src_icon_path) as im:
            im = im.convert("RGBA")
            w, h = im.size
            draw = ImageDraw.Draw(im)

            banner_h = int(h * 0.16) if not is_thumb else int(h * 0.22)
            # Top Banner: Dark Navy (#00204E) with gold/white text
            draw.rectangle([(0, 0), (w, banner_h)], fill=(0, 32, 78, 235))
            # Gold stripe
            draw.line([(0, banner_h), (w, banner_h)], fill=(212, 160, 23, 255), width=2 if not is_thumb else 1)

            # Bottom Banner: Subdued status
            draw.rectangle([(0, h - banner_h), (w, h)], fill=(0, 20, 48, 235))
            draw.line([(0, h - banner_h), (w, h - banner_h)], fill=(186, 12, 47, 255), width=2 if not is_thumb else 1)

            if not is_thumb:
                draw.text((16, 8), "CIVIL AIR PATROL &bull; USAF AUXILIARY", fill=(255, 255, 255, 255))
                draw.text((16, banner_h - 22), "CESSNA 182T NAV III &bull; LYCOMING IO-540 (230 HP)", fill=(212, 160, 23, 255))
                draw.text((w - 140, 10), "CAP 487", fill=(255, 255, 255, 255))
                draw.text((16, h - banner_h + 8), "GARMIN G1000 SVT &bull; CONSTANT SPEED &bull; SAR MISSION READY", fill=(200, 220, 245, 255))
            else:
                draw.text((4, 2), "CAP 487", fill=(255, 255, 255, 255))
                draw.text((4, h - banner_h + 2), "C182T G1000", fill=(212, 160, 23, 255))

            im.save(dst_icon_path, "PNG")
    except Exception as e:
        print(f"    [!] Warning creating custom badge icon: {e}")
        shutil.copy2(src_icon_path, dst_icon_path)


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

    pc_idx = next(i for i, l in enumerate(lines) if l.startswith("POINT_COUNTS"))
    n_vt, _n_lines, _n_lights, n_idx = map(int, lines[pc_idx].split()[1:])
    vt_start = pc_idx + 1
    vt = []
    for l in lines[vt_start:vt_start + n_vt]:
        vt.append(list(map(float, l.split()[1:])))  # x y z nx ny nz u v

    idx_flat: list[int] = []
    i = vt_start + n_vt
    while len(idx_flat) < n_idx:
        toks = lines[i].split()
        idx_flat.extend(int(t) for t in toks[1:])
        i += 1
    idx_flat = idx_flat[:n_idx]

    # TRIS start/count for the throttle and mixture knobs in cockpit_panel_G1000.obj,
    # found by inspecting the file's existing ANIM_trans / TRIS blocks for
    # throttle_ratio[0] and mixture_ratio[0].
    THROTTLE_START, THROTTLE_COUNT = 19629, 534
    MIXTURE_START, MIXTURE_COUNT = 19179, 450

    throttle_idx = idx_flat[THROTTLE_START:THROTTLE_START + THROTTLE_COUNT]
    mixture_idx = idx_flat[MIXTURE_START:MIXTURE_START + MIXTURE_COUNT]

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
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    source_dir = args.source_dir.expanduser().resolve()
    target_dir = args.target_dir.expanduser().resolve()
    donor_dir = args.flightgear_donor.expanduser().resolve()

    print("=" * 78)
    print("CAP V-SAR: Cessna 182T NAV III (G1000) Aircraft Package Builder")
    print("=" * 78)

    if not source_dir.is_dir():
        print(f"[-] Source aircraft directory not found: {source_dir}")
        sys.exit(1)
    if source_dir == target_dir:
        print("[-] Source and target aircraft directories must differ")
        sys.exit(1)
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

    # 1. Clean / create target directory
    if target_dir.exists():
        print(f"[*] Removing existing target directory...")
        shutil.rmtree(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

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
        "Cessna_172SP_seaplane_vrconfig.txt"
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

    patched_lines = []
    applied_patches = set()

    for line in lines:
        matched = False
        for pattern, replacement in ACF_PATCHES.items():
            if re.match(pattern, line.strip()):
                patched_lines.append(replacement + "\n")
                applied_patches.add(pattern)
                matched = True
                break
        if not matched:
            patched_lines.append(line)

    with acf_path.open("w", encoding="utf-8") as f:
        f.writelines(patched_lines)

    print(f"[+] Applied {len(applied_patches)} of {len(ACF_PATCHES)} aircraft parameters.")

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

    print("\n[✓] Cessna 182T NAV III CAP package built successfully!")
    print(f"[✓] Location: {target_dir}")


if __name__ == "__main__":
    main()
