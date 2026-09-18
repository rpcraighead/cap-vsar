#!/usr/bin/env python3
"""Generate preview.png for the CAP Mission Equipment Circuit Breaker Panel.

Mirrors the canvas drawn by logic.lua in its default state (all breakers IN)
so panels/cap-c182t-mo-station/generate_assets.py can composite a real
preview instead of a "stock instrument" placeholder.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT_PATH = HERE.parents[1] / "scripts" / "fonts" / "inconsolata_bold.ttf"

W, H = 520, 150
BREAKERS = ["DF", "FM RADIO", "AUDIO/MFD"]
COL_W = W / len(BREAKERS)
BTN_W, BTN_H = 64, 60
BTN_Y = 46


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
    draw_centered(draw, "MISSION EQUIP - CIRCUIT BREAKERS", W / 2, 6, 14, "#c7d0dc")

    for i, label in enumerate(BREAKERS):
        x = (i * COL_W) + (COL_W - BTN_W) / 2
        cx = x + BTN_W / 2

        draw.rectangle([x, BTN_Y, x + BTN_W, BTN_Y + BTN_H], fill="#8a1f1f")
        draw.rectangle([x, BTN_Y, x + BTN_W, BTN_Y + BTN_H], fill="#3a3f4a", outline="#565d6b", width=2)

        draw_centered(draw, label, cx, BTN_Y + BTN_H + 10, 10, "#c7d0dc")
        draw_centered(draw, "IN", cx, BTN_Y + BTN_H + 24, 9, "#8fd19e")

    img.save(HERE / "preview.png")


if __name__ == "__main__":
    main()
