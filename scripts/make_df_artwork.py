"""Generate the DF-head faceplate artwork, control images and previews.

Covers the two heads that share the DCU chassis:

    instruments/becker-sar-df-517/
    instruments/rhotheta-rt-600/

Each gets a layered set of resources:

    faceplate.png            static housing, screws, LCD recess, all legends
    knob.png                 one scalloped corner knob
    button.png / _pressed    the three domed top buttons
    power.png  / _pressed    the ON/OFF button, a different moulding
    preview.png              the whole instrument, assembled from the above

Nothing that moves and nothing the display shows is baked into faceplate.png:
the knobs, the button states and the 128x64 LCD are all separate layers that
Air Manager composites at run time.

GEOMETRY IS NOT DEFINED HERE. It is parsed out of the marked block in
instruments/becker-sar-df-517/lib/dcu.lua, which is what Air Manager uses for
the control hit regions. Artwork and hit regions therefore cannot drift apart,
and if the block ever stops being parseable this script fails instead of
guessing.

Layout authority is the Becker manual, Fig 3-3 on PDF page 29 of
docs/Becker_SARDF517_manual.pdf, rendered to
docs/figures/b517_p29_bearing_controls-29.png. Material and knob appearance
follow the installed-equipment photographs on page 8 of the CAP RT-600 training
deck; those show RT-600 hardware and were not used for Becker labelling.

    python3 scripts/make_df_artwork.py
"""
import math
import os
import random
import re
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SS = 4                                    # supersample factor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTR = os.path.join(ROOT, "instruments")

# B2-8: was two hard-coded Debian paths. Look through the places Liberation
# Sans (or its metric-compatible twin Arimo) lives on common systems, honour an
# explicit override, and fail with a message that says what to do.
_FONT_DIRS = (
    "/usr/share/fonts/truetype/liberation",    # Debian, Ubuntu
    "/usr/share/fonts/truetype/liberation2",
    "/usr/share/fonts/liberation-sans",        # Fedora
    "/usr/share/fonts/liberation",             # Arch
    "/usr/share/fonts/TTF",
    "/usr/share/fonts/truetype/croscore",      # Arimo
    "/Library/Fonts",                          # macOS (if installed)
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
)


def find_font(names, env_var, dirs=_FONT_DIRS):
    """First existing file among dirs x names, or $env_var if it is set."""
    override = os.environ.get(env_var)
    if override:
        if os.path.isfile(override):
            return override
        raise SystemExit(f"{env_var}={override} does not exist")
    tried = []
    for d in dirs:
        for n in names:
            candidate = os.path.join(d, n)
            if os.path.isfile(candidate):
                return candidate
            tried.append(candidate)
    raise SystemExit(
        "No usable font found for the faceplate artwork. Install Liberation Sans "
        "(apt install fonts-liberation / dnf install liberation-sans-fonts) or set "
        f"{env_var} to a .ttf file. Looked for:\n  " + "\n  ".join(tried))


_FONT_CACHE = {}


def font_path(bold=True):
    """Resolved lazily, so importing this module never needs a font."""
    if bold not in _FONT_CACHE:
        _FONT_CACHE[bold] = (
            find_font(("LiberationSans-Bold.ttf", "Arimo-Bold.ttf"), "CAPVSAR_FONT_BOLD") if bold
            else find_font(("LiberationSans-Regular.ttf", "Arimo-Regular.ttf"), "CAPVSAR_FONT_REGULAR"))
    return _FONT_CACHE[bold]
# Exact AM 4.2 built-in font; included here under OFL for reproducible previews.
FONT_DISPLAY = os.path.join(ROOT, "scripts", "fonts", "inconsolata_bold.ttf")
DISPLAY_EM = 5.6
DISPLAY_TOP = -1.0  # font ascender space above visible capitals, in LCD units

# Matte charcoal powder coat. The units photograph very slightly green.
BODY_HI = (57, 59, 58)
BODY = (52, 54, 52)
BODY_LO = (43, 45, 44)
EDGE_DARK = (20, 22, 20)
EDGE_LIGHT = (73, 76, 74)
LEGEND = (211, 213, 207)
LEGEND_DIM = (196, 198, 192)
SCREW_METAL = (150, 152, 148)
SCREW_DARK = (74, 76, 73)
GLASS_RIM = (16, 18, 16)
LCD_OFF = (46, 51, 32)                    # unlit transflective margin

# LCD ink / backlight, matching lib/lcd.lua
INK = (26, 37, 96)
LIT = (198, 217, 107)


# --------------------------------------------------------------- geometry ----

