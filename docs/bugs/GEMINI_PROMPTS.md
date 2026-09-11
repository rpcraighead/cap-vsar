# Gemini work prompts — open tracker items in Gemini's lanes

Generated 2026-09-10 from `docs/bugs/tracker.json`. Companion to
[`CODEX_PROMPTS.md`](CODEX_PROMPTS.md), same shape: each numbered prompt is a
PR-sized unit, ordered so that prompts touching the same file never run in
parallel.

**Status: archived handoff.** The resulting instrument and panel-tooling work
is preserved in commit `e80692d`. Use the current generated bug tracker for
open status; O-7b still requires live reconnect acceptance.

Gemini owns `instruments/**` outright (clusters C12 and C13), including both DF
heads, and the instrument tooling in `scripts/`. Seven items are open. Claude
has just closed cluster C3 in `xplane/PI_capvsar_df.py`; that file and
`tests/test_engine.py` are off limits here, but **read the 2026-09-10 CHANGELOG
entry first** — P-13 recalibrated `cap/df/signal` onto a link budget, and the
faceplates render that value.

## Standing rules — prepend to any prompt in this file

> **2026-09-10 — the simulated aircraft is now `CAP 487`, not `N499CP`.**
> N499CP is a real Cessna 172S and the simulated 182T should never have carried
> it. If any instrument, panel or artwork shows a tail number, it is CAP 487.
>
> This repository is shared by three agents working concurrently (Claude,
> Codex, Gemini) with no branch isolation. Before you start, read the head of
> `CHANGELOG.md` to see what has landed since this prompt was written, and
> verify every claim in the prompt against the current tree rather than
> assuming it still holds — if the code no longer matches the description, say
> so and stop rather than fixing something else.
>
> Stay inside the files the prompt names. Do not touch `xplane/`,
> `services/`, `tests/test_engine.py` or `tests/test_console.py` — those are
> other agents' lanes and they have uncommitted work in them.
>
> When you are done:
> 1. Run the relevant suites and paste the real output:
>    `python3 tests/test_faceplate.py`, `python3 tests/test_panel.py`,
>    `python3 tests/test_lcd_text.py`, `PYTHONPATH=. python3 tests/test_tdfm.py`,
>    `PYTHONPATH=. python3 tests/test_am.py`, and `python3 scripts/luacheck.py`
>    for any Lua you changed.
> 2. Set each item you actually fixed to `"status": "fixed"` in
>    `docs/bugs/tracker.json`, then regenerate the board with
>    `python3 scripts/render_bug_tracker.py`. Re-read the JSON immediately
>    before editing it — another agent may have changed statuses meanwhile.
> 3. Add a dated entry at the TOP of `CHANGELOG.md` saying what changed, what
>    you verified, and anything you found but did not fix.
>
> The Lua harness from I-9a exists (`tests/am.py`, `tests/test_am.py`), so
> behaviour in `logic.lua` can be tested offline. Prefer adding a test there
> over asserting a fix works from reading the code.
>
> If a fix turns out to be wrong or bigger than described, report that instead
> of forcing it through. New problems you find go in the changelog entry as
> findings, and into `docs/bugs/tracker.json` as new items — do not silently
> expand scope.

---

## Prompt 1 — I-4, I-5: two faceplate state bugs that lie to the student

`instruments/becker-sar-df-517/logic.lua`,
`instruments/rhotheta-rt-600/logic.lua`

Both small, both P2, both in the category that matters most here: the
instrument displays something that did not happen.

**I-4 (Becker, `logic.lua` around 374-404)** — the stored-message page builds
every field with the idiom `msg and msg.field or s.cs_field`. Verified in the
tree: `local has_pos = msg and msg.has_pos or s.cs_has_pos`. When a STORED
frame carries no position, `msg.has_pos` is false and the expression falls
through to the **live** frame's position, so the student reads a stored beacon
as carrying a position it never had. Note the bug is a class, not a line: the
same idiom is used for `sync`, `protocol`, `hex15` and `country` on the
surrounding lines and is wrong for any of them whose stored value is false,
nil, 0 or an empty string. Replace the idiom with an explicit if/else on
whether a stored message is being shown at all, once, for the whole page.
*Verify: store a positionless frame; page 4 shows no position. Add an
`tests/test_am.py` case.*

**I-5 (RT-600, `logic.lua` around 386 and 475-485)** — the release handler
starts `if not st.power or st.booting then return end`, so releasing a key
while the unit is off leaves `st.press_at[ctrl_key]` armed; `power_off()` stops
`boot_timer` and `dim_timer` but nothing stops the press timers. Hold F1, power
off, release: `f1_long` fires `clear_average()` on a dead set, and the
averaging store is thrown away behind the crew's back. Stop the press timers in
`power_off()` **and** on the early-return path — both, not either.
*Verify: hold F1, power off, release, power on: the averaging store is intact.*

---

## Prompt 2 — I-6: the instruments ignore the electrical bus

`instruments/becker-sar-df-517/logic.lua`,
`instruments/rhotheta-rt-600/logic.lua`,
`instruments/cap-fm-tdfm-136b/logic.lua`,
`instruments/mo-audio-panel-gma1347/logic.lua`

All four instruments light up on a cold, dark aircraft. Only the GMA subscribes
to `sim/cockpit2/switches/avionics_power_on` (at `logic.lua:486` — the tracker
says 389, which is stale), and even it ignores bus voltage. Grep confirms no
other instrument references `avionics_power_on` or `bus_volts` at all.

