"""Generate faceplate artwork, control images and previews for the MO station.

Covers the two instruments that do not share the DCU chassis:

    instruments/cap-fm-tdfm-136b/       Technisonic TDFM-136B mission radio
    instruments/mo-audio-panel-gma1347/ Garmin GMA 1347 audio panel

Same layering as the DF heads: a static faceplate carrying the housing, screws
and every silk-screened legend; separate images for anything that moves or
lights; and the live display left as a Lua canvas. Each key gets its own image
pair because the cap carries its printed legend and moves when pressed.

GEOMETRY IS NOT DEFINED HERE. It is parsed out of the marked blocks in
    instruments/cap-fm-tdfm-136b/lib/tdfm_panel.lua
    instruments/mo-audio-panel-gma1347/lib/gma_panel.lua
which are what Air Manager uses for the control hit regions, so artwork and hit
regions cannot drift apart. If a block stops parsing the script fails.

Layout authority:
  TDFM-136B  Technisonic 08RE399A Fig 1-1, docs/figures/tdfm_p11_front_panel-11.png
  GMA 1347   Garmin 190-00378-01 Fig 6A.2.1, docs/figures/gma1347_panel-05.png

    python3 scripts/make_panel_artwork.py
"""
import math
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Shared drawing helpers. make_df_artwork owns the supersampling convention, the
# legend typeface and the smooth fixed-cell Screen; there is no reason to have two.
from make_df_artwork import (SS, S, font, text_at, Screen,
                             make_knob, coat, rubber_key, round_control, metal_screw)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTR = os.path.join(ROOT, "instruments")

# The TDFM photographs as a near-black anodised plate; the GMA as Garmin's
# slightly warmer charcoal.
TDFM_HI, TDFM_LO = (45, 47, 46), (35, 37, 36)
GMA_HI, GMA_LO = (49, 51, 53), (38, 40, 42)
LEGEND = (216, 218, 212)
LEGEND_DIM = (176, 176, 170)
EDGE_DARK = (16, 16, 16)
EDGE_LIGHT = (104, 104, 104)
SCREW_METAL = (146, 148, 144)

# TDFM display: amber-red LED on black, matching lib/tdfm_display.lua.
LED_ON = (255, 154, 46)
LED_OFF_BG = (10, 8, 6)


# --------------------------------------------------------------- geometry ----

def parse_block(path, marker="make_panel_artwork.py"):
    src = open(path, encoding="utf-8").read()
    m = re.search(r"=+ GEOMETRY \(parsed by %s\) =+(.*?)=+ END GEOMETRY"
                  % re.escape(marker), src, re.S)
    if not m:
        sys.exit("make_panel_artwork: geometry block not found in %s" % path)
    # Strip trailing comments before anything parses numbers out of the block:
    # a comment such as "measured off Figure 6A.2.1" is full of digits that
    # would otherwise be read as geometry.
    return "\n".join(re.sub(r"--.*$", "", line) for line in m.group(1).splitlines())


def scalar(block, name, path):
    """One numeric constant.

    Parsed line by line rather than with a bare regex search, because
    Lua's multiple assignment makes that ambiguous: in `M.KEY_X0, M.KEY_Y0 =
    400, 202` a naive search for M.KEY_Y0 finds "= 400" and silently returns the
    wrong number. Splitting the line and matching by position is unambiguous.
    """
    want = "M." + name
    for line in block.splitlines():
        lhs, eq, rhs = line.partition("=")
        if not eq:
            continue
        names = [t.strip() for t in lhs.split(",")]
        if want not in names:
            continue
        vals = re.findall(r"-?\d+(?:\.\d+)?", rhs)
        if len(vals) != len(names):
            continue                      # a table or expression, not scalars
        v = float(vals[names.index(want)])
        return int(v) if v == int(v) else v
    sys.exit("make_panel_artwork: M.%s missing from %s" % (name, path))