def load_geometry():
    """Parse the marked geometry block out of lib/dcu.lua."""
    path = os.path.join(INSTR, "becker-sar-df-517", "lib", "dcu.lua")
    src = open(path, encoding="utf-8").read()
    m = re.search(r"=+ GEOMETRY \(parsed by make_df_artwork\.py\) =+(.*?)"
                  r"=+ END GEOMETRY", src, re.S)
    if not m:
        sys.exit("make_df_artwork: geometry block not found in %s" % path)
    block = m.group(1)

    def scalar(name):
        # Lua multiple assignment ("M.A, M.B = 1, 2") would make a bare
        # "M.NAME =" search return the wrong number, so require the name to be
        # the whole left-hand side rather than quietly mis-parsing.
        mm = re.search(r"(?m)^\s*M\.%s\s*=\s*(-?\d+(?:\.\d+)?)\s*(?:--.*)?$"
                       % name, block)
        if not mm:
            sys.exit("make_df_artwork: M.%s missing from the geometry block, or "
                     "it is part of a multiple assignment this parser cannot "
                     "read unambiguously" % name)
        v = float(mm.group(1))
        return int(v) if v == int(v) else v

    def rect(expr, name):
        mm = re.search(r"\b%s\s*=\s*\{([^}]*)\}" % name, expr)
        if not mm:
            sys.exit("make_df_artwork: rect %s missing from the geometry block" % name)
        body = mm.group(1)
        out = {}
        for k in "xywh":
            kk = re.search(r"\b%s\s*=\s*(-?\d+(?:\.\d+)?)" % k, body)
            if not kk:
                sys.exit("make_df_artwork: %s.%s missing" % (name, k))
            out[k] = float(kk.group(1))
        return out

    g = {k: scalar(k) for k in ("FACE", "LCD_SCALE", "LCD_W", "LCD_H", "LCD_X",
                                "LCD_Y", "SCREW_R", "INSET_R", "CHAMFER")}
    g["GLASS"] = rect(block, "M.GLASS")
    g["RECESS"] = rect(block, "M.RECESS")

    knob_block = re.search(r"M\.KNOB\s*=\s*\{(.*?)\n\}", block, re.S)
    btn_block = re.search(r"M\.BTN\s*=\s*\{(.*?)\n\}", block, re.S)
    if not knob_block or not btn_block:
        sys.exit("make_df_artwork: M.KNOB / M.BTN block not found")
    g["KNOB"] = {n: rect(knob_block.group(1), n)
                 for n in ("sql", "page", "vol", "freq")}
    g["BTN"] = {n: rect(btn_block.group(1), n) for n in ("clr", "store", "rep")}
    g["POWER"] = rect(block, "M.POWER")

    sm = re.search(r"M\.SCREWS\s*=\s*\{(.*?)\}\s*$", block, re.M)
    if not sm:
        sys.exit("make_df_artwork: M.SCREWS not found")
    g["SCREWS"] = [(float(a), float(b)) for a, b in
                   re.findall(r"\{\s*(-?\d+)\s*,\s*(-?\d+)\s*\}", sm.group(1))]
    if len(g["SCREWS"]) != 4:
        sys.exit("make_df_artwork: expected 4 screws, parsed %d" % len(g["SCREWS"]))

    # Sanity: the LCD active area must be the framebuffer times the scale, and
    # must sit inside the glass, which must sit inside the recess.
    if g["LCD_W"] != 128 * g["LCD_SCALE"] or g["LCD_H"] != 64 * g["LCD_SCALE"]:
        sys.exit("make_df_artwork: LCD_W/H do not match 128x64 * LCD_SCALE")
    gl, rc = g["GLASS"], g["RECESS"]
    if not (rc["x"] <= gl["x"] and gl["x"] <= g["LCD_X"]
            and g["LCD_X"] + g["LCD_W"] <= gl["x"] + gl["w"] <= rc["x"] + rc["w"]):
        sys.exit("make_df_artwork: LCD / glass / recess are not nested")
    return g


G = load_geometry()
FACE = G["FACE"]


def S(v):
    """Instrument units -> supersampled pixels."""
    return int(round(v * SS))


# ------------------------------------------------------------ draw helpers ---

def font(size, bold=True):
    return ImageFont.truetype(font_path(bold), S(size))


def text_at(d, xy, s, size, fill=LEGEND, anchor="mm", bold=True, spacing=0):
    """Smooth printed legend. spacing letterspaces, as the BECKER wordmark is."""
    f = font(size, bold)
    if not spacing:
        d.text((S(xy[0]), S(xy[1])), s, font=f, fill=fill, anchor=anchor)
        return
    widths = [d.textlength(c, font=f) for c in s]
    total = sum(widths) + S(spacing) * (len(s) - 1)
    x = S(xy[0]) - total / 2 if anchor[0] == "m" else S(xy[0])
    for c, w in zip(s, widths):
        d.text((x, S(xy[1])), c, font=f, fill=fill, anchor="l" + anchor[1])
        x += w + S(spacing)


