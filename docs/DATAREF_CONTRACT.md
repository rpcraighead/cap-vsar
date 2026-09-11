# CAP V-SAR — `cap/df/*` dataref contract

Per Implementation Plan v0.8 §5.2 the propagation engine runs in X-Plane, not in
Air Manager. Its tracked source is `xplane/PI_capvsar_df.py`; the deployment
script installs that XPPython3 plugin at

```
X-Plane 12/Resources/plugins/PythonPlugins/PI_capvsar_df.py
```

It also acts as the sim bridge, polling the exercise console on ms01:8700 from a
background thread. The faceplates in `instruments/` are bound to what it
publishes, verified by reading the plugin source.

**The interface is now two-way.** The panel tells the engine which head is
fitted, what it is tuned to and how it is configured; the engine decides what
that head can actually hear. That is what makes the 517-vs-RT-600 406 MHz
coverage difference demonstrable, which is the scenario the exercise exists for.

`tests/test_engine.py` drives the engine against a stubbed `xp` module and
asserts every behaviour described below. It needs neither X-Plane nor Air
Manager:

```
python3 tests/test_engine.py
```

---

## Part 1 — what the engine publishes

All read-only. `lib/cap_df.lua` subscribes in separate bearing, decode, and
instantaneous-reception groups so each callback remains manageable.

### Bearing

| Dataref | Type | Units | Notes |
|---|---|---|---|
| `cap/df/valid` | INT | bool | 1 when a usable bearing exists |
| `cap/df/bearing_rel` | FLOAT | deg | Relative to the nose. This is what drives the needle. Averaged — see below. |
| `cap/df/bearing_true` | FLOAT | deg | True bearing |
| `cap/df/signal` | FLOAT | **0..1** | Not a percentage. `cap_df.lua` rescales to 0–100 for display. |
| `cap/df/distance_nm` | FLOAT | NM | Slant range — ground great-circle and the height difference combined, so an aircraft directly over a beacon 3,000 ft below reads 0.49, not 0. Instructor-facing; the 517 shows it on page 3. |
| `cap/df/in_cone` | INT | bool | Inside the cone of confusion — bearing deliberately invalid |
| `cap/df/blocked` | INT | bool | Terrain masking the signal |
| `cap/df/airframe_shadowed` | INT | bool | At least 1 dB of installation-specific wing/fuselage attenuation is active. Separate from terrain masking. |
| `cap/df/airframe_attenuation_db` | FLOAT | dB | Current directional loss from the selected antenna profile. Instructor/debug truth. |
| `cap/df/rx_open` | INT | bool | A transmission is receivable at this instant. Unlike `valid`, this is never held. Audio should follow this value. |
| `cap/df/band` | FLOAT | MHz | What the head is **actually listening to**, which in scan mode is not what the crew tuned |
| `cap/df/spread` | FLOAT | deg | Scatter of the un-averaged bearings, **peak to peak** — the full width of the band, so the extremes are `bearing ± spread/2`. How the operator judges whether to trust the needle. |
| `cap/df/error_code` | INT | — | **−1 = no error**; 0–12 are Becker E0–E12. Set from the console's `effects.error_code`. |

### COSPAS/SARSAT decode

| Dataref | Type | Notes |
|---|---|---|
| `cap/df/cs_sync` | INT | 0 none, 1 SYNC OK, 2 SELFTEST |
| `cap/df/cs_protocol` | INT | 1 USER, 2 STANDARD, 3 NATIONAL; +4 for the TEST variant |
| `cap/df/cs_hex15` | BYTE[15] | 15-hex beacon ident, one ASCII character per byte. **Length 0 until a frame decodes** — X-Plane reports the array's real length, so read `cs_sync` first and do not assume 15 bytes are there. |
| `cap/df/cs_country` | INT | Numeric country code |
| `cap/df/cs_has_position` | INT | 1 when the message carries a position |
| `cap/df/cs_lat` / `cs_lon` | FLOAT | Degrees, valid only when the above is 1 |
| `cap/df/cs_msg_age_sec` | FLOAT | Seconds since the last valid decode |

### Scenario

