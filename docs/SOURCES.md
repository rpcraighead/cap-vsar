# Collected device documentation

Gathered 2026-09-06. All of these are publicly posted; the CAP wing sites and
Technisonic's dealer host them for their own members and customers.

**These files are not in the repository (D-4).** They are the manufacturers'
copyrighted manuals — publicly posted is not the same as ours to redistribute,
and this repository is headed for a public host. They are in `.gitignore`, so
they stay on the disk of anyone who already has them and nothing deletes them.
If you are working from a fresh clone and need one, fetch it from the source
URL in the table below; every faceplate citation in the code refers to these
documents by section and figure number, so a clone without them is still
readable, just not checkable against the originals.

| File | Device | Source |
|---|---|---|
| `Becker_SARDF517_manual.pdf` | SAR-DF 517 | Washington County CAP — `washingtoncounty.cap.gov/media/cms/Becker_SARDF_517_Manual_E696A5229F5E0.pdf` |
| `Becker_SARDF517_manual_akwg.pdf` | SAR-DF 517 (6 pp extract) | Alaska Wing CAP — `akwg.cap.gov/media/cms/macsbecker517manual_0CA7B1C497BC2_95e6e.pdf` |
| `RT600_SARDF517_manual.pdf` | RT-600 **and** SAR-DF 517 | North Carolina Wing CAP — `ncwg.cap.gov/media/cms/beckernew_rhotheta_rt600_manual_3F035301B3F13.pdf` |
| `RT600_america_manual.pdf` | RT-600 (full vendor manual) | RHOTHETA America — `rhothetaamerica.com/pdfs/RT-600_Manual.pdf` |
| `RT600_CAP_basic_training.pdf` | RT-600 CAP training deck | `gocivilairpatrol.com/media/cms/Basic_Rhotheta_600_Presentation_899B48891840B.pdf` |
| `TDFM136B_operating.pdf` | TDFM-136B (doc 08RE399A) | Dallas Avionics — `dallasavionics.com/technisonic/tdfm136b_operating.pdf` |
| `TDFM136_install_operating.pdf` | TDFM-136 install + operating | Dallas Avionics — `dallasavionics.com/technisonic/tdfm136_v2.pdf` |
| `GMA1347_C182T_CAP_audio_panel.pdf` | GMA 1347 audio panel, C182T | CAP TX-435 — `tx435.cap.gov/media/cms/CE182T_Cessna_G1000_Audio_Panel_7C7_DF1C1B60C2DD7.pdf` |
| `GMA1347_garmin_audio_panel_guide.pdf` | GMA 1347 (Garmin, non-airframe-specific) | `gcas.com.pl/wp-content/uploads/2018/01/G1000-Non-AirframeSpecific_AudioPanelPilotsGuide_-02_.pdf` |
| `CAP_FM_Radio_Mission_Observer_Guide.txt` | CAP FM radio procedure | Your own `~/Downloads/CAP_FM_Radio_Mission_Observer_Guide.docx` |

The primary reference for each faceplate:

- **Becker SAR-DF 517** — `Becker_SARDF517_manual.pdf`, DV 77513.04 Issue 03.01.
  Section 3 is the operating chapter and is what the control mapping follows.
- **RHOTHETA RT-600** — `RT600_america_manual.pdf`. Section 2 covers the front
  panel, the dual-function buttons and DF mode.
- **Technisonic TDFM-136B** — `TDFM136B_operating.pdf`, doc 08RE399A. §1.1 is
  the front panel and display, Table 3-1 is the full command-level key map.

## Corrections to Implementation Plan v0.8 §6.2.1

The plan's Becker control table was written before the manual was in hand and
differs from it in several places. The code follows the manual. Worth folding
back into the next revision of the plan:

| Plan v0.8 says | Manual says |
|---|---|
| Ctl 6 "steps through the four configured frequencies" | Eight receiving channels — four fixed emergency plus four freely adjustable training (§1.3.1). The knob steps whichever set the power-on mode selected. |
| Ctl 7 "Brightness button" | There is no brightness button. DIM is the **REP** key held while turning the **PAGE** knob (§3.2.2(1)). |
| Ctl 8 STORE "commits MHz and kHz values" | True on pages 5 and 6. In bearing mode STORE instead suppresses the 3 kHz tone superimposed on AM signals — and bearing is not possible while it is suppressed (§3.3.1(5)). |
| Ctl 9 CLR "clears entry" | In bearing mode CLR erases the bearing **averaging store**, which is how the operator removes the ~2 s drag error after a rapid course change (§3.3.1(4)). That is an operationally important control, not a keypad clear. |
| Ctl 11 "+/- knob … volume in normal operation" | VOLUME is its own rotary switch (§3.3.1(2)). The ±Select / ± rotaries are the edit-menu controls on pages 5 and 6. |
| (not listed) | **REPEAT** — shows the last valid bearing and its receive level (§3.3.1(6)). The plan's table omits it. |