def rect(block, name, path, extra=()):
    mm = re.search(r"\b%s\s*=\s*\{([^}]*)\}" % re.escape(name), block)
    if not mm:
        sys.exit("make_panel_artwork: rect %s missing from %s" % (name, path))
    body = mm.group(1)
    out = {}
    for k in ("x", "y", "w", "h"):
        kk = re.search(r"\b%s\s*=\s*(-?\d+(?:\.\d+)?)" % k, body)
        if not kk:
            sys.exit("make_panel_artwork: %s.%s missing from %s" % (name, k, path))
        out[k] = float(kk.group(1))
    for k in extra:
        kk = re.search(r'\b%s\s*=\s*"([^"]*)"' % k, body)
        out[k] = kk.group(1) if kk else None
    return out


def pairs(block, name, path):
    mm = re.search(r"M\.%s\s*=\s*\{(.*?)\}\s*$" % name, block, re.M | re.S)
    if not mm:
        sys.exit("make_panel_artwork: M.%s missing from %s" % (name, path))
    return [(float(a), float(b)) for a, b in
            re.findall(r"\{\s*(-?\d+)\s*,\s*(-?\d+)\s*\}", mm.group(1))]


def load_tdfm():
    path = os.path.join(INSTR, "cap-fm-tdfm-136b", "lib", "tdfm_panel.lua")
    b = parse_block(path)
    g = {k: scalar(b, k, path) for k in
         ("FACE_W", "FACE_H", "DISP_SCALE", "DISP_X", "DISP_Y", "DISP_W",
          "DISP_H", "LED_R", "SCREW_R", "SCREW_SMALL_R", "CORNER",
          "KEY_W", "KEY_H", "KEY_X0", "KEY_Y0", "KEY_PITCH_X", "KEY_PITCH_Y",
          "KEY_COLS")}
    g["WINDOW"] = rect(b, "M.WINDOW", path)
    g["MAIN_ENC"] = rect(b, "M.MAIN_ENC", path)
    g["GUARD_ENC"] = rect(b, "M.GUARD_ENC", path)
    g["PGM"] = rect(b, "M.PGM", path)
    tb = re.search(r"M\.TOGGLE\s*=\s*\{(.*?)\n\}", b, re.S).group(1)
    g["TOGGLE"] = {n: rect(tb, n, path, extra=("up", "down"))
                   for n in ("mn_gd", "g1_g2", "hi_lo")}
    g["LEDS"] = pairs(b, "LEDS", path)
    g["SCREWS"] = pairs(b, "SCREWS", path)
    g["SCREWS_SMALL"] = pairs(b, "SCREWS_SMALL", path)
    if g["DISP_W"] != (24 * 4 - 1) * g["DISP_SCALE"]:
        sys.exit("make_panel_artwork: TDFM DISP_W is not 24 characters wide")
    # Keys must not collide with the display window or the encoders.
    kx1 = g["KEY_X0"] + (g["KEY_COLS"] - 1) * g["KEY_PITCH_X"] + g["KEY_W"]
    if kx1 > g["FACE_W"]:
        sys.exit("make_panel_artwork: TDFM keypad runs off the plate")
    return g


def load_gma():
    path = os.path.join(INSTR, "mo-audio-panel-gma1347", "lib", "gma_panel.lua")
    b = parse_block(path)
    g = {k: scalar(b, k, path) for k in
         ("FACE_W", "FACE_H", "KEY_W", "KEY_H", "ANN_W", "ANN_H", "ANN_DY",
          "PHOTOCELL_R", "CORNER")}
    g["COL_X"] = [float(v) for v in
                  re.search(r"M\.COL_X\s*=\s*\{([^}]*)\}", b).group(1).split(",")]
    g["ROW_Y"] = [float(v) for v in
                  re.findall(r"-?\d+",
                             re.search(r"M\.ROW_Y\s*=\s*\{(.*?)\}", b, re.S).group(1))]
    g["GROUP_TX"] = rect(b, "M.GROUP_TX", path)
    g["GROUP_ICS"] = rect(b, "M.GROUP_ICS", path)
    g["KNOB_OUTER"] = rect(b, "M.KNOB_OUTER", path)
    g["KNOB_INNER"] = rect(b, "M.KNOB_INNER", path)
    g["BACKUP"] = rect(b, "M.BACKUP", path)
    pc = re.search(r"M\.PHOTOCELL\s*=\s*\{\s*(-?\d+)\s*,\s*(-?\d+)\s*\}", b)
    if not pc:
        sys.exit("make_panel_artwork: M.PHOTOCELL missing from %s" % path)
    g["PHOTOCELL"] = (float(pc.group(1)), float(pc.group(2)))
    if len(g["ROW_Y"]) != 11:
        sys.exit("make_panel_artwork: GMA expects 11 key rows, parsed %d"
                 % len(g["ROW_Y"]))
    return g