All four are writable, which is the whole offline test path: with no console
reachable, set the position and then `active` to 1 and the DF behaves exactly
as it would in a sortie. A live console still wins — its next poll overwrites
whatever was written here.

| Dataref | Type |
|---|---|
| `cap/scenario/active` | INT |
| `cap/scenario/beacon_lat` | DOUBLE |
| `cap/scenario/beacon_lon` | DOUBLE |
| `cap/scenario/beacon_elev` | FLOAT (ft MSL) |

### Three traps worth remembering

- **`signal` is 0..1, not 0..100.** Both DF heads display a percentage. The
  rescale happens in one place, `cap_df.lua`. Do not double-scale it.
- **`error_code` uses −1 for "none", not 0.** E0 (NO RECEIVER) is a real Becker
  code, so 0 could not also mean "healthy". The 517's error guard tests `>= 0`.
- **`band` is what the receiver is on, not what the knob says.** In scan mode the
  engine steps the receiver between 406.025 and the two continuous emergency
  frequencies on its own, and `band` follows the receiver.

---

## Part 2 — what the faceplates derive locally

The engine does not publish these, so `cap_df.lua` computes them from
`valid`-state transitions and a 250 ms tick. They are honest approximations,
not engine truth.

| Value | How it is derived |
|---|---|
| `last_signal` | Seconds since `valid` last went true. Drives the RT-600's `LS mm:ss`. |
| `burst_age` | Seconds since re-acquisition on a 406 band. Drives the 517's scan-mode timer. |

`cap_df.has_spread()` and `cap_df.has_decode()` return true once the engine has
answered on the decode subscription. If the plugin is not loaded the callback
never fires, both stay false, and the faceplates draw nothing rather than
drawing a spread of zero — which would read as a perfect bearing.

**How `spread` reaches the operator.** Both heads put it on the compass rose the
way 517 manual Fig 3-3 does: a solid marker on the rim at the averaged bearing
and a hollow marker at each un-averaged extreme, `bearing ± spread/2`. §3.3 is
what defines this — "the unaveraged maximal bearing values (spread) are
indicated and, if interpretable, the averaged bearing value" — so the width of
the gap between the hollow markers *is* the trust signal, read at a glance. The
517's page 3 also shows it numerically as `SPRD nn`. This is a display change
only; the dataref is unchanged.

---

## Part 3 — what the panel tells the engine

All writable, all registered by `PI_capvsar_df.py`. `cap_df.lua` writes them
behind `M.ENGINE_ACCEPTS_PANEL_INPUT`, which is now `true`; set it false only to
run the faceplates against an older engine build.

| Dataref | Type | Meaning |
|---|---|---|
| `cap/df/power` | INT | 0/1. Outputs sit at the noise floor when off, and nothing is held. |
| `cap/df/active_freq_hz` | INT | What the head is tuned to, in Hz. Supersedes the console-selected band. |
| `cap/df/head_type` | INT | 0 = Becker SAR-DF 517, 1 = RHOTHETA RT-600. **The 406 coverage difference lives here.** |
| `cap/df/squelch` | FLOAT | % 0–100, or −1 for the RT-600's Auto Squelch. Gates `valid`. |
| `cap/df/mode` | INT | 0 = Emergency, 1 = Training (517 only) |
| `cap/df/scan_enable` | INT | 0/1. 406 ⇔ 121.5/243.0 per 517 §3.3.3. |
| `cap/df/clear_average` | INT | Panel pulses 1; the engine clears the averaging store and self-resets to 0. |
| `cap/df/timehold_sec` | FLOAT | How long a lost bearing stays on screen. 517 edit menu, default 10 s. |
| `cap/df/offset_deg` | FLOAT | Antenna offset correction dialled in by the crew |
| `cap/df/mounting` | INT | 0 = TOP, 1 = BOTTOM |
| `cap/df/rx_span_hz` | INT | Half-width the receiver covers either side of `active_freq_hz`. 0 for a single-channel set; half the group width for an RT-600 CPSAR selection. |
| `cap/df/scan_alt1_hz` | INT | The two continuous frequencies scan sweeps between 406 bursts (517 §3.3.3). The emergency pair in Emergency mode, the crew's training channels in Training mode — the engine cannot guess which, so the panel says. |
| `cap/df/scan_alt2_hz` | INT | |

