#!/usr/bin/env python3
"""Generate preview.png for the CAP Mission Equipment Master Switch.

Mirrors the canvas drawn by logic.lua in its default state (guard closed,
switch ON) so panels/cap-c182t-mo-station/generate_assets.py can composite a
real preview instead of a "stock instrument" placeholder.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT_PATH = HERE.parents[1] / "scripts" / "fonts" / "inconsolata_bold.ttf"

W, H = 300, 150
SWITCH_X, SWITCH_Y, SWITCH_W, SWITCH_H = 110, 74, 80, 56
GUARD_CLOSED_Y, GUARD_CLOSED_H = 68, 68


def font(size):
    return ImageFont.truetype(str(FONT_PATH), size)


def draw_centered(draw, text, cx, y, size, color):
    f = font(size)
    bbox = draw.textbbox((0, 0), text, font=f)
    draw.text((cx - (bbox[2] - bbox[0]) / 2, y), text, font=f, fill=color)


def main():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W - 1, H - 1], fill="#1c1f26")
    draw.rectangle([2, 2, W - 3, H - 3], outline="#3a3f4a", width=2)

    draw_centered(draw, "MISSION EQUIP", W / 2, 8, 16, "#c7d0dc")
    draw_centered(draw, "MASTER", W / 2, 26, 13, "#8b93a1")

    draw.rectangle([SWITCH_X, SWITCH_Y, SWITCH_X + SWITCH_W, SWITCH_Y + SWITCH_H],
                   fill="#2a2e37", outline="#4a5060", width=2)

    lever_h = SWITCH_H / 2  # ON: lever occupies the top half
    draw.rectangle([SWITCH_X + 4, SWITCH_Y, SWITCH_X + SWITCH_W - 4, SWITCH_Y + lever_h - 4],
                   fill="#2f9e44")

    draw_centered(draw, "ON", W / 2, SWITCH_Y + SWITCH_H + 8, 14, "#f2f4f7")

    draw.rectangle([SWITCH_X - 8, GUARD_CLOSED_Y, SWITCH_X + SWITCH_W + 8, GUARD_CLOSED_Y + GUARD_CLOSED_H],
                   outline="#b3261e", width=3)
    draw_centered(draw, "LIFT GUARD", W / 2, GUARD_CLOSED_Y + GUARD_CLOSED_H + 22, 11, "#b3261e")

    img.save(HERE / "preview.png")


if __name__ == "__main__":
    main()