def lua_keys(path, table):
    """Pull a key table out of the Lua so the legends have one definition."""
    src = open(path, encoding="utf-8").read()
    m = re.search(r"M\.%s\s*=\s*\{(.*?)\n\}" % table, src, re.S)
    if not m:
        sys.exit("make_panel_artwork: %s not found in %s" % (table, path))
    out = []
    for line in re.findall(r"\{([^{}]*(?:\{[^}]*\})?[^{}]*)\}", m.group(1)):
        if "=" not in line:
            continue
        e = {}
        for k, v in re.findall(r'(\w+)\s*=\s*"([^"]*)"', line):
            e[k] = v
        for k, v in re.findall(r"(\w+)\s*=\s*(\d+)", line):
            e[k] = int(v)
        tx = re.search(r'text\s*=\s*\{([^}]*)\}', line)
        if tx:
            e["text"] = re.findall(r'"([^"]*)"', tx.group(1))
        if e:
            out.append(e)
    return out


# ------------------------------------------------------------ draw helpers ---

def plate(size, corner, hi, lo, seed):
    """Rounded plate with a lighting fall-off and powder-coat grain."""
    w, h = S(size[0]), S(size[1])
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / float(h)
        grad.putpixel((0, y), tuple(int(hi[i] + (lo[i] - hi[i]) * t) for i in range(3)))
    body = grad.resize((w, h))
    body = coat(body, seed)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1],
                                           radius=S(corner), fill=255)
    img.paste(body.convert("RGBA"), (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=S(corner),
                        outline=EDGE_DARK + (220,), width=S(1.4))
    d.line([S(corner), S(1.4), w - S(corner), S(1.4)],
           fill=(72, 74, 74, 255), width=S(.6))
    return img



def recess(img, d, x, y, w, h, radius, fill):
    """A sunk window: soft inner shadow, hard dark floor."""
    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.rounded_rectangle([S(x - 4), S(y - 4), S(x + w + 4), S(y + h + 4)],
                         radius=S(radius + 3), fill=(0, 0, 0, 185))
    shade = shade.filter(ImageFilter.GaussianBlur(S(2.2)))
    img.alpha_composite(shade)
    d.rounded_rectangle([S(x), S(y), S(x + w), S(y + h)],
                        radius=S(radius), fill=fill + (255,))


# ------------------------------------------------------- TDFM control art ----

def tdfm_key_image(g, entry, pressed=False):
    """One keypad cap with its printed legend. Figure 1-1 puts the digit on top
    and the Level-1 function under it; keys 2/4/6/8 put the digit inside a
    cursor arrow instead."""
    w, h = int(g["KEY_W"]), int(g["KEY_H"])
    img = rubber_key(w, h, pressed)
    d = ImageDraw.Draw(img)

    if entry.get("arrow"):
        # Digit inside an outlined cursor arrow.
        cx, cy = w / 2.0, h / 2.0
        L, T = w * 0.30, h * 0.30
        shaft = 0.42
        pts = {
            "up":    [(0, -T), (L * 0.9, -T * 0.15), (L * shaft, -T * 0.15),
                      (L * shaft, T), (-L * shaft, T), (-L * shaft, -T * 0.15),
                      (-L * 0.9, -T * 0.15)],
            "down":  [(0, T), (L * 0.9, T * 0.15), (L * shaft, T * 0.15),
                      (L * shaft, -T), (-L * shaft, -T), (-L * shaft, T * 0.15),
                      (-L * 0.9, T * 0.15)],
            "left":  [(-L, 0), (-L * 0.15, T * 0.9), (-L * 0.15, T * shaft),
                      (L, T * shaft), (L, -T * shaft), (-L * 0.15, -T * shaft),
                      (-L * 0.15, -T * 0.9)],
            "right": [(L, 0), (L * 0.15, T * 0.9), (L * 0.15, T * shaft),
                      (-L, T * shaft), (-L, -T * shaft), (L * 0.15, -T * shaft),
                      (L * 0.15, -T * 0.9)],
        }[entry["arrow"]]
        d.polygon([(S(cx + px), S(cy + py)) for px, py in pts],
                  outline=LEGEND + (235,), width=S(1.6))
        text_at(d, (cx, cy), entry["digit"], 19, LEGEND)
    else:
        text_at(d, (w / 2.0, h * 0.32), entry["digit"], 20, LEGEND)
        text_at(d, (w / 2.0, h * 0.70), entry.get("fn", ""), 16, LEGEND_DIM)
    return img.resize((w, h), Image.LANCZOS)


def tdfm_toggle_image(g, down=False):
    spec = g["TOGGLE"]["mn_gd"]
    w, h = int(spec["w"]), int(spec["h"])
    img = Image.new("RGBA", (S(w), S(h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = S(w) / 2.0
    # Hexagonal retaining nut, washer and the shadow in the lever socket.
    cy, r = S(h * .63), S(w * .43)
    d.ellipse([cx-r, cy-r*.78, cx+r, cy+r*.78], fill=(20, 22, 22, 255))
    pts = [(cx + r*math.cos(math.radians(30+i*60)),
            cy + r*.72*math.sin(math.radians(30+i*60))) for i in range(6)]
    d.polygon(pts, fill=(116, 119, 116, 255))
    d.line(pts[:3], fill=(166, 168, 162, 255), width=S(.8))
    d.ellipse([cx-r*.59, cy-r*.45, cx+r*.59, cy+r*.45],
              fill=(25, 27, 27, 255), outline=(69, 72, 71, 255), width=S(1))
    # Cylindrical satin-metal lever: narrow lateral highlight, dark right edge.
    ty = S(h * .09 if not down else h * .55)
    bottom = ty + S(h * .40)
    half = S(w * .145)
    lever = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(lever)
    for dx in range(-half, half + 1):
        t = dx / max(1, half)
        v = int(92 + 98 * max(0, 1 - (t + .25)**2))
        ld.line([cx+dx, ty, cx+dx, bottom], fill=(v, v+2, v, 255))
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([cx-half, ty, cx+half, bottom],
                                           radius=half, fill=255)
    img.paste(lever, (0, 0), mask)
    return img.resize((w, h), Image.LANCZOS)


def tdfm_led_image(g, on=False):
    r = int(g["LED_R"])
    px = S(r * 2)
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = px / 2.0
    if on:
        glow = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([c - px * 0.48, c - px * 0.48,
                                      c + px * 0.48, c + px * 0.48],
                                     fill=(90, 235, 120, 110))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(px * 0.10)))
        d.ellipse([c - px * 0.34, c - px * 0.34, c + px * 0.34, c + px * 0.34],
                  fill=(96, 236, 124, 255))
        d.ellipse([c - px * 0.17, c - px * 0.22, c + px * 0.06, c + px * 0.02],
                  fill=(206, 255, 214, 210))
    else:
        d.ellipse([c - px * 0.34, c - px * 0.34, c + px * 0.34, c + px * 0.34],
                  fill=(16, 46, 22, 255))
    d.ellipse([c - px * 0.36, c - px * 0.36, c + px * 0.36, c + px * 0.36],
              outline=(12, 12, 12, 255), width=int(SS * 1.1))
    return img.resize((r * 2, r * 2), Image.LANCZOS)


def tdfm_faceplate(g):
    W, H = int(g["FACE_W"]), int(g["FACE_H"])
    img = plate((W, H), g["CORNER"], TDFM_HI, TDFM_LO, 9021)
    d = ImageDraw.Draw(img)

    # Display window. Figure 1-1 draws it as a rounded outline reaching left of
    # the text to take the two squelch LEDs.
    win = g["WINDOW"]
    recess(img, d, win["x"], win["y"], win["w"], win["h"], 8, LED_OFF_BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([S(win["x"]), S(win["y"]),
                         S(win["x"] + win["w"]), S(win["y"] + win["h"])],
                        radius=S(8), outline=(96, 96, 96, 150), width=S(1.2))

    # Screws: slotted at the corners, small cross screws at mid-height.
    for i, (sx, sy) in enumerate(g["SCREWS"]):
        metal_screw(d, sx, sy, g["SCREW_R"], slotted=True, angle=0 if i % 2 == 0 else 12)
    for sx, sy in g["SCREWS_SMALL"]:
        metal_screw(d, sx, sy, g["SCREW_SMALL_R"], slotted=False, angle=45)

    # Keyloader data port (item 5): a circular connector with seven pins.
    p = g["PGM"]
    pcx, pcy, pr = p["x"] + p["w"] / 2, p["y"] + p["h"] / 2, p["w"] / 2
    d.ellipse([S(pcx - pr), S(pcy - pr), S(pcx + pr), S(pcy + pr)],
              fill=(26, 26, 26, 255), outline=(84, 84, 84, 255), width=S(1.8))
    d.ellipse([S(pcx - pr * 0.80), S(pcy - pr * 0.80),
               S(pcx + pr * 0.80), S(pcy + pr * 0.80)], fill=(16, 16, 16, 255))
    for k in range(7):
        a = math.radians(k * 360.0 / 7 - 90)
        px_, py_ = pcx + math.cos(a) * pr * 0.46, pcy + math.sin(a) * pr * 0.46
        d.ellipse([S(px_ - 2.4), S(py_ - 2.4), S(px_ + 2.4), S(py_ + 2.4)],
                  fill=(112, 112, 112, 255))

    # Legends.
    for spec, label in ((g["MAIN_ENC"], "MAIN"), (g["GUARD_ENC"], "GUARD"),
                        (g["PGM"], "PGM")):
        text_at(d, (spec["x"] + spec["w"] / 2, spec["y"] - 13), label, 19)

    # "OFF" with the leader line Figure 1-1 runs up to the MAIN encoder.
    me = g["MAIN_ENC"]
    off_x, off_y = me["x"] - 22, me["y"] + me["h"] + 6
    text_at(d, (off_x, off_y), "OFF", 18, LEGEND_DIM)
    d.line([S(off_x + 17), S(off_y - 3), S(me["x"] + 6), S(me["y"] + me["h"] - 4)],
           fill=LEGEND_DIM + (200,), width=S(1.3))

    for spec in g["TOGGLE"].values():
        cx = spec["x"] + spec["w"] / 2
        text_at(d, (cx, spec["y"] - 12), spec["up"], 18)
        text_at(d, (cx, spec["y"] + spec["h"] + 13), spec["down"], 18)

    # Branding row. The Technisonic mark is a stylised monogram, drawn as a
    # simple lens shape rather than reproduced.
    d.ellipse([S(46), S(9), S(78), S(26)], outline=LEGEND + (210,), width=S(1.4))
    d.line([S(52), S(24), S(74), S(11)], fill=LEGEND + (210,), width=S(1.4))
    text_at(d, (92, 18), "Technisonic", 20, LEGEND, anchor="lm")
    text_at(d, (700, 18), "TDFM-136B", 20, LEGEND, anchor="rm")
    d.ellipse([S(716), S(7), S(772), S(29)], fill=(18, 18, 18, 255),
              outline=(120, 120, 120, 200), width=S(1.2))
    text_at(d, (744, 18), "P25", 15, LEGEND)
    return img.resize((W, H), Image.LANCZOS)


# -------------------------------------------------------- GMA control art ----

def gma_key_image(g, k, pressed=False):
    w, h = int(g["KEY_W"]), int(g["KEY_H"])
    img = rubber_key(w, h, pressed)
    d = ImageDraw.Draw(img)

    lines = k.get("text") or []
    if len(lines) == 1:
        text_at(d, (w / 2.0, h / 2.0), lines[0], 19, LEGEND)
    elif lines:
        text_at(d, (w / 2.0, h * 0.33), lines[0], 18, LEGEND)
        text_at(d, (w / 2.0, h * 0.70), lines[1], 18, LEGEND)
    return img.resize((w, h), Image.LANCZOS)


def gma_ann_image(g, lit=False):
    """The triangular key annunciator. §6A.2: white when illuminated."""
    w, h = int(g["ANN_W"]), int(g["ANN_H"])
    img = Image.new("RGBA", (S(w), S(h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    tri = [(S(0.5), S(0.5)), (S(w - 0.5), S(0.5)), (S(w / 2.0), S(h - 0.5))]
    if lit:
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).polygon(tri, fill=(255, 255, 255, 120))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(S(1.4))))
        d.polygon(tri, fill=(248, 249, 252, 255))
    else:
        # Dark, but not invisible: the operator has to be able to see which key
        # an annunciator belongs to before it lights.
        d.polygon(tri, fill=(24, 24, 26, 255),
                  outline=(92, 92, 96, 255), width=int(SS * 0.9))
    return img.resize((w, h), Image.LANCZOS)


def gma_knob_image(size, inner=False):
    """Smooth tapered concentric controls as in Garmin Figure 6A.2.1."""
    return round_control(size, base=(37, 39, 41) if inner else (43, 45, 47))


def gma_backup_image(g, pressed=False):
    size = int(g["BACKUP"]["w"])
    return round_control(size, pressed=pressed, base=(157, 30, 28))


def gma_faceplate(g, keys):
    W, H = int(g["FACE_W"]), int(g["FACE_H"])
    img = plate((W, H), g["CORNER"], GMA_HI, GMA_LO, 4471)
    d = ImageDraw.Draw(img)

    for box in (g["GROUP_TX"], g["GROUP_ICS"]):
        d.rounded_rectangle([S(box["x"]), S(box["y"]),
                             S(box["x"] + box["w"]), S(box["y"] + box["h"])],
                            radius=S(9), outline=(150, 150, 150, 190), width=S(1.3))

    # "CREW" sits in a break in the top of the ICS outline, as the figure shows.
    ics = g["GROUP_ICS"]
    f = font(15)
    cw = d.textlength("CREW", font=f) / SS
    d.rectangle([S(W / 2.0 - cw / 2 - 5), S(ics["y"] - 3),
                 S(W / 2.0 + cw / 2 + 5), S(ics["y"] + 3)], fill=GMA_HI + (255,))
    text_at(d, (W / 2.0, ics["y"]), "CREW", 15, LEGEND_DIM)
    text_at(d, (W / 2.0, ics["y"] + ics["h"] - 12), "ICS   ISOLATION", 14, LEGEND_DIM)

    # PILOT -o- PASS, the isolation state cue printed under the group.
    y = ics["y"] + ics["h"] + 20
    text_at(d, (W / 2.0 - 44, y), "PILOT", 15, LEGEND_DIM)
    text_at(d, (W / 2.0 + 44, y), "PASS", 15, LEGEND_DIM)
    d.ellipse([S(W / 2.0 - 9), S(y - 9), S(W / 2.0 + 9), S(y + 9)],
              outline=LEGEND_DIM + (200,), width=S(1.2))
    d.line([S(W / 2.0 - 22), S(y), S(W / 2.0 - 10), S(y)],
           fill=LEGEND_DIM + (200,), width=S(1.2))
    d.line([S(W / 2.0 + 10), S(y), S(W / 2.0 + 22), S(y)],
           fill=LEGEND_DIM + (200,), width=S(1.2))

    # Knob seat, so the concentric pair sits in a shadow rather than on flat paint.
    ko = g["KNOB_OUTER"]
    kc = (ko["x"] + ko["w"] / 2, ko["y"] + ko["h"] / 2)
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([S(kc[0] - ko["w"] / 2 - 3), S(kc[1] - ko["h"] / 2 - 3),
                                S(kc[0] + ko["w"] / 2 + 3), S(kc[1] + ko["h"] / 2 + 3)],
                               fill=(0, 0, 0, 150))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(S(2.4))))
    d = ImageDraw.Draw(img)

    text_at(d, (44, ko["y"] + ko["h"] + 26), "VOL", 16, LEGEND_DIM)
    text_at(d, (W - 44, ko["y"] + ko["h"] + 26), "SQ", 16, LEGEND_DIM)

    bk = g["BACKUP"]
    text_at(d, (W / 2.0, bk["y"] + bk["h"] + 24), "DISPLAY BACKUP", 15, LEGEND_DIM)

    # Ambient light sensor where a right-hand key would otherwise be.
    if g["PHOTOCELL"]:
        pcx, pcy = g["PHOTOCELL"]
        r = g["PHOTOCELL_R"]
        d.ellipse([S(pcx - r), S(pcy - r), S(pcx + r), S(pcy + r)],
                  fill=(20, 20, 22, 255), outline=(70, 70, 72, 255), width=S(1.0))
    return img.resize((W, H), Image.LANCZOS)


# ---------------------------------------------------------------- previews ---

def tdfm_screen(g):
    """A representative still of the two-line display for the preview."""
    cols, lines = 24, 2
    s = Screen()
    s.text(0, 0, "001 CMD 1   n148.1500Rt")
    s.text(0, 9, "GD1 GUARD 1 n148.0000Rx")
    w = int(g["DISP_W"])
    h = int(g["DISP_H"])
    scale = int(g["DISP_SCALE"])
    return s.render(scale, w // scale, h // scale, LED_OFF_BG, LED_ON)


def build_tdfm():
    name = "cap-fm-tdfm-136b"
    g = load_tdfm()
    res = os.path.join(INSTR, name, "resources")
    os.makedirs(res, exist_ok=True)
    print(name)

    face = tdfm_faceplate(g)
    face.save(os.path.join(res, "faceplate.png"))
    print("   faceplate.png")

    knob = make_knob(int(g["MAIN_ENC"]["w"]))
    knob.save(os.path.join(res, "knob.png"))
    tdfm_toggle_image(g, False).save(os.path.join(res, "toggle_up.png"))
    tdfm_toggle_image(g, True).save(os.path.join(res, "toggle_down.png"))
    tdfm_led_image(g, False).save(os.path.join(res, "led_off.png"))
    tdfm_led_image(g, True).save(os.path.join(res, "led_on.png"))
    print("    knob.png, toggle_up/down.png, led_off/on.png")

    keys = lua_keys(os.path.join(INSTR, name, "lib", "tdfm_panel.lua"), "KEYPAD")
    for e in keys:
        safe = {"#": "hash", "*": "star"}.get(e["id"], e["id"])
        tdfm_key_image(g, e, False).save(os.path.join(res, "key_%s.png" % safe))
        tdfm_key_image(g, e, True).save(os.path.join(res, "key_%s_pressed.png" % safe))
    print("    %d key images" % (len(keys) * 2))

    out = Image.new("RGB", (int(g["FACE_W"]), int(g["FACE_H"])), (20, 20, 20))
    out.paste(face, (0, 0), face)
    out.paste(tdfm_screen(g), (int(g["DISP_X"]), int(g["DISP_Y"])))
    lit = tdfm_led_image(g, True)
    dark = tdfm_led_image(g, False)
    for i, (lx, ly) in enumerate(g["LEDS"]):
        im = lit if i == 0 else dark
        out.paste(im, (int(lx - g["LED_R"]), int(ly - g["LED_R"])), im)
    for spec in (g["MAIN_ENC"], g["GUARD_ENC"]):
        out.paste(knob, (int(spec["x"]), int(spec["y"])), knob)
    up = tdfm_toggle_image(g, False)
    for spec in g["TOGGLE"].values():
        out.paste(up, (int(spec["x"]), int(spec["y"])), up)
    for i, e in enumerate(keys):
        col, row = i % int(g["KEY_COLS"]), i // int(g["KEY_COLS"])
        x = int(g["KEY_X0"] + col * g["KEY_PITCH_X"])
        y = int(g["KEY_Y0"] + row * g["KEY_PITCH_Y"])
        im = tdfm_key_image(g, e, False)
        out.paste(im, (x, y), im)
    out.save(os.path.join(INSTR, name, "preview.png"))
    print("   preview.png")


def build_gma():
    name = "mo-audio-panel-gma1347"
    g = load_gma()
    res = os.path.join(INSTR, name, "resources")
    os.makedirs(res, exist_ok=True)
    print(name)

    keys = lua_keys(os.path.join(INSTR, name, "lib", "gma_panel.lua"), "KEYS")
    face = gma_faceplate(g, keys)
    face.save(os.path.join(res, "faceplate.png"))
    print("   faceplate.png")

    for k in keys:
        gma_key_image(g, k, False).save(os.path.join(res, "key_%s.png" % k["id"]))
        gma_key_image(g, k, True).save(os.path.join(res, "key_%s_pressed.png" % k["id"]))
    print("    %d key images" % (len(keys) * 2))

    gma_ann_image(g, False).save(os.path.join(res, "ann_off.png"))
    gma_ann_image(g, True).save(os.path.join(res, "ann_on.png"))
    knob_o = gma_knob_image(int(g["KNOB_OUTER"]["w"]))
    knob_o.save(os.path.join(res, "knob_outer.png"))
    knob_i = gma_knob_image(int(g["KNOB_INNER"]["w"]), inner=True)
    knob_i.save(os.path.join(res, "knob_inner.png"))
    gma_backup_image(g, False).save(os.path.join(res, "backup.png"))
    gma_backup_image(g, True).save(os.path.join(res, "backup_pressed.png"))
    print("    ann_off/on.png, knob_outer/inner.png, backup.png, backup_pressed.png")

    # Representative live state: the MO on the mission net — COM3 MIC selected,
    # COM1 and COM3 audio up, NAV1 monitored, marker on, CREW isolation.
    LIT = {"com3_mic", "com1", "com3", "nav1", "mkr", "pilot", "coplt"}
    out = Image.new("RGB", (int(g["FACE_W"]), int(g["FACE_H"])), (20, 20, 20))
    out.paste(face, (0, 0), face)
    ann_on, ann_off = gma_ann_image(g, True), gma_ann_image(g, False)
    for k in keys:
        x = int(g["COL_X"][int(k["col"]) - 1])
        y = int(g["ROW_Y"][int(k["row"]) - 1] - g["KEY_H"] / 2)
        im = gma_key_image(g, k, False)
        out.paste(im, (x, y), im)
        a = ann_on if k["id"] in LIT else ann_off
        ax = int(x + (g["KEY_W"] - g["ANN_W"]) / 2)
        out.paste(a, (ax, int(y - g["ANN_DY"])), a)
    out.paste(knob_o, (int(g["KNOB_OUTER"]["x"]), int(g["KNOB_OUTER"]["y"])), knob_o)
    out.paste(knob_i, (int(g["KNOB_INNER"]["x"]), int(g["KNOB_INNER"]["y"])), knob_i)
    bk = gma_backup_image(g, False)
    out.paste(bk, (int(g["BACKUP"]["x"]), int(g["BACKUP"]["y"])), bk)
    out.save(os.path.join(INSTR, name, "preview.png"))
    print("   preview.png")


def build_all():
    build_tdfm()
    build_gma()


if __name__ == "__main__":
    build_all()