Other facts worth having in the plan:

- The 517's squelch is stored **per frequency**; the RT-600's is stored **per
  band** and runs 0–60 %, with an Auto Squelch mode forced by selecting 0 or 60
  on a COSPAS-SARSAT channel.
- **The 517's technical data lists one COSPAS/SARSAT channel, not two.**
  "Receiving channels: 8 (four of them are free adjustable)", then Emergency
  mode 121.500 / 156.800 / 243.000 / **406.025**, and Training mode
  118.000–122.975 / 156.000–157.975 / 240.000–245.975 / **400.000–409.975**.
  406.028 appears nowhere in the manual; an earlier draft credited the 517 with
  it. The training range also means the head is freely tunable across the whole
  406 band in Training mode, so the single-channel limit is an Emergency-mode
  property, not a hardware one.
- **The RT-600 selects COSPAS-SARSAT channel groups, not channels** (§2.2.3):
  seven groups, CPSAR1 "022-028" (A, B, C) through CPSAR7 "073-076" (R, S), each
  covering two or three 3 kHz channels simultaneously. The inclusive
  406.022–406.076 grid is **nineteen** channels, A through S — not the eighteen
  an earlier draft got by stopping at 406.073.
- §3.3.1(5): STORE switches off the 3 kHz tone superimposed on an AM signal, and
  **"meanwhile bearing isn't possible anymore"**. On the maritime FM band an
  internal filter already removes the tone, so the key has nothing to do there.
- Garbling cone is ~30° to the vertical, bearing accuracy ±5°, internal
  resolution 1° (517 §1.3.1). That is the "cone of confusion" the plan wants to
  model, with a number attached.
- The 517's scan mode is 406.025 ⇔ (121.500 **and** 243.000), switching in the
  5–45 s window between bursts and holding a continuous signal if it finds one
  (§3.3.3). The plan describes the burst cadence but not the dwell logic.
- Burst length: the 517 manual says ~400 ms, the RT-600 manual says 440 or
  520 ms. Use the RT-600 figure — it is the newer document.
- TDFM-136B has **230** main memories (001–230), not the 200 quoted in the CAP
  observer guide; the guide is describing the older TDFM-136.

## X-Plane datarefs verified

Plan §6.7.2's split-COM analysis was checked against this machine's
`X-Plane 12/Resources/plugins/DataRefs.txt` and is accurate:

- `sim/cockpit2/radios/actuators/com2_frequency_hz_833` — writable, kHz
- `sim/cockpit/switches/audio_panel_out` — writable, "6=com1, 7=com2"
- `sim/cockpit2/radios/actuators/audio_com_selection_man_copilot` — exists,
  writable, enum "6=com1,7=com2"
- `sim/atc/com1_tx` / `com2_tx` — **read-only**, documented as "the pilot's voice"
- `sim/atc/com1_tx_override` / `com2_tx_override` — writable, **no copilot
  equivalent**

So the gap is exactly where §6.7.2 says it is: a copilot audio-panel selection
exists, but there is no way to express a second transmitting crew position to a
plugin such as PilotEdge.

## Front-panel figures — PDF page numbers

Rendered copies are in `docs/figures/`; `scripts/luacheck.py` aside, they were
produced with `pdftoppm -png -r 200 -f N -l N <pdf>`. Note these are **PDF page
numbers**, which differ from the printed page labels.

