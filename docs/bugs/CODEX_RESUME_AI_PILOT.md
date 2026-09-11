# Codex resume prompt — AI Mission Pilot live Gate A acceptance

Paste this entire prompt into Codex after the simulator host has rebooted.

---

## 2026-09-11 live-session update — read before the original handoff

The reboot and most live checks below have now been completed. Read the latest
CHANGELOG entries and AI-2 through AI-6 before repeating anything. NVIDIA versions
match 595.91.07. AI-3 fixed RREF comma-header reception. AI-5 now uses G1000 FLC
at a 110-KIAS exercise target, with pilot-managed power; altitude capture was
measured in 50.555 seconds and visually confirmed. AI-6 uses explicit pause_on:
shutdown pause and telemetry-loss fault pause were both verified live. Heading
capture, pilot takeover and old-lease refusal also passed.

Latest loss test: five-second relay drop, stale-data fault and revocation after
1.900 seconds, pause=1, fresh telemetry restored, old lease refused. The controller
and relay are stopped; relay subscriptions were cancelled. Simulator last observed
paused with preexisting AP modes still engaged (fault behavior preserves AP).
Manual recovery has since been verified: user reported stable and four seconds
of read-only telemetry confirmed pause=0, 4199.636 ft, 122.422 KIAS and near-zero
vertical speed. Controller and relay remain stopped. Latest fault-pause visual
confirmation was requested; direct pause=1 was observed during the fault.

AI-4 update: the builder and installed package have now been repaired. Tailnum
is CAP 487, trailing indices use IDX, and texture is 256x128; full installed
static checks passed. Backups are recorded in CHANGELOG.md. AI-2 and AI-4 remain
open pending fresh X-Plane load/log and visual prop-lever/cockpit verification. Do not edit other agents' aircraft lanes
or reinstall/reload silently. The original pre-reboot diagnosis below is history,
not current driver state. Raw observations are in docs/bugs/AI_2_*_2026-09-11.jsonl;
the LOSS_INVALID file is explicitly an invalidated trial, not a controller failure.

---

Continue the CAP V-SAR AI Mission Pilot work from the 2026-09-11 handoff. The
user authorizes the supervised live X-Plane Gate A acceptance described below.
Do not attempt takeoff, landing, autonomous flight, or any ground operation.

This is a shared dirty workspace. First read the head of `CHANGELOG.md`, then
read tracker items AI-1 and AI-2 in `docs/bugs/tracker.json` and the current
`services/ai_pilot/README.md`. Preserve concurrent work. Do not touch
`xplane/`, `instruments/`, `tests/test_engine.py`, `tests/test_faceplate.py`,
or `tests/test_panel.py`.

AI-1 is fixed: the legacy chat, web, Hermes-tool, and scripted-live entrypoints
are observation-only or retired. Live aircraft control must go only through
`services.ai_pilot.maneuver_server` and its serialized maneuver gate. AI-2 is
open because live CAP 487 acceptance was blocked before reboot.

The pre-reboot diagnosis was exact: NVIDIA userspace and the installed module
were 595.91.07, while the loaded kernel module was 595.84. X-Plane also
inherited Snap variables from VS Code. `scripts/launch_xplane12.sh` now strips
that environment and refuses mismatched driver versions.

Proceed autonomously:

1. Run `scripts/launch_xplane12.sh --check` and `nvidia-smi`. Confirm the loaded
   and installed NVIDIA versions agree. If they still differ, report the exact
   versions and stop the live test without sending simulator controls.
2. Check whether X-Plane is already running. If it is not, launch it with
   `scripts/launch_xplane12.sh`. The user has authorized this GUI launch for
   this acceptance run.
3. Confirm CAP 487 is loaded. Have the user position it manually in stable
   airborne flight inside the configured gate: 3000–6000 ft indicated,
   at least 1000 ft AGL, 90–140 KIAS, and no more than 35 degrees bank. Do not
   spawn, reset, or reposition the aircraft from code.
4. Ensure no legacy AI pilot or duplicate maneuver-server process is writing
   controls. Start exactly one live controller with:

   `PYTHONPATH=. /tmp/capvsar-planner-venv/bin/python -m services.ai_pilot.maneuver_server --live --min-altitude 3000 --max-altitude 6000`

5. Before acquiring control, query `/api/status` and prove all required RREF
   telemetry is finite and fresh. The backend now renews missing/stale RREF
   subscriptions once per second, so starting the server before X-Plane must
   recover without duplicate callbacks.
6. Run representative supervised maneuvers through the HTTP contract, using a
   fresh lease and strictly increasing sequence numbers:
   - acquire control;
   - select a modest heading change, then verify measured capture and the
     G1000/GFC 700 indications;
   - select a modest altitude change within the block, then verify measured
     capture and cockpit indications;
   - confirm an out-of-envelope or invalid command is refused without a control
     write;
   - invoke pilot takeover and prove the old lease cannot re-engage control;
   - verify pause/disconnect behavior deliberately and recover the simulator
     manually afterward.
7. Record commanded values, observed capture tolerances/times, controller event
   states, cockpit annunciations, and any divergence. Do not mark AI-2 fixed if
   a required observation cannot be made or if behavior is only inferred from a
   UDP write.
8. Stop the maneuver server cleanly. Run:

   `PYTHONPATH=. /tmp/capvsar-planner-venv/bin/pytest services/ai_pilot/tests -q`

   `PYTHONPATH=. /tmp/capvsar-planner-venv/bin/pytest tests/test_console.py tests/test_radio.py -q`

9. If every AI-2 verification passes, re-read `docs/bugs/tracker.json`
   immediately before setting AI-2 to `fixed`, regenerate the board with
   `python3 scripts/render_bug_tracker.py`, and add a dated entry at the top of
   `CHANGELOG.md` with the real live measurements and exact test output. If a
   live behavior fails, leave AI-2 open and record the finding without silently
   expanding scope.

Keep the user informed during the live run. Never claim the aircraft achieved
a maneuver until fresh simulator observations and the cockpit state demonstrate
it.

---
