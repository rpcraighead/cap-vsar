# CAP V-SAR — Air Manager 4.2+ instruments

Current project release: **v0.1**. The `VERSION` file and matching Git tag are
the project-wide release identifier; Air Manager's integer instrument revision
fields remain independent.

Instrument layer for the CAP V-SAR training simulator (Implementation Plan
v0.8, `~/Documents/CAP_V-SAR_Implementation_Plan_v0.8.docx`). Four instruments
targeting Air Manager 4.2 and forward-compatible with Air Manager 5, plus the
documentation they were built from.

| Instrument | Plan section | What it is |
|---|---|---|
| [`instruments/becker-sar-df-517/`](instruments/becker-sar-df-517/) | §6.2.1 | Becker SAR-DF 517 four-band DF head |
| [`instruments/rhotheta-rt-600/`](instruments/rhotheta-rt-600/) | §6.2.2 | RHOTHETA RT-600, the fleet replacement |
| [`instruments/cap-fm-tdfm-136b/`](instruments/cap-fm-tdfm-136b/) | §6.7 | Technisonic TDFM-136B CAP mission radio, MO station |
| [`instruments/mo-audio-panel-gma1347/`](instruments/mo-audio-panel-gma1347/) | §6.7 | Garmin GMA 1347 audio panel, MO station |

| Panel | Use Case | What it is |
|---|---|---|
| [`panels/cap-c182t-mo-station/`](panels/cap-c182t-mo-station/) | MO Station | Dedicated Cessna 182T Mission Observer panel (MFD + GMA 1347 + Becker 517 / RT-600 + TDFM-136B) for multi-monitor or Air Player streaming |

| Aircraft Package | Location | What it is |
|---|---|---|
| **Cessna 182T NAV III (G1000 CAP)** | `X-Plane 12/Aircraft/CAP/Cessna 182T NAV III/` | Local CAP 487 prototype using the installed Laminar G1000 cockpit and a pinned GPL FlightGear C182 exterior. The builder supplies 230 HP IO-540 data, a 3-blade constant-speed prop, 87 gal usable fuel and C182T limits. Generated via `scripts/build_c182t_package.py`; see the [GPL production plan](docs/FLIGHTGEAR_C182_GPL_PLAN.md) before distributing anything. |

| Web Application / Service | URL / Port | What it is |
|---|---|---|
| **Mission Base Headset Radio** | `https://192.0.2.151:8743/radio` | APX 4500 / EFJohnson 5300 instrument faces, live Mumble voice, touch or spacebar PTT; [headset and HTTPS setup](docs/mission-base-radio/README.md) |
| Legacy MRO Text Console | `ms01:8700/radio-legacy` | Previous APX 6500 / Icom training console, typed messages, sidetones and Form 110 log |
| Instructor Console | `ms01:8700/` | Exercise scenario management, map-pin beacon placement, propagation fault injection |
| Mission Base Console | `ms01:8700/base` | Situational awareness map (hidden beacon truth), bearing logging & intersection cuts |
| Debrief Console | `ms01:8700/debrief` | Recorded flight replay against truth, CPA, track efficiency, bearing error scoring |
| Flight Planner | `ms01:8090/` | Pre-flight navigation log, geodetic CAP search patterns (SS, CS, PS), FMS export |


## Architecture

Per plan §5.2 the propagation engine does **not** live in Air Manager — Lua has
neither terrain probing nor network access. It is an XPPython3 plugin in X-Plane
that publishes `cap/df/*`, and these faceplates are a pure display-and-control
layer that subscribes to it.

```
X-Plane 12
  └── PI_capvsar_df.py  (deployed copy of xplane/PI_capvsar_df.py)
        radio horizon, terrain and airframe line-of-sight,
        wing blanking, cone of confusion, 406 burst cadence,
        bearing averaging, C/S decode;
        also the sim bridge to ms01:8700
        │
        ├── cap/df/*  datarefs ──────────► Becker 517 faceplate
        │   ◄── panel inputs ─────────────  RHOTHETA RT-600 faceplate
        │       (head type, tuned freq,
        │        squelch, scan, mounting)
        │
        └── si_variable cap_fm_* ────────► TDFM-136B faceplate
                                          ► GMA 1347 audio panel
                                             └─► local Mumble agent (plan §6.3.2)

X-Plane copilot audio panel ◄─── GMA 1347 (audio_selection_*_copilot,
                                           sim/audio_panel_copilot/*)
```