**Nothing reads the panel until the panel writes.** `panel_seen` stays false
until a faceplate touches one of these, and while it is false the engine behaves
exactly as it did before: the console picks the band and the receiver is assumed
to be tuned to the beacon. Running X-Plane with no Air Manager attached is
unchanged.

### How each input is modelled

- **406 coverage.** The COSPAS-SARSAT grid runs 406.022–406.076 at 3 kHz
  spacing: **nineteen** channels, A through S. The two heads cover it very
  differently, and both manuals state it outright.

  The Becker's technical data lists its receiving frequencies:

  | Mode | COSPAS/SARSAT |
  |---|---|
  | Emergency | **406.025 only** — one fixed channel |
  | Training | freely adjustable anywhere in 400.000–409.975 |

  The RT-600 (§2.2.3) does not tune single channels at all. It selects one of
  **seven CPSAR groups**, each covering two or three channels at once:

  | Group | Range | Channels |
  |---|---|---|
  | CPSAR1 | 406.022 … 028 | A, B, C |
  | CPSAR2 | 406.031 … 037 | D, E, F |
  | CPSAR3 | 406.040 … 043 | G, H |
  | CPSAR4 | 406.046 … 052 | I, J, K |
  | CPSAR5 | 406.055 … 061 | L, M, N |
  | CPSAR6 | 406.064 … 070 | O, P, Q |
  | CPSAR7 | 406.073 … 076 | R, S |

  So a Becker in Emergency mode on its single 406.025 channel hears nothing from
  a beacon on 406.037, while one RT-600 group selection (CPSAR2) covers 406.031,
  406.034 and 406.037 simultaneously. That is the coverage difference the
  exercise exists to teach, and it is a wider gap than the "two of eighteen" an
  earlier build modelled. In Training mode the Becker is a freely tunable
  400–410 receiver and the restriction does not apply.
- **Tuning.** The head hears the beacon within half a channel (1.5 kHz) on the
  C/S grid, 5 kHz elsewhere, **plus `rx_span_hz`** — which is how one RT-600
  group selection takes in its two or three channels at once. The beacon's own
  frequency comes from the console's `beacon_freq_hz`, or is derived from `band`
  if it sends none.
- **Signal strength (P-13).** `cap/df/signal` is a link budget, not an inverse
  square curve: beacon ERP (a 121.5/243 analog ELT radiates about 0.1 W, a 406
  beacon 5 W), less 20 dB for a beacon lying in ground clutter with a damaged
  antenna, less free-space path loss, less terrain and airframe losses — then
  mapped onto 0..1 across the 45 dB above the heads' published ~1 µV/m
  sensitivity. The bands therefore differ in *range*, not just in cadence and
  decode: on a clear path a bearing holds to roughly 50 NM on 121.5 and 105 NM
  on 406, with a decodable 406 frame to about 44 NM. Terrain and the radio
  horizon cut all three well short of that in real country. On 406 the value is
  gated to the burst, so the bar pulses on the 50 s beacon cadence rather than
  sitting pegged between bursts (P-7).
- **Squelch.** A percentage maps onto a threshold on the 0..1 signal, from the
  noise floor at 0 % (and Auto) to just above saturation at 100 %. Wound fully
  up the set really is deaf. The RT-600's scale stops at 60 %, so its squelch
  cannot be wound as tight as the 517's — that difference is real and preserved.
- **Wing blanking / airframe shadowing.** When `effects.airframe_shadowing` is
  enabled, the engine reads X-Plane roll (`phi`) and pitch (`theta`), transforms
  the aircraft-to-beacon ray into body coordinates, and tests its intersection
  with a softened wing/fuselage silhouette. A belly profile nulls when the
  lowered wing is toward the beacon; a top profile reverses that relationship.
  Directional and terrain losses accumulate in dB before the 0..1 mapping, so
  a close strong beacon can remain receivable through shielding. `rx_open`
  closes immediately in the null while `valid` may retain the last bearing for
  TIMEHOLD. The supplied C182 profiles are training approximations and support
  per-scenario geometry/loss overrides; they are not calibrated antenna-pattern
  measurements for a particular tail number.
