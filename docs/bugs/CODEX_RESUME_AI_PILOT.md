# Codex resume prompt — AI Mission Pilot live Gate A acceptance

Paste this entire prompt into Codex after the simulator host has rebooted.

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