For a trainer whose value is procedural traps, "you never turned the avionics
master on" is the most basic one there is, and right now the panel rewards the
omission by working perfectly. Gate all four on the avionics bus and on bus
voltage, with behaviour that matches the real sets: a DF head does not snap
dark at 11 V, it browns out and reboots. Respect each instrument's existing
boot sequence rather than bypassing it — the RT-600 has a real boot animation
and it should run on bus-up, not be skipped.
*Verify: cold aircraft, nothing lit; avionics master on, all four boot; drop
the bus below the threshold and they behave like the hardware does. Add
harness cases for the cold-start path.*

---

## Prompt 3 — O-7b: the G1000 MFD freezes and never recovers

New wrapper instrument under `instruments/`; `~/Air Manager/log.txt` for
evidence

This is the only P1 left in your lanes, and it is wave 2 — every MO station
hits it. `SimVideoStreamClient` drops its connection every few minutes; Air
Manager's **stock** G1000 instrument calls `video_stream_add()` once at load
and never again, so after the first reconnect the MFD tile sits frozen on its
last frame for the rest of the session. An observer navigating from a frozen
moving map is worse than one with no map, because nothing says it is stale.

The stock instrument is not ours to edit and is not in this repo, so the fix is
a wrapper instrument or a watchdog that re-calls `video_stream_add()` when
frames stop arriving. `docs/AM4_COMPAT.md:46` notes `video_stream_add` arrived
in AM V4.2 — and says "we do not need it", which this item makes untrue, so
correct that line while you are there. Decide and state whether the watchdog
keys off frame arrival, off a connection callback, or both, and make the
recovery visible: a stale tile should say it is stale rather than silently
showing an old frame.
*Verify: a one-hour session with no frozen MFD, and `log.txt` showing at least
one reconnect with video recovered afterwards. This one cannot be verified from
the repo — if you cannot run a station, say exactly what you did verify and
leave the item open.*

---

## Prompt 4 — I-7: the shared libraries are copy-pasted

`instruments/*/lib/*.lua`, `instruments/*/resources/*.wav`,
new `instruments/_shared/`, `scripts/deploy_df_instruments.py`,
`tests/test_faceplate.py:126-129`

Confirmed by checksum in the current tree:

- `lcd.lua` is byte-identical across **three** instruments (Becker, RT-600,
  TDFM).
- `cap_df.lua`, `cap_df_audio.lua` and `dcu.lua` are byte-identical across the
  two DF heads.
- **Four** WAVs — `elt_analog_clean`, `elt_analog_df`, `elt_noise`,
  `elt_406_burst` — are byte-identical across the two heads. (The tracker says
  three; it is four.)

`tests/test_faceplate.py` asserts the DF pair matches, but only the pair — the
TDFM's copy of `lcd.lua` is checked by nothing and can drift silently, which is
the failure mode this item exists to prevent. Move the shared files to
`instruments/_shared/`, have the deploy scripts copy them in, and replace the
pairwise test with one that asserts every installed copy matches the shared
source. Air Manager needs each instrument directory to be self-contained, so
the copy has to happen at deploy time, not by symlink.
*Verify: edit a file in `_shared/`, deploy, and all instruments that use it
change; hand-edit one installed copy and the test fails.*

---

## Prompt 5 — I-9c: the deploy script covers half the instruments

`scripts/deploy_df_instruments.py:14-17,47`, `instruments/*/info.xml`,
`website/` (the page making the claim)

Verified: `INSTRUMENTS` lists exactly two UUIDs — `becker-sar-df-517` and
`rhotheta-rt-600`. The TDFM and the GMA audio panel have no deploy script at
all, while `website/deployment.html:263` says that command deploys "the custom
Becker SAR-DF 517, RHOTHETA RT-600, Technisonic TDFM-136B, and Garmin GMA 1347
instruments" — two of which it has never touched. Stale files in a target
directory are collected but never pruned. And all four `info.xml` manifests
claim FSX / P3D / FS2020 support when every one of them is X-Plane only.

Deploy all four, prune stale targets, correct the manifests, and fix the
website claim rather than leaving the docs to be caught by D-2. Do this after
prompt 4 — `_shared/` changes what "deploy an instrument" copies.
*Verify: one command deploys four instruments to a clean Air Manager and a
second run is a no-op.*

---

## Prompt 6 — I-8: the panel registrar writes Air Manager's database blind

`scripts/register_mo_panel.py:25,50,97-100,107-168,171-172,182`,
`instruments/*/info.xml`,
`panels/cap-c182t-mo-station/generate_assets.py` (the tracker calls this
`scripts/generate_assets.py`; there is no such file — this is the real path)

Depends on O-2 (station config), which is **done** — `capvsar_station.ini` and
`scripts/build_station_kit.py` exist, so parameterising the paths here now has
somewhere to read from.

The registrar hardcodes 26 panel columns and their magic values, syncs
`sqlite_sequence` for two of four tables, `pkill`s Air Manager with no
confirmation, relaunches it from a literal `/home/ron` path, and never updates
an existing layout — so a position edit silently never propagates and the
operator assumes the edit did not take. Panel geometry is triplicated across
`info.xml`, this script and `panels/cap-c182t-mo-station/generate_assets.py` with no
cross-check between them. And `Streaming=true` is only ever set through the SQLite path, so the
`--zip` route ships a panel with a dead MFD — which is the route another
station actually uses.

Confirm before killing anything; parameterise the DB and install paths off the
station config; update existing layouts instead of only inserting; make one
place the source of panel geometry; and put `Streaming` in `info.xml` so the
zip route carries it.
*Verify: the zip route produces a working MFD on a second machine — a real
second machine, not the one that built the zip.*

---

## Ordering

1 → 2 → 3 are the behaviour fixes and are independent of each other (1 and 2
both touch the two DF `logic.lua` files, so run them in sequence, not
together). 4 → 5 → 6 are tooling and must run in that order: `_shared/`
changes what deploy copies, and deploy coverage changes what the registrar
installs.