- **Receiver audio.** Both Air Manager DF heads gate their local audio directly
  from `rx_open`, so held bearings never keep a dead signal audible. Analog
  121.5/243 reception uses the distinctive downward ELT sweep with the DF
  receiver's 3 kHz Doppler tone; the 406 path plays one 440 ms data burst.
  Power, tuning, squelch, terrain and airframe loss therefore affect audio and
  bearing through the same engine decision. The volume knob controls Air
  Manager sound gain. Becker STORE selects a clean analog asset without the
  3 kHz component, while the underlying received sweep remains audible.
- **Mounting.** The console's `effects.mounting` is the truth. If the crew's
  setting disagrees, the bearing is mirror-inverted. Cheap trap, entirely
  realistic, and one of the few faults that looks like a working set.
- **Offset.** The installation has a real misalignment
  (`effects.antenna_offset_deg`) and the crew dials in a correction. They cancel
  when the correction is right.
- **Scan.** The tuned C/S channel while a burst is expected; otherwise
  `scan_alt1_hz` and `scan_alt2_hz` in turn on a 4 s dwell, holding on one if it
  answers (§3.3.3). Those default to 121.500 and 243.000 if a panel never writes
  them, which keeps an older faceplate working.
- **Mode.** Training flags the decoded frame as the TEST protocol variant, which
  both panels already render. It is also reported to the console.

### Averaging, spread and the drag error

The engine now averages. Each 250 ms tick takes one un-averaged bearing with
scatter proportional to how weak the signal is; the published `bearing_rel` is
the circular mean over a window of roughly two seconds, stretching to six on a
weak signal, which is what both manuals describe. `spread` is the maximum
deviation across that window — measured from the un-averaged stream, which is
precisely why it could not be faked in the faceplate.

The consequences fall out rather than being written in: a rapid course change
produces the manuals' drag error, and `cap/df/clear_average` throws the store
away so the needle snaps back. That is what CLR is for on the 517 and a long CLR
press on the RT-600.

### Timehold and the 406 burst

