"""Check the DF-head faceplate artwork against the geometry the Lua actually uses.

    python3 tests/test_faceplate.py

The faceplate is a baked image and the controls are hit regions declared in
lib/dcu.lua. Nothing at run time notices if the two disagree — the instrument
just ends up with a knob that does not sit on its own artwork. These checks are
the part of that which can be verified without Air Manager:

  * the geometry block still parses, and the artwork script reads it
  * no two control hit regions overlap, and none covers the live LCD window
  * every image the Lua names exists, at the size the geometry expects, and
    every shipped resource is actually referenced
  * the two heads keep byte-identical shared libraries but distinct branding —
    the Becker must never grow the RT-600's F1/F2 keys or its name

It does not check that the artwork *looks* right; that needs eyes on
preview.png, and ultimately Air Manager.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

HEADS = ("becker-sar-df-517", "rhotheta-rt-600")
FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("   " + detail if detail else ""))
    if not cond:
        FAILED.append(name)


def rects(g):
    """Every control hit region as (label, x, y, w, h)."""
    out = []
    for k, v in g["KNOB"].items():
        out.append(("knob:" + k, v["x"], v["y"], v["w"], v["h"]))
    for k, v in g["BTN"].items():
        out.append(("btn:" + k, v["x"], v["y"], v["w"], v["h"]))
    p = g["POWER"]
    out.append(("power", p["x"], p["y"], p["w"], p["h"]))
    return out


def overlap(a, b):
    return not (a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]
                or a[2] + a[4] <= b[2] or b[2] + b[4] <= a[2])


print("\n== geometry ==")
import make_df_artwork as A          # parses lib/dcu.lua on import, exits on failure

G = A.G
check("lib/dcu.lua geometry block parses", G["FACE"] > 0, "FACE=%d" % G["FACE"])
check("LCD active area is 128x64 dots", G["LCD_W"] == 128 * G["LCD_SCALE"]
      and G["LCD_H"] == 64 * G["LCD_SCALE"],
      "%dx%d at scale %d" % (G["LCD_W"], G["LCD_H"], G["LCD_SCALE"]))

print("\n== control hit regions ==")
R = rects(G)
check("all controls inside the face",
      all(0 <= x and 0 <= y and x + w <= G["FACE"] and y + h <= G["FACE"]
          for _, x, y, w, h in R))

clashes = [(a[0], b[0]) for i, a in enumerate(R) for b in R[i + 1:] if overlap(a, b)]
check("no two controls overlap", not clashes, str(clashes))

lcd_rect = ("lcd", G["LCD_X"], G["LCD_Y"], G["LCD_W"], G["LCD_H"])
on_lcd = [a[0] for a in R if overlap(a, lcd_rect)]
check("no control covers the live LCD window", not on_lcd, str(on_lcd))

glass = G["GLASS"]
check("LCD sits inside the glass, glass inside the recess",
      glass["x"] <= G["LCD_X"] and G["LCD_X"] + G["LCD_W"] <= glass["x"] + glass["w"]
      and G["RECESS"]["x"] <= glass["x"])

check("screws clear the knobs",
      all(min(((sx - (k["x"] + k["w"] / 2)) ** 2 + (sy - (k["y"] + k["h"] / 2)) ** 2) ** 0.5
              - k["w"] / 2 - G["SCREW_R"] for k in G["KNOB"].values()) > 0
          for sx, sy in G["SCREWS"]))

print("\n== resources ==")
from PIL import Image

EXPECT = {
    "faceplate.png": (G["FACE"], G["FACE"]),
    "knob.png": (G["KNOB"]["sql"]["w"], G["KNOB"]["sql"]["h"]),
    "button.png": (G["BTN"]["clr"]["w"], G["BTN"]["clr"]["h"]),
    "button_pressed.png": (G["BTN"]["clr"]["w"], G["BTN"]["clr"]["h"]),
    "power.png": (G["POWER"]["w"], G["POWER"]["h"]),
    "power_pressed.png": (G["POWER"]["w"], G["POWER"]["h"]),
}

for head in HEADS:
    d = os.path.join(ROOT, "instruments", head)
    lua = ""
    for f in ("logic.lua",):
        lua += open(os.path.join(d, f), encoding="utf-8").read()
    for f in sorted(os.listdir(os.path.join(d, "lib"))):
        lua += open(os.path.join(d, "lib", f), encoding="utf-8").read()
    named = set(re.findall(r'"([a-z0-9_]+\.png)"', lua))
    shipped = {f for f in os.listdir(os.path.join(d, "resources"))
               if f.endswith(".png")}

    check("%s: every image the Lua names is shipped" % head,
          not (named - shipped), str(sorted(named - shipped)))
    check("%s: no orphan resources" % head,
          not (shipped - named), str(sorted(shipped - named)))
    check("%s: images are the size the geometry expects" % head,
          all(Image.open(os.path.join(d, "resources", n)).size
              == (int(EXPECT[n][0]), int(EXPECT[n][1]))
              for n in named if n in EXPECT))
    pv = Image.open(os.path.join(d, "preview.png"))
    check("%s: preview.png matches the face size" % head,
          pv.size == (int(G["FACE"]), int(G["FACE"])), str(pv.size))
    info = open(os.path.join(d, "info.xml"), encoding="utf-8").read()
    check("%s: info.xml preferred size matches the face" % head,
          ("<prefWidth>%d</prefWidth>" % G["FACE"]) in info
          and ("<prefHeight>%d</prefHeight>" % G["FACE"]) in info)

print("\n== shared libraries and branding ==")
SHARED_DIR = os.path.join(ROOT, "instruments", "_shared")

# lcd.lua is shared across Becker, RT-600, and TDFM
shared_lcd = open(os.path.join(SHARED_DIR, "lib", "lcd.lua"), encoding="utf-8").read()
for inst in ("becker-sar-df-517", "rhotheta-rt-600", "cap-fm-tdfm-136b"):
    inst_lcd = open(os.path.join(ROOT, "instruments", inst, "lib", "lcd.lua"), encoding="utf-8").read()
    check("%s: lib/lcd.lua matches shared source" % inst, inst_lcd == shared_lcd)

# cap_df.lua, cap_df_audio.lua, dcu.lua are shared across the two DF heads
for lib in ("cap_df.lua", "cap_df_audio.lua", "dcu.lua"):
    shared_src = open(os.path.join(SHARED_DIR, "lib", lib), encoding="utf-8").read()
    for head in HEADS:
        inst_src = open(os.path.join(ROOT, "instruments", head, "lib", lib), encoding="utf-8").read()
        check("%s: lib/%s matches shared source" % (head, lib), inst_src == shared_src)

# cap_power.lua (the bus-power gate) is shared by all four powered instruments,
# knob_push.lua by the two with push knobs. The gate lives in one place: no
# logic.lua carries its own copy of the voltage threshold any more.
for lib, users in (("cap_power.lua", ("becker-sar-df-517", "rhotheta-rt-600",
                                      "cap-fm-tdfm-136b", "mo-audio-panel-gma1347")),
                   ("knob_push.lua", ("cap-fm-tdfm-136b", "mo-audio-panel-gma1347"))):
    shared_src = open(os.path.join(SHARED_DIR, "lib", lib), encoding="utf-8").read()
    for inst in users:
        inst_src = open(os.path.join(ROOT, "instruments", inst, "lib", lib), encoding="utf-8").read()
        check("%s: lib/%s matches shared source" % (inst, lib), inst_src == shared_src)
for inst in ("becker-sar-df-517", "rhotheta-rt-600", "cap-fm-tdfm-136b", "mo-audio-panel-gma1347"):
    logic_src = open(os.path.join(ROOT, "instruments", inst, "logic.lua"), encoding="utf-8").read()
    check("%s: bus-power gate comes from lib/cap_power.lua" % inst,
          "cap_power.watch(" in logic_src and "MIN_BUS_VOLTS" not in logic_src)

# Four shared WAV resources across the two DF heads
for wav in ("elt_analog_clean.wav", "elt_analog_df.wav", "elt_noise.wav", "elt_406_burst.wav"):
    shared_wav = open(os.path.join(SHARED_DIR, "resources", wav), "rb").read()
    for head in HEADS:
        inst_wav = open(os.path.join(ROOT, "instruments", head, "resources", wav), "rb").read()
        check("%s: resources/%s matches shared source" % (head, wav), inst_wav == shared_wav)

becker = open(os.path.join(ROOT, "instruments", HEADS[0], "logic.lua"), encoding="utf-8").read()
# The Becker's own file may say "RT-600" in prose about the sibling instrument,
# but it must not carry the RT-600's key legends as data.
check("Becker declares head type 0", "df.set_head_type(0)" in becker)
check("RT-600 declares head type 1",
      "df.set_head_type(1)" in open(os.path.join(ROOT, "instruments", HEADS[1],
                                                 "logic.lua"), encoding="utf-8").read())
bm = A.MODELS[HEADS[0]]
check("Becker faceplate has no F1/F2 alternates", bm["alt_keys"] is False)
check("Becker identification carries no RT-600 name",
      not any("RT-600" in str(v) for v in bm["ident"].values()),
      str(bm["ident"]["bottom"]))
check("RT-600 faceplate keeps its F1/F2 alternates",
      A.MODELS[HEADS[1]]["alt_keys"] is True)
check("RT-600 identification keeps its own name",
      "RT-600" in A.MODELS[HEADS[1]]["ident"]["bottom"],
      A.MODELS[HEADS[1]]["ident"]["bottom"])

print("\n== MO station: geometry vs. artwork ==")
import make_panel_artwork as P

TDFM = P.load_tdfm()
GMA = P.load_gma()

# --- TDFM -------------------------------------------------------------------
tk = P.lua_keys(os.path.join(ROOT, "instruments", "cap-fm-tdfm-136b",
                             "lib", "tdfm_panel.lua"), "KEYPAD")
check("TDFM: geometry block parses", TDFM["FACE_W"] > 0,
      "%dx%d" % (TDFM["FACE_W"], TDFM["FACE_H"]))
check("TDFM: face matches Figure 1-1's 1.916 aspect",
      abs(TDFM["FACE_W"] / float(TDFM["FACE_H"]) - 1.916) < 0.02,
      "%.3f" % (TDFM["FACE_W"] / float(TDFM["FACE_H"])))
check("TDFM: display is 24 characters by 2 lines",
      TDFM["DISP_W"] == (24 * 4 - 1) * TDFM["DISP_SCALE"]
      and TDFM["DISP_H"] == (9 + 5) * TDFM["DISP_SCALE"],
      "%dx%d at scale %d" % (TDFM["DISP_W"], TDFM["DISP_H"], TDFM["DISP_SCALE"]))
check("TDFM: keypad table has 12 keys", len(tk) == 12, str(len(tk)))

tr = []
for n, spec in (("main_enc", TDFM["MAIN_ENC"]), ("guard_enc", TDFM["GUARD_ENC"])):
    tr.append((n, spec["x"], spec["y"], spec["w"], spec["h"]))
for n, spec in TDFM["TOGGLE"].items():
    tr.append(("toggle:" + n, spec["x"], spec["y"], spec["w"], spec["h"]))
for i in range(len(tk)):
    col, row = i % int(TDFM["KEY_COLS"]), i // int(TDFM["KEY_COLS"])
    tr.append(("key:" + tk[i]["id"],
               TDFM["KEY_X0"] + col * TDFM["KEY_PITCH_X"],
               TDFM["KEY_Y0"] + row * TDFM["KEY_PITCH_Y"],
               TDFM["KEY_W"], TDFM["KEY_H"]))
clash = [(a[0], b[0]) for i, a in enumerate(tr) for b in tr[i + 1:] if overlap(a, b)]
check("TDFM: no two controls overlap", not clash, str(clash))
check("TDFM: all controls inside the plate",
      all(0 <= x and 0 <= y and x + w <= TDFM["FACE_W"] and y + h <= TDFM["FACE_H"]
          for _, x, y, w, h in tr))
disp_rect = ("display", TDFM["DISP_X"], TDFM["DISP_Y"], TDFM["DISP_W"], TDFM["DISP_H"])
check("TDFM: no control covers the display",
      not [a[0] for a in tr if overlap(a, disp_rect)])
win = TDFM["WINDOW"]
check("TDFM: display sits inside its window",
      win["x"] <= TDFM["DISP_X"]
      and TDFM["DISP_X"] + TDFM["DISP_W"] <= win["x"] + win["w"]
      and win["y"] <= TDFM["DISP_Y"]
      and TDFM["DISP_Y"] + TDFM["DISP_H"] <= win["y"] + win["h"])
check("TDFM: both squelch LEDs sit inside the window bezel",
      all(win["x"] <= lx - TDFM["LED_R"] and lx + TDFM["LED_R"] <= win["x"] + win["w"]
          and win["y"] <= ly - TDFM["LED_R"] and ly + TDFM["LED_R"] <= win["y"] + win["h"]
          for lx, ly in TDFM["LEDS"]))
check("TDFM: LEDs are clear of the character matrix",
      all(lx + TDFM["LED_R"] <= TDFM["DISP_X"] for lx, _ in TDFM["LEDS"]))

# --- GMA --------------------------------------------------------------------
gk = P.lua_keys(os.path.join(ROOT, "instruments", "mo-audio-panel-gma1347",
                             "lib", "gma_panel.lua"), "KEYS")
check("GMA: geometry block parses", GMA["FACE_W"] > 0,
      "%dx%d" % (GMA["FACE_W"], GMA["FACE_H"]))
# 6A.2: "1.3 inches in width and 7.70 inches in height".
check("GMA: face matches the 1.3 x 7.70 in panel the guide specifies",
      abs(GMA["FACE_H"] / float(GMA["FACE_W"]) - 7.70 / 1.3) < 0.03,
      "1 : %.3f" % (GMA["FACE_H"] / float(GMA["FACE_W"])))
check("GMA: key table has 21 keys", len(gk) == 21, str(len(gk)))
check("GMA: row 9 right column is the photocell, not a key",
      not any(int(k["row"]) == 9 and int(k["col"]) == 2 for k in gk))

grects, arects = [], []
for k in gk:
    x = GMA["COL_X"][int(k["col"]) - 1]
    y = GMA["ROW_Y"][int(k["row"]) - 1] - GMA["KEY_H"] / 2
    grects.append(("key:" + k["id"], x, y, GMA["KEY_W"], GMA["KEY_H"]))
    arects.append(("ann:" + k["id"], x + (GMA["KEY_W"] - GMA["ANN_W"]) / 2,
                   y - GMA["ANN_DY"], GMA["ANN_W"], GMA["ANN_H"]))
gall = grects + arects + [
    ("backup", GMA["BACKUP"]["x"], GMA["BACKUP"]["y"],
     GMA["BACKUP"]["w"], GMA["BACKUP"]["h"])]
clash = [(a[0], b[0]) for i, a in enumerate(gall) for b in gall[i + 1:] if overlap(a, b)]
check("GMA: no key, annunciator or button overlaps another", not clash, str(clash))
check("GMA: everything inside the plate",
      all(0 <= x and 0 <= y and x + w <= GMA["FACE_W"] and y + h <= GMA["FACE_H"]
          for _, x, y, w, h in gall))
check("GMA: every annunciator sits above its own key",
      all(a[2] + a[4] <= g[2] and abs((a[1] + a[3] / 2) - (g[1] + g[3] / 2)) < 0.51
          for a, g in zip(arects, grects)))
# The concentric knob is the one place two dials share space, by design.
ki, ko = GMA["KNOB_INNER"], GMA["KNOB_OUTER"]
check("GMA: the inner knob sits wholly inside the outer ring",
      ko["x"] <= ki["x"] and ko["y"] <= ki["y"]
      and ki["x"] + ki["w"] <= ko["x"] + ko["w"]
      and ki["y"] + ki["h"] <= ko["y"] + ko["h"]
      and ki["w"] < ko["w"])
check("GMA: the knob pair clears every key and the backup button",
      not any(overlap(("knob", ko["x"], ko["y"], ko["w"], ko["h"]), a) for a in gall))
check("GMA: the ICS group encloses the PILOT and COPLT keys",
      all(GMA["GROUP_ICS"]["x"] <= r[1]
          and r[1] + r[3] <= GMA["GROUP_ICS"]["x"] + GMA["GROUP_ICS"]["w"]
          and GMA["GROUP_ICS"]["y"] <= r[2]
          and r[2] + r[4] <= GMA["GROUP_ICS"]["y"] + GMA["GROUP_ICS"]["h"]
          for r in grects if r[0].split(":")[1] in ("pilot", "coplt")))

# --- resources for both -----------------------------------------------------
PANEL_EXPECT = {
    "cap-fm-tdfm-136b": dict(
        [("faceplate.png", (TDFM["FACE_W"], TDFM["FACE_H"])),
         ("knob.png", (TDFM["MAIN_ENC"]["w"], TDFM["MAIN_ENC"]["h"])),
         ("led_off.png", (TDFM["LED_R"] * 2, TDFM["LED_R"] * 2)),
         ("led_on.png", (TDFM["LED_R"] * 2, TDFM["LED_R"] * 2))]
        + [("key_%s.png" % {"#": "hash", "*": "star"}.get(k["id"], k["id"]),
            (TDFM["KEY_W"], TDFM["KEY_H"])) for k in tk]),
    "mo-audio-panel-gma1347": dict(
        [("faceplate.png", (GMA["FACE_W"], GMA["FACE_H"])),
         ("ann_on.png", (GMA["ANN_W"], GMA["ANN_H"])),
         ("ann_off.png", (GMA["ANN_W"], GMA["ANN_H"])),
         ("knob_outer.png", (ko["w"], ko["h"])),
         ("knob_inner.png", (ki["w"], ki["h"])),
         ("backup.png", (GMA["BACKUP"]["w"], GMA["BACKUP"]["h"]))]
        + [("key_%s.png" % k["id"], (GMA["KEY_W"], GMA["KEY_H"])) for k in gk]),
}
FACES = {"cap-fm-tdfm-136b": (TDFM["FACE_W"], TDFM["FACE_H"]),
         "mo-audio-panel-gma1347": (GMA["FACE_W"], GMA["FACE_H"])}

for head, expect in PANEL_EXPECT.items():
    d = os.path.join(ROOT, "instruments", head)
    shipped = set(os.listdir(os.path.join(d, "resources")))
    missing = sorted(set(expect) - shipped)
    check("%s: every expected image is shipped" % head, not missing, str(missing))
    bad = [n for n, sz in expect.items()
           if n in shipped and Image.open(os.path.join(d, "resources", n)).size
           != (int(sz[0]), int(sz[1]))]
    check("%s: images are the size the geometry expects" % head, not bad, str(bad))
    fw, fh = FACES[head]
    pv = Image.open(os.path.join(d, "preview.png"))
    check("%s: preview.png matches the face size" % head,
          pv.size == (int(fw), int(fh)), str(pv.size))
    info = open(os.path.join(d, "info.xml"), encoding="utf-8").read()
    check("%s: info.xml preferred size matches the face" % head,
          ("<prefWidth>%d</prefWidth>" % fw) in info
          and ("<prefHeight>%d</prefHeight>" % fh) in info)

print("\n== every instrument names only resources it ships ==")
ALL = ["becker-sar-df-517", "rhotheta-rt-600",
       "cap-fm-tdfm-136b", "mo-audio-panel-gma1347"]
for head in ALL:
    d = os.path.join(ROOT, "instruments", head)
    lua = open(os.path.join(d, "logic.lua"), encoding="utf-8").read()
    for f in sorted(os.listdir(os.path.join(d, "lib"))):
        lua += open(os.path.join(d, "lib", f), encoding="utf-8").read()
    named = set(re.findall(r'"([a-z0-9_]+\.(?:png|wav))"', lua))
    shipped = set(os.listdir(os.path.join(d, "resources")))
    check("%s: no resource named but missing" % head,
          not (named - shipped), str(sorted(named - shipped)))
    # Keys are named by a helper at run time, so an unreferenced file is only
    # an orphan if nothing in the folder follows the key naming convention.
    orphans = sorted(f for f in shipped - named
                     if not f.startswith("key_")
                     and f not in ("faceplate.png",))
    check("%s: no orphan resources" % head, not orphans, str(orphans))

print("\n== Air Manager library loading contract ==")
for head in ALL:
    d = os.path.join(ROOT, "instruments", head)
    lua = open(os.path.join(d, "logic.lua"), encoding="utf-8").read()
    libs = [f[:-4] for f in os.listdir(os.path.join(d, "lib"))]
    all_lua = lua
    unpublished = []
    for name in libs:
        source = open(os.path.join(d, "lib", name + ".lua"),
                      encoding="utf-8").read()
        all_lua += source
        # A lib publishes a global table (name = {}) or, for a single helper
        # such as knob_push, a global function (function name(...)).
        if not re.search(r'(?m)^(?:' + re.escape(name) + r'\s*=\s*\{\}|function\s+'
                         + re.escape(name) + r'\s*\()', source):
            unpublished.append(name)
    check("%s: lib tables are globally published" % head,
          not unpublished, str(sorted(unpublished)))
    check("%s: does not call unavailable require()" % head,
          not re.search(r'(?m)^\s*(?:local\s+[^-\n=]+?=\s*)?require\s*\(', all_lua))

print("\n== Air Manager 4.2 runtime contracts ==")
for head in ("becker-sar-df-517", "rhotheta-rt-600", "cap-fm-tdfm-136b"):
    d = os.path.join(ROOT, "instruments", head)
    logic = open(os.path.join(d, "logic.lua"), encoding="utf-8").read()
    lcd_src = open(os.path.join(d, "lib", "lcd.lua"), encoding="utf-8").read()
    # Called directly by every head (I-2 removed the pcall the two DF heads
    # once wrapped it in). canvas_id and the real draw function must reach
    # canvas_draw.
    check("%s: canvas redraw supplies its callback" % head,
          bool(re.search(r'canvas_draw[\s,(]*canvas_id\s*,\s*draw_', logic)))
    check("%s: canvas text uses the AM 4.2 built-in font" % head,
          'M.FONT_NAME = "inconsolata_bold.ttf"' in lcd_src
          and '_txt(ch, style' in lcd_src and 'spacing:' not in lcd_src)

tdfm_logic = open(os.path.join(ROOT, "instruments", "cap-fm-tdfm-136b",
                               "logic.lua"), encoding="utf-8").read()
check("TDFM: switches apply position plus direction",
      tdfm_logic.count("requested_switch_position(position, direction)") == 4)
check("TDFM: every toggle retains and updates its switch ID",
      all((name + " = switch_add") in tdfm_logic
          and ("switch_set_position(" + name) in tdfm_logic
          for name in ("mn_gd_switch", "guard_switch", "power_switch")))

gma_logic = open(os.path.join(ROOT, "instruments", "mo-audio-panel-gma1347",
                              "logic.lua"), encoding="utf-8").read()
check("GMA: VOL and SQ mode annunciators are live nodes",
      'txt_add("VOL"' in gma_logic and 'txt_add("SQ"' in gma_logic
      and "visible(mode_vol" in gma_logic and "visible(mode_sq" in gma_logic)

print("\n== LCD text stays on the 128-dot panel ==")
# Catches the class of bug that is invisible until something is actually drawn:
# a status row placed too far right loses its last glyph off the edge. Only
# literal strings at literal coordinates can be checked statically, but that is
# most of them, and it is exactly where the mistakes happen.
CALL = re.compile(r'\b(?:lcd\.)?text(_right)?\(ctx,\s*(-?\d+)\s*,\s*(-?\d+)\s*,'
                  r'\s*"([^"]*)"(?:\s*,\s*[^,)]+)?(?:\s*,\s*(\d+))?\s*\)')
for head in HEADS:
    src = open(os.path.join(ROOT, "instruments", head, "logic.lua"),
               encoding="utf-8").read()
    over = []
    for right, x, y, txt, mult in CALL.findall(src):
        x, y, m = int(x), int(y), int(mult or 1)
        w = (len(txt) * 4 - 1) * m if txt else 0
        # text_right ends at x; text starts at x.
        x0, x1 = (x - w, x) if right else (x, x + w)
        if x0 < 0 or x1 > 127 or y + 5 * m > 64:
            over.append("%r spans %d..%d, y %d" % (txt, x0, x1, y))
    check("%s: no literal LCD text runs off the panel" % head, not over,
          "; ".join(over))

print("\n== DF receiver tables match the manuals ==")
b517 = open(os.path.join(ROOT, "instruments", "becker-sar-df-517",
                         "logic.lua"), encoding="utf-8").read()
rt600 = open(os.path.join(ROOT, "instruments", "rhotheta-rt-600",
                          "logic.lua"), encoding="utf-8").read()

# Becker §1.3.1: four fixed emergency channels and four freely adjustable
# training channels. The fifth training row is the SCAN knob position and must
# carry no range, or the page-6 value knob compares a number with nil.
train = re.search(r"local training_freqs = \{(.*?)\n\}", b517, re.S).group(1)
rows = [r for r in re.findall(r"\{([^{}]*(?:\{[^}]*\})?[^{}]*)\}", train)
        if "hz =" in r]
adjustable = [r for r in rows if "min =" in r]
check("Becker: four freely adjustable training channels",
      len(adjustable) == 4, str(len(adjustable)))
check("Becker: the SCAN training row carries no range",
      all("min =" not in r for r in rows if 'label = "SCAN"' in r))
check("Becker: page 6 lists only the adjustable rows",
      "for i = 1, TRAINING_EDITABLE do" in b517)
# Rows run 12, 22, 32, 42 with a 5-dot glyph; the status line sits at 55.
check("Becker: page-6 rows clear the status line",
      12 + (len(adjustable) - 1) * 10 + 5 < 55,
      "last row ends at %d" % (12 + (len(adjustable) - 1) * 10 + 5))
check("Becker: the value knob refuses a row with no range",
      "if f.min and hz >= f.min and hz <= f.max then" in b517)

# Becker §3.3.1(5): bearing is not possible while the 3 kHz tone is suppressed.
check("Becker: suppressing the 3 kHz tone stops the bearing",
      "local function bearing_live()" in b517
      and "df.state.valid and not st.tone_suppressed" in b517)

print("\n== DF receiver audio ==")
for head, logic in (("Becker", b517), ("RT-600", rt600)):
    directory = "becker-sar-df-517" if head == "Becker" else "rhotheta-rt-600"
    audio = open(os.path.join(ROOT, "instruments", directory, "lib",
                              "cap_df_audio.lua"), encoding="utf-8").read()
    check("%s: audio is gated by instantaneous rx_open" % head,
          "df.state.rx_open" in logic and "not rx_open" in audio)
    check("%s: volume knob drives receiver gain" % head,
          "sync_audio()" in logic and "sound_volume(sounds[wanted], gain)" in audio)
    check("%s: analog audio loops and 406 plays once" % head,
          'sound_loop(sounds[wanted])' in audio
          and 'sound_play(sounds[wanted])' in audio)
    check("%s: power-off stops audio" % head,
          "df_audio.stop()" in logic)

check("Becker: STORE selects the clean analog recording",
      "st.tone_suppressed" in b517
      and 'wanted = "analog_clean"' in open(
          os.path.join(ROOT, "instruments", "becker-sar-df-517", "lib",
                       "cap_df_audio.lua"), encoding="utf-8").read())

# RT-600 §2.2.3: seven CPSAR groups spanning the 19-channel grid.
groups = re.findall(r"\{\s*lo = (\d+),\s*hi = (\d+),\s*label = \"([^\"]+)\"",
                    rt600)
check("RT-600: seven CPSAR groups", len(groups) == 7, str(len(groups)))
chans = set()
for lo, hi, _ in groups:
    lo, hi = int(lo), int(hi)
    check_ok = (hi - lo) % 3000 == 0
    for hz in range(lo, hi + 1, 3000):
        chans.add(hz)
check("RT-600: the groups cover 19 distinct channels", len(chans) == 19,
      str(len(chans)))
check("RT-600: the grid runs 406.022 to 406.076 inclusive",
      min(chans) == 406022000 and max(chans) == 406076000,
      "%.3f .. %.3f" % (min(chans) / 1e6, max(chans) / 1e6))
check("RT-600: every channel sits on the 3 kHz grid",
      all((hz - 406022000) % 3000 == 0 for hz in chans))
check("RT-600: groups do not overlap",
      sum(int((int(hi) - int(lo)) / 3000) + 1 for lo, hi, _ in groups) == 19)
check("RT-600: a group selection tells the engine its span",
      "df.set_span_hz(current_freq().span or 0)" in rt600)
check("Becker: declares itself a single-channel receiver",
      "df.set_span_hz(0)" in b517)

print("\n" + ("ALL PASS" if not FAILED else "FAILURES: " + ", ".join(FAILED)))


def test_faceplate_checks_pass():
    """The checks above run at import time; this reports them to pytest."""
    assert not FAILED, "FAILURES: " + ", ".join(FAILED)


if __name__ == "__main__":
    sys.exit(1 if FAILED else 0)