| Figure | PDF page | What it shows |
|---|---|---|
| 517 Fig 1-1 | `Becker_SARDF517_manual.pdf` p.10 | The complete DF system |
| 517 Fig 3-1 | p.27 | Power-on mode selection screen |
| 517 Fig 3-2 | p.28 | General operating elements |
| **517 Fig 3-3** | **p.29** | **Front panel, controls numbered — the layout reference** |
| 517 Fig 3-4 | p.30 | Display page 1, 360° bearing |
| 517 Fig 3-8 | p.33 | COSPAS/SARSAT analyse, page 4 |
| 517 Fig 3-9 | p.34 | Edit menu, page 5 |
| 517 Fig 3-10 | p.35 | Training frequencies, page 6 |
| **RT-600 Fig 2** | **`RT600_america_manual.pdf` p.8** | **DCU front panel layout — the layout reference** |
| RT-600 Fig 3 / 4 | p.9 | Push-buttons, short press and long press |
| RT-600 Fig 5 | p.10 | Power-on screen |
| RT-600 Fig 20 | p.18 | Operating elements in DF mode |
| RT-600 Fig 21 | p.19 | Standard DF display |
| RT-600 Fig 22 | p.20 | COSPAS-SARSAT DF mode |
| **TDFM Fig 1-1** | **`TDFM136B_operating.pdf` p.11** | **Front panel layout — the layout reference** |
| TDFM Fig 1-2 / 1-3 | p.12 | Display parameters, per-channel and common |
| TDFM Fig 1-4 | p.13 | Active channel display and control points |
| **CAP deck** | **`RT600_CAP_basic_training.pdf` p.8** | **Photographs of the RT-600 and the TDFM-136 installed in a CAP aircraft panel** |
| **GMA 1347 Fig 6A.2.1** | **`GMA1347_C182T_CAP_audio_panel.pdf` p.5** | **Audio panel front panel controls — the layout reference** |

## Layout corrections from those figures

The first draft of the faceplates was built from the manuals' *text* before the
figures had been looked at, and the physical layouts were wrong. Corrected:

- **The 517 and the RT-600 are the same physical control head.** The bezel
  carries both names — the RHOTHETA unit is silk-screened "SAR-DF 517" over
  "RT-600 DCU", the Becker one "SAR-DF 517 / BECKER / Rhotheta". It is a
  **square panel-mount instrument**, not a wide radio-stack strip: four large
  knobs at the corners (SQL top-left, PAGE top-right, VOL bottom-left, FREQ
  bottom-right), three small push-buttons across the top centre (Clr, Store,
  Rep — with F1/F2/DIM alternates on the RT-600), one ON/OFF push-button at the
  bottom centre, and the 128×64 display in the middle. Both faceplates now share
  `lib/dcu.lua` because they are the same casting.
- **The 517's display** puts the level bar hard left with a "100" label, the
  dotted compass rose centred with the bearing bracketed in the middle, and a
  right-hand status column carrying PAGE, OFS, MOUNT and the LS timer. Volume
  and frequency sit on the bottom row in inverted fields.
- **The RT-600's softkey strip runs along the top** of the display, directly
  under the three buttons it labels — not along the bottom.
- **The TDFM-136B keypad is four columns by three rows**, not a 3×4 telephone
  pad. ENTER, PROG and ESC form the right-hand column, and 2/4/6/8 carry cursor
  arrows as well as their digits.
- **The TDFM's two squelch LEDs sit inside the display bezel**, one at the start
  of each line, not off to one side.

## DF-head faceplate geometry, measured off Fig 3-3

`scripts/make_df_artwork.py` draws the two DF heads from these proportions,
measured on `docs/figures/b517_p29_bearing_controls-29.png` and expressed as a
percentage of the plate width. They are recorded here because the figure is a
scan and re-measuring it is fiddly; the live numbers are the geometry block in
`instruments/becker-sar-df-517/lib/dcu.lua`.

| Feature | Measured | As built (520-unit face) |
|---|---|---|
| Clipped corner | ~10 % | 52 |
| Circular face inset | radius ~48 % | radius 250 |
| Corner knob centres | 12.5 % / 87.5 % | 65 / 455 |
| Corner knob diameter | ~19 % | 100 |
| Push-button centres | 32.5 / 49.5 / 65.5 % | 174 / 260 / 346 |
| Push-button diameter | ~10 % | 52 |
| Screw centres | 5 % / 95 % across, 21 % / 79 % down | 24 / 496, 112 / 408 |
| LCD lit area | 13.3 – 86.7 % across, 30.5 – 69.6 % down | 62–458, 158–362 |
| ON/OFF button | centre 50 %, 92 % | 260, 478 |

Two details worth keeping:

- **"ON/OFF" is printed left of the button it labels**, centred near 40 % while
  the button sits at 50 %. Both the Becker figure and the CAP photographs of the
  RT-600 show it, so it is reproduced rather than "corrected".
- **The knobs carry no index stripe.** The figure and the photographs show plain
  scalloped mouldings. Air Manager's `dial_add` does not rotate its image, so an
  invented index would have been a mark that never moved.

