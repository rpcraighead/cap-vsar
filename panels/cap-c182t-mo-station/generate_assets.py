#!/usr/bin/env python3
"""
Generate background and preview images for the CAP C182T Mission Observer panel.
Composites real instrument previews onto a 1920x1080 panel canvas.
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
PANEL_COLOR = (28, 31, 38, 255)       # Matte charcoal cockpit panel (#1c1f26)
BORDER_COLOR = (45, 52, 64, 255)      # Subtle panel framing bevel

# Instrument bounding boxes
INSTRUMENTS_LAYOUT1 = [
    # (name, uuid, x, y, width, height)
    ("MFD", "0b852ee1-6006-4e2b-9cdf-e397b3f16ab1", 40, 100, 1100, 715),
    ("GMA1347", "1337420b-7420-4843-80eb-9d10c57a97d1", 1155, 100, 121, 715),
    ("Becker517", "faefb90d-5704-48c7-8deb-c683d94b4eb3", 1360, 100, 460, 460),
    ("TDFM136B", "26df5da8-8ce7-4255-bb0e-520453134609", 1310, 580, 560, 294),
]

INSTRUMENTS_LAYOUT2 = [
    ("MFD", "0b852ee1-6006-4e2b-9cdf-e397b3f16ab1", 40, 100, 1100, 715),
    ("GMA1347", "1337420b-7420-4843-80eb-9d10c57a97d1", 1155, 100, 121, 715),
    ("RT600", "d783d409-9bfa-49f2-ad5d-883af29848d6", 1360, 100, 460, 460),
    ("TDFM136B", "26df5da8-8ce7-4255-bb0e-520453134609", 1310, 580, 560, 294),
]

ROOT = Path(__file__).resolve().parents[2]
INST_BASE = Path.home() / "Air Manager/instruments/OPEN_DIRECTORY"
LOCAL_INSTRUMENTS = {
    "Becker517": "becker-sar-df-517", "RT600": "rhotheta-rt-600",
    "TDFM136B": "cap-fm-tdfm-136b", "GMA1347": "mo-audio-panel-gma1347",
}

def create_background():
    """Create cockpit panel background with transparent screen cutout for MFD popout/streaming."""
    bg = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), PANEL_COLOR)
    draw = ImageDraw.Draw(bg)

    # Top header bar / visor line
    draw.rectangle([0, 0, CANVAS_WIDTH, 40], fill=(20, 22, 28, 255))
    draw.line([0, 40, CANVAS_WIDTH, 40], fill=(45, 52, 64, 255), width=2)

    # Bottom edge line
    draw.line([0, CANVAS_HEIGHT - 30, CANVAS_WIDTH, CANVAS_HEIGHT - 30], fill=(45, 52, 64, 255), width=2)
    draw.rectangle([0, CANVAS_HEIGHT - 30, CANVAS_WIDTH, CANVAS_HEIGHT], fill=(20, 22, 28, 255))

    # Instrument mount outlines (subtle recess borders)
    # 1. MFD & Audio panel mount recess
    draw.rectangle([35, 95, 1281, 820], outline=BORDER_COLOR, width=2)
    # 2. Mission avionics stack recess
    draw.rectangle([1300, 95, 1880, 880], outline=BORDER_COLOR, width=2)

    # Cutout transparent area for G1000 MFD active screen:
    # 40 + 1100*(410/2880) = 196, 100 + 715*(94/1870) = 136
    # width = 1100*(2060/2880) = 787, height = 715*(1548/1870) = 592
    cutout_x0 = 196
    cutout_y0 = 136
    cutout_x1 = cutout_x0 + 787
    cutout_y1 = cutout_y0 + 592
    draw.rectangle([cutout_x0, cutout_y0, cutout_x1, cutout_y1], fill=(0, 0, 0, 0))

    return bg

def create_preview(instrument_list, subtitle="MISSION OBSERVER STATION"):
    """Render a full composite preview with all instruments."""
    preview = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), PANEL_COLOR)
    draw = ImageDraw.Draw(preview)

    # Top header bar
    draw.rectangle([0, 0, CANVAS_WIDTH, 40], fill=(20, 22, 28, 255))
    draw.line([0, 40, CANVAS_WIDTH, 40], fill=(45, 52, 64, 255), width=2)
    draw.line([0, CANVAS_HEIGHT - 30, CANVAS_WIDTH, CANVAS_HEIGHT - 30], fill=(45, 52, 64, 255), width=2)
    draw.rectangle([0, CANVAS_HEIGHT - 30, CANVAS_WIDTH, CANVAS_HEIGHT], fill=(20, 22, 28, 255))

    # Mount recesses
    draw.rectangle([35, 95, 1281, 820], outline=BORDER_COLOR, width=2)
    draw.rectangle([1300, 95, 1880, 880], outline=BORDER_COLOR, width=2)

    # Header text
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = font_title

    draw.text((45, 10), "CIVIL AIR PATROL - CESSNA 182T NAV III", fill=(210, 215, 225, 255), font=font_title)
    draw.text((CANVAS_WIDTH - 380, 12), subtitle, fill=(160, 175, 195, 255), font=font_sub)

    # Render each instrument
    for name, uuid, x, y, w, h in instrument_list:
        # Always use the current source artwork for our instruments. Only the
        # stock MFD preview comes from the Air Manager installation.
        inst_prev_path = (ROOT / "instruments" / LOCAL_INSTRUMENTS[name] / "preview.png"
                          if name in LOCAL_INSTRUMENTS else INST_BASE / uuid / "preview.png")
        if os.path.exists(inst_prev_path):
            inst_img = Image.open(inst_prev_path).convert("RGBA")
            inst_resized = inst_img.resize((w, h), Image.Resampling.LANCZOS)
            preview.paste(inst_resized, (x, y), inst_resized)
        else:
            print(f"Warning: could not find preview for {name} ({uuid}) at {inst_prev_path}")

    return preview

def main():
    repo_panel_dir = str(Path(__file__).resolve().parent)
    layout1_dir = os.path.join(repo_panel_dir, "layouts", "e1c8e710-5646-49e1-931f-4aeeb51e4491")
    layout2_dir = os.path.join(repo_panel_dir, "layouts", "e2c8e710-5646-49e1-931f-4aeeb51e4492")

    for d in [layout1_dir, layout2_dir]:
        os.makedirs(d, exist_ok=True)

    print("Generating background...")
    bg = create_background()
    bg.save(os.path.join(layout1_dir, "background.png"), "PNG")
    bg.save(os.path.join(layout2_dir, "background.png"), "PNG")

    print("Generating Layout 1 preview (Becker 517)...")
    prev1 = create_preview(INSTRUMENTS_LAYOUT1, "MISSION OBSERVER - BECKER SAR-DF 517")
    prev1.save(os.path.join(layout1_dir, "preview.png"), "PNG")
    # Save as root panel preview as well
    prev1.save(os.path.join(repo_panel_dir, "preview.png"), "PNG")

    print("Generating Layout 2 preview (RT-600)...")
    prev2 = create_preview(INSTRUMENTS_LAYOUT2, "MISSION OBSERVER - RHOTHETA RT-600")
    prev2.save(os.path.join(layout2_dir, "preview.png"), "PNG")

    print("All panel assets generated successfully in repo!")

if __name__ == "__main__":
    main()

