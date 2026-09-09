"""Regenerate every instrument's artwork and preview.

A front-end, not a renderer. Each instrument family owns its own generator, and
each of those parses the geometry out of the Lua the instrument actually uses:

    scripts/make_df_artwork.py      becker-sar-df-517, rhotheta-rt-600
                                    (geometry from lib/dcu.lua)
    scripts/make_panel_artwork.py   cap-fm-tdfm-136b, mo-audio-panel-gma1347
                                    (geometry from lib/tdfm_panel.lua,
                                     lib/gma_panel.lua)

This file used to draw all four previews itself, from a second copy of the
geometry. That copy drifted, and running it would have silently replaced a
regenerated faceplate with the superseded flat design. There is now exactly one
generator per instrument and nothing here to drift.

    python3 scripts/make_previews.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import make_df_artwork
import make_panel_artwork


def main():
    make_df_artwork.build_all()
    make_panel_artwork.build_all()


if __name__ == "__main__":
    main()