def arc_text(img, s, cx, cy, radius, a_start, a_end, size, fill=LEGEND):
    """Lettering curved around a knob, as the SQL and Page legends are.

    Angles are compass degrees: 0 up, 90 right. Each glyph is rendered on its
    own and rotated to sit tangent to the arc.
    """
    f = font(size)
    n = len(s)
    for i, ch in enumerate(s):
        t = 0.5 if n == 1 else i / (n - 1.0)
        ang = a_start + (a_end - a_start) * t
        cell = Image.new("RGBA", (S(size) * 3, S(size) * 3), (0, 0, 0, 0))
        cd = ImageDraw.Draw(cell)
        cd.text((cell.width / 2, cell.height / 2), ch, font=f, fill=fill, anchor="mm")
        # Fig 3-3 sets both words with their tops facing the knob they label,
        # so the glyph up-vector points inward, not outward.
        cell = cell.rotate(-(ang + 180), resample=Image.BICUBIC)
        px = S(cx) + S(radius) * math.sin(math.radians(ang))
        py = S(cy) - S(radius) * math.cos(math.radians(ang))
        img.alpha_composite(cell, (int(px - cell.width / 2), int(py - cell.height / 2)))


def polar(cx, cy, r, ang):
    """Compass degrees to a point."""
    return (cx + r * math.sin(math.radians(ang)),
            cy - r * math.cos(math.radians(ang)))


def arrow(d, cx, cy, ang, length, width, fill=LEGEND, head=None):
    """A straight arrow centred at (cx, cy) pointing along a compass heading."""
    head = head or length * 0.55
    tail = polar(cx, cy, -length / 2, ang)
    tip = polar(cx, cy, length / 2, ang)
    d.line([S(tail[0]), S(tail[1]), S(tip[0]), S(tip[1])], fill=fill,
           width=S(width))
    left = polar(tip[0], tip[1], head, ang + 145)
    right = polar(tip[0], tip[1], head, ang - 145)
    d.polygon([(S(tip[0]), S(tip[1])), (S(left[0]), S(left[1])),
               (S(right[0]), S(right[1]))], fill=fill)


def octagon(size, chamfer):
    c = chamfer
    return [(c, 0), (size - c, 0), (size, c), (size, size - c),
            (size - c, size), (c, size), (0, size - c), (0, c)]


