# Instrument visual refresh — 2026-09-08

The four custom instruments retain their established geometry and interaction
regions. This pass changes materials, control artwork, printed legends, and
live display typography. The source generators are authoritative; editing
only a generated PNG would be overwritten on the next build.

## Reference basis

> **D-5:** the two figures below are page extracts from third-party documents.
> They are no longer tracked in this repository - they stay on disk locally,
> like the manuals themselves, and `docs/SOURCES.md` records the public URL each
> came from so you can extract your own. The links resolve only in a working
> tree that has them; a fresh clone will not render them, and that is deliberate.


- [CAP installed-equipment photograph](figures/capdeck_p8-08.png): matte finish,
  shallow dark controls and scalloped grips. This photograph depicts RT-600
  hardware; Becker labeling continues to follow the Becker manual.
- [Becker Fig. 3-3](figures/b517_p29_bearing_controls-29.png): control placement,
  printed legends and identification.
- [RHOTHETA front panel](figures/rt600_p08_front_panel-08.png): circular front
  casting, small pushbuttons, labels, and blue-on-yellow-green display.
- [Technisonic Fig. 1-1](figures/tdfm_p11_front_panel-11.png): keypad, toggles,
  connectors and two-line display geometry.
- [Garmin Fig. 6A.2.1](figures/gma1347_panel-05.png): charcoal face, dark rubber
  keys, concentric knobs and red display-backup button.

Colors and lighting are an artistic interpretation of these references, not
measured material properties. The smooth font is an intentional readability
improvement over the previous coarse 3×5 approximation, not a claim to reproduce
the original hardware glyph ROM.

## Display implementation

The DF heads and TDFM share `lib/lcd.lua`. Text now uses built-in
`inconsolata_bold.ttf` at 5.6 em units per logical cell; each column advances
four logical units. Characters retain their case. The top offset of −1 unit
allows the font's ascender space while retaining room for bottom-row descenders.
Existing display field widths and the TDFM's nine-unit row pitch are preserved.
Graphics such as the DF compass dot ring remain on the original logical grid.

[Sim Innovations' canvas text documentation](https://wiki.siminnovations.com/index.php/Txt)
lists `_txt` and the bundled font; the
[API compatibility table](https://wiki.siminnovations.com/index.php/API)
lists canvas text from AM/AP 3.5. Inconsolata is bundled from 3.6. The newer
`spacing` style requires 5.1, so this renderer positions characters explicitly
for Air Manager 4.2. It does not require an AM 5 upgrade.

Previews use the same font and metrics, supersampled before downsampling.
The unmodified font is included in `scripts/fonts/` with its OFL license.
Pillow preview rasterization can differ slightly from Air Manager/OpenGL;
a live GUI check remains necessary after restarting Air Manager.

## Regenerate and validate

From the project root, with Python 3 and Pillow installed:

```sh
python3 scripts/make_previews.py
python3 panels/cap-c182t-mo-station/generate_assets.py
python3 tests/test_faceplate.py
python3 tests/test_lcd_text.py
python3 tests/test_panel.py
```

The artwork scripts also use system Liberation Sans for printed legends.
`test_lcd_text.py` requires the Lua 5.4 shared library and exercises the actual
Lua renderer with a captured canvas API, then measures the font's ink bounds.
The panel generator uses the installed stock MFD preview; custom instruments
come from this repository. Full panel tests also expect the local AM installation.

## Review and installation

- [Updated instrument overview](../output/visual-refresh/updated-instruments.png)
- [Before/after comparison](../output/visual-refresh/comparison.png)
- Individual snapshots in `output/visual-refresh/before/` and `after/`.

The refreshed images, affected Lua files and panel previews were copied into
`~/Air Manager/instruments/OPEN_DIRECTORY/` and the existing CAP MO panel
preview directories. All 105 selected deployed files were compared byte for
byte to their sources. The preview font also matches the local AM 4.2 font.
The prior 101 changed files are backed up in
`output/visual-refresh/installed-backup-20260908-062811/`, retaining their paths
relative to `~/Air Manager/`.

Restart Air Manager to load the new resources. Registration, UUIDs, panel
layout definitions, the stock G1000 MFD instrument, and X-Plane plugins were
not changed by this pass.