The one glyph the scan cannot settle is the bearing bracket. Fig 3-3 reads as
`<337<` at that resolution; the CAP photograph of an RT-600 DCU clearly shows
`<010>`. Both heads draw `<nnn>`.

## MO-station panel geometry, measured off the manuals

Same arrangement as the DF heads: `scripts/make_panel_artwork.py` draws both
from these proportions, and the live numbers are the geometry blocks in
`instruments/cap-fm-tdfm-136b/lib/tdfm_panel.lua` and
`instruments/mo-audio-panel-gma1347/lib/gma_panel.lua`.

### TDFM-136B, Figure 1-1 (`docs/figures/tdfm_p11_front_panel-11.png`)

The plate measures 1044 x 545 px in the rendered figure, an aspect of **1.916**,
which is what the 800 x 420 face uses. Percentages are of the plate.

| Feature | Measured | As built |
|---|---|---|
| Display window | 9–90 % across, 8–38 % down | 72–720, 36–162 |
| Character matrix | 24 x 2 at 16–87 % across | 128–698, scale 6 |
| Squelch LEDs | 12.5 % across, on each text line | (100, 80), (100, 134) |
| MAIN / GUARD encoders | centres 14.8 % / 28.3 %, 57 % down | (118, 240), (226, 240), d 76 |
| PGM data port | centre 41.5 % | (332, 240), d 58 |
| Toggles | 14.5 / 28.3 / 41.3 % across, 87 % down | x 118 / 226 / 332, y 366 |
| Keypad | 4 x 3, col centres 54.5–84.5 % | pitch 80 x 67 from (436, 231) |
| Corner screws | 3.5 % / 95 % across, 19 % / 80 % down | (30, 80), (770, 80), (30, 336), (770, 336) |

Two things the first draft had wrong and the figure settles:

- **The toggles are labelled above and below the lever** — MN over GD, G1 over
  G2, HI over LO — not with a single combined caption underneath.
- **Keys 2, 4, 6 and 8 print their digit inside a cursor arrow** and carry no
  second word. The first draft labelled them UP / BACK / FWD / DOWN.

### GMA 1347, Figure 6A.2.1 (`docs/figures/gma1347_panel-05.png`)

§6A.2 gives the dimensions outright, so this one needs no scaling from a scan:

> "The GMA 1347 front panel measures 7.79 inches in depth, **1.3 inches in width
> and 7.70 inches in height**."

That is 1 : 5.923; the measured figure agrees at 1 : 5.87. The face is 240 x
1422. The first draft's 240 x 740 was roughly half as tall as the real unit.

| Feature | Measured | As built |
|---|---|---|
| Key columns | 7–44 % and 56–93 % across | x 18 and 130, w 92 |
| Key rows | 11 rows, ~6.5 % pitch | centres 92 … 1021, h 54 |
| Transceiver group outline | rows 1–4 | (7, 47) 226 x 366 |
| ICS group outline | row 11 | (7, 978) 226 x 118 |
| VOL/SQ knob | centre 50 %, 85.5 % down | (120, 1216), outer d 86, inner d 46 |
| DISPLAY BACKUP | centre 50 %, 94 % down | (120, 1337), d 66 |

Three more corrections the same page forces:

- **The annunciator triangles are white, not green.** "The triangular key
  annunciator lights are white when illuminated and point to the corresponding
  keys."
- **The volume control is a concentric pair, not one knob.** "The small knob
  adjusts the volume/squelch level associated with the pilot channel, while the
  large knob adjusts the volume/squelch level associated with the
  copilot/passenger channels."
- **Row 9 has no right-hand key.** An ambient light sensor sits where one would
  be, which is why the key table has 21 entries and not 22.

## What the audio panel guide adds to Implementation Plan §6.7

Reading the GMA 1347 guide changes the split-COM picture in two ways, one
encouraging and one that argues *for* the plan's existing recommendation.

**The real aeroplane does support simultaneous split COM.** §SPLIT COM is
explicit: "In this mode, both the pilot and the copilot can simultaneously
transmit over separate radios." The plan's §6.7.2 was right that X-Plane's
*ATC* path is single-crew — `sim/atc/com1_tx` / `com2_tx` are documented as
"the pilot's voice" and the plugin overrides have no copilot equivalent — but
X-Plane's copilot **audio panel** is more complete than §6.7.2 implies. It
exposes a full command set, verified in `Commands.txt`:

- `sim/audio_panel_copilot/transmit_audio_com1` / `com2`
- `sim/audio_panel_copilot/monitor_audio_*` (com1, com2, nav1, nav2, adf1,
  adf2, dme, mkr — each with `_on` / `_off` variants)