def noise_layer(w, h, amount, seed):
    """Sub-pixel coating grain, with no thresholded patches or broad mottling."""
    rnd = random.Random(seed)
    grain = Image.new("L", (max(1, w // 2), max(1, h // 2)))
    grain.putdata([128 + rnd.randint(-amount, amount)
                   for _ in range(grain.width * grain.height)])
    return grain.resize((w, h), Image.BILINEAR)


def coat(body, seed):
    grain = noise_layer(*body.size, 4, seed).convert("RGB")
    return ImageChops.add(body.convert("RGB"), grain, offset=-128)


def round_control(units, lobes=0, pressed=False, base=(38, 40, 39)):
    """Matte moulded control: continuous lighting, a narrow bevel and grip.

    Light arrives from upper left. The flat top and scalloped perimeter follow
    the CAP equipment photo; no stationary index stripe is invented.
    """
    px = S(units)
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    pixels = img.load()
    c, radius = px / 2, px * .465
    for y in range(px):
        for x in range(px):
            dx, dy = (x + .5 - c) / radius, (y + .5 - c) / radius
            r = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)
            rim = .964 + .036 * math.cos(lobes * angle) if lobes else 1
            if r > rim:
                # A tight contact shadow, entirely inside the original bounds.
                if math.hypot(dx, dy - .025) < rim + .018:
                    pixels[x, y] = (9, 10, 10, 180)
                continue
            u = r / rim
            light = -(dx + dy) / math.sqrt(2)
            if u > .975:
                value = -19 + 8 * light
            elif u > .80:
                # Shaped side wall, with small highlights on the flutes.
                flute = 4 * math.sin(lobes * angle) if lobes else 0
                value = -12 + 16 * light + flute
            elif u > .74:
                value = 1 + 14 * light - 5 * (u - .74) / .06
            else:
                value = 3 + 5 * light - 4 * r * r
            if pressed:
                value -= 10
            pixels[x, y] = tuple(max(0, min(255, int(v + value))) for v in base) + (255,)
    return img.resize((units, units), Image.LANCZOS)


def make_knob(units):
    return round_control(units, lobes=12)


def make_button(units, pressed=False):
    return round_control(units, pressed=pressed, base=(35, 37, 36))


def make_power(units, pressed=False):
    return round_control(units, pressed=pressed, base=(28, 30, 31))


def rubber_key(w, h, pressed=False, radius=6):
    """Shallow rubber keycap with a recessed seat and a restrained edge bevel."""
    img = Image.new("RGBA", (S(w), S(h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = [S(1), S(1), S(w - 1), S(h - 1)]
    d.rounded_rectangle(box, radius=S(radius), fill=(10, 12, 12, 255))
    # Nested sub-pixel contours produce a continuous rolled edge, not a gloss blob.
    for step in range(S(3), S(5.5)):
        inset = step / SS
        t = (inset - 3) / 2.5
        level = int((51 - 18 * t) if not pressed else (24 + 3 * t))
        d.rounded_rectangle([step, step, S(w) - step, S(h) - step],
                            radius=S(max(2, radius - inset / 2)),
                            fill=(level, level + 1, level + 1, 255))
    d.line([S(6), S(h - 3), S(w - 6), S(h - 3)], fill=(14, 15, 15, 255), width=S(.7))
    return img


def metal_screw(d, cx, cy, r, slotted=True, angle=0):
    """Countersunk steel fastener with a satin face and a recessed slot."""
    x, y, rp = S(cx), S(cy), S(r)
    d.ellipse([x-rp-S(.9), y-rp-S(.9), x+rp+S(.9), y+rp+S(.9)],
              fill=(19, 21, 21, 255))
    d.ellipse([x-rp, y-rp, x+rp, y+rp], fill=(60, 63, 62, 255))
    d.arc([x-rp, y-rp, x+rp, y+rp], 185, 310,
          fill=(161, 164, 159, 255), width=S(.6))
    face_r = rp * .83
    for row in range(-int(face_r), int(face_r) + 1):
        half = math.sqrt(max(0, face_r**2 - row**2))
        v = int(116 - 23 * row / face_r)
        d.line([x-half, y+row, x+half, y+row], fill=(v, v+3, v, 255))
    for a in ([angle] if slotted else [angle, angle+90]):
        dx, dy = rp*.64*math.cos(math.radians(a)), rp*.64*math.sin(math.radians(a))
        d.line([x-dx, y-dy+S(.5), x+dx, y+dy+S(.5)],
               fill=(165, 169, 163, 255), width=S(1.7))
        d.line([x-dx, y-dy, x+dx, y+dy],
               fill=(27, 29, 29, 255), width=S(1.35))


# --------------------------------------------------------------- faceplate ---

def make_faceplate(model):
    """The static housing: everything printed, nothing that moves."""
    px = S(FACE)
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    plate = [(S(x), S(y)) for x, y in octagon(FACE, G["CHAMFER"])]

    # Body, with a gentle top-to-bottom fall-off and powder-coat grain.
    grad = Image.new("RGB", (1, px))
    for y in range(px):
        t = y / float(px)
        grad.putpixel((0, y), tuple(int(BODY_HI[i] + (BODY_LO[i] - BODY_HI[i]) * t)
                                    for i in range(3)))
    body = grad.resize((px, px))
    body = coat(body, 1701)
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).polygon(plate, fill=255)
    img.paste(body.convert("RGBA"), (0, 0), mask)

    # Edge: light along the top-left run, dark along the bottom-right.
    d.line(plate[7:1:-1] if False else [plate[0], plate[1]], fill=EDGE_LIGHT + (150,), width=S(1.6))
    d.line([plate[7], plate[0]], fill=EDGE_LIGHT + (110,), width=S(1.6))
    d.line([plate[6], plate[7]], fill=EDGE_LIGHT + (90,), width=S(1.6))
    d.line([plate[2], plate[3]], fill=EDGE_DARK + (170,), width=S(1.6))
    d.line([plate[3], plate[4]], fill=EDGE_DARK + (190,), width=S(1.6))
    d.line([plate[4], plate[5]], fill=EDGE_DARK + (190,), width=S(1.6))
    d.line([plate[1], plate[2]], fill=EDGE_DARK + (150,), width=S(1.6))
    d.line([plate[5], plate[6]], fill=EDGE_DARK + (120,), width=S(1.6))

    # The dark circular front casting is distinct from the mounting flange.
    cx = cy = FACE / 2.0
    R = G["INSET_R"]
    inset_mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(inset_mask).ellipse([S(cx-R), S(cy-R), S(cx+R), S(cy+R)], fill=255)
    inset = Image.eval(body, lambda v: max(0, v - 7))
    img.paste(inset, (0, 0), inset_mask)
    d.ellipse([S(cx-R), S(cy-R), S(cx+R), S(cy+R)],
              outline=(24, 26, 25, 255), width=S(1.0))
    d.arc([S(cx-R+1), S(cy-R+1), S(cx+R-1), S(cy+R-1)],
          185, 310, fill=(61, 63, 61, 255), width=S(.6))

    # LCD recess: a raised surround with the window sunk into it.
    rc, gl = G["RECESS"], G["GLASS"]
    d.rounded_rectangle([S(rc["x"]), S(rc["y"]), S(rc["x"] + rc["w"]), S(rc["y"] + rc["h"])],
                        radius=S(14), fill=(41, 43, 41, 255),
                        outline=(28, 30, 28, 255), width=S(1.2))
    d.line([S(rc["x"] + 14), S(rc["y"] + .8),
            S(rc["x"] + rc["w"] - 14), S(rc["y"] + .8)],
           fill=(64, 66, 63, 255), width=S(.7))
    # inner shadow of the sunk window
    shade = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.rounded_rectangle([S(gl["x"] - 5), S(gl["y"] - 5),
                          S(gl["x"] + gl["w"] + 5), S(gl["y"] + gl["h"] + 5)],
                         radius=S(9), fill=(0, 0, 0, 190))
    shade = shade.filter(ImageFilter.GaussianBlur(S(2.4)))
    img.alpha_composite(shade)
    d.rounded_rectangle([S(gl["x"] - 3), S(gl["y"] - 3),
                         S(gl["x"] + gl["w"] + 3), S(gl["y"] + gl["h"] + 3)],
                        radius=S(7), fill=GLASS_RIM + (255,))
    # Unlit transflective margin. The live canvas covers the active dot area.
    d.rounded_rectangle([S(gl["x"]), S(gl["y"]),
                         S(gl["x"] + gl["w"]), S(gl["y"] + gl["h"])],
                        radius=S(4), fill=LCD_OFF + (255,))

    # Mounting screws.
    for sx, sy in G["SCREWS"]:
        angle = 55 if (sx < FACE / 2) == (sy < FACE / 2) else -55
        metal_screw(d, sx, sy, G["SCREW_R"], angle=angle)

    draw_legends(img, d, model)
    return img.resize((FACE, FACE), Image.LANCZOS)


def draw_legends(img, d, model):
    """Every silk-screened marking, in smooth printed lettering.

    Positions follow Fig 3-3. The two heads differ only in the button
    sub-legends and the identification block.
    """
    K = G["KNOB"]
    B = G["BTN"]

    def centre(spec):
        return spec["x"] + spec["w"] / 2.0, spec["y"] + spec["h"] / 2.0

    # --- Button legends, primary name under each key -------------------------
    for key, label in (("clr", "Clr"), ("store", "Store"), ("rep", "Rep")):
        bx, by = centre(B[key])
        text_at(d, (bx, B[key]["y"] + B[key]["h"] + 21), label, 21)

    # --- Button alternates. The RT-600's keys are dual function and the bezel
    # --- is silk-screened with both; the 517's are not, and only Rep doubles
    # --- as DIM.
    if model["alt_keys"]:
        for key, label in (("clr", "F1"), ("store", "F2")):
            bx, _ = centre(B[key])
            y = B[key]["y"] + B[key]["h"] + 42
            f = font(17)
            w = d.textlength(label, font=f) / SS
            d.rounded_rectangle([S(bx - w / 2 - 5), S(y - 10), S(bx + w / 2 + 5), S(y + 10)],
                                radius=S(3), outline=LEGEND_DIM + (200,), width=S(1.1))
            text_at(d, (bx, y), label, 17, LEGEND_DIM)

    # --- DIM, linked from Rep across to the Page knob ------------------------
    rep_x, _ = centre(B["rep"])
    dim_y = B["rep"]["y"] + B["rep"]["h"] + (66 if model["alt_keys"] else 50)
    dim_x = rep_x + 16
    text_at(d, (dim_x, dim_y), "DIM", 16, LEGEND_DIM)
    f = font(16)
    half = d.textlength("DIM", font=f) / SS / 2
    for sgn in (-1, 1):
        x0 = dim_x + sgn * (half + 5)
        x1 = dim_x + sgn * (half + 15)
        d.line([S(x0), S(dim_y + 1), S(x1), S(dim_y - 7)], fill=LEGEND_DIM + (220,),
               width=S(1.5))

    # --- SQL and Page, curved around the two upper knobs ---------------------
    sx, sy = centre(K["sql"])
    arc_text(img, "SQL", sx, sy, 61, 158, 124, 20)
    arrow(d, *polar(sx, sy, 66, 88), ang=0, length=22, width=2.2)
    arrow(d, *polar(sx, sy, 64, 176), ang=270, length=22, width=2.2)

    px_, py_ = centre(K["page"])
    arc_text(img, "Page", px_, py_, 61, 245, 200, 20)
    arrow(d, *polar(px_, py_, 66, 272), ang=0, length=22, width=2.2)
    arrow(d, *polar(px_, py_, 64, 184), ang=90, length=22, width=2.2)

    # --- Rotation sense around the two lower knobs ---------------------------
    # Fig 3-3 marks each lower knob with an arc carrying an arrow at one end,
    # a plus toward the other and tick strokes between.
    for name, mirror in (("vol", False), ("freq", True)):
        kx, ky = centre(K[name])
        def a(deg):
            return (360 - deg) % 360 if mirror else deg
        arrow(d, *polar(kx, ky, 62, a(6)), ang=a(276), length=20, width=2.2)
        arrow(d, *polar(kx, ky, 64, a(100)), ang=a(170), length=20, width=2.2)
        for deg in (34, 52):
            p0 = polar(kx, ky, 58, a(deg))
            p1 = polar(kx, ky, 70, a(deg))
            d.line([S(p0[0]), S(p0[1]), S(p1[0]), S(p1[1])],
                   fill=LEGEND + (230,), width=S(1.8))
        px2, py2 = polar(kx, ky, 66, a(72))
        text_at(d, (px2, py2), "+", 24)

    # --- Identification block and ON/OFF -------------------------------------
    ident = model["ident"]
    mid = FACE / 2.0
    rule_y = ident["rule_y"]

    text_at(d, (ident["brand_x"], rule_y), ident["brand"], ident["brand_size"],
            LEGEND, anchor="mm", bold=ident["brand_bold"])
    f = font(ident["brand_size"], ident["brand_bold"])
    brand_w = d.textlength(ident["brand"], font=f) / SS
    rule_x0 = ident["brand_x"] + brand_w / 2 + 8
    rule_x1 = ident["rule_x1"]
    d.line([S(rule_x0), S(rule_y), S(rule_x1), S(rule_y)], fill=LEGEND + (235,),
           width=S(1.7))
    # The angled end strokes that close the lockup on the real bezel.
    d.line([S(rule_x0), S(rule_y), S(rule_x0 - 9), S(rule_y - 11)],
           fill=LEGEND + (235,), width=S(1.7))
    d.line([S(rule_x1), S(rule_y), S(rule_x1 + 9), S(rule_y - 11)],
           fill=LEGEND + (235,), width=S(1.7))

    text_at(d, (ident["top_x"], rule_y - 14), ident["top"], 19)
    if ident["bottom_spacing"]:
        text_at(d, (ident["top_x"], rule_y + 15), ident["bottom"], 19,
                spacing=ident["bottom_spacing"])
    else:
        text_at(d, (ident["top_x"], rule_y + 15), ident["bottom"], 17)

    pw = G["POWER"]
    text_at(d, (ident["onoff_x"], pw["y"] - 22), "ON/OFF", 21)


# ------------------------------------------------------------------- LCD -----
#
# A still of the live display for preview.png only. The instrument itself draws
# the LCD in Lua; this mirrors that layout closely enough to make the preview
# representative, and both sides read the same geometry constants above.

class Screen:
    """Logical display graphics plus smooth fixed-cell text, matching lcd.lua."""

    def __init__(self):
        self.dots = set()
        self.text_runs = []

    def rect(self, x, y, w, h):
        for j in range(int(h)):
            for i in range(int(w)):
                self.dots.add((int(x) + i, int(y) + j))

    def frame(self, x, y, w, h):
        self.rect(x, y, w, 1); self.rect(x, y + h - 1, w, 1)
        self.rect(x, y, 1, h); self.rect(x + w - 1, y, 1, h)

    def line(self, x0, y0, x1, y1):
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(n + 1):
            t = i / float(n)
            self.dots.add((int(round(x0 + (x1 - x0) * t)),
                           int(round(y0 + (y1 - y0) * t))))

    def circle(self, cx, cy, r, fill=False):
        for a in range(0, 360, 6 if not fill else 3):
            x = cx + r * math.cos(math.radians(a))
            y = cy + r * math.sin(math.radians(a))
            self.dots.add((int(round(x)), int(round(y))))
        if fill:
            for j in range(int(-r), int(r) + 1):
                for i in range(int(-r), int(r) + 1):
                    if i * i + j * j <= r * r:
                        self.dots.add((cx + i, cy + j))

    def marker(self, cx, cy, filled):
        """Rim marker: solid for the averaged bearing, hollow for a spread
        extreme. Hand-plotted because a rasterised r=2 circle is a cross."""
        ring = [(-1, -2), (0, -2), (1, -2), (2, -1), (2, 0), (2, 1),
                (1, 2), (0, 2), (-1, 2), (-2, 1), (-2, 0), (-2, -1)]
        for dx, dy in ring:
            self.dots.add((cx + dx, cy + dy))
        if filled:
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    self.dots.add((cx + dx, cy + dy))

    def text(self, x, y, s, m=1):
        self.text_runs.append((x, y, s, m, False))
        return x + len(s) * 4 * m

    def text_w(self, s, m=1):
        return (len(s) * 4 - 1) * m if s else 0

    def inverted(self, x, y, s):
        w = self.text_w(s) + 3
        self.rect(x, y - 1, w, 7)
        self.text_runs.append((x + 1, y + 1, s, 1, True))
        return x + w

    def render(self, scale, width=128, height=64, background=LIT, ink=INK):
        # Text is rasterised at output resolution, not the 128x64 logical grid.
        k = scale * SS
        img = Image.new("RGB", (width * k, height * k), background)
        d = ImageDraw.Draw(img)
        for x, y in self.dots:
            if 0 <= x < width and 0 <= y < height:
                d.rectangle([x*k, y*k, (x+1)*k-1, (y+1)*k-1], fill=ink)
        for x, y, text, m, inverse in self.text_runs:
            f = ImageFont.truetype(FONT_DISPLAY, round(DISPLAY_EM * k * m))
            for i, ch in enumerate(text):
                # AM _txt uses the top of the font's ascender box. The 4-unit
                # advance is explicit on both sides (AM 4.2 has no spacing style).
                d.text(((x + i*4*m + 1.5*m)*k, (y + DISPLAY_TOP*m)*k),
                       ch, font=f, anchor="ma", fill=background if inverse else ink)
        return img.resize((width * scale, height * scale), Image.LANCZOS)


def polar_lcd(cx, cy, r, deg):
    a = math.radians(deg - 90)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def rose(s, cx, cy, r, bearing, spread, ticks=True, big=True):
    for deg in range(0, 360, 6):
        x, y = polar_lcd(cx, cy, r, deg)
        s.rect(int(x), int(y), 1, 1)
    if ticks and r >= 24:
        for deg in range(0, 360, 15):
            long = (deg % 45 == 0)
            x1, y1 = polar_lcd(cx, cy, r - (6 if long else 5), deg)
            x2, y2 = polar_lcd(cx, cy, r - 3, deg)
            s.line(x1, y1, x2, y2)
    for deg in range(0, 360, 90):
        x1, y1 = polar_lcd(cx, cy, r - 2, deg)
        x2, y2 = polar_lcd(cx, cy, r + 1, deg)
        s.line(x1, y1, x2, y2)
    s.text(cx - 1, cy - r + 12, "0")
    s.text(cx - 5, cy + r - 13, "180")
    if spread:
        for side in (-1, 1):
            x, y = polar_lcd(cx, cy, r, bearing + side * spread / 2.0)
            s.marker(int(x), int(y), False)

    t = "<%03d>" % bearing
    m = 2 if big else 1
    hw = s.text_w(t, m) / 2.0 + 2
    hh = 5 * m / 2.0 + 2
    # Start the pointer clear of the bearing block. Fig 3-3 runs the line from
    # the edge of the number out to the rim, never across the digits.
    ux, uy = math.sin(math.radians(bearing)), -math.cos(math.radians(bearing))
    t0 = r - 4.0
    if abs(ux) > 1e-6:
        t0 = min(t0, hw / abs(ux))
    if abs(uy) > 1e-6:
        t0 = min(t0, hh / abs(uy))
    s.line(cx + ux * t0, cy + uy * t0, cx + ux * (r - 3), cy + uy * (r - 3))
    mx, my = polar_lcd(cx, cy, r, bearing)
    s.marker(int(mx), int(my), True)
    s.text(cx - s.text_w(t, m) / 2, cy - 2 * m, t, m)


def bar(s, x, y, h, pct, sq):
    s.frame(x, y, 5, h)
    filled = int(pct / 100.0 * (h - 2) + 0.5)
    if filled:
        s.rect(x + 1, y + h - 1 - filled, 3, filled)
    for i in range(11):
        ty = y + h - 1 - int(i / 10.0 * (h - 2) + 0.5)
        s.rect(x + 5, ty, 3 if i % 5 == 0 else 2, 1)
    if sq is None:
        s.text(x + 9, y + h - 6, "A")
    else:
        sy = y + h - 1 - int(sq * (h - 2) + 0.5)
        s.rect(x + 5, sy, 5, 1)
        s.rect(x + 9, sy - 1, 3, 3)


def screen_517():
    """Page 1, laid out as Fig 3-3 shows it."""
    s = Screen()
    s.text(10, 4, "100")
    bar(s, 4, 11, 44, 62, 0.25)
    rose(s, 51, 30, 27, 337, 31)
    s.text(94, 4, "PAGE")
    s.inverted(118, 4, "1")
    for i in range(6):
        dx = 94 + i * 4
        if i == 0:
            s.rect(dx, 12, 3, 3)
        else:
            s.rect(dx + 1, 13, 1, 1)
    s.text(94, 17, "OFS:+000")
    s.text(94, 26, "MOUNT:")
    s.rect(121, 26, 1, 4); s.rect(119, 30, 5, 1)
    s.text(94, 35, "LS:00:00")
    s.frame(88, 42, 40, 14)
    s.text(90, 44, "SEA-BAND")
    s.text(90, 50, "CHNL.(16)")
    x = s.inverted(2, 57, "60")
    s.text(x + 2, 58, "VOL")
    fw = s.text_w("156.800") + 3
    s.text(127 - fw - 17, 58, "FREQ")
    s.inverted(127 - fw, 57, "156.800")
    return s


def screen_600():
    """RT-600 DF page: softkey strip along the top, per manual Fig 21."""
    s = Screen()
    s.inverted(2, 1, "SCAN")
    s.inverted(34, 1, "DECODE")
    s.inverted(96, 1, "DF")
    s.text(113, 2, "FRQ")
    s.text(2, 11, "48%")
    bar(s, 3, 19, 30, 48, None)
    rose(s, 53, 31, 22, 18, 9, ticks=False)
    s.text(84, 11, "00:00 LS")
    s.text(84, 22, "SARSAT")
    s.text(84, 31, "031-037")      # the selected CPSAR group
    s.text(84, 40, "CH D-F")
    x = s.inverted(1, 49, "30")
    s.text(x + 2, 50, "VOL")
    fw = s.text_w("406.025") + 3
    s.text(125 - fw - 15, 50, "FRQ")
    s.inverted(125 - fw, 49, "406.025")
    return s


# ------------------------------------------------------------------ build ----

MODELS = {
    "becker-sar-df-517": {
        "alt_keys": False,
        "screen": screen_517,
        "ident": {
            "brand": "Rhotheta", "brand_x": 190, "brand_size": 18,
            "brand_bold": True, "rule_y": 408, "rule_x1": 392,
            "top": "SAR-DF 517", "top_x": 336,
            "bottom": "BECKER", "bottom_spacing": 2.4,
            "onoff_x": 212,
        },
    },
    "rhotheta-rt-600": {
        "alt_keys": True,
        "screen": screen_600,
        "ident": {
            "brand": "RHOTHETA", "brand_x": 190, "brand_size": 17,
            "brand_bold": True, "rule_y": 408, "rule_x1": 392,
            "top": "SAR-DF 517", "top_x": 336,
            "bottom": "RT-600.DCU", "bottom_spacing": 0,
            "onoff_x": 212,
        },
    },
}


def compose_preview(face_img, screen):
    """The whole instrument, assembled from exactly the layers Air Manager
    stacks at run time: faceplate, LCD canvas, then the controls."""
    out = Image.new("RGB", (FACE, FACE), (24, 25, 24))
    out.paste(face_img, (0, 0), face_img)

    lcd_img = screen.render(int(G["LCD_SCALE"]))
    out.paste(lcd_img, (int(G["LCD_X"]), int(G["LCD_Y"])))

    knob = make_knob(int(G["KNOB"]["sql"]["w"]))
    for spec in G["KNOB"].values():
        out.paste(knob, (int(spec["x"]), int(spec["y"])), knob)
    btn = make_button(int(G["BTN"]["clr"]["w"]))
    for spec in G["BTN"].values():
        out.paste(btn, (int(spec["x"]), int(spec["y"])), btn)
    pw = make_power(int(G["POWER"]["w"]))
    out.paste(pw, (int(G["POWER"]["x"]), int(G["POWER"]["y"])), pw)
    return out


def build(name):
    model = MODELS[name]
    res = os.path.join(INSTR, name, "resources")
    os.makedirs(res, exist_ok=True)
    print(name)

    face = make_faceplate(model)
    face.save(os.path.join(res, "faceplate.png"))
    print("   faceplate.png")

    make_knob(int(G["KNOB"]["sql"]["w"])).save(os.path.join(res, "knob.png"))
    bw = int(G["BTN"]["clr"]["w"])
    make_button(bw).save(os.path.join(res, "button.png"))
    make_button(bw, pressed=True).save(os.path.join(res, "button_pressed.png"))
    pwv = int(G["POWER"]["w"])
    make_power(pwv).save(os.path.join(res, "power.png"))
    make_power(pwv, pressed=True).save(os.path.join(res, "power_pressed.png"))
    for f in ("knob.png", "button.png", "button_pressed.png",
              "power.png", "power_pressed.png"):
        print("  ", f)

    preview = compose_preview(face, model["screen"]())
    preview.save(os.path.join(INSTR, name, "preview.png"))
    print("   preview.png")


def build_all():
    for name in MODELS:
        build(name)


if __name__ == "__main__":
    build_all()
