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
| `cap/df/distance_nm` | FLOAT | NM | Slant range. Instructor-facing; the 517 shows it on page 3. |
| `cap/df/in_cone` | INT | bool | Inside the cone of confusion — bearing deliberately invalid |
| `cap/df/blocked` | INT | bool | Terrain masking the signal |
| `cap/df/airframe_shadowed` | INT | bool | At least 1 dB of installation-specific wing/fuselage attenuation is active. Separate from terrain masking. |
| `cap/df/airframe_attenuation_db` | FLOAT | dB | Current directional loss from the selected antenna profile. Instructor/debug truth. |
| `cap/df/rx_open` | INT | bool | A transmission is receivable at this instant. Unlike `valid`, this is never held. Audio should follow this value. |
| `cap/df/band` | FLOAT | MHz | What the head is **actually listening to**, which in scan mode is not what the crew tuned |
| `cap/df/spread` | FLOAT | deg | Scatter of the un-averaged bearings. How the operator judges whether to trust the needle. |
| `cap/df/error_code` | INT | — | **−1 = no error**; 0–12 are Becker E0–E12. Set from the console's `effects.error_code`. |

### COSPAS/SARSAT decode

| Dataref | Type | Notes |
|---|---|---|
| `cap/df/cs_sync` | INT | 0 none, 1 SYNC OK, 2 SELFTEST |
| `cap/df/cs_protocol` | INT | 1 USER, 2 STANDARD, 3 NATIONAL; +4 for the TEST variant |
| `cap/df/cs_hex15` | BYTE[15] | 15-hex beacon ident, one ASCII character per byte |
| `cap/df/cs_country` | INT | Numeric country code |
| `cap/df/cs_has_position` | INT | 1 when the message carries a position |
| `cap/df/cs_lat` / `cs_lon` | FLOAT | Degrees, valid only when the above is 1 |
| `cap/df/cs_msg_age_sec` | FLOAT | Seconds since the last valid decode |

### Scenario

Writable for offline testing without the console:

| Dataref | Type |
|---|---|
| `cap/scenario/active` | INT (read-only) |
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
- **Squelch.** A percentage maps onto a threshold on the 0..1 signal, from the
  noise floor at 0 % (and Auto) to just above saturation at 100 %. Wound fully
  up the set really is deaf. The RT-600's scale stops at 60 %, so its squelch
  cannot be wound as tight as the 517's — that difference is real and preserved.
- **Wing blanking / airframe shadowing.** When `effects.airframe_shadowing` is
  enabled, the engine reads X-Plane roll (`phi`) and pitch (`theta`), transforms
  the aircraft-to-beacon ray into body coordinates, and tests its intersection
  with a softened wing/fuselage silhouette. A belly profile nulls when the
  lowered wing is toward the beacon; a top profile reverses that relationship.
  Directional and terrain losses are applied to unsaturated field strength, so
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
| `effects.beacon_has_gps` | Whether a synthesised decode carries a position. A plain 406 ELT without GPS is both the commoner case and the more interesting search. |
| `effects.error_code` | Injects a Becker E0–E12 fault. |
| `effects.mounting`, `effects.antenna_offset_deg` | The installation truth the crew's settings have to match. |
| `effects.airframe_shadowing` | Enables attitude-dependent wing/fuselage attenuation. Defaults off for existing scenarios. |
| `effects.df_antenna_profile` | `c182_belly` or `c182_top`; defaults to the belly profile. This is physical installation truth, independent of the crew's TOP/BOTTOM control. |
| `effects.wing_null_max_loss_db` | Optional peak loss override; nominal profile value is 24 dB. Geometry can also be overridden with the `wing_null_*_ft` fields implemented in the plugin. |

Deploy the tracked engine after validation with:

```sh
python3 tests/test_engine.py
python3 scripts/deploy_xplane_plugin.py
```

The engine reports the crew's DF settings back to the console in its position
report, under a `df` key, so the instructor can see what the panel is actually
set to. "Why can't they hear it" is usually answered there.