The MO station is two instruments working together, the way the real cockpit is:
the **TDFM-136B** is the radio (which channel, which power, who is talking) and
the **GMA 1347** is what decides whether the observer can hear it and talk on it.
The CAP guide is emphatic that this is where the failures actually are —
"nearly every 'the radio is broken' report in flight is an audio panel
selection" — so COM3 audio and COM3 MIC are separate variables
(`cap_fm_audio_selected`, `cap_fm_mic_selected`), and selecting one does not
give you the other.

The DF half of that interface is two-way. The engine owns propagation and
decides what a given head can hear; the faceplate owns the controls and tells the
engine which head is fitted and how it is set. Neither half guesses at the
other's job, and either runs without the other — the engine ignores the panel
until the panel writes something.

It is written down in
[`docs/DATAREF_CONTRACT.md`](docs/DATAREF_CONTRACT.md): Part 1 is what the engine
publishes, Part 2 what the faceplates derive for themselves, Part 3 what the
panel tells the engine, and Part 4 the scenario fields supplied by the console.

## Status

All four instruments are discovered by **Air Manager Home Use 4.2.12** on this
machine. The Becker, RHOTHETA and TDFM canvas paths have also been corrected for
the 4.2 API: libraries are preloaded from `lib/` rather than imported with
`require()`, and every `canvas_draw` supplies its callback. The TDFM has been
run and powered in the editor with a clean console and a live two-line dot
matrix display. See `CHANGELOG.md` for the per-instrument runtime matrix.

The engine is a different matter: it is tested. `tests/test_engine.py` loads
`PI_capvsar_df.py` against a stubbed `xp` module and drives it the way Air
Manager and the exercise console would, so the propagation half can be checked
on a machine with neither X-Plane nor Air Manager running:

```
python3 tests/test_engine.py        # propagation engine
python3 tests/test_faceplate.py     # artwork, resources, geometry and AM loading contract
python3 scripts/luacheck.py instruments/*/logic.lua instruments/*/lib/*.lua
python3 scripts/deploy_xplane_plugin.py       # install the tested engine into X-Plane
python3 scripts/deploy_df_instruments.py      # install all four instruments into Air Manager
```

`tests/test_faceplate.py` is the half of the instrument layer that can be
checked without Air Manager, across all four instruments: that every geometry
block still parses, that no two control hit regions overlap or cover a display,
that each GMA annunciator sits above its own key and the concentric knob nests
correctly, that every image the Lua names is shipped at the size the geometry
expects with no orphans, that no instrument ships an unused library, that the
faces match the dimensions their manuals give, that the DF heads keep
byte-identical shared libraries but distinct branding, and that no literal LCD
string runs off the 128-dot panel.

**The interface is two-way as of this revision.** The engine registers the
panel-input datarefs the faceplates already spoke to, so the frequency knob now
really retunes the receiver, and the 517-vs-RT-600 406 MHz coverage difference —
the scenario that justifies building both heads — is demonstrable.

Both manuals state that difference outright. In Emergency mode the Becker's
COSPAS/SARSAT receiver is **one fixed channel, 406.025**; the RT-600 selects one
of **seven CPSAR groups**, each covering two or three of the nineteen 3 kHz
channels at once. So a beacon on 406.037 is silent on the Becker and audible to
an RT-600 on CPSAR2 without the crew retuning anything. In Training mode the
Becker is a freely tunable 400–410 receiver and the restriction lifts.

Squelch gates the receiver, power-off is silent, a wrong TOP/BOTTOM mounting
mirror-inverts the bearing, suppressing the 3 kHz tone stops the bearing as the
manual says it does, and scan sweeps the tuned C/S channel against the two
continuous frequencies the panel names.

Scenario-controlled wing blanking reads X-Plane roll and pitch and applies a
configurable C182 belly/top antenna profile before signal saturation. The
signal indication and squelch react immediately, while the bearing can remain
on TIMEHOLD. `cap/df/rx_open` exposes instantaneous reception separately for
the audio path and instructor diagnostics. Both Air Manager DF heads use that
instantaneous state to play receiver audio: the analog 121.5/243 downward sweep,
the receiver's 3 kHz DF tone, and the 440 ms 406 data burst. The front-panel
volume controls gain; power, tuning, squelch, 406 cadence, terrain masking and
wing blanking all silence it through the same receiver state. On the Becker,
STORE removes the 3 kHz component while leaving the beacon sweep audible.

Bearing **spread** and the COSPAS/SARSAT **decode** are published too. The engine
now averages the bearing over a two-second window, which is where the manuals'
drag error after a rapid course change comes from and what CLR clears; spread is
measured from the un-averaged stream, which is exactly why the faceplate could
never have faked it.