- `sim/audio_panel/use_copilot_audio` — switches which panel *this client*
  listens through, which is what makes an Air Player MO station hear its own
  selections rather than the pilot's

So the gap to put to Laminar (§6.7.4) is narrower and more precisely stated
than the plan currently has it: the copilot audio panel and its transmit
selection already exist; what is missing is only the ATC-facing
`sim/atc/*_tx_override` equivalent for the second crew position.

**But split COM costs the observer the mission net.** The same section: "while
the pilot can still monitor COM3, NAV1, NAV2, DME, ADF, AUX and MKR audio as
selected, the copilot is only able to monitor/hear COM2." COM3 is the CAP FM
radio. So an MO working ATC on COM2 under split COM **cannot hear mission base
or the ground teams at all**. That is a genuine operational trade, independent
of anything the simulator does or does not model, and it is a strong argument
for §6.7.3 option B — the observer owning the FM mission radio continuously —
being the primary design rather than merely the convenient one. The instrument
models this: selecting COM 1/2 darkens the other annunciators and drops
`cap_fm_audio_selected`.

Other details now modelled that the plan does not mention:

- **ICS isolation is a four-state machine**, not a pair of toggles. Table 6A.3.2
  gives the transitions exactly: a PILOT key press moves PILOT→ALL,
  COPILOT→CREW, CREW→COPILOT, ALL→PILOT; a COPLT press moves PILOT→CREW,
  COPILOT→ALL, CREW→PILOT, ALL→COPILOT. The CAP guide's warning — "if your
  scanners suddenly go silent, check isolation before you check anything else" —
  is only trainable if the state machine is right.
- **MIC keys do not deselect.** Pressing an already-lit COM MIC key does
  nothing; the only way out is to select a different one. Every other key except
  MKR/MUTE and PLAY toggles.
- **MKR/MUTE is three-state**: off → on → on-but-muted (the annunciator stays
  lit while muted) → off.
- **Power-up** runs a ~2 second lamp test with every annunciator lit, then
  restores the previous selections.
- **Fail-safe** bypasses the panel entirely and wires the pilot's mic and
  headset straight to COM1 — which is the CAP guide's "nothing works, and only
  the pilot has COM 1" symptom, and worth injecting as a failure.

## X-Plane copilot audio datarefs used by the MO audio panel

All verified present in `DataRefs.txt`:

```
sim/cockpit2/radios/actuators/audio_selection_com1_copilot   (also com2, nav1,
                                                              nav2, adf1, adf2,
                                                              dme1, dme2)
sim/cockpit2/radios/actuators/audio_com_selection_man_copilot  enum 6=com1,7=com2
sim/cockpit2/radios/actuators/audio_volume_*_copilot           [0..1]
sim/operation/sound/radio_copilot_audio_panel_volume_ratio     [0..1]
sim/operation/sound/radios_are_copilot                         which jack (read-only)
sim/cockpit2/switches/avionics_power_on                        panel power
sim/GPS/G1000_display_reversion                                the red button
```

One gap: there is **no** `audio_selection_mark` dataref on either side, only the
`monitor_audio_mkr` commands and `sim/cockpit/switches/marker_panel_out`. The
instrument therefore tracks MKR annunciator state locally and drives the
commands, which is correct but cannot be read back if something else changes it.

## FlightGear C182 exterior prototype

The local CAP 487 exterior prototype uses the HHS81 FlightGear C182 project at
commit `1359d63393c7fc9145953b081d151d93627e791a`. The reviewed commit archive
has SHA-256
`d81628fff8489af41d312c0e0bc14e1de2ac10a50d6c0c75f937441f81343fbe`.
GitHub identifies the repository license as GPL-2.0 and the root contains the
GPL version 2 text.

The converter reads `Models/c182s.ac`, which is the shared exterior referenced
by the donor's `Models/c182t.xml`, and uses `Models/Liveries/Default.png`,
`Models/Lights.png` and `Models/PropBlur.png`. The donor also includes the
editable `dev/C182T.blend`. None of these inputs or their generated OBJ8 output
is stored in this repository. `scripts/fetch_flightgear_c182.py` fetches and
checks the pinned source outside the tree, and the generated aircraft records
the commit and file hashes in `flightgear-c182-prototype.json`.

See [`FLIGHTGEAR_C182_GPL_PLAN.md`](FLIGHTGEAR_C182_GPL_PLAN.md) for the local
prototype boundary, production options and release gate.