A 406 beacon radiates for about 440 ms every 50 s (the RT-600 manual's figure;
SOURCES.md prefers it over the 517's ~400 ms). Between bursts there is nothing to
take a bearing from, so the last one is held for `timehold_sec` and then dropped.
That is what TIMEHOLD on the 517's edit menu is actually for.

---

## Part 4 — scenario fields supplied by the console

The engine degrades gracefully when these fields are absent. The console now
supplies the airframe-shadowing fields through its scenario editor and live
effect controls; the remaining optional fields enrich particular exercises.

| Scenario field | Effect |
|---|---|
| `beacon_freq_hz` | The exact channel the beacon transmits on. Without it a 406 beacon is assumed to be on 406.025, and the 517 always hears it — so **the coverage scenario needs this field set** to a channel the 517 lacks. |
| `cs` block | `hex15`, `country`, `protocol`, `has_position`, `lat`, `lon`, `selftest`. Without it the ident is synthesised from the beacon position (stable per beacon, obviously not a real registration), country defaults to 366, and no position is claimed. |
| `effects.radio_horizon` | **Default on.** Enforces the two-ended radio horizon, `1.23*(sqrt(h_ac) + sqrt(h_beacon))`. Turn it off to let a beacon be heard from anywhere. |
| `effects.terrain_masking` | **Default on.** Runs the in-simulator terrain probe. This is the one effect no server-side model can reproduce, so turning it off gives up most of what the plugin is for — but it is the right switch for a first-session demo where the beacon must simply be findable. |
| `effects.burst_cadence` | **Default on.** A 406 beacon radiates for 440 ms every 50 s; the signal bar and audio are gated to the burst and the bearing is carried between bursts by TIMEHOLD. Off makes 406 continuous, which is not realistic but is far easier for a first look at the head. |
| `effects.cone_of_confusion` | **Default on.** Directly overhead the beacon, reception continues but no bearing can be resolved: `in_cone` goes to 1 and `valid` to 0. |
| `effects.multipath` | **Default off.** Terrain reflections swing the bearing. Since P-13 this is driven by the terrain probe — strongest where the path is blocked or grazing a ridge, absent on a clear path, and wandering with the aircraft's position rather than stepping on a timer. |
| `effects.multipath_offset_deg` | Peak bearing error the above can reach; defaults to 40. |
| `effects.beacon_has_gps` | Whether a synthesised decode carries a position. A plain 406 ELT without GPS is both the commoner case and the more interesting search. |
| `effects.error_code` | Injects a Becker E0–E12 fault. |
| `effects.mounting`, `effects.antenna_offset_deg` | The installation truth the crew's settings have to match. |
| `effects.airframe_shadowing` | Enables attitude-dependent wing/fuselage attenuation. Defaults off for existing scenarios. |
| `effects.df_antenna_profile` | `c182_belly` or `c182_top`; defaults to the belly profile. This is physical installation truth, independent of the crew's TOP/BOTTOM control. |
| `effects.wing_null_max_loss_db` | Optional peak loss override; nominal profile value is 24 dB. |
| `effects.df_antenna_location` | `belly` or `top`, overriding just the location half of the chosen profile. |
| `effects.wing_null_antenna_plane_distance_ft`, `..._half_span_ft`, `..._half_chord_ft`, `..._fuselage_half_width_ft`, `..._fuselage_half_length_ft`, `..._edge_softness_ft` | Per-scenario geometry overrides on the selected profile (all prefixed `wing_null_`). Each falls back independently to the profile value, so a scenario can override one dimension alone. |

Deploy the tracked engine after validation with:

```sh
python3 tests/test_engine.py
python3 scripts/deploy_xplane_plugin.py
```

The engine reports the crew's DF settings back to the console in its position
report, under a `df` key, so the instructor can see what the panel is actually
set to. "Why can't they hear it" is usually answered there.

---

## Part 5 — Sim Innovations (`si_variable_*`) VHF-FM and Audio Panel Contract

The Technisonic TDFM-136B airborne FM transceiver (`instruments/cap-fm-tdfm-136b/`) and Garmin GMA 1347 audio panel (`instruments/mo-audio-panel-gma1347/`) communicate with each other, hardware controls, and the mission net voice agent via Sim Innovations inter-instrument variables (`si_variable_*`). Because X-Plane lacks native datarefs for a third COM radio, these variables form the published contract for the Mission Observer (MO) station.

### TDFM-136B Transceiver State (Published)

| Variable | Type | Default | Producer | Consumers | Description |
|---|---|---|---|---|---|
| `cap_fm_power_on` | BOOL | false | TDFM-136B | GMA 1347, Voice Agent | Radio master power status (toggled by Main encoder press/hold). |
| `cap_fm_frequency_hz` | INT | 0 | TDFM-136B | Voice Agent, Console | Active transmit/receive RF frequency in Hz (Main or Guard depending on MN/GD switch). |
| `cap_fm_channel` | INT | 0 | TDFM-136B | Voice Agent, Console | Active memory/channel index (1–200 for Main memories, 101/102 for GD1/GD2). |
| `cap_fm_channel_name` | STRING | "" | TDFM-136B | Voice Agent, Logger | 8-character channel alphanumeric tag (e.g. `TAC 1`, `AIR 1`). |
| `cap_fm_transmitting` | BOOL | false | TDFM-136B | Voice Agent, GMA 1347 | True when actively transmitting RF. Interlocked by power, COM3 MIC, PTT, and 60s TOT timer. |
| `cap_fm_high_power` | BOOL | false | TDFM-136B | Voice Agent | HI/LO power switch position (true = 10 W, false = 1 W). |
| `cap_fm_talk_around` | BOOL | false | TDFM-136B | Voice Agent | Repeater talk-around mode (L1-*): transmits on receive frequency when true. |
| `cap_fm_ctcss_tone` | FLOAT | 0.0 | TDFM-136B | Voice Agent, Repeater Sim | Continuous Tone-Coded Squelch System (CTCSS) subaudible tone in Hz (e.g. 110.9, 156.7). 0.0 if CSQ. |
| `cap_fm_p25_nac` | INT | 0 | TDFM-136B | Voice Agent, Repeater Sim | APCO Project 25 Network Access Code (NAC) in hex (e.g. 0x293 = 659). 0 if analog. |
| `cap_fm_guard_frequency_hz` | INT | 0 | TDFM-136B | Voice Agent, Console | Dedicated Guard receiver RF frequency in Hz (independent secondary receiver path). |
| `cap_fm_guard_channel` | INT | 0 | TDFM-136B | Voice Agent, Console | Guard receiver memory channel index (101 for GD1, 102 for GD2). |
| `cap_fm_guard_channel_name` | STRING | "" | TDFM-136B | Voice Agent, Logger | 8-character Guard channel alphanumeric tag (e.g. `AIRGUARD`). |
| `cap_fm_guard_ctcss_tone` | FLOAT | 0.0 | TDFM-136B | Voice Agent | Guard receiver CTCSS tone in Hz (0.0 if CSQ). |
| `cap_fm_guard_p25_nac` | INT | 0 | TDFM-136B | Voice Agent | Guard receiver P25 NAC in hex (0 if analog). |
| `cap_fm_main_volume` | FLOAT | 1.0 | TDFM-136B | Audio Mixer | Main receiver volume potentiometer position (0.0–1.0). |
| `cap_fm_guard_volume` | FLOAT | 1.0 | TDFM-136B | Audio Mixer | Guard receiver volume potentiometer position (0.0–1.0). |

### GMA 1347 Audio Panel State (Published)

| Variable | Type | Default | Producer | Consumers | Description |
|---|---|---|---|---|---|
| `cap_ics_isolation` | STRING | "ALL" | GMA 1347 | Intercom Mixer, Radio Service | ICS intercom isolation mode (`"ALL"`, `"PILOT"`, `"COPILOT"`, `"CREW"`). |
| `cap_ics_pilot_isolated` | BOOL | false | GMA 1347 | Radio Service | True when pilot is isolated from copilot/passengers. |
| `cap_ics_copilot_isolated` | BOOL | false | GMA 1347 | Radio Service | True when copilot is isolated from pilot. |
| `cap_ics_crew_isolated` | BOOL | false | GMA 1347 | Radio Service | True when passengers/cabin are isolated. |
| `cap_split_com_active` | BOOL | false | GMA 1347 | Radio Service | True when Split COM is active (pilot COM1, copilot COM2, observer isolated). |
| `cap_recorder_playing` | BOOL | false | GMA 1347 | Headset Audio, UI | True when digital clearance recorder is actively playing back a recorded block. |
| `cap_recorder_block` | INT | 0 | GMA 1347 | UI, Logger | Currently selected clearance recorder playback block index (1–16). |
| `cap_recorder_count` | INT | 0 | GMA 1347 | UI, Logger | Total number of recorded transmission blocks stored in clearance recorder buffer. |
| `cap_recorder_text` | STRING | "" | GMA 1347 | UI, Logger | Alphanumeric metadata / callsign tag of the active clearance recorder block. |

### Mission Net & Audio Control Handshake (Subscribed / Ingested)

| Variable | Type | Default | Producer | Consumers | Description |
|---|---|---|---|---|---|
| `cap_fm_ptt` | BOOL | false | Air Manager Touch/Key, Copilot PTT, Voice Agent | TDFM-136B | Observer Push-To-Talk input. Also synchronised from X-Plane dataref `sim/cockpit2/radios/actuators/audio_panel_copilot_ptt`. |
| `cap_fm_main_rx` | BOOL | false | Voice Agent / Mumble Bridge | TDFM-136B, GMA 1347 | Main receiver carrier/squelch open. Drives upper squelch LED and feeds GMA clearance recorder. |
| `cap_fm_guard_rx` | BOOL | false | Voice Agent / Mumble Bridge | TDFM-136B | Guard receiver carrier/squelch open. Drives lower squelch LED. Gated by radio power. |
| `cap_fm_audio_selected` | BOOL | false | GMA 1347 | TDFM-136B, Headset Audio | COM3 audio monitor enabled. When false, observer headset is muted for FM, but squelch LEDs still illuminate on receive. |
| `cap_fm_mic_selected` | BOOL | false | GMA 1347 | TDFM-136B | COM3 MIC transmitter selected. Interlocks TDFM transmission (PTT will not key unless true). |