What is left is on the exercise console rather than here — see
`docs/DATAREF_CONTRACT.md` Part 4. The important one: a 406 scenario must set
`beacon_freq_hz` to a channel the 517 lacks, or both heads hear the beacon and
the coverage lesson does not land.

## Installing

### Instruments
Air Manager instruments are plain folders. For editable local instruments in
Air Manager 4.2, copy each folder's contents under its UUID in `OPEN_DIRECTORY`
(the UUID is the root `<instrument id>` in that folder's `info.xml`):

```
~/Air Manager/instruments/OPEN_DIRECTORY/<instrument-uuid>/
```

### Panels
The dedicated Mission Observer (MO) station panel (`cap-c182t-mo-station`) lives in
`panels/cap-c182t-mo-station/`. Deploy it into Air Manager or package it for a secondary PC:

```bash
python3 scripts/deploy_mo_panel.py        # deploys to ~/Air Manager/panels/OPEN_DIRECTORY/
python3 scripts/deploy_mo_panel.py --zip  # packages cap-c182t-mo-station.zip for transfer
```

Each folder holds `info.xml`, `logic.lua`, `preview.png`, `lib/` and
`resources/`. Air Manager executes every `lib/*.lua` file before `logic.lua` in
an unspecified order; its 4.2 sandbox does not expose `require()`. Each library
therefore publishes one global table matching its filename, and no library may
depend on another library having run first. Air Manager scopes `lib/` to a
single instrument, so a shared module is duplicated into each instrument that
needs it — edit
`becker-sar-df-517/lib/` and copy across, rather than editing the copies
separately. `tests/test_faceplate.py` fails if the DF heads' copies diverge, and
if any instrument ships a library nothing requires.

| Module | Shipped by |
|---|---|
| `lcd.lua` | the two DF heads and the TDFM — the dot-matrix font and canvas helpers |
| `dcu.lua` | the two DF heads — their shared chassis |
| `cap_df.lua` | the two DF heads — the engine binding |
| `tdfm_display.lua`, `tdfm_panel.lua` | the TDFM |
| `gma_panel.lua` | the GMA, which needs no display code at all |

Preferred sizes come from each instrument's own reference: 520×520 for the DF
heads, 800×420 for the TDFM (Figure 1-1's 1.916 aspect), 240×1422 for the GMA
(§6A.2 gives the panel as 1.3 × 7.70 inches). Changing one means changing the
geometry block, re-running the generator and updating `info.xml` — the tests
check all three agree.

## Artwork

The faceplates are generated, not traced from photographs of the real units.
Plan §6.2.3 lists three options and this is the third: functionally equivalent,
clearly not a copy of the vendor's panel. That removes the likeness question in
§10 and the 3–6 days per head the plan budgets for graphics work.

**Physical layouts are measured from the manuals' front-panel figures**, rendered
into `docs/figures/` — see `docs/SOURCES.md` for the PDF page numbers and the
list of things the first draft got wrong. The two DF heads share `lib/dcu.lua`
because they are literally the same control head: the bezel carries both the
"SAR-DF 517" and "RT-600.DCU" names.

All four instruments are built the same way, which is what lets the printed
lettering be smooth while the displays stay dot matrices:

| Layer | Contains |
|---|---|
| back | `resources/faceplate.png` — housing, screws, display recess, group outlines, every silk-screened legend |
| middle | the live display, drawn on a Lua canvas — 128×64 on the DF heads, 24×2 on the TDFM. The GMA has none: it is all lamps. |
| front | the images and text nodes Air Manager moves, swaps or lights — knobs, buttons, toggles, key caps, LEDs and annunciators |

Nothing dynamic is baked into a faceplate: no bearing, frequency, channel or
annunciator state, and no control. Knobs carry **no index stripe** — `dial_add`
does not rotate its image, so a painted index would be a mark that never moved.

Keys that carry their own printed legend get their own image pair, because the
cap moves when it is pressed: twelve for the TDFM keypad, twenty-one for the
GMA.

### Generators

Neither script defines geometry. Each **parses a marked block in the Lua the
instrument actually uses**, so the artwork and the control hit regions cannot
drift apart; if a block stops parsing the script fails rather than guessing.

| Script | Instruments | Geometry read from |
|---|---|---|
| `scripts/make_df_artwork.py` | Becker 517, RHOTHETA RT-600 | `becker-sar-df-517/lib/dcu.lua` |
| `scripts/make_panel_artwork.py` | TDFM-136B, GMA 1347 | `cap-fm-tdfm-136b/lib/tdfm_panel.lua`, `mo-audio-panel-gma1347/lib/gma_panel.lua` |

```
python3 scripts/make_previews.py       # runs both: faceplates, controls, previews
```

`make_previews.py` is now only a front-end. It used to draw all four previews
from a second copy of the geometry — a copy that drifted, and that would have
quietly replaced a regenerated faceplate with the superseded flat design.
## Cessna 182T NAV III (G1000 CAP) Aircraft Package

To support high-fidelity Virtual Search and Rescue (V-SAR) training in X-Plane 12, a dedicated **Cessna 182T Skylane NAV III (`CAP 487`)** aircraft package has been engineered.

- **Standalone Package Path:** `/home/ron/X-Plane 12/Aircraft/CAP/Cessna 182T NAV III/`
- **Builder Script:** `python3 scripts/build_c182t_package.py`
- **Exterior Prototype:** pinned HHS81 FlightGear C182 source, converted locally
  to OBJ8; see [`docs/FLIGHTGEAR_C182_GPL_PLAN.md`](docs/FLIGHTGEAR_C182_GPL_PLAN.md)

### Aircraft Specifications
- **Powerplant:** 230 HP Lycoming IO-540-AB1A5 direct-drive fuel-injected engine (2,400 RPM redline).
- **Propeller:** 3-blade McCauley constant-speed propeller. Setting constant-speed prop type (`_prop_type = 1`) automatically triggers the Garmin G1000 MFD Engine Indication System (EIS) to render dual **Manifold Pressure (`MAN IN HG`)** and **Tachometer (`RPM`)** gauges with authentic C182T limits.
- **Fuel System:** 87 gallons usable fuel (522 lbs 100LL).
- **Weights:** 1,970 lbs empty weight; 3,100 lbs max takeoff weight (1,130 lbs useful load).
- **Cowl Flaps:** Equipped with manual cowl flaps for engine cooling management.
- **Flight Envelope:** $V_S=51$, $V_{S0}=41$, $V_X=65$, $V_Y=80$, $V_{BG}=76$, $V_{FE1}=140$, $V_{FEM}=100$, $V_{NO}=140$, $V_{NE}=175$ KIAS.
- **Livery & Registration:** CAP 487, ICAO code `C182`, Civil Air Patrol livery and custom menu selection icons with USAF Auxiliary branding.

The package leaves the base Laminar Research C172SP completely untouched and
can be rebuilt or refreshed at any time. The generated aircraft combines GPL
donor-derived exterior files with files copied from the operator's X-Plane
installation, so it is a local prototype and must not be redistributed.

## What is deliberately not here

- **CAP frequencies.** The communications plan is access-restricted through
  eServices and channel plans differ between airframes. `cap-fm-tdfm-136b`
  ships placeholder channels inside 136–174 MHz; the instructor loads the
  exercise's channel card by editing the `memories` table.
- **TDFM levels 4 and 5.** Maintenance and supervisor commands. The manual says
  never to fly with them accessible, and the observer has no use for them.
- **ATC transmit.** Plan §6.7.3 option B routes the MO's mission radio to the
  Mumble net, not to PilotEdge, so this instrument does not touch
  `sim/cockpit/switches/audio_panel_out` or the `sim/atc/*` transmit path.

## Documentation collected

[`docs/SOURCES.md`](docs/SOURCES.md) lists the equipment documentation this
work is built from — the Becker 517 and RT-600 manuals, the Technisonic
operating instructions, the CAP RT-600 training deck and the CAP FM radio
observer guide — with the public URL each one came from.

The manuals themselves are **not in this repository**: they are the
manufacturers' copyright, not ours to redistribute. Fetch your own from the
URLs in `SOURCES.md` if you want to check the faceplates against them. Every
citation in the code gives a section or figure number, so the code is readable
without them.

Gathering the RT-600 documentation closes the dependency flagged in plan §6.2.2
("RT-600 operating documentation has not yet been gathered; the control mapping
cannot be written until it is"). It is gathered, and the mapping is written.

## Licence

The project's own code, artwork and documentation are licensed under the
Apache License 2.0 — see [`LICENSE`](LICENSE).

[`NOTICE`](NOTICE) is the part that matters before you copy anything out of
here: what this repository deliberately does *not* redistribute. In short, the
Cessna 182T package is **built** from Laminar Research's stock 172SP in your
own X-Plane installation and no Laminar asset is stored here; the instruments
run inside Air Manager, which each station licenses itself; and the equipment
manuals stay with their manufacturers.

This is a member-built training project. It is not an official Civil Air Patrol
product, it carries no CAP endorsement, and nothing in it may be used for real
flight planning or a real search.
